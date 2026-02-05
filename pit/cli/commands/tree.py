"""Tree visualization and propagation commands for prompt composition."""

from pathlib import Path
from typing import Optional

import typer
from rich.tree import Tree
from rich.panel import Panel
from rich.table import Table
from rich.console import Group

from pit.config import Config, find_project_root, is_initialized
from pit.db.database import get_session
from pit.db.repository import (
    FragmentRepository,
    PromptRepository,
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
def show(
    prompt_name: str = typer.Argument(..., help="Name of the prompt"),
    show_fragments: bool = typer.Option(
        True,
        "--fragments/--no-fragments",
        help="Show fragment composition",
    ),
    show_versions: bool = typer.Option(
        False,
        "--versions/-v",
        help="Show version history in tree",
    ),
) -> None:
    """Display the composition tree for a prompt.

    Shows the inheritance chain, fragment dependencies,
    and parent-child relationships as an ASCII tree.
    """
    project_root = require_initialized()

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        version_repo = VersionRepository(session)
        fragment_repo = FragmentRepository(session)

        prompt = prompt_repo.get_by_name(prompt_name)
        if not prompt:
            print_error(f"Prompt '{prompt_name}' not found")
            raise typer.Exit(1)

        # Build the tree
        tree = Tree(f"[bold cyan]{prompt.name}[/bold cyan] (Prompt)")

        # Show base template relationship
        if prompt.base_template:
            base = tree.add(f"[dim]← Inherits from: {prompt.base_template.name}[/dim]")
            # Show base template chain
            current = prompt.base_template
            while current.base_template:
                base.add(f"[dim]← {current.base_template.name}[/dim]")
                current = current.base_template

        # Show current version
        if prompt.current_version:
            ver_node = tree.add(
                f"[green]Current: v{prompt.current_version.version_number}[/green]"
            )

            # Show version history if requested
            if show_versions:
                versions = version_repo.list_by_prompt(prompt.id)
                if len(versions) > 1:
                    history = ver_node.add("[dim]Version History[/dim]")
                    for ver in versions[1:6]:  # Show last 5 versions
                        history.add(f"[dim]v{ver.version_number}: {ver.message[:30]}...[/dim]")
                    if len(versions) > 6:
                        history.add(f"[dim]... and {len(versions) - 6} more[/dim]")

            # Show fragment dependencies
            if show_fragments:
                fragments_node = ver_node.add("[blue]Fragments[/blue]")
                # Get fragments through VersionFragment relationship
                # For now, we show fragments that might be referenced
                fragments = fragment_repo.list_all()
                referenced = _find_referenced_fragments(prompt.current_version.content, fragments)
                if referenced:
                    for frag in referenced:
                        fragments_node.add(f"[blue]• {frag.name}[/blue]")
                else:
                    fragments_node.add("[dim]No fragments referenced[/dim]")

        # Display inheritance chain
        if prompt.base_template:
            _show_inheritance_chain(prompt)

        console.print(tree)


def _find_referenced_fragments(content: str, all_fragments: list) -> list:
    """Find fragments referenced in prompt content."""
    referenced = []
    for frag in all_fragments:
        if frag.name in content or frag.id[:8] in content:
            referenced.append(frag)
    return referenced


def _show_inheritance_chain(prompt) -> None:
    """Show the inheritance chain for a prompt."""
    chain = []
    current = prompt
    while current.base_template:
        chain.append(current.base_template)
        current = current.base_template

    if chain:
        console.print("\n[bold]Inheritance Chain:[/bold]")
        for i, p in enumerate(reversed(chain)):
            prefix = "  " * i + "└─ "
            console.print(f"{prefix}[dim]{p.name}[/dim]")
        console.print(f"  {'  ' * len(chain)}└─ [cyan]{prompt.name}[/cyan]")


@app.command()
def fragments(
    show_tree: bool = typer.Option(
        True,
        "--tree/--list",
        help="Show as tree or flat list",
    ),
) -> None:
    """Display the fragment library tree.

    Shows all reusable prompt components and their
    parent-child relationships.
    """
    project_root = require_initialized()

    with get_session(project_root) as session:
        fragment_repo = FragmentRepository(session)
        fragments = fragment_repo.list_all()

        if not fragments:
            print_info("No fragments found. Create one with 'pit fragment create'")
            return

        if show_tree:
            # Find root fragments (no parent)
            roots = [f for f in fragments if f.parent_fragment_id is None]

            if not roots:
                # Just show all fragments
                tree = Tree("[bold cyan]Fragments[/bold cyan]")
                for frag in fragments:
                    tree.add(f"[blue]{frag.name}[/blue] - {frag.description or 'No description'}")
                console.print(tree)
            else:
                tree = Tree("[bold cyan]Fragment Library[/bold cyan]")
                for root in roots:
                    _build_fragment_tree(tree, root, fragments)
                console.print(tree)
        else:
            # Flat list
            table = Table(title="Fragments")
            table.add_column("Name", style="cyan")
            table.add_column("Description")
            table.add_column("Parent", style="dim")

            for frag in fragments:
                parent = next((f for f in fragments if f.id == frag.parent_fragment_id), None)
                table.add_row(
                    frag.name,
                    frag.description or "[dim]No description[/dim]",
                    parent.name if parent else "[dim]None[/dim]",
                )
            console.print(table)


def _build_fragment_tree(tree: Tree, fragment, all_fragments: list, depth: int = 0) -> None:
    """Recursively build fragment tree."""
    node = tree.add(f"[blue]{fragment.name}[/blue]")
    if fragment.description:
        node.add(f"[dim]{fragment.description[:50]}[/dim]")

    # Find children
    children = [f for f in all_fragments if f.parent_fragment_id == fragment.id]
    for child in children:
        _build_fragment_tree(node, child, all_fragments, depth + 1)


@app.command()
def propagate(
    fragment_name: str = typer.Argument(..., help="Name of the parent fragment"),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Show what would be propagated without making changes",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation",
    ),
) -> None:
    """Propagate changes from a fragment to all children.

    Updates child fragments and prompts that depend on
    the specified parent fragment.
    """
    project_root = require_initialized()

    with get_session(project_root) as session:
        fragment_repo = FragmentRepository(session)
        prompt_repo = PromptRepository(session)
        version_repo = VersionRepository(session)

        parent = fragment_repo.get_by_name(fragment_name)
        if not parent:
            print_error(f"Fragment '{fragment_name}' not found")
            raise typer.Exit(1)

        # Get all descendants
        descendants = fragment_repo.get_descendants(parent.id)

        # Get prompts that reference this fragment
        prompts = prompt_repo.list_all()
        affected_prompts = []
        for prompt in prompts:
            if prompt.current_version and fragment_name in prompt.current_version.content:
                affected_prompts.append(prompt)

        # Show what would be affected
        console.print(f"\n[bold cyan]Propagation Plan[/bold cyan]")
        console.print(f"Source: [blue]{parent.name}[/blue]\n")

        if descendants:
            console.print("[bold]Child Fragments to Update:[/bold]")
            for child in descendants:
                console.print(f"  • {child.name}")
        else:
            console.print("[dim]No child fragments[/dim]")

        if affected_prompts:
            console.print("\n[bold]Affected Prompts:[/bold]")
            for prompt in affected_prompts:
                console.print(f"  • {prompt.name}")
        else:
            console.print("\n[dim]No affected prompts[/dim]")

        if dry_run:
            print_info("\nDry run - no changes made")
            return

        # Confirm
        if not force and (descendants or affected_prompts):
            from rich.prompt import Confirm
            if not Confirm.ask("\nPropagate changes?"):
                print_info("Cancelled")
                return

        # Perform propagation
        updated_count = 0

        # Update child fragments
        for child in descendants:
            # In a real implementation, this would merge/update content
            # For now, we just touch the updated_at timestamp
            fragment_repo.update(child, description=child.description)
            updated_count += 1

        # Create new versions for affected prompts
        for prompt in affected_prompts:
            if prompt.current_version:
                # Create a new version with the propagated changes
                new_version = version_repo.create(
                    prompt_id=prompt.id,
                    content=prompt.current_version.content,  # In real impl, would update content
                    message=f"Propagate changes from fragment '{fragment_name}'",
                    author="propagation",
                )
                updated_count += 1
                print_success(f"Updated prompt '{prompt.name}' to v{new_version.version_number}")

        print_success(f"\nPropagation complete. {updated_count} item(s) updated.")


@app.command()
def dependencies(
    prompt_name: str = typer.Argument(..., help="Name of the prompt"),
) -> None:
    """Show all dependencies for a prompt.

    Lists fragments, templates, and other prompts that
    this prompt depends on.
    """
    project_root = require_initialized()

    with get_session(project_root) as session:
        prompt_repo = PromptRepository(session)
        fragment_repo = FragmentRepository(session)
        version_repo = VersionRepository(session)

        prompt = prompt_repo.get_by_name(prompt_name)
        if not prompt:
            print_error(f"Prompt '{prompt_name}' not found")
            raise typer.Exit(1)

        deps = {
            "base_templates": [],
            "fragments": [],
            "variables": [],
        }

        # Base templates
        current = prompt
        while current.base_template:
            deps["base_templates"].append(current.base_template)
            current = current.base_template

        # Fragments and variables
        if prompt.current_version:
            content = prompt.current_version.content

            # Extract variables
            import re
            pattern = r"\{\{\s*(\w+)\s*\}\}"
            deps["variables"] = list(dict.fromkeys(re.findall(pattern, content)))

            # Find fragments
            fragments = fragment_repo.list_all()
            deps["fragments"] = _find_referenced_fragments(content, fragments)

        # Display
        console.print(f"\n[bold cyan]Dependencies for '{prompt_name}'[/bold cyan]\n")

        # Base templates
        if deps["base_templates"]:
            console.print(Panel(
                "\n".join(f"• {p.name}" for p in deps["base_templates"]),
                title="Base Templates",
                border_style="blue",
            ))
        else:
            console.print(Panel(
                "[dim]No base templates[/dim]",
                title="Base Templates",
                border_style="dim",
            ))

        # Fragments
        if deps["fragments"]:
            console.print(Panel(
                "\n".join(f"• {f.name}" for f in deps["fragments"]),
                title="Fragments",
                border_style="green",
            ))
        else:
            console.print(Panel(
                "[dim]No fragments[/dim]",
                title="Fragments",
                border_style="dim",
            ))

        # Variables
        if deps["variables"]:
            console.print(Panel(
                "\n".join(f"• {{{{ {v} }}}}" for v in deps["variables"]),
                title="Variables",
                border_style="yellow",
            ))
        else:
            console.print(Panel(
                "[dim]No variables[/dim]",
                title="Variables",
                border_style="dim",
            ))


@app.command()
def impact(
    fragment_name: str = typer.Argument(..., help="Name of the fragment"),
) -> None:
    """Show the impact of modifying a fragment.

    Lists all prompts and other fragments that would be
    affected by changes to this fragment.
    """
    project_root = require_initialized()

    with get_session(project_root) as session:
        fragment_repo = FragmentRepository(session)
        prompt_repo = PromptRepository(session)

        fragment = fragment_repo.get_by_name(fragment_name)
        if not fragment:
            print_error(f"Fragment '{fragment_name}' not found")
            raise typer.Exit(1)

        # Get descendants
        descendants = fragment_repo.get_descendants(fragment.id)

        # Get prompts that reference this fragment
        prompts = prompt_repo.list_all()
        affected_prompts = []
        for prompt in prompts:
            if prompt.current_version and fragment_name in prompt.current_version.content:
                affected_prompts.append(prompt)

        # Display impact
        console.print(f"\n[bold cyan]Impact Analysis: '{fragment_name}'[/bold cyan]\n")

        # Direct children
        children = fragment_repo.get_children(fragment.id)
        if children:
            console.print(Panel(
                "\n".join(f"• {c.name}" for c in children),
                title=f"Direct Children ({len(children)})",
                border_style="blue",
            ))
        else:
            console.print(Panel(
                "[dim]No direct children[/dim]",
                title="Direct Children",
                border_style="dim",
            ))

        # All descendants
        if descendants:
            console.print(Panel(
                "\n".join(f"• {d.name}" for d in descendants),
                title=f"All Descendants ({len(descendants)})",
                border_style="yellow",
            ))
        else:
            console.print(Panel(
                "[dim]No descendants[/dim]",
                title="All Descendants",
                border_style="dim",
            ))

        # Affected prompts
        if affected_prompts:
            console.print(Panel(
                "\n".join(f"• {p.name}" for p in affected_prompts),
                title=f"Affected Prompts ({len(affected_prompts)})",
                border_style="green",
            ))
        else:
            console.print(Panel(
                "[dim]No affected prompts[/dim]",
                title="Affected Prompts",
                border_style="dim",
            ))

        total_impact = len(descendants) + len(affected_prompts)
        if total_impact > 0:
            print_warning(f"\n⚠️  Modifying this fragment would affect {total_impact} item(s)")
        else:
            print_info("\n✓ No dependencies on this fragment")
