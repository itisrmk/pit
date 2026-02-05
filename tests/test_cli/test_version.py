"""Tests for version control commands."""

import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from pit.cli.main import app
from pit.db.database import get_session
from pit.db.repository import PromptRepository, VersionRepository


runner = CliRunner()


class TestCommitCommand:
    """Tests for the commit command."""

    def test_commit_new_version(self, initialized_project: Path) -> None:
        """Test creating a new version of a prompt."""
        os.chdir(initialized_project)
        
        # First create a prompt
        runner.invoke(app, ["add", "test-prompt", "-c", "Initial content", "-m", "Initial"])
        
        # Now commit a new version
        result = runner.invoke(
            app,
            ["commit", "test-prompt", "-m", "Updated content", "-c", "New improved content"],
        )

        assert result.exit_code == 0
        assert "Created version v2" in result.output

    def test_commit_with_stdin(self, initialized_project: Path) -> None:
        """Test committing with content from stdin."""
        os.chdir(initialized_project)
        
        # First create a prompt
        runner.invoke(app, ["add", "test-prompt", "-c", "Initial content", "-m", "Initial"])
        
        # Commit with stdin
        result = runner.invoke(
            app,
            ["commit", "test-prompt", "-m", "Stdin version"],
            input="Content from stdin\n",
        )

        assert result.exit_code == 0
        assert "Created version v2" in result.output

    def test_commit_prompt_not_found(self, initialized_project: Path) -> None:
        """Test commit fails when prompt doesn't exist."""
        os.chdir(initialized_project)
        
        result = runner.invoke(
            app,
            ["commit", "nonexistent", "-m", "Test", "-c", "Content"],
        )

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_commit_empty_content(self, initialized_project: Path) -> None:
        """Test commit fails with empty content."""
        os.chdir(initialized_project)
        
        runner.invoke(app, ["add", "test-prompt", "-c", "Initial", "-m", "Initial"])
        
        result = runner.invoke(
            app,
            ["commit", "test-prompt", "-m", "Test", "-c", ""],
        )

        assert result.exit_code == 1

    def test_commit_with_semantic_diff(self, initialized_project: Path) -> None:
        """Test committing with semantic diff generation."""
        os.chdir(initialized_project)
        
        runner.invoke(app, ["add", "test-prompt", "-c", "Initial content", "-m", "Initial"])
        
        # Mock the semantic diff analyzer
        mock_semantic_diff = {
            "intent_changes": [{"description": "Changed purpose", "severity": "medium"}],
            "scope_changes": [],
            "constraint_changes": [],
            "tone_changes": [],
            "structure_changes": [],
            "breaking_changes": [],
            "summary": "Changed the purpose of the prompt",
        }
        
        with patch("pit.cli.commands.version.SemanticDiffAnalyzer") as mock_analyzer_class:
            mock_analyzer = Mock()
            mock_analyzer.analyze_diff.return_value = mock_semantic_diff
            mock_analyzer_class.return_value = mock_analyzer
            
            result = runner.invoke(
                app,
                ["commit", "test-prompt", "-m", "Updated", "-c", "New content"],
            )

            assert result.exit_code == 0
            mock_analyzer.analyze_diff.assert_called_once()


class TestLogCommand:
    """Tests for the log command."""

    def test_log_empty(self, initialized_project: Path) -> None:
        """Test log shows no versions when prompt has none."""
        os.chdir(initialized_project)
        
        # Create a prompt without version
        with get_session(initialized_project) as session:
            repo = PromptRepository(session)
            repo.create(name="empty-prompt")
        
        result = runner.invoke(app, ["log", "empty-prompt"])

        assert result.exit_code == 0
        assert "Total: 0 version(s)" in result.output or "No versions" in result.output

    def test_log_with_versions(self, initialized_project: Path) -> None:
        """Test log shows version history."""
        os.chdir(initialized_project)
        
        runner.invoke(app, ["add", "test-prompt", "-c", "Content v1", "-m", "First"])
        runner.invoke(app, ["commit", "test-prompt", "-c", "Content v2", "-m", "Second"])
        runner.invoke(app, ["commit", "test-prompt", "-c", "Content v3", "-m", "Third"])
        
        result = runner.invoke(app, ["log", "test-prompt"])

        assert result.exit_code == 0
        assert "v3" in result.output
        assert "v2" in result.output
        assert "v1" in result.output
        assert "Total: 3 version(s)" in result.output

    def test_log_with_limit(self, initialized_project: Path) -> None:
        """Test log with --limit option."""
        os.chdir(initialized_project)
        
        runner.invoke(app, ["add", "test-prompt", "-c", "Content v1", "-m", "First"])
        runner.invoke(app, ["commit", "test-prompt", "-c", "Content v2", "-m", "Second"])
        runner.invoke(app, ["commit", "test-prompt", "-c", "Content v3", "-m", "Third"])
        
        result = runner.invoke(app, ["log", "test-prompt", "--limit", "2"])

        assert result.exit_code == 0
        # Should only show 2 versions

    def test_log_prompt_not_found(self, initialized_project: Path) -> None:
        """Test log fails when prompt doesn't exist."""
        os.chdir(initialized_project)
        
        result = runner.invoke(app, ["log", "nonexistent"])

        assert result.exit_code == 1
        assert "not found" in result.output


class TestDiffCommand:
    """Tests for the diff command."""

    def test_diff_two_versions(self, initialized_project: Path) -> None:
        """Test diff between two versions."""
        os.chdir(initialized_project)
        
        runner.invoke(app, ["add", "test-prompt", "-c", "Line 1\nLine 2", "-m", "First"])
        runner.invoke(app, ["commit", "test-prompt", "-c", "Line 1\nLine 3", "-m", "Second"])
        
        result = runner.invoke(app, ["diff", "test-prompt", "1", "2"])

        assert result.exit_code == 0
        assert "Diff between v1 and v2" in result.output
        assert "Line 2" in result.output or "Line 3" in result.output

    def test_diff_with_v_prefix(self, initialized_project: Path) -> None:
        """Test diff with 'v' prefix in version numbers."""
        os.chdir(initialized_project)
        
        runner.invoke(app, ["add", "test-prompt", "-c", "Content 1", "-m", "First"])
        runner.invoke(app, ["commit", "test-prompt", "-c", "Content 2", "-m", "Second"])
        
        result = runner.invoke(app, ["diff", "test-prompt", "v1", "v2"])

        assert result.exit_code == 0
        assert "Diff between v1 and v2" in result.output

    def test_diff_version_not_found(self, initialized_project: Path) -> None:
        """Test diff fails when version doesn't exist."""
        os.chdir(initialized_project)
        
        runner.invoke(app, ["add", "test-prompt", "-c", "Content", "-m", "First"])
        
        result = runner.invoke(app, ["diff", "test-prompt", "1", "99"])

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_diff_semantic(self, initialized_project: Path) -> None:
        """Test diff with --semantic flag."""
        os.chdir(initialized_project)
        
        runner.invoke(app, ["add", "test-prompt", "-c", "Content 1", "-m", "First"])
        runner.invoke(app, ["commit", "test-prompt", "-c", "Content 2", "-m", "Second"])
        
        # Add semantic diff to version 2
        with get_session(initialized_project) as session:
            version_repo = VersionRepository(session)
            prompt_repo = PromptRepository(session)
            prompt = prompt_repo.get_by_name("test-prompt")
            version = version_repo.get_latest(prompt.id)
            version_repo.update_semantic_diff(version, {
                "summary": "Test semantic diff",
                "intent_changes": [{"description": "Changed intent", "severity": "high"}],
            })
        
        result = runner.invoke(app, ["diff", "test-prompt", "1", "2", "--semantic"])

        assert result.exit_code == 0
        assert "Semantic diff" in result.output
        assert "Test semantic diff" in result.output

    def test_diff_semantic_not_available(self, initialized_project: Path) -> None:
        """Test semantic diff when not available."""
        os.chdir(initialized_project)
        
        runner.invoke(app, ["add", "test-prompt", "-c", "Content 1", "-m", "First"])
        runner.invoke(app, ["commit", "test-prompt", "-c", "Content 2", "-m", "Second"])
        
        result = runner.invoke(app, ["diff", "test-prompt", "1", "2", "--semantic"])

        assert result.exit_code == 0
        assert "No semantic diff available" in result.output


class TestCheckoutCommand:
    """Tests for the checkout command."""

    def test_checkout_version(self, initialized_project: Path) -> None:
        """Test viewing a specific version."""
        os.chdir(initialized_project)
        
        runner.invoke(app, ["add", "test-prompt", "-c", "Version 1 content", "-m", "First"])
        runner.invoke(app, ["commit", "test-prompt", "-c", "Version 2 content", "-m", "Second"])
        
        result = runner.invoke(app, ["checkout", "test-prompt", "1"])

        assert result.exit_code == 0
        assert "Version 1 content" in result.output
        assert "v1" in result.output

    def test_checkout_with_v_prefix(self, initialized_project: Path) -> None:
        """Test checkout with 'v' prefix."""
        os.chdir(initialized_project)
        
        runner.invoke(app, ["add", "test-prompt", "-c", "Content", "-m", "First"])
        
        result = runner.invoke(app, ["checkout", "test-prompt", "v1"])

        assert result.exit_code == 0
        assert "v1" in result.output

    def test_checkout_version_not_found(self, initialized_project: Path) -> None:
        """Test checkout fails when version doesn't exist."""
        os.chdir(initialized_project)
        
        runner.invoke(app, ["add", "test-prompt", "-c", "Content", "-m", "First"])
        
        result = runner.invoke(app, ["checkout", "test-prompt", "99"])

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_checkout_prompt_not_found(self, initialized_project: Path) -> None:
        """Test checkout fails when prompt doesn't exist."""
        os.chdir(initialized_project)
        
        result = runner.invoke(app, ["checkout", "nonexistent", "1"])

        assert result.exit_code == 1
        assert "not found" in result.output


class TestTagCommand:
    """Tests for the tag command."""

    def test_tag_add(self, initialized_project: Path) -> None:
        """Test adding a tag to a version."""
        os.chdir(initialized_project)
        
        runner.invoke(app, ["add", "test-prompt", "-c", "Content", "-m", "First"])
        
        result = runner.invoke(app, ["tag", "test-prompt", "1", "stable"])

        assert result.exit_code == 0
        assert "Added tag 'stable' to v1" in result.output

    def test_tag_remove(self, initialized_project: Path) -> None:
        """Test removing a tag from a version."""
        os.chdir(initialized_project)
        
        runner.invoke(app, ["add", "test-prompt", "-c", "Content", "-m", "First"])
        runner.invoke(app, ["tag", "test-prompt", "1", "stable"])
        
        result = runner.invoke(app, ["tag", "test-prompt", "1", "stable", "--remove"])

        assert result.exit_code == 0
        assert "Removed tag 'stable' from v1" in result.output

    def test_tag_list(self, initialized_project: Path) -> None:
        """Test listing tags for a version."""
        os.chdir(initialized_project)
        
        runner.invoke(app, ["add", "test-prompt", "-c", "Content", "-m", "First"])
        runner.invoke(app, ["tag", "test-prompt", "1", "stable"])
        runner.invoke(app, ["tag", "test-prompt", "1", "production"])
        
        result = runner.invoke(app, ["tag", "test-prompt", "1", "--list"])

        assert result.exit_code == 0
        assert "stable" in result.output
        assert "production" in result.output

    def test_tag_add_duplicate(self, initialized_project: Path) -> None:
        """Test adding a duplicate tag fails."""
        os.chdir(initialized_project)
        
        runner.invoke(app, ["add", "test-prompt", "-c", "Content", "-m", "First"])
        runner.invoke(app, ["tag", "test-prompt", "1", "stable"])
        
        result = runner.invoke(app, ["tag", "test-prompt", "1", "stable"])

        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_tag_remove_nonexistent(self, initialized_project: Path) -> None:
        """Test removing a non-existent tag fails."""
        os.chdir(initialized_project)
        
        runner.invoke(app, ["add", "test-prompt", "-c", "Content", "-m", "First"])
        
        result = runner.invoke(app, ["tag", "test-prompt", "1", "nonexistent", "--remove"])

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_tag_version_not_found(self, initialized_project: Path) -> None:
        """Test tag fails when version doesn't exist."""
        os.chdir(initialized_project)
        
        runner.invoke(app, ["add", "test-prompt", "-c", "Content", "-m", "First"])
        
        result = runner.invoke(app, ["tag", "test-prompt", "99", "stable"])

        assert result.exit_code == 1
        assert "not found" in result.output
