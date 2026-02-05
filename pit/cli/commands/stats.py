"""Analytics and statistics commands for prompts."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import typer
from rich.table import Table
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.columns import Columns
from rich import box

from pit.config import find_project_root, is_initialized
from pit.db.database import get_session
from pit.db.repository import (
    ABTestResultRepository,
    PromptRepository,
    TestRunRepository,
    VersionRepository,
)
from pit.cli.formatters import (
    console,
    print_error,
    print_info,
    print_success,
)

app = typer.Typer()


def require_initialized() -> Path:
    """Ensure pit is initialized and return project root."""
    project_root = find_project_root()
    if project_root is None:
        print_error("Not a pit project. Run 'pit init' first.")
        raise typer.Exit(1)
    return project_root


@app.command()
def show(
    prompt_name: str = typer.Argument(..., help="Name of the prompt"),
    version: Optional[int] = typer.Option(
        None,
        "--version",
        "-v",
        help="Show stats for specific version only",
    ),
    days: int = typer.Option(
        30,
        "--days",
        "-d",
        help="Number of days to include in analysis",
    ),
    export: Optional[str] = typer.Option(
        None,
        "--export",
        "-e",
        help="Export stats to JSON file",
    ),
) -> None:
    """Display analytics dashboard for a prompt.

    Shows token usage, latency, success rates, and cost
    analysis across versions with rich visualizations.
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
        if not versions:
            print_info(f"No versions found for prompt '{prompt_name}'")
            return

        # Filter to specific version if requested
        if version is not None:
            versions = [v for v in versions if v.version_number == version]
            if not versions:
                print_error(f"Version v{version} not found")
                raise typer.Exit(1)

        # Calculate stats
        stats = _calculate_stats(versions)

        # Display dashboard
        _display_dashboard(prompt_name, versions, stats)

        # Show charts
        _display_charts(versions)

        # Cost analysis
        _display_cost_analysis(versions, days)

        # Export if requested
        if export:
            _export_stats(stats, export)
            print_success(f"Stats exported to {export}")


def _calculate_stats(versions: list) -> dict:
    """Calculate aggregate statistics."""
    total_invocations = sum(v.total_invocations for v in versions)

    # Average metrics across versions
    versions_with_metrics = [v for v in versions if v.total_invocations > 0]

    if versions_with_metrics:
        avg_latency = sum(
            (v.avg_latency_ms or 0) * v.total_invocations for v in versions_with_metrics
        ) / total_invocations if total_invocations > 0 else 0

        avg_tokens = sum(
            (v.avg_token_usage or 0) * v.total_invocations for v in versions_with_metrics
        ) / total_invocations if total_invocations > 0 else 0

        avg_success = sum(
            (v.success_rate or 0) * v.total_invocations for v in versions_with_metrics
        ) / total_invocations if total_invocations > 0 else 0

        avg_cost = sum(
            (v.avg_cost_per_1k or 0) * v.total_invocations for v in versions_with_metrics
        ) / total_invocations if total_invocations > 0 else 0
    else:
        avg_latency = avg_tokens = avg_success = avg_cost = 0

    return {
        "total_invocations": total_invocations,
        "version_count": len(versions),
        "avg_latency_ms": avg_latency,
        "avg_token_usage": avg_tokens,
        "avg_success_rate": avg_success,
        "avg_cost_per_1k": avg_cost,
        "versions_with_data": len(versions_with_metrics),
    }


def _display_dashboard(prompt_name: str, versions: list, stats: dict) -> None:
    """Display the main statistics dashboard."""
    console.print(f"\n[bold cyan]Analytics Dashboard: {prompt_name}[/bold cyan]\n")

    # Summary metrics
    summary = (
        f"[bold]Total Versions:[/bold] {stats['version_count']}\n"
        f"[bold]Total Invocations:[/bold] {stats['total_invocations']:,}\n"
        f"[bold]Versions with Metrics:[/bold] {stats['versions_with_data']}\n"
        f"[bold]Avg Latency:[/bold] {stats['avg_latency_ms']:.1f}ms\n"
        f"[bold]Avg Token Usage:[/bold] {stats['avg_token_usage']:.0f} tokens\n"
        f"[bold]Avg Success Rate:[/bold] {stats['avg_success_rate']*100:.1f}%\n"
        f"[bold]Avg Cost:[/bold] ${stats['avg_cost_per_1k']:.4f} per 1K invocations"
    )

    console.print(Panel(summary, title="Summary", border_style="blue"))


def _display_charts(versions: list) -> None:
    """Display ASCII bar charts for metrics."""
    # Version comparison table
    table = Table(title="Version Performance Comparison", box=box.ROUNDED)
    table.add_column("Version", style="cyan", justify="center")
    table.add_column("Invocations", justify="right")
    table.add_column("Latency", justify="right")
    table.add_column("Tokens", justify="right")
    table.add_column("Success Rate", justify="center")
    table.add_column("Cost/1K", justify="right")

    # Sort by version number
    sorted_versions = sorted(versions, key=lambda v: v.version_number, reverse=True)

    for v in sorted_versions[:10]:  # Show last 10 versions
        latency = f"{v.avg_latency_ms:.0f}ms" if v.avg_latency_ms else "-"
        tokens = f"{v.avg_token_usage:.0f}" if v.avg_token_usage else "-"
        success = f"{v.success_rate*100:.0f}%" if v.success_rate else "-"
        cost = f"${v.avg_cost_per_1k:.4f}" if v.avg_cost_per_1k else "-"

        # Success rate bar
        if v.success_rate:
            bar_width = int(v.success_rate * 10)
            success_bar = "█" * bar_width + "░" * (10 - bar_width)
            success = f"{success_bar} {success}"

        table.add_row(
            f"v{v.version_number}",
            f"{v.total_invocations:,}",
            latency,
            tokens,
            success,
            cost,
        )

    console.print(table)


def _display_cost_analysis(versions: list, days: int) -> None:
    """Display cost analysis."""
    console.print("\n[bold]Cost Analysis[/bold]\n")

    # Calculate estimated costs
    total_invocations = sum(v.total_invocations for v in versions)
    avg_cost_per_1k = 0

    versions_with_cost = [v for v in versions if v.avg_cost_per_1k]
    if versions_with_cost:
        total_cost = sum(v.avg_cost_per_1k * v.total_invocations / 1000 for v in versions_with_cost)
        avg_cost_per_1k = total_cost * 1000 / total_invocations if total_invocations > 0 else 0
    else:
        total_cost = 0

    # Cost breakdown
    cost_table = Table(box=box.SIMPLE)
    cost_table.add_column("Metric", style="cyan")
    cost_table.add_column("Value", justify="right")

    cost_table.add_row("Total Invocations", f"{total_invocations:,}")
    cost_table.add_row("Estimated Total Cost", f"${total_cost:.4f}")
    cost_table.add_row("Avg Cost per 1K Calls", f"${avg_cost_per_1k:.4f}")

    if total_invocations > 0:
        cost_table.add_row("Avg Cost per Call", f"${total_cost/total_invocations:.6f}")

    # Projected costs
    if avg_cost_per_1k > 0:
        cost_table.add_row("", "")
        cost_table.add_row("[bold]Projected Costs[/bold]", "")
        cost_table.add_row("1K invocations/day", f"${avg_cost_per_1k * 1:.4f}/day")
        cost_table.add_row("10K invocations/day", f"${avg_cost_per_1k * 10:.4f}/day")
        cost_table.add_row("100K invocations/day", f"${avg_cost_per_1k * 100:.4f}/day")

    console.print(cost_table)


def _export_stats(stats: dict, output_path: str) -> None:
    """Export stats to JSON."""
    with open(output_path, "w") as f:
        json.dump(stats, f, indent=2)


@app.command()
def compare(
    prompt_name: str = typer.Argument(..., help="Name of the prompt"),
    v1: int = typer.Argument(..., help="First version number"),
    v2: int = typer.Argument(..., help="Second version number"),
) -> None:
    """Compare statistics between two versions."""
    project_root = require_initialized()

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        version_repo = VersionRepository(session)

        prompt = prompt_repo.get_by_name(prompt_name)
        if not prompt:
            print_error(f"Prompt '{prompt_name}' not found")
            raise typer.Exit(1)

        ver_a = version_repo.get_by_number(prompt.id, v1)
        ver_b = version_repo.get_by_number(prompt.id, v2)

        if not ver_a:
            print_error(f"Version v{v1} not found")
            raise typer.Exit(1)
        if not ver_b:
            print_error(f"Version v{v2} not found")
            raise typer.Exit(1)

        # Comparison table
        console.print(f"\n[bold cyan]Version Comparison: v{v1} vs v{v2}[/bold cyan]\n")

        table = Table(box=box.ROUNDED)
        table.add_column("Metric", style="cyan")
        table.add_column(f"v{v1}", justify="right")
        table.add_column(f"v{v2}", justify="right")
        table.add_column("Change", justify="center")

        metrics = [
            ("Invocations", lambda v: v.total_invocations, "{:,}", False),
            ("Avg Latency", lambda v: v.avg_latency_ms or 0, "{:.1f}ms", True),
            ("Avg Tokens", lambda v: v.avg_token_usage or 0, "{:.0f}", False),
            ("Success Rate", lambda v: (v.success_rate or 0) * 100, "{:.1f}%", False),
            ("Cost per 1K", lambda v: v.avg_cost_per_1k or 0, "${:.4f}", True),
        ]

        for name, getter, fmt, lower_is_better in metrics:
            val_a = getter(ver_a)
            val_b = getter(ver_b)

            str_a = fmt.format(val_a) if val_a or isinstance(val_a, int) else "-"
            str_b = fmt.format(val_b) if val_b or isinstance(val_b, int) else "-"

            # Calculate change
            if val_a and val_b:
                change_pct = ((val_b - val_a) / val_a) * 100 if val_a != 0 else 0
                if lower_is_better:
                    color = "green" if change_pct < 0 else "red"
                else:
                    color = "green" if change_pct > 0 else "red"

                if abs(change_pct) < 0.1:
                    change_str = "[dim]~[/dim]"
                else:
                    arrow = "↑" if change_pct > 0 else "↓"
                    change_str = f"[{color}]{arrow} {abs(change_pct):.1f}%[/{color}]"
            else:
                change_str = "[dim]-[/dim]"

            table.add_row(name, str_a, str_b, change_str)

        console.print(table)


@app.command()
def trends(
    prompt_name: str = typer.Argument(..., help="Name of the prompt"),
) -> None:
    """Show performance trends across versions."""
    project_root = require_initialized()

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        version_repo = VersionRepository(session)

        prompt = prompt_repo.get_by_name(prompt_name)
        if not prompt:
            print_error(f"Prompt '{prompt_name}' not found")
            raise typer.Exit(1)

        versions = version_repo.list_by_prompt(prompt.id)
        versions_with_data = [v for v in versions if v.total_invocations > 0]

        if len(versions_with_data) < 2:
            print_info("Need at least 2 versions with metrics to show trends")
            return

        console.print(f"\n[bold cyan]Performance Trends: {prompt_name}[/bold cyan]\n")

        # Calculate trends
        sorted_versions = sorted(versions_with_data, key=lambda v: v.version_number)

        # Trend indicators
        latency_trend = _calculate_trend([v.avg_latency_ms for v in sorted_versions if v.avg_latency_ms])
        token_trend = _calculate_trend([v.avg_token_usage for v in sorted_versions if v.avg_token_usage])
        success_trend = _calculate_trend([v.success_rate for v in sorted_versions if v.success_rate])

        trend_table = Table(title="Trend Analysis", box=box.ROUNDED)
        trend_table.add_column("Metric", style="cyan")
        trend_table.add_column("Trend")
        trend_table.add_column("Direction")

        trends_data = [
            ("Latency", latency_trend, "lower"),
            ("Token Usage", token_trend, "lower"),
            ("Success Rate", success_trend, "higher"),
        ]

        for name, trend, preferred in trends_data:
            if trend:
                direction = trend["direction"]
                arrow = "↑" if direction == "increasing" else "↓"
                if (direction == "decreasing" and preferred == "lower") or \
                   (direction == "increasing" and preferred == "higher"):
                    color = "green"
                else:
                    color = "red"

                trend_str = f"[{color}]{arrow} {abs(trend['change_pct']):.1f}%[/color]"
                dir_str = f"[dim]{direction}[/dim]"
            else:
                trend_str = "[dim]insufficient data[/dim]"
                dir_str = "-"

            trend_table.add_row(name, trend_str, dir_str)

        console.print(trend_table)


def _calculate_trend(values: list) -> Optional[dict]:
    """Calculate trend from a series of values."""
    if len(values) < 2:
        return None

    first = values[0]
    last = values[-1]

    if first == 0:
        return None

    change = last - first
    change_pct = (change / first) * 100

    return {
        "change": change,
        "change_pct": change_pct,
        "direction": "increasing" if change > 0 else "decreasing",
        "first": first,
        "last": last,
    }


@app.command()
def report(
    prompt_name: str = typer.Argument(..., help="Name of the prompt"),
    output: str = typer.Option(
        "report.html",
        "--output",
        "-o",
        help="Output file for HTML report",
    ),
) -> None:
    """Generate a comprehensive HTML analytics report."""
    project_root = require_initialized()

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        version_repo = VersionRepository(session)
        test_repo = TestRunRepository(session)
        ab_repo = ABTestResultRepository(session)

        prompt = prompt_repo.get_by_name(prompt_name)
        if not prompt:
            print_error(f"Prompt '{prompt_name}' not found")
            raise typer.Exit(1)

        versions = version_repo.list_by_prompt(prompt.id)
        stats = _calculate_stats(versions)

        # Generate HTML report
        html = _generate_html_report(prompt_name, versions, stats)

        with open(output, "w") as f:
            f.write(html)

        print_success(f"Report saved to {output}")


def _generate_html_report(prompt_name: str, versions: list, stats: dict) -> str:
    """Generate an HTML analytics report."""
    html_parts = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        f"<title>Analytics Report: {prompt_name}</title>",
        """<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       margin: 40px; background: #f5f5f5; }
.container { max-width: 1200px; margin: 0 auto; background: white;
              padding: 40px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
h1 { color: #333; border-bottom: 3px solid #4CAF50; padding-bottom: 10px; }
h2 { color: #555; margin-top: 30px; }
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
               gap: 20px; margin: 20px 0; }
.stat-card { background: #f8f9fa; padding: 20px; border-radius: 8px;
              border-left: 4px solid #4CAF50; }
.stat-value { font-size: 2em; font-weight: bold; color: #333; }
.stat-label { color: #666; margin-top: 5px; }
table { width: 100%; border-collapse: collapse; margin: 20px 0; }
th, td { text-align: left; padding: 12px; border-bottom: 1px solid #ddd; }
th { background-color: #4CAF50; color: white; }
tr:hover { background-color: #f5f5f5; }
.positive { color: #4CAF50; }
.negative { color: #f44336; }
</style>""",
        "</head>",
        "<body>",
        "<div class='container'>",
        f"<h1>Analytics Report: {prompt_name}</h1>",
        f"<p>Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>",
        "<h2>Summary Statistics</h2>",
        "<div class='stats-grid'>",
        f"<div class='stat-card'><div class='stat-value'>{stats['version_count']}</div><div class='stat-label'>Total Versions</div></div>",
        f"<div class='stat-card'><div class='stat-value'>{stats['total_invocations']:,}</div><div class='stat-label'>Total Invocations</div></div>",
        f"<div class='stat-card'><div class='stat-value'>{stats['avg_latency_ms']:.1f}ms</div><div class='stat-label'>Avg Latency</div></div>",
        f"<div class='stat-card'><div class='stat-value'>{stats['avg_success_rate']*100:.1f}%</div><div class='stat-label'>Avg Success Rate</div></div>",
        "</div>",
        "<h2>Version Performance</h2>",
        "<table>",
        "<tr><th>Version</th><th>Invocations</th><th>Avg Latency</th><th>Avg Tokens</th><th>Success Rate</th></tr>",
    ]

    for v in sorted(versions, key=lambda x: x.version_number, reverse=True):
        success_rate = f"{(v.success_rate or 0)*100:.1f}%" if v.success_rate else "-"
        html_parts.append(
            f"<tr><td>v{v.version_number}</td><td>{v.total_invocations:,}</td>"
            f"<td>{v.avg_latency_ms or '-'}ms</td><td>{v.avg_token_usage or '-'}</td>"
            f"<td>{success_rate}</td></tr>"
        )

    html_parts.extend([
        "</table>",
        "</div>",
        "</body>",
        "</html>",
    ])

    return "\n".join(html_parts)
