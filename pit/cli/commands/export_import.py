"""Export and import commands for framework integrations."""

from pathlib import Path
from typing import Optional

import typer
from rich.table import Table

from pit.config import find_project_root, is_initialized
from pit.db.database import get_session
from pit.db.repository import PromptRepository, VersionRepository
from pit.cli.formatters import console, print_error, print_success, print_info
from pit.integrations import (
    export_prompt as export_prompt_data,
    import_prompt as import_prompt_data,
    get_integration,
    INTEGRATIONS,
)

app = typer.Typer()


def require_initialized() -> Path:
    """Ensure pit is initialized and return project root."""
    project_root = find_project_root()
    if project_root is None:
        print_error("Not a pit project. Run 'pit init' first.")
        raise typer.Exit(1)
    return project_root


@app.command("export")
def export_command(
    prompt_name: str = typer.Argument(..., help="Name of the prompt to export"),
    format: str = typer.Argument(..., help="Export format (langchain, openai, json, yaml)"),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path (default: stdout)",
    ),
    version: Optional[int] = typer.Option(
        None,
        "--version",
        "-v",
        help="Version to export (default: current)",
    ),
) -> None:
    """Export a prompt to a framework-specific format.

    Supports:
    - langchain: LangChain PromptTemplate JSON
    - openai: OpenAI Assistants instructions format
    - json: Generic JSON format
    - yaml: YAML format
    """
    project_root = require_initialized()

    # Validate format
    if format not in INTEGRATIONS:
        print_error(f"Unknown format: {format}")
        print_info(f"Available formats: {', '.join(INTEGRATIONS.keys())}")
        raise typer.Exit(1)

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        version_repo = VersionRepository(session)

        prompt = prompt_repo.get_by_name(prompt_name)
        if not prompt:
            print_error(f"Prompt '{prompt_name}' not found")
            raise typer.Exit(1)

        # Get version
        ver = None
        if version is not None:
            ver = version_repo.get_by_number(prompt.id, version)
            if not ver:
                print_error(f"Version v{version} not found")
                raise typer.Exit(1)
        else:
            ver = prompt.current_version
            if not ver:
                print_error("No current version to export")
                raise typer.Exit(1)

        # Export
        try:
            exported = export_prompt_data(prompt, format, ver)
        except ValueError as e:
            print_error(str(e))
            raise typer.Exit(1)

        # Output
        if output:
            with open(output, "w") as f:
                f.write(exported)
            print_success(f"Exported to {output}")
        else:
            console.print(exported)


@app.command("import")
def import_command(
    file_path: str = typer.Argument(..., help="Path to file to import"),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        "-n",
        help="Name for the imported prompt (default: from file)",
    ),
    format: Optional[str] = typer.Option(
        None,
        "--format",
        "-f",
        help="Import format (auto-detected from extension if not specified)",
    ),
    message: str = typer.Option(
        "Imported from external format",
        "--message",
        "-m",
        help="Commit message for initial version",
    ),
) -> None:
    """Import a prompt from a file.

    Auto-detects format from file extension:
    - .json -> langchain or generic JSON
    - .yaml/.yml -> YAML
    - .md -> OpenAI Assistants
    """
    project_root = require_initialized()

    # Read file
    try:
        with open(file_path, "r") as f:
            data = f.read()
    except FileNotFoundError:
        print_error(f"File not found: {file_path}")
        raise typer.Exit(1)

    # Detect format
    if format is None:
        format = _detect_format(file_path, data)
        if format is None:
            print_error("Could not auto-detect format. Use --format to specify.")
            raise typer.Exit(1)
        print_info(f"Auto-detected format: {format}")

    # Validate format
    if format not in INTEGRATIONS:
        print_error(f"Unknown format: {format}")
        print_info(f"Available formats: {', '.join(INTEGRATIONS.keys())}")
        raise typer.Exit(1)

    # Import
    try:
        imported = import_prompt_data(data, format, name)
    except Exception as e:
        print_error(f"Import failed: {e}")
        raise typer.Exit(1)

    # Create prompt
    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        version_repo = VersionRepository(session)

        from pit.config import Config
        config = Config.load(project_root)

        # Check for existing
        if prompt_repo.get_by_name(imported.name):
            print_error(f"Prompt '{imported.name}' already exists")
            raise typer.Exit(1)

        # Create prompt
        prompt = prompt_repo.create(
            name=imported.name,
            description=imported.description,
        )

        # Create initial version
        version = version_repo.create(
            prompt_id=prompt.id,
            content=imported.content,
            message=message,
            author=config.project.default_author,
        )

        print_success(f"Imported prompt '{imported.name}' as v{version.version_number}")
        print_info(f"Variables detected: {', '.join(imported.variables) if imported.variables else 'None'}")


def _detect_format(file_path: str, data: str) -> Optional[str]:
    """Auto-detect format from file path and content."""
    path = Path(file_path)
    extension = path.suffix.lower()

    # Check extension
    if extension in [".yaml", ".yml"]:
        return "yaml"
    elif extension == ".md":
        return "openai"
    elif extension == ".json":
        # Try to determine if it's LangChain or generic
        try:
            import json
            parsed = json.loads(data)
            if "template" in parsed or "input_variables" in parsed:
                return "langchain"
            return "json"
        except json.JSONDecodeError:
            return None

    # Try content detection
    try:
        import json
        json.loads(data)
        return "json"
    except json.JSONDecodeError:
        pass

    if data.strip().startswith("---") or ":" in data[:100]:
        return "yaml"

    return None


@app.command("formats")
def list_formats() -> None:
    """List available export/import formats."""
    table = Table(title="Available Formats")
    table.add_column("Format", style="cyan")
    table.add_column("Extension")
    table.add_column("Description")

    descriptions = {
        "langchain": "LangChain PromptTemplate JSON format",
        "openai": "OpenAI Assistants instructions format",
        "json": "Generic JSON format",
        "yaml": "YAML format",
    }

    for name, cls in INTEGRATIONS.items():
        integration = cls()
        table.add_row(
            name,
            integration.get_file_extension(),
            descriptions.get(name, ""),
        )

    console.print(table)


@app.command("sync")
def sync_command(
    prompt_name: str = typer.Argument(..., help="Name of the prompt to sync"),
    format: str = typer.Argument(..., help="Sync format (langchain, openai)"),
    output_dir: str = typer.Option(
        ".",
        "--output-dir",
        "-d",
        help="Output directory for synced files",
    ),
) -> None:
    """Sync a prompt to a framework-specific file.

    Exports the prompt to a file and maintains a mapping
    for bidirectional synchronization.
    """
    project_root = require_initialized()

    if format not in INTEGRATIONS:
        print_error(f"Unknown format: {format}")
        raise typer.Exit(1)

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        version_repo = VersionRepository(session)

        prompt = prompt_repo.get_by_name(prompt_name)
        if not prompt:
            print_error(f"Prompt '{prompt_name}' not found")
            raise typer.Exit(1)

        ver = prompt.current_version
        if not ver:
            print_error("No current version to sync")
            raise typer.Exit(1)

        # Export
        exported = export_prompt_data(prompt, format, ver)

        # Write file
        integration = get_integration(format)
        ext = integration.get_file_extension()
        output_path = Path(output_dir) / f"{prompt_name}{ext}"

        # Ensure directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            f.write(exported)

        print_success(f"Synced '{prompt_name}' to {output_path}")

        # Create/update sync mapping
        sync_file = Path(project_root) / ".pit" / "sync_mapping.json"
        sync_file.parent.mkdir(parents=True, exist_ok=True)

        import json
        mapping = {}
        if sync_file.exists():
            with open(sync_file) as f:
                mapping = json.load(f)

        mapping[prompt_name] = {
            "format": format,
            "path": str(output_path),
            "version": ver.version_number,
        }

        with open(sync_file, "w") as f:
            json.dump(mapping, f, indent=2)
