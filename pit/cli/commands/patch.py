"""Patch commands for sharing prompt changes."""

from pathlib import Path
from typing import Optional

import typer
from rich.syntax import Syntax

from pit.config import find_project_root, is_initialized, Config
from pit.db.database import get_session
from pit.db.repository import PromptRepository, VersionRepository
from pit.cli.formatters import console, print_error, print_success, print_info
from pit.core.patch import PatchGenerator, PatchApplier, PromptPatch, PATCH_EXTENSION

app = typer.Typer()


def require_initialized() -> Path:
    """Ensure pit is initialized and return project root."""
    project_root = find_project_root()
    if project_root is None:
        print_error("Not a pit project. Run 'pit init' first.")
        raise typer.Exit(1)
    return project_root


@app.command("create")
def create_patch(
    prompt_name: str = typer.Argument(..., help="Name of the prompt"),
    from_version: str = typer.Argument(..., help="Source version (e.g., v1 or 1)"),
    to_version: str = typer.Argument(..., help="Target version (e.g., v2 or 2)"),
    output: str = typer.Option(
        None,
        "--output",
        "-o",
        help=f"Output file path (default: <prompt>_<v1>_{PATCH_EXTENSION})",
    ),
    description: Optional[str] = typer.Option(
        None,
        "--description",
        "-d",
        help="Description of the patch",
    ),
) -> None:
    """Create a patch file from two versions of a prompt."""
    project_root = require_initialized()
    config = Config.load(project_root)

    # Parse version numbers
    from_ver_num = _parse_version(from_version)
    to_ver_num = _parse_version(to_version)

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        version_repo = VersionRepository(session)

        # Find prompt
        prompt = prompt_repo.get_by_name(prompt_name)
        if not prompt:
            print_error(f"Prompt '{prompt_name}' not found")
            raise typer.Exit(1)

        # Get versions
        old_version = version_repo.get_by_number(prompt.id, from_ver_num)
        if not old_version:
            print_error(f"Version v{from_ver_num} not found")
            raise typer.Exit(1)

        new_version = version_repo.get_by_number(prompt.id, to_ver_num)
        if not new_version:
            print_error(f"Version v{to_ver_num} not found")
            raise typer.Exit(1)

        # Generate patch
        generator = PatchGenerator(author=config.project.default_author)
        patch = generator.generate(
            prompt_name=prompt_name,
            old_version=old_version,
            new_version=new_version,
            description=description,
        )

        # Determine output path
        if output is None:
            output = f"{prompt_name}_v{from_ver_num}_to_v{to_ver_num}{PATCH_EXTENSION}"

        output_path = Path(output)
        patch.save(output_path)

        print_success(f"Created patch: {output_path}")
        print_info(f"Hash: {patch.patch_hash}")
        print_info(f"From v{from_ver_num} to v{to_ver_num}")


@app.command("apply")
def apply_patch(
    patch_file: str = typer.Argument(..., help="Path to patch file"),
    to_prompt: Optional[str] = typer.Option(
        None,
        "--to",
        "-t",
        help="Target prompt name (default: from patch metadata)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Apply even if content doesn't match exactly",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Show what would be applied without making changes",
    ),
) -> None:
    """Apply a patch file to a prompt."""
    project_root = require_initialized()
    config = Config.load(project_root)

    # Load patch
    patch_path = Path(patch_file)
    if not patch_path.exists():
        print_error(f"Patch file not found: {patch_file}")
        raise typer.Exit(1)

    try:
        patch = PromptPatch.load(patch_path)
    except Exception as e:
        print_error(f"Failed to load patch: {e}")
        raise typer.Exit(1)

    # Determine target prompt
    target_name = to_prompt or patch.metadata.source_prompt

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        version_repo = VersionRepository(session)

        # Find target prompt
        prompt = prompt_repo.get_by_name(target_name)
        if not prompt:
            print_error(f"Prompt '{target_name}' not found")
            raise typer.Exit(1)

        # Get current version content
        current_version = prompt.current_version
        if not current_version:
            print_error("No current version to apply patch to")
            raise typer.Exit(1)

        target_content = current_version.content

        # Check if patch can be applied
        applier = PatchApplier(project_root)
        can_apply, reason = applier.can_apply(patch, target_content)

        if dry_run:
            preview = applier.preview(patch, target_content)
            console.print(preview)
            return

        if not can_apply and not force:
            print_error(f"Cannot apply patch: {reason}")
            print_info("Use --force to attempt fuzzy matching")
            raise typer.Exit(1)

        # Apply patch
        try:
            if can_apply:
                new_content = applier.apply(patch, target_content)
            else:
                # Try fuzzy apply
                new_content = applier.apply_fuzzy(patch, target_content)
                if new_content is None:
                    print_error("Fuzzy apply failed")
                    raise typer.Exit(1)
                print_info("Applied with fuzzy matching")

            # Create new version
            version = version_repo.create(
                prompt_id=prompt.id,
                content=new_content,
                message=f"Applied patch from {patch.metadata.source_prompt} v{patch.metadata.source_versions[0]}-v{patch.metadata.source_versions[1]}",
                author=config.project.default_author,
            )

            print_success(f"Applied patch as v{version.version_number}")

        except ValueError as e:
            print_error(f"Apply failed: {e}")
            raise typer.Exit(1)


@app.command("show")
def show_patch(
    patch_file: str = typer.Argument(..., help="Path to patch file"),
    show_content: bool = typer.Option(
        False,
        "--content",
        "-c",
        help="Show full content, not just metadata",
    ),
) -> None:
    """Display the contents of a patch file."""
    patch_path = Path(patch_file)
    if not patch_path.exists():
        print_error(f"Patch file not found: {patch_file}")
        raise typer.Exit(1)

    try:
        patch = PromptPatch.load(patch_path)
    except Exception as e:
        print_error(f"Failed to load patch: {e}")
        raise typer.Exit(1)

    # Show metadata
    console.print(f"[bold cyan]Patch: {patch_path.name}[/bold cyan]")
    console.print(f"  Format: {patch.metadata.format}")
    console.print(f"  Created: {patch.metadata.created_at}")
    console.print(f"  Author: {patch.metadata.author or 'Unknown'}")
    console.print(f"  Source: {patch.metadata.source_prompt} v{patch.metadata.source_versions[0]} → v{patch.metadata.source_versions[1]}")
    console.print(f"  Hash: {patch.patch_hash}")

    if patch.metadata.description:
        console.print(f"  Description: {patch.metadata.description}")

    if patch.semantic_diff:
        console.print(f"\n[bold]Semantic Changes:[/bold]")
        for change_type, changes in patch.semantic_diff.items():
            if changes:
                console.print(f"  {change_type}: {len(changes)} change(s)")

    if show_content:
        console.print(f"\n[bold]Diff:[/bold]")
        syntax = Syntax(patch.text_diff, "diff", theme="monokai")
        console.print(syntax)


@app.command("preview")
def preview_patch(
    patch_file: str = typer.Argument(..., help="Path to patch file"),
    on_prompt: Optional[str] = typer.Option(
        None,
        "--on",
        "-p",
        help="Preview against specific prompt (default: from patch metadata)",
    ),
) -> None:
    """Preview what a patch would do without applying it."""
    project_root = require_initialized()

    # Load patch
    patch_path = Path(patch_file)
    if not patch_path.exists():
        print_error(f"Patch file not found: {patch_file}")
        raise typer.Exit(1)

    try:
        patch = PromptPatch.load(patch_path)
    except Exception as e:
        print_error(f"Failed to load patch: {e}")
        raise typer.Exit(1)

    # Determine target prompt
    target_name = on_prompt or patch.metadata.source_prompt

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)

        prompt = prompt_repo.get_by_name(target_name)
        if not prompt:
            print_error(f"Prompt '{target_name}' not found")
            raise typer.Exit(1)

        current_version = prompt.current_version
        if not current_version:
            print_error("No current version")
            raise typer.Exit(1)

        # Preview
        applier = PatchApplier(project_root)
        preview = applier.preview(patch, current_version.content)
        console.print(preview)


def _parse_version(version_str: str) -> int:
    """Parse version string to number."""
    if version_str.startswith("v"):
        version_str = version_str[1:]
    try:
        return int(version_str)
    except ValueError:
        print_error(f"Invalid version: {version_str}")
        raise typer.Exit(1)
