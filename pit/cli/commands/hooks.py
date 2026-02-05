"""Hooks commands for managing git-style prompt hooks."""

from pathlib import Path
from typing import Optional

import typer
from rich.table import Table

from pit.config import find_project_root, is_initialized
from pit.cli.formatters import console, print_error, print_success, print_info, print_warning
from pit.core.hooks import HookManager, HookType

app = typer.Typer()


def require_initialized() -> Path:
    """Ensure pit is initialized and return project root."""
    project_root = find_project_root()
    if project_root is None:
        print_error("Not a pit project. Run 'pit init' first.")
        raise typer.Exit(1)
    return project_root


@app.command("list")
def list_hooks() -> None:
    """List all installed hooks."""
    project_root = require_initialized()
    manager = HookManager(project_root)

    hooks = manager.list_hooks()

    table = Table(title="PIT Hooks")
    table.add_column("Hook", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Executable", style="yellow")
    table.add_column("Modified")

    for hook_type, hook in hooks.items():
        if hook:
            status = "✓ Installed"
            executable = "✓ Yes" if hook.is_executable else "✗ No"
            modified = hook.created_at.strftime("%Y-%m-%d %H:%M")
        else:
            status = "✗ Not installed"
            executable = "-"
            modified = "-"

        table.add_row(hook_type.value, status, executable, modified)

    console.print(table)

    installed = sum(1 for h in hooks.values() if h is not None)
    print_info(f"{installed}/{len(hooks)} hooks installed")


@app.command("install")
def install_hook(
    hook_name: str = typer.Argument(..., help="Name of the hook (pre-commit, post-commit, etc.)"),
    script_path: Optional[str] = typer.Option(
        None,
        "--script",
        "-s",
        help="Path to script file (creates sample if not provided)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing hook",
    ),
) -> None:
    """Install a hook script.

    If --script is not provided, creates a sample hook that you can edit.
    """
    project_root = require_initialized()
    manager = HookManager(project_root)

    # Validate hook type
    try:
        hook_type = HookType(hook_name)
    except ValueError:
        print_error(f"Unknown hook: {hook_name}")
        print_info(f"Available hooks: {', '.join(h.value for h in HookType.all())}")
        raise typer.Exit(1)

    # Check if already exists
    existing = manager.get_hook(hook_type)
    if existing and not force:
        print_error(f"Hook {hook_name} already exists. Use --force to overwrite.")
        raise typer.Exit(1)

    if script_path:
        # Install from file
        source = Path(script_path)
        if not source.exists():
            print_error(f"Script not found: {script_path}")
            raise typer.Exit(1)

        hook = manager.install_hook_from_file(hook_type, source)
        print_success(f"Installed {hook_name} hook from {script_path}")
    else:
        # Create sample hook
        sample = manager.create_sample_hook(hook_type)
        hook = manager.install_hook(hook_type, sample)
        print_success(f"Created sample {hook_name} hook")
        print_info(f"Edit at: {hook.path}")
        print_info("Make it executable with: chmod +x " + str(hook.path))


@app.command("uninstall")
def uninstall_hook(
    hook_name: str = typer.Argument(..., help="Name of the hook to uninstall"),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation",
    ),
) -> None:
    """Remove a hook script."""
    project_root = require_initialized()
    manager = HookManager(project_root)

    try:
        hook_type = HookType(hook_name)
    except ValueError:
        print_error(f"Unknown hook: {hook_name}")
        raise typer.Exit(1)

    hook = manager.get_hook(hook_type)
    if not hook:
        print_warning(f"Hook {hook_name} is not installed")
        return

    if not force:
        confirm = typer.confirm(f"Remove {hook_name} hook?")
        if not confirm:
            print_info("Cancelled")
            return

    manager.uninstall_hook(hook_type)
    print_success(f"Uninstalled {hook_name} hook")


@app.command("show")
def show_hook(
    hook_name: str = typer.Argument(..., help="Name of the hook to show"),
) -> None:
    """Display the contents of a hook script."""
    project_root = require_initialized()
    manager = HookManager(project_root)

    try:
        hook_type = HookType(hook_name)
    except ValueError:
        print_error(f"Unknown hook: {hook_name}")
        raise typer.Exit(1)

    hook = manager.get_hook(hook_type)
    if not hook:
        print_error(f"Hook {hook_name} is not installed")
        raise typer.Exit(1)

    from rich.syntax import Syntax

    console.print(f"[bold cyan]{hook_name} hook[/bold cyan]")
    console.print(f"Path: {hook.path}")
    console.print(f"Executable: {'Yes' if hook.is_executable else 'No'}")
    console.print(f"Modified: {hook.created_at}\n")

    # Try to detect language for syntax highlighting
    lang = "bash"
    if hook.content.strip().startswith("#!/usr/bin/env python") or hook.content.strip().startswith("#!/usr/bin/python"):
        lang = "python"

    syntax = Syntax(hook.content, lang, theme="monokai")
    console.print(syntax)


@app.command("run")
def run_hook(
    hook_name: str = typer.Argument(..., help="Name of the hook to run"),
    prompt: Optional[str] = typer.Option(
        None,
        "--prompt",
        "-p",
        help="Prompt name (sets PROMPT_NAME env var)",
    ),
    version: Optional[str] = typer.Option(
        None,
        "--version",
        "-v",
        help="Version number (sets VERSION_NUMBER env var)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Show what would be run without executing",
    ),
) -> None:
    """Manually run a hook script."""
    project_root = require_initialized()
    manager = HookManager(project_root)

    try:
        hook_type = HookType(hook_name)
    except ValueError:
        print_error(f"Unknown hook: {hook_name}")
        raise typer.Exit(1)

    hook = manager.get_hook(hook_type)
    if not hook:
        print_warning(f"Hook {hook_name} is not installed")
        return

    # Prepare environment variables
    env_vars = {}
    if prompt:
        env_vars["PROMPT_NAME"] = prompt
    if version:
        env_vars["VERSION_NUMBER"] = version

    if dry_run:
        print_info(f"Would run: {hook.path}")
        for key, value in env_vars.items():
            print_info(f"  {key}={value}")
        return

    # Run the hook
    result = manager.run_hook(hook_type, env_vars)

    if result.stdout:
        console.print("[bold]Output:[/bold]")
        console.print(result.stdout)

    if result.stderr:
        console.print("[bold red]Errors:[/bold red]")
        console.print(result.stderr)

    if result.success:
        print_success(result.message)
    else:
        print_error(result.message)
        raise typer.Exit(result.exit_code)


@app.command("edit")
def edit_hook(
    hook_name: str = typer.Argument(..., help="Name of the hook to edit"),
) -> None:
    """Open a hook script in your default editor."""
    project_root = require_initialized()
    manager = HookManager(project_root)

    try:
        hook_type = HookType(hook_name)
    except ValueError:
        print_error(f"Unknown hook: {hook_name}")
        raise typer.Exit(1)

    hook = manager.get_hook(hook_type)
    if not hook:
        print_error(f"Hook {hook_name} is not installed. Use 'pit hooks install {hook_name}' first.")
        raise typer.Exit(1)

    # Open in editor
    import subprocess
    import os

    editor = os.environ.get("EDITOR", "vi")

    try:
        subprocess.run([editor, str(hook.path)], check=True)
        print_success(f"Edited {hook_name} hook")
    except subprocess.CalledProcessError as e:
        print_error(f"Editor failed: {e}")
        raise typer.Exit(1)
    except FileNotFoundError:
        print_error(f"Editor not found: {editor}")
        print_info("Set the EDITOR environment variable to your preferred editor")
        raise typer.Exit(1)
