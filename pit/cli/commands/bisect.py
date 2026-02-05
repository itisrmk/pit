"""Bisect commands for finding which version introduced a bug."""

from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table

from pit.config import find_project_root
from pit.core.bisect import BisectManager, BisectResult, BisectState
from pit.db.database import get_session
from pit.db.repository import VersionRepository
from pit.cli.formatters import console, print_error, print_info, print_success, print_warning

app = typer.Typer(
    name="bisect",
    help="Use binary search to find the version that introduced a bug",
    no_args_is_help=True,
)


def require_bisect_manager() -> BisectManager:
    """Get bisect manager for current project."""
    project_root = find_project_root()
    if project_root is None:
        print_error("Not a pit project. Run 'pit init' first.")
        raise typer.Exit(1)
    return BisectManager(project_root)


@app.command("start")
def bisect_start(
    failing_input: str = typer.Option(
        ...,
        "--failing-input",
        "-i",
        help="The input that triggers the bug",
    ),
    prompt: Optional[str] = typer.Option(
        None,
        "--prompt",
        "-p",
        help="Prompt to bisect (defaults to current if in worktree)",
    ),
) -> None:
    """Start a bisect session to find the first bad version."""
    manager = require_bisect_manager()

    if not prompt:
        print_error("Please specify a prompt: --prompt <name>")
        raise typer.Exit(1)

    with get_session(manager.project_root) as db_session:
        try:
            session = manager.start(db_session, prompt, failing_input)
            print_success(f"Started bisect session for prompt '{prompt}'")
            print_info(f"Failing input: {failing_input[:80]}...")
            print_info("")
            print_info("Next steps:")
            print_info("  1. Find a version where it works: pit bisect good <version>")
            print_info("  2. Find a version where it's broken: pit bisect bad <version>")
            print_info("")
            print_info("Or let PIT test automatically with:")
            print_info("  pit bisect run --command 'your-test-script'")
        except ValueError as e:
            print_error(str(e))
            raise typer.Exit(1)


@app.command("good")
def bisect_good(
    version: Optional[str] = typer.Argument(
        None,
        help="Version number (e.g., 'v1' or '1'). Uses current checkout if not specified.",
    ),
) -> None:
    """Mark a version as good (works correctly)."""
    manager = require_bisect_manager()

    # Parse version number
    version_num = None
    if version:
        version_str = version.lower().removeprefix("v")
        try:
            version_num = int(version_str)
        except ValueError:
            print_error(f"Invalid version: {version}")
            raise typer.Exit(1)

    with get_session(manager.project_root) as db_session:
        try:
            session = manager.mark_version(db_session, BisectResult.GOOD, version_num)

            if session.state == BisectState.COMPLETED:
                _show_completion(session, db_session)
            else:
                print_success(f"Marked version {session.good_version} as good")
                if session.current_version:
                    print_info(f"Testing version {session.current_version}...")
                    _show_version_info(session, db_session)
                else:
                    print_info("")
                    print_info("Mark a bad version with: pit bisect bad <version>")

        except ValueError as e:
            print_error(str(e))
            raise typer.Exit(1)


@app.command("bad")
def bisect_bad(
    version: Optional[str] = typer.Argument(
        None,
        help="Version number (e.g., 'v1' or '1'). Uses current checkout if not specified.",
    ),
) -> None:
    """Mark a version as bad (has the bug)."""
    manager = require_bisect_manager()

    # Parse version number
    version_num = None
    if version:
        version_str = version.lower().removeprefix("v")
        try:
            version_num = int(version_str)
        except ValueError:
            print_error(f"Invalid version: {version}")
            raise typer.Exit(1)

    with get_session(manager.project_root) as db_session:
        try:
            session = manager.mark_version(db_session, BisectResult.BAD, version_num)

            if session.state == BisectState.COMPLETED:
                _show_completion(session, db_session)
            else:
                print_success(f"Marked version {session.bad_version} as bad")
                if session.current_version:
                    print_info(f"Testing version {session.current_version}...")
                    _show_version_info(session, db_session)
                else:
                    print_info("")
                    print_info("Mark a good version with: pit bisect good <version>")

        except ValueError as e:
            print_error(str(e))
            raise typer.Exit(1)


@app.command("skip")
def bisect_skip(
    version: Optional[str] = typer.Argument(
        None,
        help="Version to skip (uses current if not specified)",
    ),
) -> None:
    """Skip testing a version (can't determine good/bad)."""
    manager = require_bisect_manager()

    version_num = None
    if version:
        version_str = version.lower().removeprefix("v")
        try:
            version_num = int(version_str)
        except ValueError:
            print_error(f"Invalid version: {version}")
            raise typer.Exit(1)

    with get_session(manager.project_root) as db_session:
        try:
            session = manager.mark_version(db_session, BisectResult.SKIP, version_num)
            print_info(f"Skipped version {version_num or session.current_version}")

            if session.current_version:
                print_info(f"Now testing version {session.current_version}...")
                _show_version_info(session, db_session)

        except ValueError as e:
            print_error(str(e))
            raise typer.Exit(1)


@app.command("run")
def bisect_run(
    command: str = typer.Option(
        ...,
        "--command",
        "-c",
        help="Command to test each version (exit 0 = good, non-zero = bad)",
    ),
) -> None:
    """Automatically test versions using a command."""
    import subprocess

    manager = require_bisect_manager()
    session = manager.get_session()

    if not session or session.state != BisectState.RUNNING:
        print_error("No active bisect session. Run 'bisect start' first.")
        raise typer.Exit(1)

    print_info("Running automated bisect...")
    print_info(f"Command: {command}")
    print_info("")

    with get_session(manager.project_root) as db_session:
        version_repo = VersionRepository(db_session)
        max_iterations = 50  # Safety limit

        for iteration in range(max_iterations):
            if session.state == BisectState.COMPLETED:
                break

            if session.current_version is None:
                print_error("Need at least one good and one bad version to continue")
                raise typer.Exit(1)

            version = version_repo.get_by_prompt_and_number(
                session.prompt_id, session.current_version
            )
            if not version:
                print_error(f"Version {session.current_version} not found")
                raise typer.Exit(1)

            print_info(f"Iteration {iteration + 1}: Testing version {session.current_version}")

            # Run test command
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                print_success(f"  Version {session.current_version}: GOOD")
                test_result = BisectResult.GOOD
            else:
                print_warning(f"  Version {session.current_version}: BAD")
                test_result = BisectResult.BAD

            session = manager.mark_version(db_session, test_result)

        if session.state == BisectState.COMPLETED:
            _show_completion(session, db_session)
        else:
            print_warning("Bisect did not complete (hit iteration limit)")


@app.command("reset")
def bisect_reset(
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation",
    ),
) -> None:
    """Reset/clear the current bisect session."""
    manager = require_bisect_manager()
    session = manager.get_session()

    if not session:
        print_info("No active bisect session")
        return

    if not force:
        confirm = typer.confirm("Are you sure you want to reset the bisect session?")
        if not confirm:
            print_info("Bisect session preserved")
            return

    manager.reset()
    print_success("Bisect session cleared")


@app.command("log")
def bisect_log() -> None:
    """Show current bisect session status."""
    manager = require_bisect_manager()
    session = manager.get_session()

    if not session:
        print_info("No active bisect session")
        return

    with get_session(manager.project_root) as db_session:
        if session.state == BisectState.COMPLETED:
            _show_completion(session, db_session)
        else:
            _show_session_status(session)
            if session.current_version:
                _show_version_info(session, db_session)


def _show_session_status(session) -> None:
    """Display current bisect session status."""
    table = Table(title="Bisect Session Status")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Prompt", session.prompt_name)
    table.add_row("Status", session.state.value)
    table.add_row("Failing Input", session.failing_input[:60] + "...")
    table.add_row("Good Version", str(session.good_version) if session.good_version else "-")
    table.add_row("Bad Version", str(session.bad_version) if session.bad_version else "-")
    table.add_row("Current Version", str(session.current_version) if session.current_version else "-")
    table.add_row("Tested", str(len(session.tested_versions)))

    if session.good_version and session.bad_version:
        remaining = session.bad_version - session.good_version - 1
        table.add_row("Remaining", str(remaining))

    console.print(table)


def _show_version_info(session, db_session) -> None:
    """Show details of version currently being tested."""
    if not session.current_version:
        return

    version_repo = VersionRepository(db_session)
    version = version_repo.get_by_prompt_and_number(
        session.prompt_id, session.current_version
    )

    if version:
        console.print(Panel(
            f"[bold]Version {version.version_number}[/bold]\n"
            f"Message: {version.message}\n"
            f"Created: {version.created_at}\n\n"
            f"[dim]Test this version with your failing input:[/dim]\n"
            f"[cyan]{session.failing_input[:100]}...[/cyan]",
            title="Current Version to Test",
            border_style="blue"
        ))


def _show_completion(session, db_session) -> None:
    """Show bisect completion results."""
    version_repo = VersionRepository(db_session)
    bad_version = version_repo.get_by_prompt_and_number(
        session.prompt_id, session.first_bad_version
    )
    good_version = version_repo.get_by_prompt_and_number(
        session.prompt_id, session.first_bad_version - 1
    ) if session.first_bad_version > 1 else None

    console.print(Panel(
        f"[bold green]Bisect Complete![/bold green]\n\n"
        f"First bad version: [bold]v{session.first_bad_version}[/bold]\n"
        f"Commit: {bad_version.message if bad_version else 'N/A'}\n"
        f"Date: {bad_version.created_at if bad_version else 'N/A'}\n\n"
        f"Tested {len(session.tested_versions)} versions",
        title="🎯 Result Found",
        border_style="green"
    ))

    if good_version and bad_version:
        console.print("\n[bold]Changes in this version:[/bold]")
        # Show diff summary
        good_preview = good_version.content[:200].replace("\n", " ")
        bad_preview = bad_version.content[:200].replace("\n", " ")
        console.print(f"  Before: {good_preview}...")
        console.print(f"  After:  {bad_preview}...")
