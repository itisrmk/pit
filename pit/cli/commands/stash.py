"""Stash commands for saving and restoring WIP prompt changes."""

from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table

from pit.config import find_project_root
from pit.core.stash import StashManager
from pit.db.database import get_session
from pit.db.repository import PromptRepository, VersionRepository
from pit.cli.formatters import console, print_error, print_info, print_success, print_warning

app = typer.Typer(
    name="stash",
    help="Stash and restore WIP prompt changes",
    no_args_is_help=True,
)


def require_stash_manager() -> StashManager:
    """Get stash manager for current project."""
    project_root = find_project_root()
    if project_root is None:
        print_error("Not a pit project. Run 'pit init' first.")
        raise typer.Exit(1)
    return StashManager(project_root)


@app.command("save")
def stash_save(
    message: str = typer.Argument(..., help="Description of the stashed changes"),
    prompt: Optional[str] = typer.Option(
        None,
        "--prompt",
        "-p",
        help="Prompt to stash (defaults to current checkout)",
    ),
    with_test: Optional[Path] = typer.Option(
        None,
        "--with-test",
        "-t",
        help="Associate a test case file with this stash",
    ),
    with_input: Optional[str] = typer.Option(
        None,
        "--with-input",
        "-i",
        help="Associate test input string with this stash",
    ),
) -> None:
    """Save current prompt state to stash."""
    manager = require_stash_manager()

    with get_session(manager.project_root) as db_session:
        prompt_repo = PromptRepository(db_session)
        version_repo = VersionRepository(db_session)

        # Find prompt
        if prompt:
            prompt_obj = prompt_repo.get_by_name(prompt)
        else:
            # TODO: Detect from current checkout
            print_error("Please specify a prompt with --prompt")
            raise typer.Exit(1)

        if not prompt_obj:
            print_error(f"Prompt '{prompt}' not found")
            raise typer.Exit(1)

        # Get current content
        if prompt_obj.current_version:
            content = prompt_obj.current_version.content
        else:
            print_error(f"Prompt '{prompt}' has no versions")
            raise typer.Exit(1)

        # Get test input
        test_input = None
        if with_test:
            if not with_test.exists():
                print_error(f"Test file not found: {with_test}")
                raise typer.Exit(1)
            test_input = with_test.read_text()
        elif with_input:
            test_input = with_input

        # Save stash
        stash_manager = StashManager(manager.project_root)
        entry = stash_manager.save_stash(
            prompt_name=prompt_obj.name,
            prompt_id=prompt_obj.id,
            content=content,
            message=message,
            test_input=test_input,
        )

        print_success(f"Stashed changes: {message}")
        print_info(f"Stash index: stash@{{{entry.index}}}")
        if test_input:
            print_info(f"Associated test: {test_input[:60]}...")


@app.command("list")
def stash_list() -> None:
    """List all stashed changes."""
    manager = require_stash_manager()
    stash_manager = StashManager(manager.project_root)
    entries = stash_manager.list_stashes()

    if not entries:
        print_info("No stashes. Save with: pit stash save \"message\"")
        return

    table = Table(title="Stash Stack")
    table.add_column("Index", style="cyan", justify="right")
    table.add_column("Prompt", style="green")
    table.add_column("Message", style="white")
    table.add_column("Hash", style="dim")
    table.add_column("Created", style="dim")

    for entry in entries:
        created = entry.created_at[:16] if entry.created_at else "?"
        has_test = "📎" if entry.test_input else ""
        table.add_row(
            f"stash@{{{entry.index}}}",
            entry.prompt_name,
            f"{entry.message} {has_test}",
            entry.content_hash[:8],
            created,
        )

    console.print(table)
    print_info(f"\nTotal: {len(entries)} stash(es)")
    print_info("Use 'stash pop' to restore the top stash")


@app.command("pop")
def stash_pop(
    index: Optional[int] = typer.Argument(
        None,
        help="Stash index to pop (default: 0 = top of stack)",
    ),
    restore_test: bool = typer.Option(
        True,
        "--restore-test/--no-restore-test",
        help="Restore associated test case to a file",
    ),
) -> None:
    """Restore and remove a stash (default: top of stack)."""
    manager = require_stash_manager()
    stash_manager = StashManager(manager.project_root)

    index = index or 0

    entry = stash_manager.pop_stash(index)
    if not entry:
        print_error(f"No stash at index stash@{{{index}}}")
        raise typer.Exit(1)

    # Apply the stash content (create new version)
    with get_session(manager.project_root) as db_session:
        prompt_repo = PromptRepository(db_session)
        version_repo = VersionRepository(db_session)

        prompt_obj = prompt_repo.get_by_id(entry.prompt_id)
        if not prompt_obj:
            print_error(f"Prompt '{entry.prompt_name}' no longer exists")
            raise typer.Exit(1)

        # Create new version from stash
        new_version = version_repo.create(
            prompt_id=prompt_obj.id,
            content=entry.content,
            message=f"Restored from stash: {entry.message}",
        )

        print_success(f"Restored stash@{{{index}}}: {entry.message}")
        print_info(f"Created version v{new_version.version_number}")

        if entry.test_input and restore_test:
            test_file = Path.cwd() / f"stash_test_{entry.index}.txt"
            test_file.write_text(entry.test_input)
            print_info(f"Restored test case to: {test_file}")


@app.command("apply")
def stash_apply(
    index: Optional[int] = typer.Argument(
        None,
        help="Stash index to apply (default: 0 = top of stack)",
    ),
) -> None:
    """Apply a stash without removing it."""
    manager = require_stash_manager()
    stash_manager = StashManager(manager.project_root)

    index = index or 0

    entry = stash_manager.apply_stash(index)
    if not entry:
        print_error(f"No stash at index stash@{{{index}}}")
        raise typer.Exit(1)

    # Apply the stash content (create new version)
    with get_session(manager.project_root) as db_session:
        prompt_repo = PromptRepository(db_session)
        version_repo = VersionRepository(db_session)

        prompt_obj = prompt_repo.get_by_id(entry.prompt_id)
        if not prompt_obj:
            print_error(f"Prompt '{entry.prompt_name}' no longer exists")
            raise typer.Exit(1)

        new_version = version_repo.create(
            prompt_id=prompt_obj.id,
            content=entry.content,
            message=f"Applied from stash: {entry.message}",
        )

        print_success(f"Applied stash@{{{index}}}: {entry.message}")
        print_info(f"Created version v{new_version.version_number}")
        print_info("Stash preserved. Use 'stash drop' to remove it.")


@app.command("drop")
def stash_drop(
    index: Optional[int] = typer.Argument(
        None,
        help="Stash index to drop (default: 0 = top of stack)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation",
    ),
) -> None:
    """Remove a stash without applying."""
    manager = require_stash_manager()
    stash_manager = StashManager(manager.project_root)

    index = index or 0

    entry = stash_manager.apply_stash(index)
    if not entry:
        print_error(f"No stash at index stash@{{{index}}}")
        raise typer.Exit(1)

    if not force:
        confirm = typer.confirm(f"Drop stash@{{{index}}}: {entry.message}?")
        if not confirm:
            print_info("Aborted")
            return

    if stash_manager.drop_stash(index):
        print_success(f"Dropped stash@{{{index}}}")
    else:
        print_error("Failed to drop stash")
        raise typer.Exit(1)


@app.command("clear")
def stash_clear(
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation",
    ),
) -> None:
    """Remove all stashes."""
    manager = require_stash_manager()
    stash_manager = StashManager(manager.project_root)

    count = stash_manager.get_stash_count()
    if count == 0:
        print_info("No stashes to clear")
        return

    if not force:
        confirm = typer.confirm(f"Clear all {count} stash(es)? This cannot be undone.")
        if not confirm:
            print_info("Aborted")
            return

    cleared = stash_manager.clear_all()
    print_success(f"Cleared {cleared} stash(es)")


@app.command("show")
def stash_show(
    index: Optional[int] = typer.Argument(
        None,
        help="Stash index to show (default: 0 = top of stack)",
    ),
) -> None:
    """Show details of a stash."""
    manager = require_stash_manager()
    stash_manager = StashManager(manager.project_root)

    index = index or 0

    entry = stash_manager.show_stash(index)
    if not entry:
        print_error(f"No stash at index stash@{{{index}}}")
        raise typer.Exit(1)

    has_test = "✓" if entry.test_input else "✗"
    test_preview = ""
    if entry.test_input:
        test_preview = f"\n[dim]Test Input:[/dim]\n{entry.test_input[:200]}..."

    console.print(Panel(
        f"[bold]Prompt:[/bold] {entry.prompt_name}\n"
        f"[bold]Message:[/bold] {entry.message}\n"
        f"[bold]Created:[/bold] {entry.created_at}\n"
        f"[bold]Content Hash:[/bold] {entry.content_hash}\n"
        f"[bold]Has Test Case:[/bold] {has_test}"
        f"{test_preview}",
        title=f"Stash stash@{{{index}}}",
        border_style="blue"
    ))

    # Show content preview
    content_preview = entry.content[:500] if entry.content else "(empty)"
    console.print(Panel(
        content_preview + "...",
        title="Content Preview",
        border_style="dim"
    ))
