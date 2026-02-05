"""Optimization commands for prompts."""

import json
from pathlib import Path
from typing import Optional

import typer
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns

from pit.config import find_project_root, is_initialized
from pit.db.database import get_session
from pit.db.repository import PromptRepository, VersionRepository
from pit.cli.formatters import (
    console,
    print_error,
    print_info,
    print_success,
)
from pit.core.optimizer import PromptOptimizer, OptimizationType

app = typer.Typer()


def require_initialized() -> Path:
    """Ensure pit is initialized and return project root."""
    project_root = find_project_root()
    if project_root is None:
        print_error("Not a pit project. Run 'pit init' first.")
        raise typer.Exit(1)
    return project_root


@app.command()
def analyze(
    prompt_name: str = typer.Argument(..., help="Name of the prompt to analyze"),
    version: Optional[int] = typer.Option(
        None,
        "--version",
        "-v",
        help="Version to analyze (default: current)",
    ),
    min_confidence: float = typer.Option(
        0.5,
        "--min-confidence",
        "-c",
        help="Minimum confidence threshold (0-1)",
    ),
    export: Optional[str] = typer.Option(
        None,
        "--export",
        "-e",
        help="Export suggestions to JSON file",
    ),
) -> None:
    """Analyze a prompt and suggest optimizations.

    Uses heuristics to identify potential improvements in
    clarity, specificity, structure, and more.
    """
    project_root = require_initialized()

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        version_repo = VersionRepository(session)

        prompt = prompt_repo.get_by_name(prompt_name)
        if not prompt:
            print_error(f"Prompt '{prompt_name}' not found")
            raise typer.Exit(1)

        # Get version
        if version is not None:
            ver = version_repo.get_by_number(prompt.id, version)
            if not ver:
                print_error(f"Version v{version} not found")
                raise typer.Exit(1)
        else:
            ver = prompt.current_version
            if not ver:
                print_error("No current version found")
                raise typer.Exit(1)

        # Get version history for context
        version_history = version_repo.list_by_prompt(prompt.id)

        # Analyze
        optimizer = PromptOptimizer()
        suggestions = optimizer.analyze(ver.content, version_history)

        # Filter by confidence
        suggestions = [s for s in suggestions if s.confidence >= min_confidence]

        # Display results
        _display_suggestions(prompt_name, ver, suggestions)

        # Export if requested
        if export:
            _export_suggestions(suggestions, export)
            print_success(f"Suggestions exported to {export}")


def _display_suggestions(prompt_name: str, version, suggestions: list) -> None:
    """Display optimization suggestions."""
    console.print(f"\n[bold cyan]Optimization Analysis: {prompt_name} v{version.version_number}[/bold cyan]\n")

    if not suggestions:
        print_success("✓ No optimization suggestions found! Your prompt looks good.")
        return

    # Summary by category
    categories = {}
    for s in suggestions:
        if s.type not in categories:
            categories[s.type] = []
        categories[s.type].append(s)

    console.print(Panel(
        f"Found [bold]{len(suggestions)}[/bold] optimization suggestion(s) "
        f"across [bold]{len(categories)}[/bold] categories.",
        title="Summary",
        border_style="blue",
    ))

    # Category breakdown
    console.print("\n[bold]Categories:[/bold]")
    for opt_type, items in sorted(categories.items(), key=lambda x: -len(x[1])):
        console.print(f"  • {opt_type.value.title()}: {len(items)} suggestion(s)")

    # Detailed suggestions
    console.print("\n[bold]Top Suggestions (by priority):[/bold]\n")

    for i, suggestion in enumerate(suggestions[:10], 1):
        priority_colors = {
            1: "red",
            2: "yellow",
            3: "blue",
            4: "dim",
            5: "dim",
        }
        color = priority_colors.get(suggestion.priority, "white")

        console.print(Panel(
            f"[bold]Issue:[/bold] {suggestion.current_issue}\n\n"
            f"[bold]Suggestion:[/bold] {suggestion.suggested_change}\n\n"
            f"[bold]Expected Improvement:[/bold] {suggestion.expected_improvement}\n\n"
            f"[dim]Confidence: {suggestion.confidence*100:.0f}%[/dim]",
            title=f"[{color}]#{i} {suggestion.title}[/{color}]",
            border_style=color,
        ))


def _export_suggestions(suggestions: list, output_path: str) -> None:
    """Export suggestions to JSON."""
    data = [
        {
            "type": s.type.value,
            "title": s.title,
            "description": s.description,
            "current_issue": s.current_issue,
            "suggested_change": s.suggested_change,
            "expected_improvement": s.expected_improvement,
            "confidence": s.confidence,
            "priority": s.priority,
        }
        for s in suggestions
    ]

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)


@app.command()
def improve(
    prompt_name: str = typer.Argument(..., help="Name of the prompt to improve"),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file for improved version",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        "-a",
        help="Create a new version with improvements",
    ),
    message: str = typer.Option(
        "Auto-optimized version",
        "--message",
        "-m",
        help="Commit message for new version",
    ),
) -> None:
    """Generate an improved version of a prompt.

    Creates an optimized version based on analysis results.
    Use --apply to commit the improved version.
    """
    project_root = require_initialized()

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        version_repo = VersionRepository(session)

        prompt = prompt_repo.get_by_name(prompt_name)
        if not prompt or not prompt.current_version:
            print_error(f"Prompt '{prompt_name}' not found or has no versions")
            raise typer.Exit(1)

        ver = prompt.current_version
        version_history = version_repo.list_by_prompt(prompt.id)

        # Analyze and generate improvements
        optimizer = PromptOptimizer()
        suggestions = optimizer.analyze(ver.content, version_history)

        # Generate improved version
        improved = optimizer.generate_improved_version(ver.content, suggestions)

        # Display comparison
        console.print(f"\n[bold cyan]Improvement Preview: {prompt_name}[/bold cyan]\n")

        console.print("[bold]Current Version:[/bold]")
        console.print(Panel(ver.content[:500] + "..." if len(ver.content) > 500 else ver.content, border_style="dim"))

        console.print("\n[bold]Improved Version:[/bold]")
        console.print(Panel(improved[:500] + "..." if len(improved) > 500 else improved, border_style="green"))

        # Key improvements applied
        high_impact = [s for s in suggestions if s.confidence >= 0.7 and s.priority <= 2]
        if high_impact:
            console.print("\n[bold]Key Improvements:[/bold]")
            for s in high_impact[:5]:
                console.print(f"  • {s.title}")

        # Output to file
        if output:
            with open(output, "w") as f:
                f.write(improved)
            print_success(f"Improved version saved to {output}")

        # Apply as new version
        if apply:
            from pit.config import Config
            config = Config.load(project_root)

            new_version = version_repo.create(
                prompt_id=prompt.id,
                content=improved,
                message=message,
                author=config.project.default_author,
            )
            print_success(f"Created new version v{new_version.version_number}")


@app.command()
def experiments(
    prompt_name: str = typer.Argument(..., help="Name of the prompt"),
) -> None:
    """Suggest next experiments based on version history.

    Analyzes past versions and performance to recommend
    promising optimization experiments.
    """
    project_root = require_initialized()

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        version_repo = VersionRepository(session)

        prompt = prompt_repo.get_by_name(prompt_name)
        if not prompt:
            print_error(f"Prompt '{prompt_name}' not found")
            raise typer.Exit(1)

        versions = version_repo.list_by_prompt(prompt.id)
        if len(versions) < 2:
            print_info("Need at least 2 versions to suggest experiments")
            return

        console.print(f"\n[bold cyan]Suggested Experiments: {prompt_name}[/bold cyan]\n")

        # Analyze version patterns
        experiments = _generate_experiments(versions)

        if not experiments:
            print_info("No specific experiments suggested based on current history")
            return

        for i, exp in enumerate(experiments, 1):
            console.print(Panel(
                f"[bold]Rationale:[/bold] {exp['rationale']}\n\n"
                f"[bold]Approach:[/bold] {exp['approach']}\n\n"
                f"[bold]Expected Outcome:[/bold] {exp['expected_outcome']}",
                title=f"Experiment #{i}: {exp['name']}",
                border_style="blue",
            ))


def _generate_experiments(versions: list) -> list[dict]:
    """Generate experiment suggestions based on version history."""
    experiments = []

    # Check for success rate variations
    versions_with_success = [v for v in versions if v.success_rate is not None]
    if len(versions_with_success) >= 2:
        success_rates = [v.success_rate for v in versions_with_success]
        if max(success_rates) - min(success_rates) > 0.2:
            experiments.append({
                "name": "Success Rate Optimization",
                "rationale": "Success rate has varied significantly across versions",
                "approach": "A/B test the highest and lowest performing versions to identify key differences",
                "expected_outcome": "Identify winning patterns and consolidate into a stable version",
            })

    # Check for latency variations
    versions_with_latency = [v for v in versions if v.avg_latency_ms is not None]
    if len(versions_with_latency) >= 2:
        latencies = [v.avg_latency_ms for v in versions_with_latency]
        if max(latencies) / min(latencies) > 2:
            experiments.append({
                "name": "Latency Reduction",
                "rationale": "Latency varies significantly (2x+) between versions",
                "approach": "Compare concise vs. detailed prompt versions",
                "expected_outcome": "Find the optimal balance between instruction clarity and length",
            })

    # Check for version count
    if len(versions) > 5:
        experiments.append({
            "name": "Prompt Consolidation",
            "rationale": f"Many versions ({len(versions)}) suggest potential bloat",
            "approach": "Create a clean-sheet version incorporating only the most effective elements",
            "expected_outcome": "A focused, maintainable prompt that captures best practices",
        })

    # Check for token usage growth
    versions_with_tokens = [v for v in versions if v.avg_token_usage is not None]
    if len(versions_with_tokens) >= 2:
        first_tokens = versions_with_tokens[0].avg_token_usage
        last_tokens = versions_with_tokens[-1].avg_token_usage
        if last_tokens > first_tokens * 1.5:
            experiments.append({
                "name": "Token Efficiency",
                "rationale": "Token usage has increased significantly",
                "approach": "Experiment with more concise instructions and fewer examples",
                "expected_outcome": "Reduced token costs while maintaining quality",
            })

    return experiments


@app.command()
def benchmark(
    prompt_name: str = typer.Argument(..., help="Name of the prompt"),
) -> None:
    """Compare current prompt against optimization best practices.

    Scores the prompt on various dimensions and provides
    a benchmark report.
    """
    project_root = require_initialized()

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)

        prompt = prompt_repo.get_by_name(prompt_name)
        if not prompt or not prompt.current_version:
            print_error(f"Prompt '{prompt_name}' not found or has no versions")
            raise typer.Exit(1)

        content = prompt.current_version.content
        optimizer = PromptOptimizer()
        suggestions = optimizer.analyze(content)

        # Calculate scores
        scores = _calculate_benchmark_scores(content, suggestions)

        console.print(f"\n[bold cyan]Benchmark Report: {prompt_name}[/bold cyan]\n")

        # Score table
        table = Table(show_header=True, header_style="bold")
        table.add_column("Dimension", style="cyan")
        table.add_column("Score", justify="center")
        table.add_column("Rating", justify="center")
        table.add_column("Issues")

        for dimension, score in scores.items():
            rating = _get_rating(score)
            issues = len([s for s in suggestions if s.type.value == dimension.lower()])
            issue_text = str(issues) if issues > 0 else "✓"

            table.add_row(
                dimension,
                f"{score}/100",
                rating,
                issue_text,
            )

        console.print(table)

        # Overall score
        overall = sum(scores.values()) / len(scores)
        console.print(f"\n[bold]Overall Score:[/bold] {overall:.1f}/100 {_get_rating(overall)}")


def _calculate_benchmark_scores(content: str, suggestions: list) -> dict:
    """Calculate benchmark scores for each dimension."""
    scores = {
        "Clarity": 100,
        "Specificity": 100,
        "Structure": 100,
        "Examples": 100,
        "Constraints": 100,
        "Context": 100,
        "Length": 100,
        "Safety": 100,
    }

    # Deduct points based on suggestions
    for s in suggestions:
        dim_key = s.type.value.title()
        if dim_key in scores:
            # Deduct based on priority
            deduction = {1: 25, 2: 15, 3: 10, 4: 5, 5: 3}.get(s.priority, 5)
            scores[dim_key] = max(0, scores[dim_key] - deduction)

    return scores


def _get_rating(score: float) -> str:
    """Get a rating based on score."""
    if score >= 90:
        return "[green]Excellent[/green]"
    elif score >= 75:
        return "[green]Good[/green]"
    elif score >= 60:
        return "[yellow]Fair[/yellow]"
    elif score >= 40:
        return "[yellow]Needs Work[/yellow]"
    else:
        return "[red]Poor[/red]"
