"""Prompt commands - add, list, show prompts."""

from pathlib import Path
from typing import Optional

import typer
from rich.prompt import Prompt as RichPrompt

from pit.config import Config, find_project_root, is_initialized
from pit.db.database import get_session
from pit.db.repository import PromptRepository, VersionRepository
from pit.cli.formatters import (
    console,
    print_error,
    print_info,
    print_prompt_detail,
    print_prompt_table,
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


@app.command("add")
def add_prompt(
    name: str = typer.Argument(..., help="Name of the prompt (e.g., 'summarize')"),
    description: Optional[str] = typer.Option(
        None,
        "--description",
        "-d",
        help="Description of the prompt",
    ),
    content: Optional[str] = typer.Option(
        None,
        "--content",
        "-c",
        help="Initial prompt content (opens editor if not provided)",
    ),
    message: str = typer.Option(
        "Initial version",
        "--message",
        "-m",
        help="Commit message for the initial version",
    ),
) -> None:
    """Add a new prompt to the project.

    Creates a new prompt and optionally its first version.
    """
    project_root = require_initialized()
    config = Config.load(project_root)

    # Validate name
    if not name.replace("-", "").replace("_", "").isalnum():
        print_error("Prompt name must be alphanumeric (hyphens and underscores allowed)")
        raise typer.Exit(1)

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        version_repo = VersionRepository(session)

        # Check if prompt already exists
        existing = prompt_repo.get_by_name(name)
        if existing:
            print_error(f"Prompt '{name}' already exists")
            raise typer.Exit(1)

        # Create the prompt
        prompt = prompt_repo.create(name=name, description=description)
        print_success(f"Created prompt '{name}'")

        # Get content interactively if not provided
        if content is None:
            console.print("\n[bold]Enter prompt content[/bold] (Ctrl+D when done):")
            lines = []
            try:
                while True:
                    line = input()
                    lines.append(line)
            except EOFError:
                pass
            content = "\n".join(lines)

        if content.strip():
            # Create initial version
            version = version_repo.create(
                prompt_id=prompt.id,
                content=content.strip(),
                message=message,
                author=config.project.default_author,
            )
            print_success(f"Created version v{version.version_number}")
        else:
            print_info("No content provided. Use 'pit commit' to add the first version.")


@app.command("list")
def list_prompts() -> None:
    """List all prompts in the project."""
    project_root = require_initialized()

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        prompts = prompt_repo.list_all()
        print_prompt_table(prompts)


@app.command("show")
def show_prompt(
    name: str = typer.Argument(..., help="Name of the prompt to show"),
    version: Optional[int] = typer.Option(
        None,
        "--version",
        "-v",
        help="Show a specific version (default: current)",
    ),
) -> None:
    """Show details of a prompt."""
    project_root = require_initialized()

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        version_repo = VersionRepository(session)

        prompt = prompt_repo.get_by_name(name)
        if not prompt:
            print_error(f"Prompt '{name}' not found")
            raise typer.Exit(1)

        if version is not None:
            ver = version_repo.get_by_number(prompt.id, version)
            if not ver:
                print_error(f"Version v{version} not found for prompt '{name}'")
                raise typer.Exit(1)
            print_prompt_detail(prompt, ver)
        else:
            print_prompt_detail(prompt)


@app.command("delete")
def delete_prompt(
    name: str = typer.Argument(..., help="Name of the prompt to delete"),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation",
    ),
) -> None:
    """Delete a prompt and all its versions."""
    project_root = require_initialized()

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)

        prompt = prompt_repo.get_by_name(name)
        if not prompt:
            print_error(f"Prompt '{name}' not found")
            raise typer.Exit(1)

        version_count = len(prompt.versions)

        if not force:
            confirm = RichPrompt.ask(
                f"Delete prompt '{name}' with {version_count} version(s)?",
                choices=["y", "n"],
                default="n",
            )
            if confirm != "y":
                print_info("Cancelled")
                raise typer.Exit(0)

        prompt_repo.delete(prompt)
        print_success(f"Deleted prompt '{name}'")
