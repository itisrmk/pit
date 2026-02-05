"""Version control commands - commit, log, diff, checkout, tag."""

from pathlib import Path
from typing import Optional

import typer
from rich.syntax import Syntax
from rich.panel import Panel

from pit.config import Config, find_project_root, is_initialized
from pit.db.database import get_session
from pit.db.repository import PromptRepository, VersionRepository
from pit.cli.formatters import (
    console,
    print_error,
    print_info,
    print_prompt_detail,
    print_success,
    print_warning,
    print_version_list,
    print_version_detail,
    format_tags,
    format_datetime,
)
from pit.core.semantic_diff import SemanticDiffAnalyzer
from pit.db.models import Version

app = typer.Typer()


def require_initialized() -> Path:
    """Ensure pit is initialized and return project root."""
    project_root = find_project_root()
    if project_root is None:
        print_error("Not a pit project. Run 'pit init' first.")
        raise typer.Exit(1)
    return project_root


@app.command("commit")
def commit_version(
    name: str = typer.Argument(..., help="Name of the prompt"),
    message: str = typer.Option(
        ...,
        "--message",
        "-m",
        help="Commit message describing the change",
    ),
    content: Optional[str] = typer.Option(
        None,
        "--content",
        "-c",
        help="New prompt content (opens editor if not provided)",
    ),
    semantic: bool = typer.Option(
        True,
        "--semantic/--no-semantic",
        help="Generate semantic diff using LLM (if configured)",
    ),
) -> None:
    """Save a new version of a prompt.
    
    Creates a new version with the given content and commit message.
    If semantic analysis is enabled and an LLM provider is configured,
    automatically generates a semantic diff describing the changes.
    """
    project_root = require_initialized()
    config = Config.load(project_root)

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        version_repo = VersionRepository(session)

        prompt = prompt_repo.get_by_name(name)
        if not prompt:
            print_error(f"Prompt '{name}' not found")
            raise typer.Exit(1)

        # Get content interactively if not provided
        if content is None:
            console.print("\n[bold]Enter prompt content[/bold] (Ctrl+D when done):")
            lines = []
            try:
                while True:
                    line = input()
                    lines.append(line)
            except EOFError:
                pass
            content = "\n".join(lines)

        content = content.strip()
        if not content:
            print_error("No content provided")
            raise typer.Exit(1)

        # Generate semantic diff if enabled and configured
        semantic_diff = None
        if semantic and config.llm.provider:
            current_version = prompt.current_version
            if current_version:
                try:
                    analyzer = SemanticDiffAnalyzer(config.llm)
                    semantic_diff = analyzer.analyze_diff(
                        old_prompt=current_version.content,
                        new_prompt=content,
                    )
                    print_info("Generated semantic diff")
                except Exception as e:
                    print_warning(f"Could not generate semantic diff: {e}")

        # Create new version
        version = version_repo.create(
            prompt_id=prompt.id,
            content=content,
            message=message,
            author=config.project.default_author,
        )

        # Store semantic diff if generated
        if semantic_diff:
            version_repo.update_semantic_diff(version, semantic_diff)

        print_success(f"Created version v{version.version_number}")


@app.command("log")
def show_log(
    name: str = typer.Argument(..., help="Name of the prompt"),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-n",
        help="Limit number of versions shown",
    ),
    where: Optional[str] = typer.Option(
        None,
        "--where",
        "-w",
        help="Query filter (e.g., 'success_rate >= 0.9', 'tags contains production')",
    ),
) -> None:
    """Show version history for a prompt.

    Displays all versions in a table with version number, message,
    author, date, and tags.

    Query syntax:
    - Field operators: >, <, >=, <=, =, !=, contains
    - Boolean: AND, OR
    - Examples:
      - success_rate >= 0.9
      - avg_latency_ms < 500
      - tags contains 'production'
      - content contains 'be concise'
      - created_at > '2024-01-01'
    """
    project_root = require_initialized()

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        version_repo = VersionRepository(session)

        prompt = prompt_repo.get_by_name(name)
        if not prompt:
            print_error(f"Prompt '{name}' not found")
            raise typer.Exit(1)

        versions = version_repo.list_by_prompt(prompt.id)

        # Apply query filter if provided
        if where:
            from pit.core.query import QueryParser, QueryExecutor
            parser = QueryParser()
            query = parser.parse(where)
            executor = QueryExecutor(versions)
            versions = executor.execute(query)

        if limit is not None:
            versions = versions[:limit]

        console.print(f"\n[bold cyan]Version history for '{name}':[/bold cyan]")
        if where:
            console.print(f"[dim]Filter: {where}[/dim]")
        print_version_list(versions)
        console.print(f"\n[dim]Total: {len(versions)} version(s)[/dim]")


@app.command("diff")
def show_diff(
    name: str = typer.Argument(..., help="Name of the prompt"),
    v1: str = typer.Argument(..., help="First version number (e.g., '1' or 'v1')"),
    v2: str = typer.Argument(..., help="Second version number (e.g., '2' or 'v2')"),
    semantic: bool = typer.Option(
        False,
        "--semantic",
        "-s",
        help="Show semantic diff instead of text diff",
    ),
) -> None:
    """Compare two versions of a prompt.
    
    By default, shows a unified text diff. With --semantic, shows
    the semantic analysis of changes (if available).
    """
    import difflib
    
    project_root = require_initialized()

    # Parse version numbers (handle both "1" and "v1")
    v1_num = int(v1.lower().lstrip('v'))
    v2_num = int(v2.lower().lstrip('v'))

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        version_repo = VersionRepository(session)

        prompt = prompt_repo.get_by_name(name)
        if not prompt:
            print_error(f"Prompt '{name}' not found")
            raise typer.Exit(1)

        version1 = version_repo.get_by_number(prompt.id, v1_num)
        version2 = version_repo.get_by_number(prompt.id, v2_num)

        if not version1:
            print_error(f"Version v{v1_num} not found")
            raise typer.Exit(1)
        if not version2:
            print_error(f"Version v{v2_num} not found")
            raise typer.Exit(1)

        if semantic:
            _show_semantic_diff(version2, v1_num, v2_num)
        else:
            _show_text_diff(version1, version2, v1_num, v2_num)


def _show_text_diff(
    version1: Version,
    version2: Version,
    v1_num: int,
    v2_num: int,
) -> None:
    """Display a unified text diff between two versions."""
    import difflib
    
    old_lines = version1.content.splitlines(keepends=True)
    new_lines = version2.content.splitlines(keepends=True)

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"v{v1_num}",
        tofile=f"v{v2_num}",
    )

    diff_text = "".join(diff)
    
    console.print(f"\n[bold cyan]Diff between v{v1_num} and v{v2_num}:[/bold cyan]")
    
    if diff_text:
        syntax = Syntax(diff_text, "diff", theme="monokai", line_numbers=False)
        console.print(syntax)
    else:
        print_info("No differences found.")


def _show_semantic_diff(
    version: Version,
    v1_num: int,
    v2_num: int,
) -> None:
    """Display semantic diff for a version."""
    from rich.table import Table
    
    console.print(f"\n[bold cyan]Semantic diff between v{v1_num} and v{v2_num}:[/bold cyan]")
    
    if not version.semantic_diff:
        print_info("No semantic diff available for this version.")
        print_info("Use 'pit commit' with semantic analysis enabled to generate one.")
        return

    semantic = version.semantic_diff
    
    # Summary
    if "summary" in semantic:
        console.print(Panel(
            semantic["summary"],
            title="Summary",
            border_style="blue",
        ))

    # Changes by category
    categories = {
        "intent_changes": ("Intent Changes", "yellow"),
        "scope_changes": ("Scope Changes", "green"),
        "constraint_changes": ("Constraint Changes", "red"),
        "tone_changes": ("Tone Changes", "magenta"),
        "structure_changes": ("Structure Changes", "cyan"),
    }

    for key, (title, color) in categories.items():
        changes = semantic.get(key, [])
        if changes:
            console.print(f"\n[bold {color}]{title}:[/bold {color}]")
            for change in changes:
                if isinstance(change, dict):
                    desc = change.get("description", str(change))
                    severity = change.get("severity", "medium")
                    console.print(f"  • {desc} [dim]({severity})[/dim]")
                else:
                    console.print(f"  • {change}")

    # Breaking changes warning
    if semantic.get("breaking_changes"):
        console.print("\n[bold red]⚠ Breaking Changes Detected![/bold red]")
        for change in semantic["breaking_changes"]:
            console.print(f"  • {change}")


@app.command("checkout")
def checkout_version(
    name: str = typer.Argument(..., help="Name of the prompt"),
    version_number: str = typer.Argument(..., help="Version number (e.g., '1' or 'v1')"),
) -> None:
    """View a specific version of a prompt.
    
    Displays the content and metadata for a specific version.
    """
    project_root = require_initialized()

    # Parse version number
    v_num = int(version_number.lower().lstrip('v'))

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        version_repo = VersionRepository(session)

        prompt = prompt_repo.get_by_name(name)
        if not prompt:
            print_error(f"Prompt '{name}' not found")
            raise typer.Exit(1)

        version = version_repo.get_by_number(prompt.id, v_num)
        if not version:
            print_error(f"Version v{v_num} not found for prompt '{name}'")
            raise typer.Exit(1)

        console.print(f"\n[bold cyan]Prompt: {name}[/bold cyan]")
        print_version_detail(version)


@app.command("tag")
def manage_tags(
    name: str = typer.Argument(..., help="Name of the prompt"),
    version_number: Optional[str] = typer.Argument(
        None,
        help="Version number (e.g., '1' or 'v1')",
    ),
    tag: Optional[str] = typer.Argument(
        None,
        help="Tag to add or remove",
    ),
    remove: bool = typer.Option(
        False,
        "--remove",
        "-r",
        help="Remove the tag instead of adding it",
    ),
    list_tags: bool = typer.Option(
        False,
        "--list",
        "-l",
        help="List all tags for the version",
    ),
) -> None:
    """Manage tags for prompt versions.
    
    Add, remove, or list tags for a specific version:
    
    - Add tag: pit tag <prompt> <version> <tag>
    - Remove tag: pit tag <prompt> <version> <tag> --remove
    - List tags: pit tag <prompt> <version> --list
    """
    project_root = require_initialized()

    # Parse version number
    if version_number is None:
        print_error("Version number is required")
        raise typer.Exit(1)
    
    v_num = int(version_number.lower().lstrip('v'))

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        version_repo = VersionRepository(session)

        prompt = prompt_repo.get_by_name(name)
        if not prompt:
            print_error(f"Prompt '{name}' not found")
            raise typer.Exit(1)

        version = version_repo.get_by_number(prompt.id, v_num)
        if not version:
            print_error(f"Version v{v_num} not found for prompt '{name}'")
            raise typer.Exit(1)

        if list_tags or tag is None:
            # List tags
            console.print(f"\n[bold cyan]Tags for {name} v{v_num}:[/bold cyan]")
            if version.tags:
                for t in version.tags:
                    console.print(f"  [cyan]• {t}[/cyan]")
            else:
                print_info("No tags")
        elif remove:
            # Remove tag
            if tag not in version.tags:
                print_warning(f"Tag '{tag}' not found on this version")
                raise typer.Exit(1)
            version_repo.remove_tag(version, tag)
            print_success(f"Removed tag '{tag}' from v{v_num}")
        else:
            # Add tag
            if tag in version.tags:
                print_warning(f"Tag '{tag}' already exists on this version")
                raise typer.Exit(1)
            version_repo.add_tag(version, tag)
            print_success(f"Added tag '{tag}' to v{v_num}")
