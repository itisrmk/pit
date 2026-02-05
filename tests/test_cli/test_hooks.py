"""Tests for hooks commands and core logic."""

import os
import stat
import pytest
from typer.testing import CliRunner
from pathlib import Path

from pit.cli.main import app
from pit.core.hooks import (
    HookManager, HookType, HookScript, HookResult
)


runner = CliRunner()


class TestHookCore:
    """Test core hooks logic."""

    def test_list_hooks_empty(self, initialized_project):
        """Test listing hooks when none are installed."""
        project_root = initialized_project
        manager = HookManager(project_root)

        hooks = manager.list_hooks()

        assert len(hooks) == 6  # All hook types
        for hook_type, hook in hooks.items():
            assert hook is None

    def test_install_hook(self, initialized_project):
        """Test installing a hook."""
        project_root = initialized_project
        manager = HookManager(project_root)

        content = "#!/bin/bash\necho 'Hello'\n"
        hook = manager.install_hook(HookType.PRE_COMMIT, content)

        assert hook.hook_type == HookType.PRE_COMMIT
        assert hook.content == content
        assert hook.is_executable is True
        assert hook.path.exists()

    def test_install_hook_not_executable(self, initialized_project):
        """Test installing a hook without executable flag."""
        project_root = initialized_project
        manager = HookManager(project_root)

        content = "#!/bin/bash\necho 'Hello'\n"
        hook = manager.install_hook(HookType.PRE_COMMIT, content, make_executable=False)

        assert hook.is_executable is False

    def test_get_hook(self, initialized_project):
        """Test retrieving a specific hook."""
        project_root = initialized_project
        manager = HookManager(project_root)

        manager.install_hook(HookType.POST_COMMIT, "#!/bin/bash\n")

        hook = manager.get_hook(HookType.POST_COMMIT)
        assert hook is not None
        assert hook.hook_type == HookType.POST_COMMIT

        # Non-existent hook
        assert manager.get_hook(HookType.PRE_MERGE) is None

    def test_uninstall_hook(self, initialized_project):
        """Test uninstalling a hook."""
        project_root = initialized_project
        manager = HookManager(project_root)

        manager.install_hook(HookType.PRE_COMMIT, "#!/bin/bash\n")

        result = manager.uninstall_hook(HookType.PRE_COMMIT)
        assert result is True
        assert manager.get_hook(HookType.PRE_COMMIT) is None

    def test_uninstall_nonexistent_hook(self, initialized_project):
        """Test uninstalling a hook that doesn't exist."""
        project_root = initialized_project
        manager = HookManager(project_root)

        result = manager.uninstall_hook(HookType.PRE_COMMIT)
        assert result is False

    def test_create_sample_hooks(self, initialized_project):
        """Test that sample hooks are generated for all types."""
        project_root = initialized_project
        manager = HookManager(project_root)

        for hook_type in HookType.all():
            sample = manager.create_sample_hook(hook_type)
            assert sample.startswith("#!/bin/bash")
            assert hook_type.value in sample.lower()


class TestHookRun:
    """Test hook execution."""

    def test_run_hook_success(self, initialized_project):
        """Test running a hook that succeeds."""
        project_root = initialized_project
        manager = HookManager(project_root)

        # Create a hook that exits 0
        manager.install_hook(HookType.PRE_COMMIT, "#!/bin/bash\necho 'OK'\nexit 0\n")

        result = manager.run_hook(HookType.PRE_COMMIT)

        assert result.success is True
        assert result.exit_code == 0
        assert "OK" in result.stdout
        assert result.hook_type == HookType.PRE_COMMIT

    def test_run_hook_failure(self, initialized_project):
        """Test running a hook that fails."""
        project_root = initialized_project
        manager = HookManager(project_root)

        manager.install_hook(HookType.PRE_COMMIT, "#!/bin/bash\necho 'Error' >&2\nexit 1\n")

        result = manager.run_hook(HookType.PRE_COMMIT)

        assert result.success is False
        assert result.exit_code == 1

    def test_run_nonexistent_hook(self, initialized_project):
        """Test running a hook that doesn't exist."""
        project_root = initialized_project
        manager = HookManager(project_root)

        result = manager.run_hook(HookType.PRE_COMMIT)

        assert result.success is True  # No hook is not an error
        assert "No pre-commit hook" in result.message

    def test_run_hook_with_env_vars(self, initialized_project):
        """Test running a hook with environment variables."""
        project_root = initialized_project
        manager = HookManager(project_root)

        # Create hook that echoes env var
        manager.install_hook(HookType.PRE_COMMIT, "#!/bin/bash\necho $TEST_VAR\n")

        result = manager.run_hook(HookType.PRE_COMMIT, env_vars={"TEST_VAR": "hello"})

        assert "hello" in result.stdout

    def test_run_non_executable_hook(self, initialized_project):
        """Test running a hook that's not executable."""
        project_root = initialized_project
        manager = HookManager(project_root)

        manager.install_hook(HookType.PRE_COMMIT, "#!/bin/bash\n", make_executable=False)

        result = manager.run_hook(HookType.PRE_COMMIT)

        assert result.success is False
        assert "not executable" in result.message


class TestHookCLI:
    """Test hooks CLI commands."""

    def test_hooks_list_empty(self, initialized_project, monkeypatch):
        """Test hooks list with no hooks."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        result = runner.invoke(app, ["hooks", "list"])

        assert result.exit_code == 0
        assert "0/6 hooks installed" in result.output

    def test_hooks_list_with_hooks(self, initialized_project, monkeypatch):
        """Test hooks list shows installed hooks."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        # Install a hook
        manager = HookManager(project_root)
        manager.install_hook(HookType.PRE_COMMIT, "#!/bin/bash\n")

        result = runner.invoke(app, ["hooks", "list"])

        assert result.exit_code == 0
        assert "pre-commit" in result.output
        assert "1/6 hooks installed" in result.output

    def test_hooks_install_sample(self, initialized_project, monkeypatch):
        """Test installing a sample hook."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        result = runner.invoke(app, ["hooks", "install", "pre-commit"])

        assert result.exit_code == 0
        assert "Created sample pre-commit hook" in result.output

        # Verify file exists
        manager = HookManager(project_root)
        hook = manager.get_hook(HookType.PRE_COMMIT)
        assert hook is not None

    def test_hooks_install_from_file(self, initialized_project, monkeypatch, tmp_path):
        """Test installing a hook from file."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        # Create a script file
        script_path = tmp_path / "my-hook.sh"
        script_path.write_text("#!/bin/bash\necho 'Custom'\n")

        result = runner.invoke(app, ["hooks", "install", "post-commit", "--script", str(script_path)])

        assert result.exit_code == 0
        assert "Installed post-commit hook" in result.output

        manager = HookManager(project_root)
        hook = manager.get_hook(HookType.POST_COMMIT)
        assert "Custom" in hook.content

    def test_hooks_install_already_exists(self, initialized_project, monkeypatch):
        """Test installing hook when one already exists."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        # First install
        runner.invoke(app, ["hooks", "install", "pre-commit"])

        # Second install without --force
        result = runner.invoke(app, ["hooks", "install", "pre-commit"])

        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_hooks_install_force(self, initialized_project, monkeypatch):
        """Test installing hook with --force."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        # First install
        runner.invoke(app, ["hooks", "install", "pre-commit"])

        # Second install with --force
        result = runner.invoke(app, ["hooks", "install", "pre-commit", "--force"])

        assert result.exit_code == 0

    def test_hooks_install_unknown_type(self, initialized_project, monkeypatch):
        """Test installing unknown hook type."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        result = runner.invoke(app, ["hooks", "install", "unknown-hook"])

        assert result.exit_code == 1
        assert "Unknown hook" in result.output

    def test_hooks_uninstall(self, initialized_project, monkeypatch):
        """Test uninstalling a hook."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        # Install first
        runner.invoke(app, ["hooks", "install", "pre-commit"])

        # Uninstall with --force
        result = runner.invoke(app, ["hooks", "uninstall", "pre-commit", "--force"])

        assert result.exit_code == 0
        assert "Uninstalled pre-commit hook" in result.output

    def test_hooks_show(self, initialized_project, monkeypatch):
        """Test showing a hook."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        runner.invoke(app, ["hooks", "install", "pre-commit"])

        result = runner.invoke(app, ["hooks", "show", "pre-commit"])

        assert result.exit_code == 0
        assert "pre-commit hook" in result.output
        assert "#!/bin/bash" in result.output

    def test_hooks_show_not_installed(self, initialized_project, monkeypatch):
        """Test showing a hook that doesn't exist."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        result = runner.invoke(app, ["hooks", "show", "pre-commit"])

        assert result.exit_code == 1
        assert "not installed" in result.output

    def test_hooks_run_success(self, initialized_project, monkeypatch):
        """Test running a hook."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        manager = HookManager(project_root)
        manager.install_hook(HookType.PRE_COMMIT, "#!/bin/bash\necho 'Running'\nexit 0\n")

        result = runner.invoke(app, ["hooks", "run", "pre-commit"])

        assert result.exit_code == 0
        assert "Running" in result.output

    def test_hooks_run_with_env(self, initialized_project, monkeypatch):
        """Test running a hook with environment variables."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        manager = HookManager(project_root)
        manager.install_hook(HookType.PRE_COMMIT, "#!/bin/bash\necho $PROMPT_NAME\n")

        result = runner.invoke(app, ["hooks", "run", "pre-commit", "--prompt", "my-prompt"])

        assert result.exit_code == 0
        assert "my-prompt" in result.output

    def test_hooks_run_not_installed(self, initialized_project, monkeypatch):
        """Test running a hook that doesn't exist."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        result = runner.invoke(app, ["hooks", "run", "pre-commit"])

        assert result.exit_code == 0  # Not an error, just a warning
        assert "not installed" in result.output


class TestHookData:
    """Test Hook dataclasses."""

    def test_hook_type_enum(self):
        """Test HookType enum values."""
        assert HookType.PRE_COMMIT.value == "pre-commit"
        assert HookType.POST_COMMIT.value == "post-commit"
        assert HookType.PRE_CHECKOUT.value == "pre-checkout"
        assert HookType.POST_CHECKOUT.value == "post-checkout"
        assert HookType.PRE_MERGE.value == "pre-merge"
        assert HookType.POST_MERGE.value == "post-merge"

    def test_hook_type_all(self):
        """Test HookType.all() returns all types."""
        all_types = HookType.all()
        assert len(all_types) == 6
        assert HookType.PRE_COMMIT in all_types
        assert HookType.POST_MERGE in all_types

    def test_hook_result_success(self):
        """Test HookResult for success."""
        result = HookResult(
            success=True,
            hook_type=HookType.PRE_COMMIT,
            stdout="output",
            stderr="",
            exit_code=0,
            message="OK",
        )
        assert result.success is True
        assert result.exit_code == 0

    def test_hook_result_failure(self):
        """Test HookResult for failure."""
        result = HookResult(
            success=False,
            hook_type=HookType.PRE_COMMIT,
            stdout="",
            stderr="error",
            exit_code=1,
            message="Failed",
        )
        assert result.success is False
        assert result.exit_code == 1
