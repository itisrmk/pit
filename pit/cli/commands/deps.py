"""Dependencies commands for external prompt dependencies."""

from pathlib import Path
from typing import Optional

import typer
from rich.tree import Tree
from rich.table import Table

from pit.config import find_project_root, is_initialized
from pit.cli.formatters import console, print_error, print_success, print_info, print_warning
from pit.core.dependencies import (
    DependencyManager, DependencySource, Dependency
)

app = typer.Typer()


def require_initialized() -> Path:
    """Ensure pit is initialized and return project root."""
    project_root = find_project_root()
    if project_root is None:
        print_error("Not a pit project. Run 'pit init' first.")
        raise typer.Exit(1)
    return project_root


@app.command("list")
def list_deps() -> None:
    """List all dependencies."""
    project_root = require_initialized()
    manager = DependencyManager(project_root)

    try:
        deps = manager.list_dependencies()
    except Exception as e:
        print_error(f"Failed to load dependencies: {e}")
        raise typer.Exit(1)

    if not deps:
        print_info("No dependencies configured")
        return

    table = Table(title="Dependencies")
    table.add_column("Name", style="cyan")
    table.add_column("Source", style="green")
    table.add_column("Path")
    table.add_column("Version", style="yellow")
    table.add_column("Status")

    for dep in deps:
        status = "✓ Installed" if dep.installed_at else "✗ Not installed"
        table.add_row(
            dep.name,
            dep.source.value,
            dep.path,
            dep.version,
            status,
        )

    console.print(table)
    print_info(f"{len(deps)} dependency(s)")


@app.command("install")
def install_deps(
    name: Optional[str] = typer.Argument(
        None,
        help="Specific dependency to install (default: all)",
    ),
) -> None:
    """Install dependencies."""
    project_root = require_initialized()
    manager = DependencyManager(project_root)

    try:
        installed = manager.install(name)
    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(1)
    except Exception as e:
        print_error(f"Installation failed: {e}")
        raise typer.Exit(1)

    if installed:
        print_success(f"Installed {len(installed)} dependency(s):")
        for lock in installed:
            print_info(f"  - {lock.name}@{lock.version}")
    else:
        print_info("No dependencies to install")


@app.command("update")
def update_deps(
    name: Optional[str] = typer.Argument(
        None,
        help="Specific dependency to update (default: all)",
    ),
) -> None:
    """Update dependencies to latest versions."""
    project_root = require_initialized()
    manager = DependencyManager(project_root)

    try:
        updated = manager.update(name)
    except Exception as e:
        print_error(f"Update failed: {e}")
        raise typer.Exit(1)

    if updated:
        print_success(f"Updated {len(updated)} dependency(s)")
    else:
        print_info("No dependencies updated")


@app.command("add")
def add_dep(
    name: str = typer.Argument(..., help="Name for the dependency"),
    source: str = typer.Argument(..., help="Source type (github, local, url)"),
    path: str = typer.Argument(..., help="Path or URL to the dependency"),
    version: str = typer.Option(
        "main",
        "--version",
        "-v",
        help="Version/tag/branch to use",
    ),
) -> None:
    """Add a new dependency.

    Examples:
        pit deps add my-dep github org/repo/path --version v1.0
        pit deps add shared local ../shared/prompts
        pit deps add remote url https://example.com/prompt.bundle
    """
    project_root = require_initialized()
    manager = DependencyManager(project_root)

    # Validate source
    try:
        dep_source = DependencySource(source)
    except ValueError:
        print_error(f"Unknown source: {source}")
        print_info("Valid sources: github, local, url")
        raise typer.Exit(1)

    try:
        dep = manager.add_dependency(name, dep_source, path, version)
    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(1)

    print_success(f"Added dependency: {name}")
    print_info(f"Source: {source}")
    print_info(f"Path: {path}")
    print_info(f"Version: {version}")
    print_info("Run 'pit deps install' to fetch it")


@app.command("remove")
def remove_dep(
    name: str = typer.Argument(..., help="Name of the dependency to remove"),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation",
    ),
) -> None:
    """Remove a dependency."""
    project_root = require_initialized()
    manager = DependencyManager(project_root)

    if not force:
        confirm = typer.confirm(f"Remove dependency '{name}'?")
        if not confirm:
            print_info("Cancelled")
            return

    removed = manager.remove_dependency(name)

    if removed:
        print_success(f"Removed dependency: {name}")
    else:
        print_warning(f"Dependency '{name}' not found")


@app.command("tree")
def dep_tree() -> None:
    """Show dependency tree."""
    project_root = require_initialized()
    manager = DependencyManager(project_root)

    try:
        tree_data = manager.get_dependency_tree()
    except Exception as e:
        print_error(f"Failed to get dependency tree: {e}")
        raise typer.Exit(1)

    if not tree_data:
        print_info("No dependencies")
        return

    tree = Tree("[bold cyan]Dependencies[/bold cyan]")

    for name, info in tree_data.items():
        source = info.get("source", "unknown")
        version = info.get("version", "unknown")
        status = "✓" if info.get("installed") else "✗"
        tree.add(f"{status} {name} [{source}@{version}]")

    console.print(tree)
