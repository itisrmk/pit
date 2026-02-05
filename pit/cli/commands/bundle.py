"""Bundle commands for packaging and sharing prompts."""

from pathlib import Path
from typing import List, Optional

import typer
from rich.table import Table
from rich.tree import Tree

from pit.config import find_project_root, is_initialized, Config
from pit.db.database import get_session
from pit.db.repository import PromptRepository, VersionRepository
from pit.cli.formatters import console, print_error, print_success, print_info, print_warning
from pit.core.bundle import (
    BundleBuilder, BundleInspector, BundleInstaller,
    BUNDLE_EXTENSION
)

app = typer.Typer()


def require_initialized() -> Path:
    """Ensure pit is initialized and return project root."""
    project_root = find_project_root()
    if project_root is None:
        print_error("Not a pit project. Run 'pit init' first.")
        raise typer.Exit(1)
    return project_root


@app.command("create")
def create_bundle(
    name: str = typer.Argument(..., help="Name of the bundle"),
    prompts: Optional[str] = typer.Option(
        None,
        "--prompts",
        "-p",
        help="Comma-separated list of prompts to include (default: all)",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help=f"Output file path (default: {{name}}{BUNDLE_EXTENSION})",
    ),
    description: Optional[str] = typer.Option(
        None,
        "--description",
        "-d",
        help="Bundle description",
    ),
    with_tests: bool = typer.Option(
        False,
        "--with-tests",
        "-t",
        help="Include test suites",
    ),
    with_history: bool = typer.Option(
        True,
        "--with-history/--no-history",
        help="Include full version history",
    ),
) -> None:
    """Create a bundle from prompts in the current project."""
    project_root = require_initialized()
    config = Config.load(project_root)

    # Determine which prompts to include
    prompt_list: Optional[List[str]] = None
    if prompts:
        prompt_list = [p.strip() for p in prompts.split(",")]

    # Build bundle
    builder = BundleBuilder(
        name=name,
        description=description,
        author=config.project.default_author,
    )

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        version_repo = VersionRepository(session)

        if prompt_list:
            # Include specified prompts
            for prompt_name in prompt_list:
                prompt = prompt_repo.get_by_name(prompt_name)
                if not prompt:
                    print_error(f"Prompt '{prompt_name}' not found")
                    raise typer.Exit(1)

                versions = version_repo.list_by_prompt(prompt.id)
                if not with_history and versions:
                    # Only include latest
                    versions = [versions[-1]]

                builder.add_prompt(
                    name=prompt.name,
                    description=prompt.description,
                    versions=[{
                        "version_number": v.version_number,
                        "content": v.content,
                        "message": v.message,
                        "author": v.author,
                        "created_at": v.created_at.isoformat() if v.created_at else None,
                        "semantic_diff": v.semantic_diff,
                    } for v in versions],
                    current_version=prompt.current_version.version_number if prompt.current_version else 1,
                    tags=prompt.current_version.tags if prompt.current_version else [],
                )
        else:
            # Include all prompts
            all_prompts = prompt_repo.list_all()
            for prompt in all_prompts:
                versions = version_repo.list_by_prompt(prompt.id)
                if not with_history and versions:
                    versions = [versions[-1]]

                builder.add_prompt(
                    name=prompt.name,
                    description=prompt.description,
                    versions=[{
                        "version_number": v.version_number,
                        "content": v.content,
                        "message": v.message,
                        "author": v.author,
                        "created_at": v.created_at.isoformat() if v.created_at else None,
                        "semantic_diff": v.semantic_diff,
                    } for v in versions],
                    current_version=prompt.current_version.version_number if prompt.current_version else 1,
                    tags=prompt.current_version.tags if prompt.current_version else [],
                )

    # Determine output path
    if output is None:
        output = f"{name}{BUNDLE_EXTENSION}"

    output_path = Path(output)
    builder.build(output_path)

    print_success(f"Created bundle: {output_path}")
    print_info(f"Included {len(builder.prompts)} prompt(s)")


@app.command("inspect")
def inspect_bundle(
    bundle_file: str = typer.Argument(..., help="Path to bundle file"),
    show_content: bool = typer.Option(
        False,
        "--content",
        "-c",
        help="Show full content of prompts",
    ),
) -> None:
    """Display information about a bundle."""
    bundle_path = Path(bundle_file)
    if not bundle_path.exists():
        print_error(f"Bundle not found: {bundle_file}")
        raise typer.Exit(1)

    try:
        inspector = BundleInspector(bundle_path)
        manifest = inspector.get_manifest()
    except Exception as e:
        print_error(f"Failed to read bundle: {e}")
        raise typer.Exit(1)

    console.print(f"[bold cyan]Bundle: {manifest.name}[/bold cyan]")
    console.print(f"Version: {manifest.bundle_version}")
    console.print(f"Created: {manifest.created_at}")

    if manifest.author:
        console.print(f"Author: {manifest.author}")

    if manifest.description:
        console.print(f"Description: {manifest.description}")

    console.print(f"\n[bold]Prompts ({len(manifest.prompts)}):[/bold]")

    for prompt_data in manifest.prompts:
        tree = Tree(f"[cyan]{prompt_data['name']}[/cyan]")

        if prompt_data.get("description"):
            tree.add(f"Description: {prompt_data['description']}")

        versions = prompt_data.get("versions", [])
        tree.add(f"Versions: {len(versions)}")

        if versions:
            ver_tree = tree.add("Version history:")
            for v in versions:
                ver_tree.add(f"v{v['version_number']}: {v.get('message', 'No message')}")

        if show_content and versions:
            # Show latest version content
            content = inspector.extract_prompt_content(
                prompt_data["name"],
                versions[-1]["version_number"]
            )
            if content:
                from rich.syntax import Syntax
                syntax = Syntax(content[:500] + "..." if len(content) > 500 else content, "text")
                tree.add(syntax)

        console.print(tree)


@app.command("install")
def install_bundle(
    bundle_file: str = typer.Argument(..., help="Path to bundle file"),
    prefix: Optional[str] = typer.Option(
        None,
        "--prefix",
        "-p",
        help="Prefix to add to installed prompt names",
    ),
    prompts: Optional[str] = typer.Option(
        None,
        "--prompts",
        help="Comma-separated list of prompts to install (default: all)",
    ),
) -> None:
    """Install prompts from a bundle."""
    project_root = require_initialized()

    bundle_path = Path(bundle_file)
    if not bundle_path.exists():
        print_error(f"Bundle not found: {bundle_file}")
        raise typer.Exit(1)

    # Determine which prompts to install
    prompt_list: Optional[List[str]] = None
    if prompts:
        prompt_list = [p.strip() for p in prompts.split(",")]

    # Install
    installer = BundleInstaller(project_root, prefix=prefix)

    try:
        installed = installer.install(bundle_path, prompt_names=prompt_list)
    except Exception as e:
        print_error(f"Installation failed: {e}")
        raise typer.Exit(1)

    if installed:
        print_success(f"Installed {len(installed)} prompt(s):")
        for name in installed:
            print_info(f"  - {name}")
    else:
        print_warning("No prompts were installed (may already exist)")


@app.command("export")
def export_bundle(
    bundle_file: str = typer.Argument(..., help="Path to bundle file"),
    format: str = typer.Option(
        "json",
        "--format",
        "-f",
        help="Export format (json or yaml)",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path (default: stdout)",
    ),
) -> None:
    """Export bundle manifest to JSON or YAML."""
    bundle_path = Path(bundle_file)
    if not bundle_path.exists():
        print_error(f"Bundle not found: {bundle_file}")
        raise typer.Exit(1)

    try:
        inspector = BundleInspector(bundle_path)
        manifest = inspector.get_manifest()
    except Exception as e:
        print_error(f"Failed to read bundle: {e}")
        raise typer.Exit(1)

    data = manifest.to_dict()

    if format == "json":
        import json
        output_text = json.dumps(data, indent=2)
    elif format == "yaml":
        try:
            import yaml
            output_text = yaml.dump(data, default_flow_style=False)
        except ImportError:
            print_error("PyYAML not installed. Install with: pip install pyyaml")
            raise typer.Exit(1)
    else:
        print_error(f"Unknown format: {format}")
        raise typer.Exit(1)

    if output:
        Path(output).write_text(output_text)
        print_success(f"Exported to {output}")
    else:
        console.print(output_text)


@app.command("list-contents")
def list_bundle_contents(
    bundle_file: str = typer.Argument(..., help="Path to bundle file"),
) -> None:
    """List all files in a bundle (like tar -tf)."""
    import tarfile

    bundle_path = Path(bundle_file)
    if not bundle_path.exists():
        print_error(f"Bundle not found: {bundle_file}")
        raise typer.Exit(1)

    try:
        with tarfile.open(bundle_path, "r:gz") as tar:
            members = tar.getmembers()

        table = Table(title=f"Contents of {bundle_path.name}")
        table.add_column("File")
        table.add_column("Size", justify="right")
        table.add_column("Type")

        for member in members:
            size = f"{member.size}" if member.isfile() else "-"
            mtype = "file" if member.isfile() else "dir" if member.isdir() else "other"
            table.add_row(member.name, size, mtype)

        console.print(table)
        print_info(f"{len(members)} entries")

    except Exception as e:
        print_error(f"Failed to read bundle: {e}")
        raise typer.Exit(1)
