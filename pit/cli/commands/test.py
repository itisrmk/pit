"""Test framework commands for regression testing."""

import json
import time
from pathlib import Path
from typing import Optional

import typer
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from pit.config import Config, find_project_root, is_initialized
from pit.db.database import get_session
from pit.db.repository import (
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
    format_datetime,
)
from pit.db.models import TestCase

app = typer.Typer()


def require_initialized() -> Path:
    """Ensure pit is initialized and return project root."""
    project_root = find_project_root()
    if project_root is None:
        print_error("Not a pit project. Run 'pit init' first.")
        raise typer.Exit(1)
    return project_root


@app.command("create-suite")
def create_suite(
    prompt_name: str = typer.Argument(..., help="Name of the prompt to test"),
    suite_name: str = typer.Argument(..., help="Name for the test suite"),
    description: Optional[str] = typer.Option(
        None,
        "--description",
        "-d",
        help="Description of the test suite",
    ),
) -> None:
    """Create a new test suite for a prompt."""
    project_root = require_initialized()

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        suite_repo = TestSuiteRepository(session)

        prompt = prompt_repo.get_by_name(prompt_name)
        if not prompt:
            print_error(f"Prompt '{prompt_name}' not found")
            raise typer.Exit(1)

        suite = suite_repo.create(
            name=suite_name,
            prompt_id=prompt.id,
            description=description,
        )
        print_success(f"Created test suite '{suite_name}' for prompt '{prompt_name}'")
        print_info(f"Suite ID: {suite.id}")


@app.command("add-case")
def add_test_case(
    suite_id: str = typer.Argument(..., help="ID of the test suite"),
    input_data: Optional[str] = typer.Option(
        None,
        "--input",
        "-i",
        help="Input data as JSON string or @file.json",
    ),
    expected: Optional[str] = typer.Option(
        None,
        "--expected",
        "-e",
        help="Expected criteria as JSON string or @file.json",
    ),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        "-n",
        help="Name for this test case",
    ),
) -> None:
    """Add a test case to a suite."""
    project_root = require_initialized()

    with get_session(project_root) as session:
        suite_repo = TestSuiteRepository(session)
        case_repo = TestCaseRepository(session)

        suite = suite_repo.get_by_id(suite_id)
        if not suite:
            print_error(f"Test suite '{suite_id}' not found")
            raise typer.Exit(1)

        # Parse input data
        if input_data is None:
            console.print("[bold]Enter input data as JSON:[/bold]")
            input_lines = []
            try:
                while True:
                    line = input()
                    input_lines.append(line)
            except EOFError:
                pass
            input_data = "\n".join(input_lines)

        parsed_input = _parse_json_input(input_data)
        if parsed_input is None:
            print_error("Invalid JSON input data")
            raise typer.Exit(1)

        # Parse expected criteria
        parsed_expected = None
        if expected:
            parsed_expected = _parse_json_input(expected)
            if parsed_expected is None:
                print_error("Invalid JSON expected criteria")
                raise typer.Exit(1)

        test_case = case_repo.create(
            suite_id=suite_id,
            input_data=parsed_input,
            expected_criteria=parsed_expected,
            name=name,
        )
        print_success(f"Added test case to suite '{suite.name}'")
        print_info(f"Case ID: {test_case.id}")


@app.command("list-suites")
def list_suites(
    prompt_name: str = typer.Argument(..., help="Name of the prompt"),
) -> None:
    """List all test suites for a prompt."""
    project_root = require_initialized()

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        suite_repo = TestSuiteRepository(session)

        prompt = prompt_repo.get_by_name(prompt_name)
        if not prompt:
            print_error(f"Prompt '{prompt_name}' not found")
            raise typer.Exit(1)

        suites = suite_repo.list_by_prompt(prompt.id)

        if not suites:
            print_info(f"No test suites found for prompt '{prompt_name}'")
            return

        table = Table(title=f"Test Suites for '{prompt_name}'")
        table.add_column("Name", style="cyan")
        table.add_column("ID", style="dim")
        table.add_column("Cases", justify="center")
        table.add_column("Description")

        for suite in suites:
            case_count = len(suite.test_cases)
            desc = (suite.description or "")[:40]
            if suite.description and len(suite.description) > 40:
                desc += "..."
            table.add_row(
                suite.name,
                suite.id[:8],
                str(case_count),
                desc or "[dim]No description[/dim]",
            )

        console.print(table)


@app.command("list-cases")
def list_cases(
    suite_id: str = typer.Argument(..., help="ID of the test suite"),
) -> None:
    """List all test cases in a suite."""
    project_root = require_initialized()

    with get_session(project_root) as session:
        suite_repo = TestSuiteRepository(session)
        case_repo = TestCaseRepository(session)

        suite = suite_repo.get_by_id(suite_id)
        if not suite:
            print_error(f"Test suite '{suite_id}' not found")
            raise typer.Exit(1)

        cases = case_repo.list_by_suite(suite_id)

        if not cases:
            print_info(f"No test cases found in suite '{suite.name}'")
            return

        table = Table(title=f"Test Cases in '{suite.name}'")
        table.add_column("#", justify="center", style="cyan")
        table.add_column("Name/ID")
        table.add_column("Input Preview")

        for i, case in enumerate(cases, 1):
            name = case.name or case.id[:8]
            input_preview = json.dumps(case.input_data)[:50]
            if len(json.dumps(case.input_data)) > 50:
                input_preview += "..."
            table.add_row(str(i), name, input_preview)

        console.print(table)


@app.command("run")
def run_tests(
    prompt_name: str = typer.Argument(..., help="Name of the prompt to test"),
    suite: Optional[str] = typer.Option(
        None,
        "--suite",
        "-s",
        help="Test suite name or ID (default: all suites)",
    ),
    version: Optional[int] = typer.Option(
        None,
        "--version",
        "-v",
        help="Version to test (default: current)",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file for HTML report",
    ),
    json_output: Optional[str] = typer.Option(
        None,
        "--json",
        help="Output file for JSON results",
    ),
) -> None:
    """Run regression tests for a prompt.

    Executes all test cases in the specified suite(s) against
    the given version and reports on pass/fail status and performance.
    """
    project_root = require_initialized()

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        version_repo = VersionRepository(session)
        suite_repo = TestSuiteRepository(session)
        run_repo = TestRunRepository(session)

        prompt = prompt_repo.get_by_name(prompt_name)
        if not prompt:
            print_error(f"Prompt '{prompt_name}' not found")
            raise typer.Exit(1)

        # Get version to test
        if version is not None:
            ver = version_repo.get_by_number(prompt.id, version)
            if not ver:
                print_error(f"Version v{version} not found")
                raise typer.Exit(1)
        else:
            ver = prompt.current_version
            if not ver:
                print_error(f"No current version for prompt '{prompt_name}'")
                raise typer.Exit(1)

        # Get test suites
        if suite:
            suites = [s for s in suite_repo.list_by_prompt(prompt.id) if s.name == suite or s.id == suite]
            if not suites:
                print_error(f"Test suite '{suite}' not found")
                raise typer.Exit(1)
        else:
            suites = suite_repo.list_by_prompt(prompt.id)
            if not suites:
                print_error(f"No test suites found for prompt '{prompt_name}'")
                raise typer.Exit(1)

        # Run tests
        all_results = []
        for test_suite in suites:
            results = _run_test_suite(run_repo, ver, test_suite)
            all_results.append(results)

        # Display results
        _display_test_results(all_results, ver)

        # Generate reports
        if output:
            _generate_html_report(all_results, output, prompt_name, ver)
            print_success(f"HTML report saved to {output}")

        if json_output:
            _generate_json_report(all_results, json_output)
            print_success(f"JSON report saved to {json_output}")


def _run_test_suite(
    run_repo: TestRunRepository,
    version,
    test_suite,
) -> dict:
    """Run a test suite and return results."""
    from pit.core.llm.provider import get_llm_provider
    from pit.config import Config

    project_root = find_project_root()
    config = Config.load(project_root)

    # Create test run record
    test_run = run_repo.create(
        version_id=version.id,
        suite_id=test_suite.id,
        status="running",
    )

    cases = test_suite.test_cases
    results = {
        "suite_name": test_suite.name,
        "suite_id": test_suite.id,
        "version": version.version_number,
        "version_id": version.id,
        "total": len(cases),
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "cases": [],
        "metrics": {
            "total_time_ms": 0,
            "avg_latency_ms": 0,
            "total_tokens": 0,
        },
    }

    if not cases:
        run_repo.update_results(test_run, results, results["metrics"], "completed")
        return results

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
        task = progress.add_task(f"Running {len(cases)} test case(s)...", total=len(cases))

        for case in cases:
            case_result = _run_single_test(case, version, provider)
            results["cases"].append(case_result)

            if case_result["status"] == "passed":
                results["passed"] += 1
            elif case_result["status"] == "failed":
                results["failed"] += 1
            else:
                results["errors"] += 1

            results["metrics"]["total_time_ms"] += case_result.get("latency_ms", 0)
            results["metrics"]["total_tokens"] += case_result.get("token_usage", 0)

            progress.advance(task)

    # Calculate averages
    if cases:
        results["metrics"]["avg_latency_ms"] = results["metrics"]["total_time_ms"] / len(cases)

    run_repo.update_results(test_run, results, results["metrics"], "completed")
    return results


def _run_single_test(
    test_case: TestCase,
    version,
    provider,
) -> dict:
    """Run a single test case."""
    start_time = time.time()

    result = {
        "case_id": test_case.id,
        "case_name": test_case.name,
        "status": "error",
        "output": None,
        "latency_ms": 0,
        "token_usage": 0,
        "error": None,
    }

    try:
        # Prepare prompt content with variables
        content = version.content
        if test_case.input_data:
            # Simple variable substitution
            for key, value in test_case.input_data.items():
                placeholder = f"{{{{{key}}}}}"
                content = content.replace(placeholder, str(value))

        if provider:
            # Call LLM provider
            response = provider.generate(content)
            result["output"] = response.text
            result["token_usage"] = response.token_usage or 0
        else:
            # Mock execution - just check if variables were substituted
            result["output"] = content
            result["token_usage"] = len(content.split())

        # Check against expected criteria
        result["status"] = "passed"
        if test_case.expected_criteria:
            passed = _evaluate_criteria(result["output"], test_case.expected_criteria)
            result["status"] = "passed" if passed else "failed"

    except Exception as e:
        result["error"] = str(e)
        result["status"] = "error"

    result["latency_ms"] = (time.time() - start_time) * 1000
    return result


def _evaluate_criteria(output: str, criteria: dict) -> bool:
    """Evaluate if output matches expected criteria."""
    # Simple criteria evaluation
    if "contains" in criteria:
        if criteria["contains"] not in output:
            return False
    if "not_contains" in criteria:
        if criteria["not_contains"] in output:
            return False
    if "starts_with" in criteria:
        if not output.startswith(criteria["starts_with"]):
            return False
    if "ends_with" in criteria:
        if not output.endswith(criteria["ends_with"]):
            return False
    if "min_length" in criteria:
        if len(output) < criteria["min_length"]:
            return False
    if "max_length" in criteria:
        if len(output) > criteria["max_length"]:
            return False
    return True


def _display_test_results(results_list: list[dict], version) -> None:
    """Display test results in a formatted table."""
    console.print(f"\n[bold cyan]Test Results for v{version.version_number}[/bold cyan]")

    for results in results_list:
        suite_name = results["suite_name"]
        total = results["total"]
        passed = results["passed"]
        failed = results["failed"]
        errors = results["errors"]

        # Summary panel
        status_color = "green" if failed == 0 and errors == 0 else "red"
        summary = (
            f"[bold]{suite_name}[/bold]\n"
            f"Passed: [green]{passed}[/green] | "
            f"Failed: [red]{failed}[/red] | "
            f"Errors: [yellow]{errors}[/yellow] | "
            f"Total: {total}"
        )
        console.print(Panel(summary, border_style=status_color))

        # Individual cases
        if results["cases"]:
            table = Table(show_header=True, header_style="bold")
            table.add_column("Case", style="cyan")
            table.add_column("Status")
            table.add_column("Latency")
            table.add_column("Preview")

            for case in results["cases"]:
                status_color = {
                    "passed": "green",
                    "failed": "red",
                    "error": "yellow",
                }.get(case["status"], "white")

                output_preview = (case.get("output") or "")[:40]
                if case.get("output") and len(case["output"]) > 40:
                    output_preview += "..."

                table.add_row(
                    case.get("case_name") or case["case_id"][:8],
                    f"[{status_color}]{case['status'].upper()}[/{status_color}]",
                    f"{case.get('latency_ms', 0):.0f}ms",
                    output_preview or "[dim]N/A[/dim]",
                )

            console.print(table)

        # Metrics
        metrics = results["metrics"]
        console.print(
            f"[dim]Total time: {metrics['total_time_ms']:.0f}ms | "
            f"Avg latency: {metrics['avg_latency_ms']:.0f}ms | "
            f"Total tokens: {metrics['total_tokens']}[/dim]\n"
        )


def _generate_html_report(results_list: list[dict], output_path: str, prompt_name: str, version) -> None:
    """Generate an HTML report of test results."""
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Test Report: {prompt_name} v{version.version_number}</title>
    <style>
        body {{ font-family: sans-serif; margin: 40px; }}
        .header {{ margin-bottom: 30px; }}
        .suite {{ margin: 20px 0; border: 1px solid #ddd; padding: 20px; border-radius: 8px; }}
        .passed {{ color: green; }}
        .failed {{ color: red; }}
        .error {{ color: orange; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
        th, td {{ text-align: left; padding: 8px; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #f5f5f5; }}
        .metrics {{ background-color: #f9f9f9; padding: 10px; border-radius: 4px; margin-top: 10px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Test Report: {prompt_name}</h1>
        <p>Version: v{version.version_number}</p>
        <p>Generated: {format_datetime(__import__('datetime').datetime.now())}</p>
    </div>
"""

    for results in results_list:
        suite_name = results["suite_name"]
        total = results["total"]
        passed = results["passed"]
        failed = results["failed"]

        html += f"""
    <div class="suite">
        <h2>{suite_name}</h2>
        <p>
            <span class="passed">Passed: {passed}</span> |
            <span class="failed">Failed: {failed}</span> |
            Total: {total}
        </p>
        <table>
            <tr>
                <th>Case</th>
                <th>Status</th>
                <th>Latency</th>
                <th>Output Preview</th>
            </tr>
"""
        for case in results["cases"]:
            status_class = case["status"]
            output = (case.get("output") or "")[:50]
            html += f"""
            <tr>
                <td>{case.get('case_name') or case['case_id'][:8]}</td>
                <td class="{status_class}">{case['status'].upper()}</td>
                <td>{case.get('latency_ms', 0):.0f}ms</td>
                <td><code>{output}</code></td>
            </tr>
"""

        metrics = results["metrics"]
        html += f"""
        </table>
        <div class="metrics">
            <strong>Metrics:</strong>
            Total time: {metrics['total_time_ms']:.0f}ms |
            Avg latency: {metrics['avg_latency_ms']:.0f}ms |
            Total tokens: {metrics['total_tokens']}
        </div>
    </div>
"""

    html += """
</body>
</html>
"""

    with open(output_path, "w") as f:
        f.write(html)


def _generate_json_report(results_list: list[dict], output_path: str) -> None:
    """Generate a JSON report of test results."""
    with open(output_path, "w") as f:
        json.dump(results_list, f, indent=2)


def _parse_json_input(input_str: str) -> Optional[dict]:
    """Parse JSON input, handling file references."""
    if input_str.startswith("@"):
        file_path = input_str[1:]
        try:
            with open(file_path, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None
    else:
        try:
            return json.loads(input_str)
        except json.JSONDecodeError:
            return None
