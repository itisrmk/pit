"""Security scan commands for prompts."""

import json
from pathlib import Path
from typing import Optional

import typer
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax

from pit.config import find_project_root, is_initialized
from pit.db.database import get_session
from pit.db.repository import PromptRepository, FragmentRepository
from pit.cli.formatters import (
    console,
    print_error,
    print_info,
    print_success,
    print_warning,
)
from pit.core.security import SecurityScanner, Severity

app = typer.Typer()


def require_initialized() -> Path:
    """Ensure pit is initialized and return project root."""
    project_root = find_project_root()
    if project_root is None:
        print_error("Not a pit project. Run 'pit init' first.")
        raise typer.Exit(1)
    return project_root


@app.command()
def scan(
    target: str = typer.Argument(..., help="Name of prompt or 'all' for all prompts"),
    severity: str = typer.Option(
        "medium",
        "--severity",
        "-s",
        help="Minimum severity to report: critical, high, medium, low, info",
    ),
    json_output: Optional[str] = typer.Option(
        None,
        "--json",
        "-j",
        help="Output results as JSON file",
    ),
    fail_on: str = typer.Option(
        "high",
        "--fail-on",
        "-f",
        help="Fail if finding of this severity or higher is found",
    ),
) -> None:
    """Scan prompts for security vulnerabilities.

    Detects prompt injection attempts, data leakage risks,
    and OWASP LLM Top 10 compliance issues.
    """
    project_root = require_initialized()

    # Parse severity levels
    severity_map = {
        "critical": Severity.CRITICAL,
        "high": Severity.HIGH,
        "medium": Severity.MEDIUM,
        "low": Severity.LOW,
        "info": Severity.INFO,
    }

    min_severity = severity_map.get(severity.lower(), Severity.MEDIUM)
    fail_severity = severity_map.get(fail_on.lower(), Severity.HIGH)

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        scanner = SecurityScanner()

        if target == "all":
            prompts = prompt_repo.list_all()
            if not prompts:
                print_info("No prompts found")
                raise typer.Exit(0)
        else:
            prompt = prompt_repo.get_by_name(target)
            if not prompt:
                print_error(f"Prompt '{target}' not found")
                raise typer.Exit(1)
            prompts = [prompt]

        all_results = []
        has_failures = False

        for prompt in prompts:
            if not prompt.current_version:
                print_info(f"Skipping '{prompt.name}' - no versions")
                continue

            content = prompt.current_version.content
            findings = scanner.scan(content, context="system")

            # Filter by severity
            findings = [f for f in findings if _severity_at_least(f.severity, min_severity)]

            if findings:
                all_results.append({
                    "prompt": prompt.name,
                    "findings": findings,
                })

                # Check for failures
                for f in findings:
                    if _severity_at_least(f.severity, fail_severity):
                        has_failures = True

        # Display results
        if all_results:
            _display_scan_results(all_results)
        else:
            print_success("✓ No security issues found!")

        # JSON output
        if json_output:
            _export_json(all_results, json_output)
            print_success(f"Results exported to {json_output}")

        # Exit with error if failures found
        if has_failures:
            print_error(f"\nSecurity scan failed: found issues at {fail_on} severity or higher")
            raise typer.Exit(1)


def _severity_at_least(severity: Severity, minimum: Severity) -> bool:
    """Check if severity is at least as high as minimum."""
    order = [Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
    return order.index(severity) >= order.index(minimum)


def _display_scan_results(results: list[dict]) -> None:
    """Display scan results in a formatted table."""
    console.print("\n[bold red]Security Scan Results[/bold red]\n")

    for item in results:
        prompt_name = item["prompt"]
        findings = item["findings"]

        # Summary panel
        summary = scanner_summary(findings)
        console.print(Panel(
            summary,
            title=f"[bold]{prompt_name}[/bold]",
            border_style="red" if any(f.severity == Severity.CRITICAL for f in findings) else "yellow",
        ))

        # Findings table
        table = Table(show_header=True, header_style="bold")
        table.add_column("Severity", justify="center", width=10)
        table.add_column("Rule")
        table.add_column("Description")
        table.add_column("Line")

        for finding in findings:
            severity_style = {
                Severity.CRITICAL: "bold red",
                Severity.HIGH: "red",
                Severity.MEDIUM: "yellow",
                Severity.LOW: "blue",
                Severity.INFO: "dim",
            }.get(finding.severity, "white")

            table.add_row(
                f"[{severity_style}]{finding.severity.value.upper()}[/{severity_style}]",
                finding.rule_id,
                finding.description,
                str(finding.line_number) if finding.line_number else "-",
            )

        console.print(table)

        # Show detailed recommendations
        console.print("\n[bold]Recommendations:[/bold]")
        seen_recs = set()
        for finding in findings:
            if finding.recommendation and finding.recommendation not in seen_recs:
                console.print(f"  • {finding.recommendation}")
                seen_recs.add(finding.recommendation)

        console.print()


def scanner_summary(findings: list) -> str:
    """Generate summary text for findings."""
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for f in findings:
        counts[f.severity.value] += 1

    parts = []
    if counts["critical"]:
        parts.append(f"[bold red]Critical: {counts['critical']}[/bold red]")
    if counts["high"]:
        parts.append(f"[red]High: {counts['high']}[/red]")
    if counts["medium"]:
        parts.append(f"[yellow]Medium: {counts['medium']}[/yellow]")
    if counts["low"]:
        parts.append(f"[blue]Low: {counts['low']}[/blue]")
    if counts["info"]:
        parts.append(f"[dim]Info: {counts['info']}[/dim]")

    return " | ".join(parts) if parts else "No issues found"


def _export_json(results: list[dict], output_path: str) -> None:
    """Export scan results to JSON."""
    export_data = []
    for item in results:
        export_data.append({
            "prompt": item["prompt"],
            "findings": [
                {
                    "rule_id": f.rule_id,
                    "title": f.title,
                    "description": f.description,
                    "severity": f.severity.value,
                    "category": f.category,
                    "line_number": f.line_number,
                    "snippet": f.snippet,
                    "recommendation": f.recommendation,
                }
                for f in item["findings"]
            ],
        })

    with open(output_path, "w") as f:
        json.dump(export_data, f, indent=2)


@app.command()
def check(
    prompt_name: str = typer.Argument(..., help="Name of the prompt"),
    version: Optional[int] = typer.Option(
        None,
        "--version",
        "-v",
        help="Version to check (default: current)",
    ),
) -> None:
    """Quick security check with detailed output."""
    project_root = require_initialized()

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        version_repo = None

        prompt = prompt_repo.get_by_name(prompt_name)
        if not prompt:
            print_error(f"Prompt '{prompt_name}' not found")
            raise typer.Exit(1)

        if version is not None:
            from pit.db.repository import VersionRepository
            version_repo = VersionRepository(session)
            ver = version_repo.get_by_number(prompt.id, version)
            if not ver:
                print_error(f"Version v{version} not found")
                raise typer.Exit(1)
        else:
            ver = prompt.current_version
            if not ver:
                print_error("No current version")
                raise typer.Exit(1)

        # Scan
        scanner = SecurityScanner()
        findings = scanner.scan(ver.content, context="system")

        # Display content with line numbers
        console.print(f"\n[bold cyan]Prompt: {prompt_name} v{ver.version_number}[/bold cyan]\n")

        lines = ver.content.split("\n")
        numbered_content = "\n".join(f"{i+1:4d} | {line}" for i, line in enumerate(lines))
        syntax = Syntax(numbered_content, "markdown", theme="monokai", line_numbers=False)
        console.print(syntax)

        # Display findings
        if findings:
            console.print("\n[bold red]Security Issues:[/bold red]\n")
            for finding in findings:
                color = {
                    Severity.CRITICAL: "red",
                    Severity.HIGH: "red",
                    Severity.MEDIUM: "yellow",
                    Severity.LOW: "blue",
                    Severity.INFO: "dim",
                }.get(finding.severity, "white")

                console.print(Panel(
                    f"[bold]{finding.title}[/bold]\n"
                    f"[dim]{finding.description}[/dim]\n\n"
                    f"[bold]Category:[/bold] {finding.category}\n"
                    f"[bold]Recommendation:[/bold] {finding.recommendation}",
                    title=f"[{color}]{finding.severity.value.upper()}[/{color}] - {finding.rule_id}",
                    border_style=color,
                ))
        else:
            print_success("\n✓ No security issues found!")


@app.command()
def validate(
    prompt_name: str = typer.Argument(..., help="Name of the prompt"),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Fail on medium severity and higher",
    ),
) -> None:
    """Validate prompt against OWASP LLM Top 10."""
    project_root = require_initialized()

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)

        prompt = prompt_repo.get_by_name(prompt_name)
        if not prompt or not prompt.current_version:
            print_error(f"Prompt '{prompt_name}' not found or has no versions")
            raise typer.Exit(1)

        scanner = SecurityScanner()
        findings = scanner.scan(prompt.current_version.content, context="system")

        # Group by OWASP category
        categories = {}
        for finding in findings:
            if finding.category not in categories:
                categories[finding.category] = []
            categories[finding.category].append(finding)

        # Display OWASP compliance
        console.print(f"\n[bold cyan]OWASP LLM Top 10 Compliance Check[/bold cyan]\n")
        console.print(f"Prompt: [bold]{prompt_name}[/bold]\n")

        table = Table(show_header=True, header_style="bold")
        table.add_column("Category")
        table.add_column("Status", justify="center")
        table.add_column("Issues")

        all_categories = [
            "Prompt Injection",
            "Insecure Output Handling",
            "Training Data Poisoning",
            "Model Denial of Service",
            "Supply Chain Vulnerabilities",
            "Sensitive Information Disclosure",
            "Insecure Plugin Design",
            "Excessive Agency",
            "Overreliance",
            "Model Theft",
        ]

        for category in all_categories:
            cat_findings = categories.get(category, [])
            if cat_findings:
                critical = len([f for f in cat_findings if f.severity == Severity.CRITICAL])
                high = len([f for f in cat_findings if f.severity == Severity.HIGH])

                if critical > 0:
                    status = "[bold red]FAIL[/bold red]"
                elif high > 0:
                    status = "[red]WARN[/red]"
                else:
                    status = "[yellow]REVIEW[/yellow]"

                issue_summary = f"{len(cat_findings)} finding(s)"
                if critical > 0:
                    issue_summary += f", {critical} critical"
            else:
                status = "[green]PASS[/green]"
                issue_summary = "-"

            table.add_row(category, status, issue_summary)

        console.print(table)

        # Overall compliance
        critical_count = len([f for f in findings if f.severity == Severity.CRITICAL])
        high_count = len([f for f in findings if f.severity == Severity.HIGH])
        medium_count = len([f for f in findings if f.severity == Severity.MEDIUM])

        if critical_count > 0 or high_count > 0:
            print_error(f"\n✗ Compliance check failed: {critical_count} critical, {high_count} high issues")
            raise typer.Exit(1)
        elif strict and medium_count > 0:
            print_warning(f"\n⚠ Compliance check failed (strict mode): {medium_count} medium issues")
            raise typer.Exit(1)
        else:
            print_success(f"\n✓ Compliance check passed")
