"""Init command - initialize pit in a project."""

from pathlib import Path

import typer

from pit.config import CONFIG_FILE, DEFAULT_DIR, get_default_config_template, is_initialized
from pit.db.database import init_database
from pit.cli.formatters import print_success, print_warning


def init_command(
    path: Path = typer.Argument(
        Path("."),
        help="Path to initialize pit in (default: current directory)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Reinitialize even if already initialized",
    ),
) -> None:
    """Initialize pit in a project directory.

    Creates a .pit directory with the database and config file.
    """
    project_path = path.resolve()

    # Check if already initialized
    if is_initialized(project_path):
        if not force:
            print_warning(f"Already initialized in {project_path}")
            print_warning("Use --force to reinitialize")
            raise typer.Exit(1)
        print_warning("Reinitializing...")

    # Create .pit directory
    pit_dir = project_path / DEFAULT_DIR
    pit_dir.mkdir(parents=True, exist_ok=True)

    # Initialize database
    init_database(project_path)

    # Create default config file if it doesn't exist
    config_file = project_path / CONFIG_FILE
    if not config_file.exists():
        config_file.write_text(get_default_config_template())

    print_success(f"Initialized pit in {project_path}")
    print_success(f"  Created {DEFAULT_DIR}/")
    print_success(f"  Created {CONFIG_FILE}")
