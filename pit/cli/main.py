"""Main CLI entry point for pit."""

import random
import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich import box

from pit import __version__
from pit.cli.commands.init import init_command
from pit.cli.commands import prompt as prompt_cmd
from pit.cli.commands import version as version_cmd
from pit.cli.commands import test as test_cmd
from pit.cli.commands import ab_test as ab_test_cmd
from pit.cli.commands import tree as tree_cmd
from pit.cli.commands import scan as scan_cmd
from pit.cli.commands import stats as stats_cmd
from pit.cli.commands import optimize as optimize_cmd
from pit.cli.commands import export_import as export_cmd
from pit.cli.commands import bisect as bisect_cmd
from pit.cli.commands import worktree as worktree_cmd
from pit.cli.commands import stash as stash_cmd
from pit.cli.commands import patch as patch_cmd
from pit.cli.commands import hooks as hooks_cmd
from pit.cli.commands import bundle as bundle_cmd
from pit.cli.commands import replay as replay_cmd
from pit.cli.commands import deps as deps_cmd

console = Console()

# Fun ASCII banner variants
BANNERS = [
    r"""
    ╔═══════════════════════════════════════╗
    ║  🕳️  PIT - Prompt Information Tracker ║
    ║     "Where prompts go to evolve"      ║
    ╚═══════════════════════════════════════╝
    """,
    r"""
     ____  _   _   ____  
    |  _ \| |_| |_|___ \ 
    | |_) | __| __|__) |
    |  __/| |_| |_| __/ 
    |_|    \__|\__|_____|
    Prompt Information Tracker
    """,
    r"""
    ┌─────────────────────────────┐
    │  🎯 PIT  │  Prompt Tracker  │
    └─────────────────────────────┘
    """,
]

# Fun messages to show on startup
FUN_MESSAGES = [
    "Where prompts go to evolve 🌱",
    "Version control that actually understands you 🧠",
    "Because Git doesn't speak 'prompt' 🗣️",
    "Track your prompts like a pro 📊",
    "Semantic versioning for the AI age 🤖",
    "Your prompts' time machine ⏰",
    "From chaos to organized brilliance ✨",
    "Prompt engineering, elevated 🚀",
    "The pit stop for great prompts 🏎️",
    "Where good prompts become great 🌟",
]

# Tips to show randomly
TIPS = [
    "💡 Tip: Use 'pit log --where \"success_rate > 0.9\"' to find your best versions",
    "💡 Tip: Run 'pit bisect' to find which version broke your prompt",
    "💡 Tip: Try 'pit optimize analyze' for AI-powered improvements",
    "💡 Tip: Use 'pit stash' to save work-in-progress changes",
    "💡 Tip: Create bundles with 'pit bundle create' to share prompts",
    "💡 Tip: Run 'pit replay' to test inputs across all versions",
    "💡 Tip: Use 'pit hooks install' to add git-style automation",
    "💡 Tip: Try 'pit ab-test' for statistically significant comparisons",
]


def get_banner() -> str:
    """Get a random banner."""
    return random.choice(BANNERS)


def get_fun_message() -> str:
    """Get a random fun message."""
    return random.choice(FUN_MESSAGES)


def get_tip() -> str:
    """Get a random tip."""
    return random.choice(TIPS)


def show_interactive_menu():
    """Show an interactive menu when no command is provided."""
    banner = get_banner()
    message = get_fun_message()
    tip = get_tip()

    # Show banner
    console.print(f"[bold cyan]{banner}[/bold cyan]")
    console.print(f"[italic]{message}[/italic]\n")

    # Create menu table
    table = Table(
        title="[bold green]Quick Actions[/bold green]",
        box=box.ROUNDED,
        show_header=False,
    )
    table.add_column("Command", style="cyan", no_wrap=True)
    table.add_column("Description", style="white")

    menu_items = [
        ("pit init", "Initialize a new PIT project"),
        ("pit add <file>", "Add a new prompt to track"),
        ("pit list", "List all tracked prompts"),
        ("pit commit <prompt>", "Save a new version"),
        ("pit log <prompt>", "View version history"),
        ("pit diff <prompt>", "Compare versions"),
        ("pit --help", "Show all available commands"),
    ]

    for cmd, desc in menu_items:
        table.add_row(cmd, desc)

    console.print(table)

    # Show tip in a panel
    console.print(Panel(
        tip,
        title="[yellow]Did you know?[/yellow]",
        border_style="yellow",
    ))

    console.print("\n[dim]Run 'pit --help' for all commands or 'pit <command> --help' for details[/dim]")


# Create main app
app = typer.Typer(
    name="pit",
    help="PIT - Prompt Information Tracker: Semantic versioning for LLM prompts",
    add_completion=False,
    no_args_is_help=False,  # We'll handle this ourselves for the menu
)

# Register prompt subcommand group
app.add_typer(prompt_cmd.app, name="prompt", help="Manage prompts")

# Register test subcommand group
app.add_typer(test_cmd.app, name="test", help="Test framework commands")

# Register tree subcommand group
app.add_typer(tree_cmd.app, name="tree", help="Composition tree commands")

# Register scan subcommand group
app.add_typer(scan_cmd.app, name="scan", help="Security scanning commands")

# Register stats subcommand group
app.add_typer(stats_cmd.app, name="stats", help="Analytics commands")

# Register optimize subcommand group
app.add_typer(optimize_cmd.app, name="optimize", help="Optimization commands")

# Register export/import subcommand group
app.add_typer(export_cmd.app, name="export", help="Export commands")
# Import is handled within the same app

# Register bisect subcommand group
app.add_typer(bisect_cmd.app, name="bisect", help="Binary search for bad versions")

# Register worktree subcommand group
app.add_typer(worktree_cmd.app, name="worktree", help="Manage multiple prompt contexts")

# Register stash subcommand group
app.add_typer(stash_cmd.app, name="stash", help="Stash and restore WIP changes")

# Register patch subcommand group
app.add_typer(patch_cmd.app, name="patch", help="Shareable patches for prompt changes")

# Register hooks subcommand group
app.add_typer(hooks_cmd.app, name="hooks", help="Manage git-style hooks")

# Register bundle subcommand group
app.add_typer(bundle_cmd.app, name="bundle", help="Package and share prompts")

# Register replay subcommand group
app.add_typer(replay_cmd.app, name="replay", help="Replay input across versions")

# Register deps subcommand group
app.add_typer(deps_cmd.app, name="deps", help="Manage external prompt dependencies")

# Register init as a direct command
app.command("init")(init_command)

# Also register prompt commands at top level for convenience
app.command("add")(prompt_cmd.add_prompt)
app.command("list")(prompt_cmd.list_prompts)
app.command("show")(prompt_cmd.show_prompt)
app.command("delete")(prompt_cmd.delete_prompt)

# Register version control commands at top level
app.command("commit")(version_cmd.commit_version)
app.command("log")(version_cmd.show_log)
app.command("diff")(version_cmd.show_diff)
app.command("checkout")(version_cmd.checkout_version)
app.command("tag")(version_cmd.manage_tags)

# Register Phase 4 commands at top level for convenience
app.command("ab-test")(ab_test_cmd.run)
app.command("optimize-cmd")(optimize_cmd.analyze)


@app.command("version")
def version() -> None:
    """Show the pit version."""
    banner = get_banner()
    console.print(f"[cyan]{banner}[/cyan]")
    console.print(f"[bold]Version:[/bold] {__version__}")
    console.print(f"[dim]{get_fun_message()}[/dim]")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    ver: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show version and exit",
    ),
    menu: bool = typer.Option(
        False,
        "--menu",
        "-m",
        help="Show interactive menu",
    ),
) -> None:
    """PIT - Prompt Information Tracker: Semantic versioning for LLM prompts."""
    if ver:
        banner = get_banner()
        console.print(f"[cyan]{banner}[/cyan]")
        console.print(f"[bold]Version:[/bold] {__version__}")
        console.print(f"[dim]{get_fun_message()}[/dim]")
        raise typer.Exit()

    # If no command provided, show interactive menu
    if ctx.invoked_subcommand is None or menu:
        show_interactive_menu()
        raise typer.Exit()


if __name__ == "__main__":
    app()
