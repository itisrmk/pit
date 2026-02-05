"""A/B Testing commands for comparing prompt versions."""

import json
from pathlib import Path
from typing import Optional

import typer
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from pit.config import Config, find_project_root, is_initialized
from pit.db.database import get_session
from pit.db.repository import (
    ABTestResultRepository,
    PromptRepository,
    TestCaseRepository,
    TestRunRepository,
    TestSuiteRepository,
    VersionRepository,
)
from pit.cli.formatters import (
    console,
    print_error,
    print_info,
    print_success,
    print_warning,
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
def run(
    prompt_name: str = typer.Argument(..., help="Name of the prompt"),
    version_a: str = typer.Argument(..., help="First version (e.g., '1' or 'v1')"),
    version_b: str = typer.Argument(..., help="Second version (e.g., '2' or 'v2')"),
    suite: Optional[str] = typer.Option(
        None,
        "--suite",
        "-s",
        help="Test suite name or ID to use for testing",
    ),
    metric: str = typer.Option(
        "combined",
        "--metric",
        "-m",
        help="Metric to optimize for: latency, token_usage, success_rate, or combined",
    ),
    confidence_threshold: float = typer.Option(
        0.95,
        "--confidence",
        "-c",
        help="Confidence threshold for statistical significance (0-1)",
    ),
    auto_winner: bool = typer.Option(
        False,
        "--auto-winner",
        "-a",
        help="Automatically select winner based on metric",
    ),
    export: Optional[str] = typer.Option(
        None,
        "--export",
        "-e",
        help="Export results to file (CSV or JSON)",
    ),
) -> None:
    """Run an A/B test between two versions of a prompt.

    Compares two versions using the same test inputs and performs
    statistical significance testing to determine the winner.
    """
    project_root = require_initialized()

    # Parse version numbers
    v1_num = int(version_a.lower().lstrip("v"))
    v2_num = int(version_b.lower().lstrip("v"))

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        version_repo = VersionRepository(session)
        suite_repo = TestSuiteRepository(session)
        ab_repo = ABTestResultRepository(session)

        prompt = prompt_repo.get_by_name(prompt_name)
        if not prompt:
            print_error(f"Prompt '{prompt_name}' not found")
            raise typer.Exit(1)

        ver_a = version_repo.get_by_number(prompt.id, v1_num)
        ver_b = version_repo.get_by_number(prompt.id, v2_num)

        if not ver_a:
            print_error(f"Version v{v1_num} not found")
            raise typer.Exit(1)
        if not ver_b:
            print_error(f"Version v{v2_num} not found")
            raise typer.Exit(1)

        # Get test suite
        test_suite = None
        if suite:
            suites = suite_repo.list_by_prompt(prompt.id)
            test_suite = next(
                (s for s in suites if s.name == suite or s.id == suite),
                None,
            )
            if not test_suite:
                print_error(f"Test suite '{suite}' not found")
                raise typer.Exit(1)
        else:
            # Use first available suite
            suites = suite_repo.list_by_prompt(prompt.id)
            if suites:
                test_suite = suites[0]
                print_info(f"Using test suite '{test_suite.name}'")
            else:
                print_error("No test suites found. Create one with 'pit test create-suite'")
                raise typer.Exit(1)

        # Run A/B test
        results = _run_ab_test(ver_a, ver_b, test_suite)

        # Perform statistical analysis
        analysis = _analyze_results(results, confidence_threshold, metric)

        # Display results
        _display_ab_results(results, analysis, ver_a, ver_b)

        # Auto-select winner if requested
        winner_id = None
        if auto_winner and analysis.get("significant"):
            winner_id = analysis.get("winner_id")
            winner_ver = v1_num if winner_id == ver_a.id else v2_num
            print_success(f"Auto-selected v{winner_ver} as winner based on {metric}")

        # Save A/B test result
        ab_result = ab_repo.create(
            prompt_id=prompt.id,
            version_a_id=ver_a.id,
            version_b_id=ver_b.id,
            confidence=analysis.get("confidence", 0.0),
            winner_id=winner_id,
            metrics=analysis.get("metrics", {}),
            test_suite_id=test_suite.id,
        )
        print_info(f"A/B test saved with ID: {ab_result.id[:8]}")

        # Export if requested
        if export:
            _export_results(results, analysis, export, ver_a, ver_b)


def _run_ab_test(ver_a, ver_b, test_suite) -> dict:
    """Run A/B test between two versions."""
    from pit.core.llm.provider import get_llm_provider
    from pit.config import Config
    import time

    project_root = find_project_root()
    config = Config.load(project_root)

    case_repo = TestCaseRepository(None)
    case_repo.session = test_suite.__class__.__session__

    # Get test cases directly from the suite relationship
    test_cases = test_suite.test_cases

    results = {
        "version_a": {
            "version_number": ver_a.version_number,
            "version_id": ver_a.id,
            "metrics": [],
        },
        "version_b": {
            "version_number": ver_b.version_number,
            "version_id": ver_b.id,
            "metrics": [],
        },
        "test_cases": [],
    }

    provider = None
    if config.llm.provider:
        try:
            provider = get_llm_provider(config.llm)
        except Exception as e:
            print_warning(f"Could not initialize LLM provider: {e}")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"Running A/B test with {len(test_cases)} cases...",
            total=len(test_cases) * 2,
        )

        for test_case in test_cases:
            case_results = {
                "case_id": test_case.id,
                "case_name": test_case.name,
                "version_a": _run_version_test(ver_a, test_case, provider),
                "version_b": _run_version_test(ver_b, test_case, provider),
            }
            results["test_cases"].append(case_results)
            results["version_a"]["metrics"].append(case_results["version_a"])
            results["version_b"]["metrics"].append(case_results["version_b"])
            progress.advance(task, 2)

    return results


def _run_version_test(version, test_case, provider) -> dict:
    """Run a single test case against a version."""
    import time

    start_time = time.time()
    result = {
        "latency_ms": 0,
        "token_usage": 0,
        "success": False,
        "output": "",
    }

    try:
        content = version.content
        if test_case.input_data:
            for key, value in test_case.input_data.items():
                placeholder = f"{{{{{key}}}}}"
                content = content.replace(placeholder, str(value))

        if provider:
            response = provider.generate(content)
            result["output"] = response.text
            result["token_usage"] = response.token_usage or 0
        else:
            result["output"] = content
            result["token_usage"] = len(content.split())

        # Check expected criteria
        if test_case.expected_criteria:
            from pit.cli.commands.test import _evaluate_criteria
            result["success"] = _evaluate_criteria(result["output"], test_case.expected_criteria)
        else:
            result["success"] = True

    except Exception as e:
        result["output"] = str(e)
        result["success"] = False

    result["latency_ms"] = (time.time() - start_time) * 1000
    return result


def _analyze_results(results: dict, confidence_threshold: float, metric: str) -> dict:
    """Perform statistical analysis on A/B test results."""
    try:
        from scipy import stats
    except ImportError:
        print_warning("scipy not installed. Statistical testing disabled.")
        return _analyze_simple(results, metric)

    metrics_a = results["version_a"]["metrics"]
    metrics_b = results["version_b"]["metrics"]

    # Extract metric values
    if metric == "latency":
        values_a = [m["latency_ms"] for m in metrics_a]
        values_b = [m["latency_ms"] for m in metrics_b]
        lower_is_better = True
    elif metric == "token_usage":
        values_a = [m["token_usage"] for m in metrics_a]
        values_b = [m["token_usage"] for m in metrics_b]
        lower_is_better = True
    elif metric == "success_rate":
        values_a = [1.0 if m["success"] else 0.0 for m in metrics_a]
        values_b = [1.0 if m["success"] else 0.0 for m in metrics_b]
        lower_is_better = False
    else:  # combined
        # Normalize and combine metrics
        latencies_a = [m["latency_ms"] for m in metrics_a]
        latencies_b = [m["latency_ms"] for m in metrics_b]
        tokens_a = [m["token_usage"] for m in metrics_a]
        tokens_b = [m["token_usage"] for m in metrics_b]
        success_a = [1.0 if m["success"] else 0.0 for m in metrics_a]
        success_b = [1.0 if m["success"] else 0.0 for m in metrics_b]

        # Simple combined score (lower is better)
        values_a = [
            (lat / max(latencies_a + [1])) * 0.3 +
            (tok / max(tokens_a + [1])) * 0.3 +
            (1 - suc) * 0.4
            for lat, tok, suc in zip(latencies_a, tokens_a, success_a)
        ]
        values_b = [
            (lat / max(latencies_b + [1])) * 0.3 +
            (tok / max(tokens_b + [1])) * 0.3 +
            (1 - suc) * 0.4
            for lat, tok, suc in zip(latencies_b, tokens_b, success_b)
        ]
        lower_is_better = True

    # Calculate statistics
    mean_a = sum(values_a) / len(values_a) if values_a else 0
    mean_b = sum(values_b) / len(values_b) if values_b else 0
    std_a = (sum((x - mean_a) ** 2 for x in values_a) / len(values_a)) ** 0.5 if values_a else 0
    std_b = (sum((x - mean_b) ** 2 for x in values_b) / len(values_b)) ** 0.5 if values_b else 0

    # Perform t-test
    if len(values_a) > 1 and len(values_b) > 1:
        t_stat, p_value = stats.ttest_ind(values_a, values_b)
        confidence = 1 - p_value
        significant = confidence >= confidence_threshold
    else:
        t_stat, p_value, confidence, significant = 0, 1, 0, False

    # Determine winner
    winner_id = None
    if significant:
        if lower_is_better:
            winner_id = results["version_a"]["version_id"] if mean_a < mean_b else results["version_b"]["version_id"]
        else:
            winner_id = results["version_a"]["version_id"] if mean_a > mean_b else results["version_b"]["version_id"]

    return {
        "metric": metric,
        "mean_a": mean_a,
        "mean_b": mean_b,
        "std_a": std_a,
        "std_b": std_b,
        "t_statistic": t_stat,
        "p_value": p_value,
        "confidence": confidence,
        "significant": significant,
        "threshold": confidence_threshold,
        "winner_id": winner_id,
        "metrics": {
            "version_a_mean": mean_a,
            "version_a_std": std_a,
            "version_b_mean": mean_b,
            "version_b_std": std_b,
            "sample_size_a": len(values_a),
            "sample_size_b": len(values_b),
        },
    }


def _analyze_simple(results: dict, metric: str) -> dict:
    """Simple analysis without statistical testing."""
    metrics_a = results["version_a"]["metrics"]
    metrics_b = results["version_b"]["metrics"]

    if metric == "latency":
        mean_a = sum(m["latency_ms"] for m in metrics_a) / len(metrics_a) if metrics_a else 0
        mean_b = sum(m["latency_ms"] for m in metrics_b) / len(metrics_b) if metrics_b else 0
        lower_is_better = True
    elif metric == "token_usage":
        mean_a = sum(m["token_usage"] for m in metrics_a) / len(metrics_a) if metrics_a else 0
        mean_b = sum(m["token_usage"] for m in metrics_b) / len(metrics_b) if metrics_b else 0
        lower_is_better = True
    elif metric == "success_rate":
        mean_a = sum(1.0 if m["success"] else 0.0 for m in metrics_a) / len(metrics_a) if metrics_a else 0
        mean_b = sum(1.0 if m["success"] else 0.0 for m in metrics_b) / len(metrics_b) if metrics_b else 0
        lower_is_better = False
    else:
        mean_a = mean_b = 0
        lower_is_better = True

    # Simple comparison without significance
    winner_id = None
    if mean_a != mean_b:
        if lower_is_better:
            winner_id = results["version_a"]["version_id"] if mean_a < mean_b else results["version_b"]["version_id"]
        else:
            winner_id = results["version_a"]["version_id"] if mean_a > mean_b else results["version_b"]["version_id"]

    return {
        "metric": metric,
        "mean_a": mean_a,
        "mean_b": mean_b,
        "std_a": 0,
        "std_b": 0,
        "t_statistic": 0,
        "p_value": 1,
        "confidence": 0.5,
        "significant": False,
        "threshold": 0.95,
        "winner_id": winner_id,
        "metrics": {
            "version_a_mean": mean_a,
            "version_b_mean": mean_b,
            "sample_size_a": len(metrics_a),
            "sample_size_b": len(metrics_b),
        },
    }


def _display_ab_results(results: dict, analysis: dict, ver_a, ver_b) -> None:
    """Display A/B test results."""
    console.print(f"\n[bold cyan]A/B Test Results[/bold cyan]")
    console.print(f"Comparing v{ver_a.version_number} vs v{ver_b.version_number}\n")

    # Metric comparison panel
    metric_name = analysis["metric"].replace("_", " ").title()
    metric_color = "green" if analysis.get("significant") else "yellow"

    comparison_text = (
        f"[bold]Metric:[/bold] {metric_name}\n"
        f"[bold]Version A (v{ver_a.version_number}):[/bold] "
        f"{analysis['mean_a']:.2f} ± {analysis['std_a']:.2f}\n"
        f"[bold]Version B (v{ver_b.version_number}):[/bold] "
        f"{analysis['mean_b']:.2f} ± {analysis['std_b']:.2f}\n"
        f"\n[bold]Statistical Analysis:[/bold]\n"
        f"t-statistic: {analysis['t_statistic']:.4f}\n"
        f"p-value: {analysis['p_value']:.4f}\n"
        f"Confidence: [{metric_color}]{analysis['confidence']*100:.1f}%[/{metric_color}]\n"
        f"Threshold: {analysis['threshold']*100:.0f}%"
    )

    console.print(Panel(comparison_text, title="Comparison", border_style="blue"))

    # Significance indicator
    if analysis.get("significant"):
        winner_num = ver_a.version_number if analysis["winner_id"] == ver_a.id else ver_b.version_number
        print_success(f"✓ Statistically significant result! Winner: v{winner_num}")
    else:
        print_warning("✗ No statistically significant difference detected")

    # Test case results table
    table = Table(title="Individual Test Results")
    table.add_column("Case", style="cyan")
    table.add_column(f"v{ver_a.version_number} Latency", justify="right")
    table.add_column(f"v{ver_a.version_number} Tokens", justify="right")
    table.add_column(f"v{ver_b.version_number} Latency", justify="right")
    table.add_column(f"v{ver_b.version_number} Tokens", justify="right")
    table.add_column("Winner")

    for case in results["test_cases"]:
        a_metrics = case["version_a"]
        b_metrics = case["version_b"]

        # Determine winner for this case
        case_winner = "Tie"
        if analysis["metric"] == "latency":
            case_winner = f"v{ver_a.version_number}" if a_metrics["latency_ms"] < b_metrics["latency_ms"] else f"v{ver_b.version_number}"
        elif analysis["metric"] == "token_usage":
            case_winner = f"v{ver_a.version_number}" if a_metrics["token_usage"] < b_metrics["token_usage"] else f"v{ver_b.version_number}"
        elif analysis["metric"] == "success_rate":
            a_success = 1 if a_metrics["success"] else 0
            b_success = 1 if b_metrics["success"] else 0
            if a_success > b_success:
                case_winner = f"v{ver_a.version_number}"
            elif b_success > a_success:
                case_winner = f"v{ver_b.version_number}"

        table.add_row(
            case.get("case_name") or case["case_id"][:8],
            f"{a_metrics['latency_ms']:.0f}ms",
            str(a_metrics["token_usage"]),
            f"{b_metrics['latency_ms']:.0f}ms",
            str(b_metrics["token_usage"]),
            case_winner,
        )

    console.print(table)


def _export_results(results: dict, analysis: dict, export_path: str, ver_a, ver_b) -> None:
    """Export A/B test results to file."""
    export_data = {
        "versions": {
            "a": {"number": ver_a.version_number, "id": ver_a.id},
            "b": {"number": ver_b.version_number, "id": ver_b.id},
        },
        "analysis": analysis,
        "test_results": results["test_cases"],
    }

    if export_path.endswith(".csv"):
        # Export as CSV
        import csv

        with open(export_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "case_id", "case_name",
                "v{}_latency".format(ver_a.version_number),
                "v{}_tokens".format(ver_a.version_number),
                "v{}_success".format(ver_a.version_number),
                "v{}_latency".format(ver_b.version_number),
                "v{}_tokens".format(ver_b.version_number),
                "v{}_success".format(ver_b.version_number),
            ])
            for case in results["test_cases"]:
                writer.writerow([
                    case["case_id"],
                    case.get("case_name", ""),
                    case["version_a"]["latency_ms"],
                    case["version_a"]["token_usage"],
                    case["version_a"]["success"],
                    case["version_b"]["latency_ms"],
                    case["version_b"]["token_usage"],
                    case["version_b"]["success"],
                ])
    else:
        # Export as JSON
        with open(export_path, "w") as f:
            json.dump(export_data, f, indent=2)

    print_success(f"Results exported to {export_path}")


@app.command("list")
def list_ab_tests(
    prompt_name: str = typer.Argument(..., help="Name of the prompt"),
) -> None:
    """List all A/B tests for a prompt."""
    project_root = require_initialized()

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        ab_repo = ABTestResultRepository(session)

        prompt = prompt_repo.get_by_name(prompt_name)
        if not prompt:
            print_error(f"Prompt '{prompt_name}' not found")
            raise typer.Exit(1)

        results = ab_repo.list_by_prompt(prompt.id)

        if not results:
            print_info(f"No A/B tests found for prompt '{prompt_name}'")
            return

        table = Table(title=f"A/B Tests for '{prompt_name}'")
        table.add_column("Versions", style="cyan")
        table.add_column("Winner")
        table.add_column("Confidence")
        table.add_column("Date", style="dim")

        for result in results:
            versions = f"v{result.version_a.version_number} vs v{result.version_b.version_number}"
            winner = f"v{result.winner.version_number}" if result.winner else "Tie/Undetermined"
            confidence = f"{result.confidence*100:.1f}%"
            date = result.created_at.strftime("%Y-%m-%d %H:%M")

            table.add_row(versions, winner, confidence, date)

        console.print(table)
