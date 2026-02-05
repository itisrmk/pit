"""Worktree commands for multiple prompt contexts."""

from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table

from pit.config import find_project_root
from pit.core.worktree import WorktreeManager
from pit.db.database import get_session
from pit.db.repository import PromptRepository, VersionRepository
from pit.cli.formatters import console, print_error, print_info, print_success, print_warning

app = typer.Typer(
    name="worktree",
    help="Manage multiple prompt contexts (worktrees)",
    no_args_is_help=True,
)


def require_worktree_manager() -> WorktreeManager:
    """Get worktree manager for current project."""
    project_root = find_project_root()
    if project_root is None:
        print_error("Not a pit project. Run 'pit init' first.")
        raise typer.Exit(1)
    return WorktreeManager(project_root)


@app.command("add")
def worktree_add(
    path: str = typer.Argument(..., help="Path for the new worktree"),
    prompt: str = typer.Argument(..., help="Prompt name (optionally with @version)"),
) -> None:
    """Create a new worktree with an independent prompt context."""
    manager = require_worktree_manager()

    # Parse prompt[@version]
    if "@" in prompt:
        prompt_name, version_str = prompt.split("@", 1)
        version_str = version_str.lower().removeprefix("v")
        try:
            version = int(version_str)
        except ValueError:
            print_error(f"Invalid version: {version_str}")
            raise typer.Exit(1)
    else:
        prompt_name = prompt
        version = None

    path_obj = Path(path).expanduser().resolve()

    with get_session(manager.project_root) as db_session:
        # Find prompt
        prompt_repo = PromptRepository(db_session)
        prompt_obj = prompt_repo.get_by_name(prompt_name)
        if not prompt_obj:
            print_error(f"Prompt '{prompt_name}' not found")
            raise typer.Exit(1)

        # Validate version if specified
        if version is not None:
            version_repo = VersionRepository(db_session)
            v = version_repo.get_by_number(prompt_obj.id, version)
            if not v:
                print_error(f"Version {version} not found for prompt '{prompt_name}'")
                raise typer.Exit(1)

        try:
            worktree = manager.create_worktree(
                path_obj, prompt_name, prompt_obj.id, version
            )

            # Write the prompt content to the worktree
            content_path = manager.get_prompt_content_path(path_obj, prompt_name)
            if version:
                v = version_repo.get_by_number(prompt_obj.id, version)
                content = v.content if v else ""
            else:
                # Use current version
                if prompt_obj.current_version:
                    content = prompt_obj.current_version.content
                else:
                    content = ""

            content_path.write_text(content)

            print_success(f"Created worktree at {path}")
            print_info(f"Prompt: {prompt_name}")
            if version:
                print_info(f"Version: v{version}")
            else:
                print_info("Version: current (HEAD)")
            print_info("")
            print_info(f"Edit: {content_path}")
            print_info("Commit changes with: pit commit (from within worktree)")

        except ValueError as e:
            print_error(str(e))
            raise typer.Exit(1)


@app.command("list")
def worktree_list() -> None:
    """List all worktrees."""
    manager = require_worktree_manager()
    worktrees = manager.list_worktrees()

    if not worktrees:
        print_info("No worktrees. Create one with: pit worktree add <path> <prompt>")
        return

    table = Table(title="Prompt Worktrees")
    table.add_column("Path", style="cyan")
    table.add_column("Prompt", style="green")
    table.add_column("Version", style="yellow")
    table.add_column("Created", style="dim")

    for wt in worktrees:
        version_str = f"v{wt.checked_out_version}" if wt.checked_out_version else "HEAD"
        created = wt.created_at[:10] if wt.created_at else "?"
        table.add_row(
            wt.path.replace(str(Path.home()), "~"),
            wt.prompt_name,
            version_str,
            created,
        )

    console.print(table)
    print_info(f"\nTotal: {len(worktrees)} worktree(s)")


@app.command("remove")
def worktree_remove(
    path: str = typer.Argument(..., help="Path of worktree to remove"),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Remove even if worktree has uncommitted changes",
    ),
) -> None:
    """Remove a worktree."""
    manager = require_worktree_manager()
    path_obj = Path(path).expanduser().resolve()

    try:
        manager.remove_worktree(path_obj, force=force)
        print_success(f"Removed worktree: {path}")
    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(1)


@app.command("prune")
def worktree_prune(
    days: int = typer.Option(
        30,
        "--days",
        "-d",
        help="Remove worktrees unused for this many days",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Show what would be removed without removing",
    ),
) -> None:
    """Remove stale worktrees that haven't been used recently."""
    manager = require_worktree_manager()

    if dry_run:
        # Just list what would be removed
        worktrees = manager.list_worktrees()
        from datetime import datetime, timedelta
        cutoff = datetime.now() - timedelta(days=days)
        stale = []
        for wt in worktrees:
            last_used = datetime.fromisoformat(wt.last_used or wt.created_at)
            if last_used < cutoff:
                stale.append(wt)

        if stale:
            print_info(f"Would remove {len(stale)} worktree(s) unused for {days}+ days:")
            for wt in stale:
                print_info(f"  {wt.path}")
        else:
            print_info(f"No worktrees unused for {days}+ days")
        return

    removed = manager.prune_stale(days=days)
    if removed:
        print_success(f"Removed {len(removed)} stale worktree(s)")
        for wt in removed:
            print_info(f"  {wt.path}")
    else:
        print_info(f"No worktrees unused for {days}+ days")


@app.command("info")
def worktree_info(
    path: Optional[str] = typer.Argument(
        None,
        help="Worktree path (defaults to current directory)",
    ),
) -> None:
    """Show information about a worktree."""
    manager = require_worktree_manager()

    if path:
        path_obj = Path(path).expanduser().resolve()
    else:
        path_obj = Path.cwd()

    worktree = manager.get_worktree(path_obj)
    if not worktree:
        print_error(f"Not a pit worktree: {path_obj}")
        raise typer.Exit(1)

    with get_session(manager.project_root) as db_session:
        prompt_repo = PromptRepository(db_session)
        prompt = prompt_repo.get_by_id(worktree.prompt_id)

        version_str = f"v{worktree.checked_out_version}" if worktree.checked_out_version else "HEAD (current)"
        content_path = manager.get_prompt_content_path(path_obj, worktree.prompt_name)

        console.print(Panel(
            f"[bold]Prompt:[/bold] {worktree.prompt_name}\n"
            f"[bold]Version:[/bold] {version_str}\n"
            f"[bold]Path:[/bold] {worktree.path}\n"
            f"[bold]Prompt File:[/bold] {content_path}\n"
            f"[bold]Created:[/bold] {worktree.created_at}\n"
            f"[bold]Last Used:[/bold] {worktree.last_used or 'Never'}",
            title="Worktree Information",
            border_style="blue"
        ))

        if prompt:
            current_v = prompt.current_version.version_number if prompt.current_version else None
            if current_v and worktree.checked_out_version != current_v:
                print_warning(
                    f"This worktree is on v{worktree.checked_out_version}, "
                    f"but prompt HEAD is now v{current_v}"
                )
