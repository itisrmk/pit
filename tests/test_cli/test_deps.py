"""Tests for dependencies commands and core logic."""

import pytest
from typer.testing import CliRunner
from pathlib import Path

from pit.cli.main import app
from pit.core.dependencies import (
    DependencyManager, Dependency, DependencySource,
    DependencyLock, DependencyResolver
)


runner = CliRunner()


class TestDependencyResolver:
    """Test dependency resolution."""

    def test_resolve_github(self):
        """Test GitHub URL resolution."""
        url = DependencyResolver.resolve_github(
            "anthropic/prompts", "citation-format", "v2.1"
        )
        assert "githubusercontent.com" in url
        assert "anthropic/prompts" in url
        assert "v2.1" in url
        assert "citation-format" in url

    def test_resolve_local(self, tmp_path):
        """Test local path resolution."""
        test_file = tmp_path / "test.bundle"
        test_file.write_text("test")

        url = DependencyResolver.resolve_local(str(test_file))
        assert url.startswith("file://")

    def test_resolve_url(self):
        """Test URL resolution."""
        url = DependencyResolver.resolve_url("https://example.com/test.bundle")
        assert url == "https://example.com/test.bundle"


class TestDependencyManager:
    """Test dependency manager functionality."""

    def test_list_empty(self, initialized_project):
        """Test listing when no dependencies."""
        project_root = initialized_project
        manager = DependencyManager(project_root)

        deps = manager.list_dependencies()
        assert deps == []

    def test_add_dependency(self, initialized_project):
        """Test adding a dependency."""
        project_root = initialized_project
        manager = DependencyManager(project_root)

        dep = manager.add_dependency(
            "my-dep",
            DependencySource.LOCAL,
            "/path/to/dep",
            "v1.0",
        )

        assert dep.name == "my-dep"
        assert dep.source == DependencySource.LOCAL

        # Verify it's in the list
        deps = manager.list_dependencies()
        assert len(deps) == 1
        assert deps[0].name == "my-dep"

    def test_add_duplicate_fails(self, initialized_project):
        """Test adding duplicate dependency fails."""
        project_root = initialized_project
        manager = DependencyManager(project_root)

        manager.add_dependency("my-dep", DependencySource.LOCAL, "/path", "v1")

        with pytest.raises(ValueError, match="already exists"):
            manager.add_dependency("my-dep", DependencySource.LOCAL, "/other", "v2")

    def test_remove_dependency(self, initialized_project):
        """Test removing a dependency."""
        project_root = initialized_project
        manager = DependencyManager(project_root)

        manager.add_dependency("my-dep", DependencySource.LOCAL, "/path", "v1")
        removed = manager.remove_dependency("my-dep")

        assert removed is True
        assert manager.list_dependencies() == []

    def test_remove_nonexistent(self, initialized_project):
        """Test removing non-existent dependency."""
        project_root = initialized_project
        manager = DependencyManager(project_root)

        removed = manager.remove_dependency("nonexistent")
        assert removed is False

    def test_get_dependency_tree(self, initialized_project):
        """Test getting dependency tree."""
        project_root = initialized_project
        manager = DependencyManager(project_root)

        manager.add_dependency("dep1", DependencySource.GITHUB, "org/repo/path", "v1")
        manager.add_dependency("dep2", DependencySource.LOCAL, "/path", "main")

        tree = manager.get_dependency_tree()

        assert "dep1" in tree
        assert "dep2" in tree
        assert tree["dep1"]["source"] == "github"


class TestDependencyData:
    """Test dependency dataclasses."""

    def test_dependency_to_dict(self):
        """Test dependency serialization."""
        dep = Dependency(
            name="test",
            source=DependencySource.GITHUB,
            path="org/repo/prompt",
            version="v1.0",
        )

        data = dep.to_dict()
        assert data["name"] == "test"
        assert data["source"] == "github"

    def test_dependency_from_dict(self):
        """Test dependency deserialization."""
        data = {
            "name": "test",
            "source": "local",
            "path": "/path/to/prompt",
            "version": "main",
            "resolved_url": None,
            "installed_at": None,
        }

        dep = Dependency.from_dict(data)
        assert dep.name == "test"
        assert dep.source == DependencySource.LOCAL

    def test_dependency_lock_to_dict(self):
        """Test lock entry serialization."""
        lock = DependencyLock(
            name="test",
            source="github",
            version="v1.0",
            resolved_url="https://example.com/test.bundle",
        )

        data = lock.to_dict()
        assert data["name"] == "test"
        assert data["resolved_url"] == "https://example.com/test.bundle"


class TestDependencyCLI:
    """Test dependencies CLI commands."""

    def test_deps_list_empty(self, initialized_project, monkeypatch):
        """Test deps list with no dependencies."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        result = runner.invoke(app, ["deps", "list"])

        assert result.exit_code == 0
        assert "No dependencies" in result.output

    def test_deps_add(self, initialized_project, monkeypatch):
        """Test deps add command."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        result = runner.invoke(app, [
            "deps", "add", "my-dep", "local", "/path/to/prompt",
            "--version", "v1.0"
        ])

        assert result.exit_code == 0
        assert "Added dependency" in result.output

    def test_deps_add_unknown_source(self, initialized_project, monkeypatch):
        """Test deps add with unknown source fails."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        result = runner.invoke(app, ["deps", "add", "my-dep", "unknown", "/path"])

        assert result.exit_code == 1
        assert "Unknown source" in result.output

    def test_deps_add_duplicate(self, initialized_project, monkeypatch):
        """Test deps add with duplicate name fails."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        runner.invoke(app, ["deps", "add", "my-dep", "local", "/path1"])
        result = runner.invoke(app, ["deps", "add", "my-dep", "local", "/path2"])

        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_deps_list_with_deps(self, initialized_project, monkeypatch):
        """Test deps list shows dependencies."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        runner.invoke(app, ["deps", "add", "dep1", "github", "org/repo/prompt"])
        runner.invoke(app, ["deps", "add", "dep2", "local", "/path"])

        result = runner.invoke(app, ["deps", "list"])

        assert result.exit_code == 0
        assert "dep1" in result.output
        assert "dep2" in result.output
        assert "2 dependency(s)" in result.output

    def test_deps_remove(self, initialized_project, monkeypatch):
        """Test deps remove command."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        runner.invoke(app, ["deps", "add", "my-dep", "local", "/path"])
        result = runner.invoke(app, ["deps", "remove", "my-dep", "--force"])

        assert result.exit_code == 0
        assert "Removed dependency" in result.output

    def test_deps_remove_not_found(self, initialized_project, monkeypatch):
        """Test deps remove with non-existent dep."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        result = runner.invoke(app, ["deps", "remove", "nonexistent", "--force"])

        assert result.exit_code == 0
        assert "not found" in result.output

    def test_deps_tree(self, initialized_project, monkeypatch):
        """Test deps tree command."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        runner.invoke(app, ["deps", "add", "dep1", "github", "org/repo/prompt", "--version", "v1"])

        result = runner.invoke(app, ["deps", "tree"])

        assert result.exit_code == 0
        assert "Dependencies" in result.output
        assert "dep1" in result.output

    def test_deps_tree_empty(self, initialized_project, monkeypatch):
        """Test deps tree with no dependencies."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        result = runner.invoke(app, ["deps", "tree"])

        assert result.exit_code == 0
        assert "No dependencies" in result.output
