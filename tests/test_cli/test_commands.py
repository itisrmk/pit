"""Tests for CLI commands."""

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pit.cli.main import app
from pit.config import DEFAULT_DIR, CONFIG_FILE


runner = CliRunner()


class TestInitCommand:
    """Tests for the init command."""

    def test_init_creates_directory(self, temp_project: Path) -> None:
        """Test that init creates the .pit directory."""
        os.chdir(temp_project)
        result = runner.invoke(app, ["init"])

        assert result.exit_code == 0
        assert (temp_project / DEFAULT_DIR).exists()
        assert (temp_project / DEFAULT_DIR / "pit.db").exists()
        assert (temp_project / CONFIG_FILE).exists()

    def test_init_with_path(self, temp_project: Path) -> None:
        """Test init with explicit path argument."""
        result = runner.invoke(app, ["init", str(temp_project)])

        assert result.exit_code == 0
        assert (temp_project / DEFAULT_DIR).exists()

    def test_init_already_initialized(self, initialized_project: Path) -> None:
        """Test init fails when already initialized."""
        os.chdir(initialized_project)
        result = runner.invoke(app, ["init"])

        assert result.exit_code == 1
        assert "Already initialized" in result.output

    def test_init_force_reinitialize(self, initialized_project: Path) -> None:
        """Test init --force reinitializes."""
        os.chdir(initialized_project)
        result = runner.invoke(app, ["init", "--force"])

        assert result.exit_code == 0
        assert "Reinitializing" in result.output


class TestAddCommand:
    """Tests for the add command."""

    def test_add_prompt(self, initialized_project: Path) -> None:
        """Test adding a new prompt."""
        os.chdir(initialized_project)
        result = runner.invoke(
            app,
            ["add", "summarize", "-d", "Summarizes text", "-c", "Test content", "-m", "Initial"],
        )

        assert result.exit_code == 0
        assert "Created prompt 'summarize'" in result.output
        assert "Created version v1" in result.output

    def test_add_duplicate_fails(self, initialized_project: Path) -> None:
        """Test that adding a duplicate prompt fails."""
        os.chdir(initialized_project)
        runner.invoke(app, ["add", "test-prompt", "-c", "content"])
        result = runner.invoke(app, ["add", "test-prompt", "-c", "content"])

        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_add_invalid_name(self, initialized_project: Path) -> None:
        """Test that invalid names are rejected."""
        os.chdir(initialized_project)
        result = runner.invoke(app, ["add", "invalid name!", "-c", "content"])

        assert result.exit_code == 1
        assert "alphanumeric" in result.output

    def test_add_not_initialized(self, temp_project: Path) -> None:
        """Test add fails when not initialized."""
        os.chdir(temp_project)
        result = runner.invoke(app, ["add", "test", "-c", "content"])

        assert result.exit_code == 1
        assert "Not a pit project" in result.output


class TestListCommand:
    """Tests for the list command."""

    def test_list_empty(self, initialized_project: Path) -> None:
        """Test listing when no prompts exist."""
        os.chdir(initialized_project)
        result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        assert "No prompts found" in result.output

    def test_list_prompts(self, initialized_project: Path) -> None:
        """Test listing existing prompts."""
        os.chdir(initialized_project)
        runner.invoke(app, ["add", "prompt-a", "-c", "Content A"])
        runner.invoke(app, ["add", "prompt-b", "-c", "Content B"])

        result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        assert "prompt-a" in result.output
        assert "prompt-b" in result.output


class TestShowCommand:
    """Tests for the show command."""

    def test_show_prompt(self, initialized_project: Path) -> None:
        """Test showing a prompt's details."""
        os.chdir(initialized_project)
        runner.invoke(
            app,
            ["add", "test-prompt", "-d", "A test prompt", "-c", "Test content"],
        )

        result = runner.invoke(app, ["show", "test-prompt"])

        assert result.exit_code == 0
        assert "test-prompt" in result.output
        assert "Test content" in result.output

    def test_show_not_found(self, initialized_project: Path) -> None:
        """Test showing a nonexistent prompt."""
        os.chdir(initialized_project)
        result = runner.invoke(app, ["show", "nonexistent"])

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_show_specific_version(self, initialized_project: Path) -> None:
        """Test showing a specific version."""
        os.chdir(initialized_project)
        runner.invoke(app, ["add", "test-prompt", "-c", "Version 1"])
        # Would need commit command for v2, which is Phase 2

        result = runner.invoke(app, ["show", "test-prompt", "--version", "1"])

        assert result.exit_code == 0
        assert "Version 1" in result.output


class TestVersionFlag:
    """Tests for the version flag."""

    def test_version_flag(self) -> None:
        """Test --version flag shows version."""
        result = runner.invoke(app, ["--version"])

        assert result.exit_code == 0
        assert "Version:" in result.output

    def test_version_command(self) -> None:
        """Test version command shows version."""
        result = runner.invoke(app, ["version"])

        assert result.exit_code == 0
        assert "Version:" in result.output
