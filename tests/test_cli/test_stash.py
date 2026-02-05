"""Tests for stash commands and core logic."""

import pytest
from typer.testing import CliRunner
from pathlib import Path

from pit.cli.main import app
from pit.core.stash import StashManager, StashEntry
from pit.db.database import get_session
from pit.db.repository import PromptRepository, VersionRepository


runner = CliRunner()


class TestStashCore:
    """Test core stash logic."""

    def test_save_stash(self, initialized_project):
        """Test saving a stash."""
        project_root = initialized_project
        manager = StashManager(project_root)

        entry = manager.save_stash(
            prompt_name="test-prompt",
            prompt_id="abc123",
            content="Test content",
            message="WIP: improving tone",
        )

        assert entry.index == 0
        assert entry.prompt_name == "test-prompt"
        assert entry.message == "WIP: improving tone"
        assert entry.content == "Test content"

    def test_save_multiple_stashes(self, initialized_project):
        """Test saving multiple stashes."""
        project_root = initialized_project
        manager = StashManager(project_root)

        entry1 = manager.save_stash("prompt1", "id1", "content1", "first")
        entry2 = manager.save_stash("prompt2", "id2", "content2", "second")

        assert entry1.index == 0
        assert entry2.index == 1

        entries = manager.list_stashes()
        assert len(entries) == 2

    def test_pop_stash(self, initialized_project):
        """Test popping a stash."""
        project_root = initialized_project
        manager = StashManager(project_root)

        manager.save_stash("prompt", "id", "content1", "first")
        manager.save_stash("prompt", "id", "content2", "second")

        popped = manager.pop_stash(0)
        assert popped is not None
        assert popped.message == "first"

        # Remaining stashes renumbered
        entries = manager.list_stashes()
        assert len(entries) == 1
        assert entries[0].index == 0
        assert entries[0].message == "second"

    def test_apply_stash_without_removing(self, initialized_project):
        """Test applying stash without removing."""
        project_root = initialized_project
        manager = StashManager(project_root)

        manager.save_stash("prompt", "id", "content", "test")

        applied = manager.apply_stash(0)
        assert applied is not None
        assert applied.message == "test"

        # Still in stash
        entries = manager.list_stashes()
        assert len(entries) == 1

    def test_drop_stash(self, initialized_project):
        """Test dropping a stash."""
        project_root = initialized_project
        manager = StashManager(project_root)

        manager.save_stash("prompt", "id", "content", "to drop")
        assert manager.get_stash_count() == 1

        assert manager.drop_stash(0) is True
        assert manager.get_stash_count() == 0

    def test_clear_all_stashes(self, initialized_project):
        """Test clearing all stashes."""
        project_root = initialized_project
        manager = StashManager(project_root)

        for i in range(3):
            manager.save_stash("prompt", "id", f"content{i}", f"stash{i}")

        assert manager.get_stash_count() == 3

        cleared = manager.clear_all()
        assert cleared == 3
        assert manager.get_stash_count() == 0

    def test_stash_with_test_input(self, initialized_project):
        """Test saving stash with test input."""
        project_root = initialized_project
        manager = StashManager(project_root)

        entry = manager.save_stash(
            prompt_name="prompt",
            prompt_id="id",
            content="content",
            message="with test",
            test_input="test input here",
        )

        assert entry.test_input == "test input here"

        retrieved = manager.apply_stash(0)
        assert retrieved.test_input == "test input here"


class TestStashCLI:
    """Test stash CLI commands."""

    def test_stash_save(self, initialized_project, monkeypatch):
        """Test stash save command."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        # Create a prompt with a version
        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            prompt = prompt_repo.create(name="my-prompt")
            version_repo = VersionRepository(db_session)
            version_repo.create(prompt_id=prompt.id, content="v1 content", message="V1")

        result = runner.invoke(
            app,
            ["stash", "save", "--prompt", "my-prompt", "WIP changes"]
        )

        assert result.exit_code == 0
        assert "Stashed changes" in result.output
        assert "WIP changes" in result.output

    def test_stash_list_empty(self, initialized_project, monkeypatch):
        """Test stash list with no stashes."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        result = runner.invoke(app, ["stash", "list"])
        assert result.exit_code == 0
        assert "No stashes" in result.output

    def test_stash_list_with_entries(self, initialized_project, monkeypatch):
        """Test stash list shows entries."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        # Create prompt and stashes
        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            prompt = prompt_repo.create(name="prompt1")
            version_repo = VersionRepository(db_session)
            version_repo.create(prompt_id=prompt.id, content="v1", message="V1")

        runner.invoke(app, ["stash", "save", "--prompt", "prompt1", "first stash"])
        runner.invoke(app, ["stash", "save", "--prompt", "prompt1", "second stash"])

        result = runner.invoke(app, ["stash", "list"])
        assert result.exit_code == 0
        assert "first stash" in result.output
        assert "second stash" in result.output
        assert "2 stash(es)" in result.output

    def test_stash_show(self, initialized_project, monkeypatch):
        """Test stash show command."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            prompt = prompt_repo.create(name="prompt1")
            version_repo = VersionRepository(db_session)
            version_repo.create(prompt_id=prompt.id, content="test content here", message="V1")

        runner.invoke(app, ["stash", "save", "--prompt", "prompt1", "my stash"])

        result = runner.invoke(app, ["stash", "show", "0"])
        assert result.exit_code == 0
        assert "my stash" in result.output
        assert "prompt1" in result.output

    def test_stash_drop(self, initialized_project, monkeypatch):
        """Test stash drop command."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            prompt = prompt_repo.create(name="prompt1")
            version_repo = VersionRepository(db_session)
            version_repo.create(prompt_id=prompt.id, content="v1", message="V1")

        runner.invoke(app, ["stash", "save", "--prompt", "prompt1", "to drop"])

        result = runner.invoke(app, ["stash", "drop", "0", "--force"])
        assert result.exit_code == 0
        assert "Dropped stash@{0}" in result.output

    def test_stash_clear(self, initialized_project, monkeypatch):
        """Test stash clear command."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            prompt = prompt_repo.create(name="prompt1")
            version_repo = VersionRepository(db_session)
            version_repo.create(prompt_id=prompt.id, content="v1", message="V1")

        runner.invoke(app, ["stash", "save", "--prompt", "prompt1", "stash1"])
        runner.invoke(app, ["stash", "save", "--prompt", "prompt1", "stash2"])

        result = runner.invoke(app, ["stash", "clear", "--force"])
        assert result.exit_code == 0
        assert "Cleared 2 stash(es)" in result.output


class TestStashData:
    """Test StashEntry dataclass."""

    def test_stash_to_dict(self):
        """Test stash serialization."""
        entry = StashEntry(
            index=0,
            prompt_name="test",
            prompt_id="abc123",
            content="content",
            message="test stash",
            test_input="input",
        )

        data = entry.to_dict()
        assert data["index"] == 0
        assert data["prompt_name"] == "test"
        assert data["test_input"] == "input"

    def test_stash_from_dict(self):
        """Test stash deserialization."""
        data = {
            "index": 1,
            "prompt_name": "test",
            "prompt_id": "abc123",
            "content": "content",
            "message": "test stash",
            "test_input": None,
            "created_at": "2024-01-01T00:00:00",
            "author": None,
        }

        entry = StashEntry.from_dict(data)
        assert entry.index == 1
        assert entry.prompt_name == "test"
        assert entry.created_at == "2024-01-01T00:00:00"

    def test_content_hash(self):
        """Test content hash generation."""
        entry = StashEntry(
            index=0,
            prompt_name="test",
            prompt_id="id",
            content="test content",
            message="msg",
        )

        hash1 = entry.content_hash
        assert len(hash1) == 8

        # Same content = same hash
        entry2 = StashEntry(
            index=1,
            prompt_name="test2",
            prompt_id="id2",
            content="test content",
            message="msg2",
        )
        assert entry2.content_hash == hash1
