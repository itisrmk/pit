"""Tests for worktree commands and core logic."""

import pytest
from typer.testing import CliRunner
from pathlib import Path

from pit.cli.main import app
from pit.core.worktree import WorktreeManager, Worktree
from pit.db.database import get_session
from pit.db.repository import PromptRepository, VersionRepository


runner = CliRunner()


class TestWorktreeCore:
    """Test core worktree logic."""

    def test_create_worktree(self, initialized_project):
        """Test creating a worktree."""
        project_root = initialized_project
        manager = WorktreeManager(project_root)

        worktree_path = project_root / "wt1"

        worktree = manager.create_worktree(
            path=worktree_path,
            prompt_name="test-prompt",
            prompt_id="abc123",
            version=3,
        )

        assert worktree.path == str(worktree_path.resolve())
        assert worktree.prompt_name == "test-prompt"
        assert worktree.prompt_id == "abc123"
        assert worktree.checked_out_version == 3
        assert worktree_path.exists()
        assert (worktree_path / ".pit-worktree").exists()

    def test_create_duplicate_worktree_fails(self, initialized_project):
        """Test can't create duplicate worktree."""
        project_root = initialized_project
        manager = WorktreeManager(project_root)

        worktree_path = project_root / "wt1"
        manager.create_worktree(worktree_path, "prompt1", "id1")

        with pytest.raises(ValueError, match="already exists"):
            manager.create_worktree(worktree_path, "prompt2", "id2")

    def test_list_worktrees(self, initialized_project):
        """Test listing worktrees."""
        project_root = initialized_project
        manager = WorktreeManager(project_root)

        # Create some worktrees
        wt1 = project_root / "wt1"
        wt2 = project_root / "wt2"
        manager.create_worktree(wt1, "prompt1", "id1", 1)
        manager.create_worktree(wt2, "prompt2", "id2", 2)

        worktrees = manager.list_worktrees()
        assert len(worktrees) == 2
        paths = {w.path for w in worktrees}
        assert str(wt1.resolve()) in paths
        assert str(wt2.resolve()) in paths

    def test_remove_worktree(self, initialized_project):
        """Test removing a worktree."""
        project_root = initialized_project
        manager = WorktreeManager(project_root)

        worktree_path = project_root / "wt1"
        manager.create_worktree(worktree_path, "prompt", "id")

        assert worktree_path.exists()
        manager.remove_worktree(worktree_path)
        assert not worktree_path.exists()

        # Verify removed from tracking
        worktrees = manager.list_worktrees()
        assert len(worktrees) == 0

    def test_remove_nonexistent_worktree_fails(self, initialized_project):
        """Test removing non-existent worktree fails."""
        project_root = initialized_project
        manager = WorktreeManager(project_root)

        with pytest.raises(ValueError, match="Not a pit worktree"):
            manager.remove_worktree(project_root / "nonexistent")

    def test_is_worktree(self, initialized_project):
        """Test checking if path is a worktree."""
        project_root = initialized_project
        manager = WorktreeManager(project_root)

        worktree_path = project_root / "wt1"
        manager.create_worktree(worktree_path, "prompt", "id")

        assert manager.is_worktree(worktree_path)
        assert not manager.is_worktree(project_root)

    def test_get_worktree(self, initialized_project):
        """Test getting worktree info."""
        project_root = initialized_project
        manager = WorktreeManager(project_root)

        worktree_path = project_root / "wt1"
        created = manager.create_worktree(worktree_path, "my-prompt", "abc123", 5)

        retrieved = manager.get_worktree(worktree_path)
        assert retrieved is not None
        assert retrieved.prompt_name == "my-prompt"
        assert retrieved.prompt_id == "abc123"
        assert retrieved.checked_out_version == 5

    def test_update_worktree_version(self, initialized_project):
        """Test updating worktree version."""
        project_root = initialized_project
        manager = WorktreeManager(project_root)

        worktree_path = project_root / "wt1"
        manager.create_worktree(worktree_path, "prompt", "id", 1)

        updated = manager.update_worktree_version(worktree_path, 5)
        assert updated.checked_out_version == 5

        # Verify persisted
        retrieved = manager.get_worktree(worktree_path)
        assert retrieved.checked_out_version == 5


class TestWorktreeCLI:
    """Test worktree CLI commands."""

    def test_worktree_add(self, initialized_project, monkeypatch):
        """Test worktree add command."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        # Create a prompt first
        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            prompt = prompt_repo.create(name="my-prompt")
            version_repo = VersionRepository(db_session)
            version_repo.create(prompt_id=prompt.id, content="v1 content", message="V1")
            version_repo.create(prompt_id=prompt.id, content="v2 content", message="V2")

        worktree_path = project_root / "test-wt"

        result = runner.invoke(
            app,
            ["worktree", "add", str(worktree_path), "my-prompt@v2"]
        )

        assert result.exit_code == 0
        assert "Created worktree" in result.output
        assert "my-prompt" in result.output
        assert worktree_path.exists()

    def test_worktree_list_empty(self, initialized_project, monkeypatch):
        """Test worktree list with no worktrees."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        result = runner.invoke(app, ["worktree", "list"])
        assert result.exit_code == 0
        assert "No worktrees" in result.output

    def test_worktree_list_with_worktrees(self, initialized_project, monkeypatch):
        """Test worktree list shows worktrees."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        # Create prompt and worktrees
        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            prompt = prompt_repo.create(name="prompt1")
            version_repo = VersionRepository(db_session)
            version_repo.create(prompt_id=prompt.id, content="v1", message="V1")

        wt1 = project_root / "wt1"
        wt2 = project_root / "wt2"

        runner.invoke(app, ["worktree", "add", str(wt1), "prompt1"])
        runner.invoke(app, ["worktree", "add", str(wt2), "prompt1@v1"])

        result = runner.invoke(app, ["worktree", "list"])
        assert result.exit_code == 0
        assert "prompt1" in result.output
        assert "2 worktree(s)" in result.output

    def test_worktree_remove(self, initialized_project, monkeypatch):
        """Test worktree remove command."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        # Create prompt and worktree
        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            prompt = prompt_repo.create(name="prompt1")

        wt_path = project_root / "wt-to-remove"
        runner.invoke(app, ["worktree", "add", str(wt_path), "prompt1"])
        assert wt_path.exists()

        result = runner.invoke(app, ["worktree", "remove", str(wt_path), "--force"])
        assert result.exit_code == 0
        assert "Removed worktree" in result.output
        assert not wt_path.exists()

    def test_worktree_info(self, initialized_project, monkeypatch):
        """Test worktree info command."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        # Create prompt and worktree
        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            prompt = prompt_repo.create(name="prompt1")

        wt_path = project_root / "wt-info"
        runner.invoke(app, ["worktree", "add", str(wt_path), "prompt1"])

        result = runner.invoke(app, ["worktree", "info", str(wt_path)])
        assert result.exit_code == 0
        assert "prompt1" in result.output
        assert "Worktree Information" in result.output


class TestWorktreeData:
    """Test Worktree dataclass."""

    def test_worktree_to_dict(self):
        """Test worktree serialization."""
        wt = Worktree(
            path="/path/to/wt",
            prompt_name="test",
            prompt_id="abc123",
            checked_out_version=5,
            created_at="2024-01-01T00:00:00",
        )

        data = wt.to_dict()
        assert data["path"] == "/path/to/wt"
        assert data["prompt_name"] == "test"
        assert data["checked_out_version"] == 5

    def test_worktree_from_dict(self):
        """Test worktree deserialization."""
        data = {
            "path": "/path/to/wt",
            "prompt_name": "test",
            "prompt_id": "abc123",
            "checked_out_version": 5,
            "created_at": "2024-01-01T00:00:00",
            "last_used": "2024-01-02T00:00:00",
        }

        wt = Worktree.from_dict(data)
        assert wt.path == "/path/to/wt"
        assert wt.prompt_name == "test"
        assert wt.last_used == "2024-01-02T00:00:00"
