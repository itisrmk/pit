"""Tests for bisect commands and core logic."""

import json
import os
import pytest
from typer.testing import CliRunner

from pit.cli.main import app
from pit.core.bisect import BisectManager, BisectSession, BisectState, BisectResult
from pit.db.database import get_session
from pit.db.repository import PromptRepository, VersionRepository


runner = CliRunner()


class TestBisectCore:
    """Test core bisect logic."""

    def test_start_bisect_session(self, initialized_project):
        """Test starting a bisect session."""
        project_root = initialized_project
        manager = BisectManager(project_root)

        with get_session(project_root) as db_session:
            # Create a prompt
            prompt_repo = PromptRepository(db_session)
            prompt = prompt_repo.create(name="test-prompt", description="Test")

            # Start bisect
            session = manager.start(db_session, "test-prompt", "failing input here")

            assert session.state == BisectState.RUNNING
            assert session.prompt_name == "test-prompt"
            assert session.failing_input == "failing input here"
            assert session.prompt_id == prompt.id

    def test_start_duplicate_session_fails(self, initialized_project):
        """Test can't start bisect if one already running."""
        project_root = initialized_project
        manager = BisectManager(project_root)

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            prompt_repo.create(name="test-prompt", description="Test")

            manager.start(db_session, "test-prompt", "input")

            with pytest.raises(ValueError, match="already running"):
                manager.start(db_session, "test-prompt", "input2")

    def test_mark_good_version(self, initialized_project):
        """Test marking a version as good."""
        project_root = initialized_project
        manager = BisectManager(project_root)

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            version_repo = VersionRepository(db_session)

            prompt = prompt_repo.create(name="test-prompt")
            version_repo.create(prompt_id=prompt.id, content="v1", message="First")
            version_repo.create(prompt_id=prompt.id, content="v2", message="Second")
            version_repo.create(prompt_id=prompt.id, content="v3", message="Third")

            manager.start(db_session, "test-prompt", "input")
            session = manager.mark_version(db_session, BisectResult.GOOD, 1)

            assert session.good_version == 1
            assert session.tested_versions[1] == "good"

    def test_mark_bad_version(self, initialized_project):
        """Test marking a version as bad."""
        project_root = initialized_project
        manager = BisectManager(project_root)

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            version_repo = VersionRepository(db_session)

            prompt = prompt_repo.create(name="test-prompt")
            version_repo.create(prompt_id=prompt.id, content="v1", message="V1")
            version_repo.create(prompt_id=prompt.id, content="v2", message="V2")
            version_repo.create(prompt_id=prompt.id, content="v3", message="V3")

            manager.start(db_session, "test-prompt", "input")
            session = manager.mark_version(db_session, BisectResult.BAD, 3)

            assert session.bad_version == 3
            assert session.tested_versions[3] == "bad"

    def test_bisect_completes_when_adjacent(self, initialized_project):
        """Test bisect completes when good and bad are adjacent."""
        project_root = initialized_project
        manager = BisectManager(project_root)

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            version_repo = VersionRepository(db_session)

            prompt = prompt_repo.create(name="test-prompt")
            for i in range(1, 6):
                version_repo.create(prompt_id=prompt.id, content=f"v{i}", message=f"V{i}")

            manager.start(db_session, "test-prompt", "input")
            manager.mark_version(db_session, BisectResult.GOOD, 1)
            session = manager.mark_version(db_session, BisectResult.BAD, 2)

            assert session.state == BisectState.COMPLETED
            assert session.first_bad_version == 2

    def test_binary_search_picks_middle(self, initialized_project):
        """Test binary search picks middle version."""
        project_root = initialized_project
        manager = BisectManager(project_root)

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            version_repo = VersionRepository(db_session)

            prompt = prompt_repo.create(name="test-prompt")
            for i in range(1, 11):  # 10 versions
                version_repo.create(prompt_id=prompt.id, content=f"v{i}", message=f"V{i}")

            manager.start(db_session, "test-prompt", "input")
            manager.mark_version(db_session, BisectResult.GOOD, 1)
            session = manager.mark_version(db_session, BisectResult.BAD, 10)

            # Should pick middle (version 5 or 6)
            assert session.current_version in [5, 6]

    def test_reset_clears_session(self, initialized_project):
        """Test reset clears the session."""
        project_root = initialized_project
        manager = BisectManager(project_root)

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            prompt_repo.create(name="test-prompt")

            manager.start(db_session, "test-prompt", "input")
            assert manager.get_session() is not None

            manager.reset()
            assert manager.get_session() is None


class TestBisectCLI:
    """Test bisect CLI commands."""

    def test_bisect_start(self, initialized_project, monkeypatch):
        """Test bisect start command."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        # Create a prompt first
        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            prompt_repo.create(name="my-prompt", description="Test")

        result = runner.invoke(
            app,
            ["bisect", "start", "--prompt", "my-prompt", "--failing-input", "test input"]
        )

        assert result.exit_code == 0
        assert "Started bisect session" in result.output
        assert "my-prompt" in result.output

    def test_bisect_start_no_prompt_fails(self, initialized_project, monkeypatch):
        """Test bisect start requires prompt."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        result = runner.invoke(
            app,
            ["bisect", "start", "--failing-input", "test"]
        )

        assert result.exit_code == 1

    def test_bisect_good_requires_session(self, initialized_project, monkeypatch):
        """Test bisect good requires active session."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        result = runner.invoke(
            app,
            ["bisect", "good", "v1"]
        )

        assert result.exit_code == 1
        assert "No active bisect session" in result.output

    def test_bisect_log_no_session(self, initialized_project, monkeypatch):
        """Test bisect log with no session."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        result = runner.invoke(
            app,
            ["bisect", "log"]
        )

        assert result.exit_code == 0
        assert "No active bisect session" in result.output

    def test_bisect_reset(self, initialized_project, monkeypatch):
        """Test bisect reset command."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            prompt_repo.create(name="my-prompt")

        # Start a session
        runner.invoke(
            app,
            ["bisect", "start", "--prompt", "my-prompt", "--failing-input", "test"]
        )

        # Reset it
        result = runner.invoke(
            app,
            ["bisect", "reset", "--force"]
        )

        assert result.exit_code == 0
        assert "cleared" in result.output

    def test_bisect_full_workflow(self, initialized_project, monkeypatch):
        """Test complete bisect workflow."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            version_repo = VersionRepository(db_session)

            prompt = prompt_repo.create(name="workflow-test")
            for i in range(1, 5):
                version_repo.create(prompt_id=prompt.id, content=f"v{i}", message=f"V{i}")

        # Start
        result = runner.invoke(
            app,
            ["bisect", "start", "--prompt", "workflow-test", "--failing-input", "broken input"]
        )
        assert result.exit_code == 0

        # Mark v1 good
        result = runner.invoke(
            app,
            ["bisect", "good", "v1"]
        )
        assert result.exit_code == 0
        assert "good" in result.output

        # Mark v4 bad
        result = runner.invoke(
            app,
            ["bisect", "bad", "v4"]
        )
        assert result.exit_code == 0
        assert "bad" in result.output

        # Check log shows progress
        result = runner.invoke(
            app,
            ["bisect", "log"]
        )
        assert result.exit_code == 0
        assert "workflow-test" in result.output


class TestBisectSession:
    """Test BisectSession data class."""

    def test_session_to_dict(self):
        """Test session serialization."""
        session = BisectSession(
            state=BisectState.RUNNING,
            prompt_name="test",
            prompt_id="abc123",
            failing_input="input",
            good_version=1,
            bad_version=10,
        )

        data = session.to_dict()
        assert data["state"] == "running"
        assert data["prompt_name"] == "test"
        assert data["good_version"] == 1

    def test_session_from_dict(self):
        """Test session deserialization."""
        data = {
            "state": "completed",
            "prompt_name": "test",
            "prompt_id": "abc123",
            "failing_input": "input",
            "good_version": 1,
            "bad_version": 2,
            "tested_versions": {"1": "good", "2": "bad"},
            "started_at": "2024-01-01T00:00:00",
            "current_version": None,
        }

        session = BisectSession.from_dict(data)
        assert session.state == BisectState.COMPLETED
        assert session.prompt_name == "test"
        assert session.tested_versions["1"] == "good"
