"""Replay commands for time-travel across versions."""

from pathlib import Path
from typing import List, Optional

import typer
from rich.table import Table

from pit.config import find_project_root, is_initialized
from pit.cli.formatters import console, print_error, print_success, print_info, print_warning
from pit.core.replay import ReplayEngine, ReplayCache

app = typer.Typer()


def require_initialized() -> Path:
    """Ensure pit is initialized and return project root."""
    project_root = find_project_root()
    if project_root is None:
        print_error("Not a pit project. Run 'pit init' first.")
        raise typer.Exit(1)
    return project_root


@app.command("run")
def replay_run(
    prompt_name: str = typer.Argument(..., help="Name of the prompt"),
    input_text: Optional[str] = typer.Option(
        None,
        "--input",
        "-i",
        help="Input text to replay",
    ),
    input_file: Optional[str] = typer.Option(
        None,
        "--input-file",
        "-f",
        help="File containing input text",
    ),
    versions: Optional[str] = typer.Option(
        None,
        "--versions",
        "-v",
        help="Version range (e.g., '1-5' or '1,2,3')",
    ),
    all_versions: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Replay on all versions",
    ),
    no_cache: bool = typer.Option(
        False,
        "--no-cache",
        help="Skip cache and re-run all",
    ),
    compare: bool = typer.Option(
        False,
        "--compare",
        "-c",
        help="Show side-by-side comparison",
    ),
) -> None:
    """Replay input across prompt versions.

    Runs the same input through multiple versions of a prompt
    and compares the outputs, latency, and token usage.
    """
    project_root = require_initialized()
    engine = ReplayEngine(project_root)

    # Get input
    if input_file:
        input_text = Path(input_file).read_text()
    elif not input_text:
        print_error("Provide input with --input or --input-file")
        raise typer.Exit(1)

    # Determine versions
    from pit.db.database import get_session
    from pit.db.repository import PromptRepository, VersionRepository

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        version_repo = VersionRepository(session)

        prompt = prompt_repo.get_by_name(prompt_name)
        if not prompt:
            print_error(f"Prompt '{prompt_name}' not found")
            raise typer.Exit(1)

        all_vers = version_repo.list_by_prompt(prompt.id)
        all_version_nums = [v.version_number for v in all_vers]

        if all_versions:
            version_nums = all_version_nums
        elif versions:
            version_nums = _parse_version_range(versions, all_version_nums)
        else:
            # Default to last 3 versions
            version_nums = all_version_nums[-3:] if len(all_version_nums) >= 3 else all_version_nums

    if not version_nums:
        print_error("No versions to replay")
        raise typer.Exit(1)

    # Run replay
    print_info(f"Replaying input across {len(version_nums)} version(s)...")

    results = engine.replay(
        prompt_name=prompt_name,
        versions=version_nums,
        input_text=input_text,
        use_cache=not no_cache,
    )

    # Display results
    if compare:
        _display_comparison(results)
    else:
        _display_results(results)

    # Show summary
    successful = sum(1 for r in results if r.error is None)
    cached = sum(1 for r in results if r.cached)
    print_info(f"Successful: {successful}/{len(results)}")
    if cached:
        print_info(f"Cached results: {cached}")


@app.command("compare")
def replay_compare(
    prompt_name: str = typer.Argument(..., help="Name of the prompt"),
    input_text: Optional[str] = typer.Option(
        None,
        "--input",
        "-i",
        help="Input text to compare",
    ),
    input_file: Optional[str] = typer.Option(
        None,
        "--input-file",
        "-f",
        help="File containing input text",
    ),
    versions: Optional[str] = typer.Option(
        None,
        "--versions",
        "-v",
        help="Versions to compare (default: last 3)",
    ),
) -> None:
    """Compare outputs across versions side-by-side."""
    project_root = require_initialized()
    engine = ReplayEngine(project_root)

    # Get input
    if input_file:
        input_text = Path(input_file).read_text()
    elif not input_text:
        print_error("Provide input with --input or --input-file")
        raise typer.Exit(1)

    # Determine versions
    from pit.db.database import get_session
    from pit.db.repository import PromptRepository, VersionRepository

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        version_repo = VersionRepository(session)

        prompt = prompt_repo.get_by_name(prompt_name)
        if not prompt:
            print_error(f"Prompt '{prompt_name}' not found")
            raise typer.Exit(1)

        all_vers = version_repo.list_by_prompt(prompt.id)
        all_version_nums = [v.version_number for v in all_vers]

        if versions:
            version_nums = _parse_version_list(versions)
        else:
            version_nums = all_version_nums[-3:] if len(all_version_nums) >= 3 else all_version_nums

    # Get comparison
    comparison = engine.compare(prompt_name, version_nums, input_text)

    # Display comparison
    console.print(f"\n[bold cyan]Comparison for '{prompt_name}':[/bold cyan]")
    console.print(f"[dim]Input: {input_text[:100]}{'...' if len(input_text) > 100 else ''}[/dim]\n")

    # Show statistics
    stats = comparison["statistics"]
    console.print(f"[bold]Statistics:[/bold]")
    console.print(f"  Total: {stats['total']}")
    console.print(f"  Successful: {stats['successful']}")
    if stats.get('avg_latency_ms'):
        console.print(f"  Avg latency: {stats['avg_latency_ms']:.1f}ms")

    # Show differences
    console.print(f"\n[bold]Results:[/bold]")
    for result in comparison["results"]:
        version = result["version_number"]
        if result.get("error"):
            console.print(f"  [red]v{version}: {result['error']}[/red]")
        else:
            output = result.get("output", "")[:50]
            latency = result.get("latency_ms")
            cached = "[cached] " if result.get("cached") else ""
            latency_str = f" ({latency:.0f}ms)" if latency else ""
            console.print(f"  [green]v{version}{latency_str}:[/green] {cached}{output}...")


@app.command("cache")
def replay_cache(
    action: str = typer.Argument(..., help="Action: clear, stats, or show"),
) -> None:
    """Manage replay cache."""
    project_root = require_initialized()
    cache = ReplayCache(project_root)

    if action == "clear":
        count = cache.clear()
        print_success(f"Cleared {count} cached result(s)")

    elif action == "stats":
        cache_files = list(cache.cache_dir.glob("*.json"))
        print_info(f"Cached results: {len(cache_files)}")
        print_info(f"Cache directory: {cache.cache_dir}")

    elif action == "show":
        cache_files = list(cache.cache_dir.glob("*.json"))
        if not cache_files:
            print_info("No cached results")
            return

        table = Table(title="Replay Cache")
        table.add_column("Key")
        table.add_column("Version")
        table.add_column("Preview")

        for cache_file in cache_files[:20]:  # Show first 20
            try:
                import json
                data = json.loads(cache_file.read_text())
                preview = data.get("output", "")[:30] + "..."
                table.add_row(
                    cache_file.stem,
                    f"v{data.get('version_number', '?')}",
                    preview,
                )
            except:
                table.add_row(cache_file.stem, "?", "[error]")

        console.print(table)
        if len(cache_files) > 20:
            print_info(f"... and {len(cache_files) - 20} more")

    else:
        print_error(f"Unknown action: {action}")
        raise typer.Exit(1)


def _parse_version_range(range_str: str, all_versions: List[int]) -> List[int]:
    """Parse a version range string."""
    range_str = range_str.strip()

    # Check for range (e.g., "1-5")
    if "-" in range_str:
        parts = range_str.split("-")
        if len(parts) == 2:
            start, end = int(parts[0]), int(parts[1])
            return [v for v in all_versions if start <= v <= end]

    # Check for list (e.g., "1,2,3")
    if "," in range_str:
        nums = [int(v.strip()) for v in range_str.split(",")]
        return [v for v in nums if v in all_versions]

    # Single version
    v = int(range_str)
    return [v] if v in all_versions else []


def _parse_version_list(list_str: str) -> List[int]:
    """Parse a comma-separated version list."""
    return [int(v.strip().lstrip("v")) for v in list_str.split(",")]


def _display_results(results: List[Any]) -> None:
    """Display replay results in a table."""
    table = Table(title="Replay Results")
    table.add_column("Version", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Latency", justify="right")
    table.add_column("Output Preview")

    for result in results:
        if result.error:
            status = "[red]Error[/red]"
            latency = "-"
            preview = result.error[:40]
        else:
            status = "[green]OK[/green]" if not result.cached else "[blue]Cached[/blue]"
            latency = f"{result.latency_ms:.0f}ms" if result.latency_ms else "-"
            preview = (result.output or "")[:40] + "..."

        table.add_row(
            f"v{result.version_number}",
            status,
            latency,
            preview,
        )

    console.print(table)


def _display_comparison(results: List[Any]) -> None:
    """Display side-by-side comparison."""
    from rich.columns import Columns
    from rich.panel import Panel

    panels = []
    for result in results:
        if result.error:
            content = f"[red]{result.error}[/red]"
        else:
            content = result.output or "[dim]No output[/dim]"

        header = f"v{result.version_number}"
        if result.latency_ms:
            header += f" ({result.latency_ms:.0f}ms)"
        if result.cached:
            header += " [cached]"

        panels.append(Panel(content, title=header, border_style="blue"))

    console.print(Columns(panels))
