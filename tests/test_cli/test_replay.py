"""Tests for replay commands and core logic."""

import json
import pytest
from typer.testing import CliRunner
from pathlib import Path

from pit.cli.main import app
from pit.core.replay import (
    ReplayEngine, ReplayCache, ReplayResult
)
from pit.db.database import get_session
from pit.db.repository import PromptRepository, VersionRepository


runner = CliRunner()


class TestReplayCache:
    """Test replay cache functionality."""

    def test_cache_get_miss(self, initialized_project):
        """Test cache miss."""
        project_root = initialized_project
        cache = ReplayCache(project_root)

        result = cache.get("prompt1", 1, "test input")
        assert result is None

    def test_cache_set_and_get(self, initialized_project):
        """Test cache set and get."""
        project_root = initialized_project
        cache = ReplayCache(project_root)

        result = ReplayResult(
            version_number=1,
            input_text="test input",
            output="test output",
            latency_ms=100.0,
            token_usage=50,
            error=None,
            cached=False,
        )

        cache.set("prompt1", 1, result)

        cached = cache.get("prompt1", 1, "test input")
        assert cached is not None
        assert cached.output == "test output"
        assert cached.cached is True

    def test_cache_clear(self, initialized_project):
        """Test cache clear."""
        project_root = initialized_project
        cache = ReplayCache(project_root)

        # Add some cache entries
        result = ReplayResult(1, "input", "output", None, None, None, False)
        cache.set("prompt1", 1, result)
        cache.set("prompt1", 2, result)

        count = cache.clear()
        assert count == 2

        # Verify cleared
        assert cache.get("prompt1", 1, "input") is None


class TestReplayEngine:
    """Test replay engine functionality."""

    def test_replay_version_not_found(self, initialized_project):
        """Test replay with missing version."""
        project_root = initialized_project
        engine = ReplayEngine(project_root)

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            prompt_repo.create(name="test-prompt")

        results = engine.replay("test-prompt", [1], "input")

        assert len(results) == 1
        assert results[0].error is not None
        assert "not found" in results[0].error

    def test_replay_prompt_not_found(self, initialized_project):
        """Test replay with missing prompt."""
        project_root = initialized_project
        engine = ReplayEngine(project_root)

        with pytest.raises(ValueError, match="not found"):
            engine.replay("nonexistent", [1], "input")

    def test_replay_uses_cache(self, initialized_project):
        """Test that replay uses cache."""
        project_root = initialized_project
        engine = ReplayEngine(project_root)

        # Pre-populate cache
        result = ReplayResult(
            version_number=1,
            input_text="test",
            output="cached output",
            latency_ms=50.0,
            token_usage=10,
            error=None,
            cached=True,
        )
        engine.cache.set("test-prompt", 1, result)

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            version_repo = VersionRepository(db_session)

            prompt = prompt_repo.create(name="test-prompt")
            version_repo.create(prompt_id=prompt.id, content="v1", message="V1")

        results = engine.replay("test-prompt", [1], "test", use_cache=True)

        assert len(results) == 1
        assert results[0].cached is True
        assert results[0].output == "cached output"

    def test_compare(self, initialized_project):
        """Test compare functionality."""
        project_root = initialized_project
        engine = ReplayEngine(project_root)

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            version_repo = VersionRepository(db_session)

            prompt = prompt_repo.create(name="test-prompt")
            version_repo.create(prompt_id=prompt.id, content="v1", message="V1")
            version_repo.create(prompt_id=prompt.id, content="v2", message="V2")

        comparison = engine.compare("test-prompt", [1, 2], "test input")

        assert comparison["input"] == "test input"
        assert comparison["versions"] == [1, 2]
        assert "statistics" in comparison
        assert comparison["statistics"]["total"] == 2


class TestReplayCLI:
    """Test replay CLI commands."""

    def test_replay_run(self, initialized_project, monkeypatch):
        """Test replay run command."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            version_repo = VersionRepository(db_session)

            prompt = prompt_repo.create(name="test-prompt")
            version_repo.create(prompt_id=prompt.id, content="v1", message="V1")

        result = runner.invoke(app, ["replay", "run", "test-prompt", "--input", "Hello"])

        assert result.exit_code == 0
        assert "Replaying" in result.output or "v1" in result.output

    def test_replay_run_with_versions(self, initialized_project, monkeypatch):
        """Test replay run with version range."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            version_repo = VersionRepository(db_session)

            prompt = prompt_repo.create(name="test-prompt")
            for i in range(1, 5):
                version_repo.create(prompt_id=prompt.id, content=f"v{i}", message=f"V{i}")

        result = runner.invoke(app, ["replay", "run", "test-prompt", "--input", "test", "--versions", "1-3"])

        assert result.exit_code == 0

    def test_replay_run_missing_input(self, initialized_project, monkeypatch):
        """Test replay run without input fails."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        result = runner.invoke(app, ["replay", "run", "test-prompt"])

        assert result.exit_code == 1
        assert "input" in result.output.lower()

    def test_replay_run_missing_prompt(self, initialized_project, monkeypatch):
        """Test replay run with missing prompt fails."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        result = runner.invoke(app, ["replay", "run", "nonexistent", "--input", "test"])

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_replay_compare(self, initialized_project, monkeypatch):
        """Test replay compare command."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            version_repo = VersionRepository(db_session)

            prompt = prompt_repo.create(name="test-prompt")
            version_repo.create(prompt_id=prompt.id, content="v1", message="V1")
            version_repo.create(prompt_id=prompt.id, content="v2", message="V2")

        result = runner.invoke(app, ["replay", "compare", "test-prompt", "--input", "test"])

        assert result.exit_code == 0
        assert "Comparison" in result.output

    def test_replay_cache_clear(self, initialized_project, monkeypatch):
        """Test replay cache clear."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        # Add a cache entry
        cache = ReplayCache(project_root)
        result = ReplayResult(1, "input", "output", None, None, None, False)
        cache.set("test", 1, result)

        result = runner.invoke(app, ["replay", "cache", "clear"])

        assert result.exit_code == 0
        assert "Cleared" in result.output

    def test_replay_cache_stats(self, initialized_project, monkeypatch):
        """Test replay cache stats."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        result = runner.invoke(app, ["replay", "cache", "stats"])

        assert result.exit_code == 0
        assert "Cached results" in result.output

    def test_replay_cache_show_empty(self, initialized_project, monkeypatch):
        """Test replay cache show when empty."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        result = runner.invoke(app, ["replay", "cache", "show"])

        assert result.exit_code == 0
        assert "No cached" in result.output

    def test_replay_cache_unknown_action(self, initialized_project, monkeypatch):
        """Test replay cache with unknown action."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        result = runner.invoke(app, ["replay", "cache", "unknown"])

        assert result.exit_code == 1
        assert "Unknown action" in result.output


class TestReplayResult:
    """Test ReplayResult dataclass."""

    def test_replay_result_to_dict(self):
        """Test result serialization."""
        result = ReplayResult(
            version_number=1,
            input_text="test",
            output="output",
            latency_ms=100.0,
            token_usage=50,
            error=None,
            cached=False,
        )

        data = result.to_dict()
        assert data["version_number"] == 1
        assert data["output"] == "output"
        assert data["latency_ms"] == 100.0

    def test_replay_result_with_error(self):
        """Test result with error."""
        result = ReplayResult(
            version_number=1,
            input_text="test",
            output=None,
            latency_ms=None,
            token_usage=None,
            error="Something went wrong",
            cached=False,
        )

        assert result.error is not None
        data = result.to_dict()
        assert data["error"] == "Something went wrong"
