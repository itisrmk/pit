"""Rich formatting utilities for CLI output."""

from datetime import datetime
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.text import Text

from pit.db.models import Prompt, Version

console = Console()


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[green]{message}[/green]")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[red]Error:[/red] {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[yellow]Warning:[/yellow] {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(f"[blue]{message}[/blue]")


def format_datetime(dt: datetime) -> str:
    """Format a datetime for display."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def format_tags(tags: list[str]) -> str:
    """Format tags for display."""
    if not tags:
        return "[dim]none[/dim]"
    return " ".join(f"[cyan]{tag}[/cyan]" for tag in tags)


def print_prompt_table(prompts: list[Prompt]) -> None:
    """Print a table of prompts."""
    if not prompts:
        print_info("No prompts found. Use 'pit add <name>' to create one.")
        return

    table = Table(title="Prompts", show_header=True, header_style="bold")
    table.add_column("Name", style="cyan")
    table.add_column("Version", justify="center")
    table.add_column("Description")
    table.add_column("Updated", style="dim")

    for prompt in prompts:
        version = f"v{prompt.current_version.version_number}" if prompt.current_version else "-"
        description = (prompt.description or "")[:50]
        if prompt.description and len(prompt.description) > 50:
            description += "..."
        table.add_row(
            prompt.name,
            version,
            description or "[dim]No description[/dim]",
            format_datetime(prompt.updated_at),
        )

    console.print(table)


def print_prompt_detail(prompt: Prompt, version: Optional[Version] = None) -> None:
    """Print detailed information about a prompt."""
    if version is None:
        version = prompt.current_version

    # Header
    console.print()
    console.print(f"[bold cyan]{prompt.name}[/bold cyan]")
    console.print(f"[dim]ID: {prompt.id}[/dim]")

    if prompt.description:
        console.print(f"\n{prompt.description}")

    console.print()

    # Version info
    if version:
        console.print(f"[bold]Version:[/bold] v{version.version_number}")
        console.print(f"[bold]Message:[/bold] {version.message}")
        if version.author:
            console.print(f"[bold]Author:[/bold] {version.author}")
        console.print(f"[bold]Tags:[/bold] {format_tags(version.tags)}")
        console.print(f"[bold]Created:[/bold] {format_datetime(version.created_at)}")

        if version.variables:
            console.print(f"[bold]Variables:[/bold] {', '.join(version.variables)}")

        console.print()
        console.print("[bold]Content:[/bold]")
        console.print(Panel(version.content, border_style="dim"))
    else:
        print_warning("No versions yet. Use 'pit commit' to create the first version.")


def print_version_list(versions: list[Version]) -> None:
    """Print a list of versions."""
    if not versions:
        print_info("No versions found.")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Version", style="cyan", justify="center")
    table.add_column("Message")
    table.add_column("Tags")
    table.add_column("Author")
    table.add_column("Created", style="dim")

    for version in versions:
        table.add_row(
            f"v{version.version_number}",
            version.message[:60] + ("..." if len(version.message) > 60 else ""),
            format_tags(version.tags),
            version.author or "[dim]-[/dim]",
            format_datetime(version.created_at),
        )

    console.print(table)


def print_version_detail(version: Version) -> None:
    """Print detailed version information."""
    console.print()
    console.print(f"[bold cyan]Version v{version.version_number}[/bold cyan]")
    console.print(f"[dim]ID: {version.id}[/dim]")
    console.print()
    console.print(f"[bold]Message:[/bold] {version.message}")
    if version.author:
        console.print(f"[bold]Author:[/bold] {version.author}")
    console.print(f"[bold]Tags:[/bold] {format_tags(version.tags)}")
    console.print(f"[bold]Created:[/bold] {format_datetime(version.created_at)}")

    if version.variables:
        console.print(f"[bold]Variables:[/bold] {', '.join(version.variables)}")

    console.print()
    console.print("[bold]Content:[/bold]")
    console.print(Panel(version.content, border_style="dim"))


def print_diff(
    old_content: str,
    new_content: str,
    old_label: str = "old",
    new_label: str = "new",
) -> None:
    """Print a unified diff between two contents."""
    import difflib

    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=old_label,
        tofile=new_label,
    )

    diff_text = "".join(diff)
    if diff_text:
        syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=False)
        console.print(syntax)
    else:
        print_info("No differences found.")
