"""Core worktree logic for multiple prompt contexts."""

import json
import os
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class Worktree:
    """A worktree - an independent checkout of a prompt."""
    path: str  # Absolute path to worktree directory
    prompt_name: str
    prompt_id: str
    checked_out_version: Optional[int]  # None = prompt HEAD (current version)
    created_at: str
    last_used: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "prompt_name": self.prompt_name,
            "prompt_id": self.prompt_id,
            "checked_out_version": self.checked_out_version,
            "created_at": self.created_at,
            "last_used": self.last_used,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Worktree":
        return cls(
            path=data["path"],
            prompt_name=data["prompt_name"],
            prompt_id=data["prompt_id"],
            checked_out_version=data.get("checked_out_version"),
            created_at=data["created_at"],
            last_used=data.get("last_used"),
        )


class WorktreeManager:
    """Manages prompt worktrees - multiple independent contexts."""

    WORKTREES_FILE = "worktrees.json"
    WORKTREE_MARKER = ".pit-worktree"

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.worktrees_path = project_root / ".pit" / self.WORKTREES_FILE

    def _load_worktrees(self) -> dict[str, Worktree]:
        """Load all worktrees from disk."""
        if not self.worktrees_path.exists():
            return {}

        with open(self.worktrees_path) as f:
            data = json.load(f)
            return {k: Worktree.from_dict(v) for k, v in data.items()}

    def _save_worktrees(self, worktrees: dict[str, Worktree]) -> None:
        """Save worktrees to disk."""
        self.worktrees_path.parent.mkdir(parents=True, exist_ok=True)
        data = {k: v.to_dict() for k, v in worktrees.items()}
        with open(self.worktrees_path, "w") as f:
            json.dump(data, f, indent=2)

    def _get_worktree_key(self, path: Path) -> str:
        """Get the key for a worktree path."""
        return str(path.resolve())

    def _write_worktree_marker(self, worktree_path: Path, worktree: Worktree) -> None:
        """Write a marker file identifying this as a pit worktree."""
        marker_path = worktree_path / self.WORKTREE_MARKER
        with open(marker_path, "w") as f:
            json.dump(worktree.to_dict(), f, indent=2)

    def _read_worktree_marker(self, worktree_path: Path) -> Optional[Worktree]:
        """Read the marker file from a worktree directory."""
        marker_path = worktree_path / self.WORKTREE_MARKER
        if not marker_path.exists():
            return None
        with open(marker_path) as f:
            return Worktree.from_dict(json.load(f))

    def list_worktrees(self) -> list[Worktree]:
        """List all active worktrees."""
        worktrees = self._load_worktrees()
        # Filter to only existent directories
        active = []
        for wt in worktrees.values():
            if Path(wt.path).exists():
                active.append(wt)
        return active

    def create_worktree(
        self,
        path: Path,
        prompt_name: str,
        prompt_id: str,
        version: Optional[int] = None,
    ) -> Worktree:
        """Create a new worktree at the given path."""
        # Validate path
        if path.exists():
            raise ValueError(f"Path already exists: {path}")

        # Check if already a worktree
        worktrees = self._load_worktrees()
        key = self._get_worktree_key(path)
        if key in worktrees:
            raise ValueError(f"Worktree already exists at: {path}")

        # Create directory
        path.mkdir(parents=True)

        # Create worktree record
        now = datetime.now().isoformat()
        worktree = Worktree(
            path=str(path.resolve()),
            prompt_name=prompt_name,
            prompt_id=prompt_id,
            checked_out_version=version,
            created_at=now,
            last_used=now,
        )

        # Write marker and save
        self._write_worktree_marker(path, worktree)
        worktrees[key] = worktree
        self._save_worktrees(worktrees)

        return worktree

    def remove_worktree(self, path: Path, force: bool = False) -> None:
        """Remove a worktree."""
        key = self._get_worktree_key(path)
        worktrees = self._load_worktrees()

        if key not in worktrees:
            # Check if it has a marker anyway
            marker = self._read_worktree_marker(path)
            if marker:
                worktrees[key] = marker
            else:
                raise ValueError(f"Not a pit worktree: {path}")

        # Remove directory
        if path.exists():
            if force:
                shutil.rmtree(path)
            else:
                # Check if empty or only has marker
                contents = list(path.iterdir())
                if len(contents) > 1 or (len(contents) == 1 and contents[0].name != self.WORKTREE_MARKER):
                    raise ValueError(
                        f"Worktree is not empty. Use --force to remove anyway, "
                        f"or manually clean up: {path}"
                    )
                shutil.rmtree(path)

        # Remove from tracking
        del worktrees[key]
        self._save_worktrees(worktrees)

    def get_worktree(self, path: Path) -> Optional[Worktree]:
        """Get worktree info for a path."""
        key = self._get_worktree_key(path)
        worktrees = self._load_worktrees()
        return worktrees.get(key)

    def update_worktree_version(
        self,
        path: Path,
        version: Optional[int],
    ) -> Worktree:
        """Update the checked-out version of a worktree."""
        key = self._get_worktree_key(path)
        worktrees = self._load_worktrees()

        if key not in worktrees:
            raise ValueError(f"Not a tracked worktree: {path}")

        worktree = worktrees[key]
        worktree.checked_out_version = version
        worktree.last_used = datetime.now().isoformat()

        # Update marker and save
        self._write_worktree_marker(path, worktree)
        self._save_worktrees(worktrees)

        return worktree

    def prune_stale(self, days: int = 30) -> list[Worktree]:
        """Remove worktrees that haven't been used in N days."""
        from datetime import timedelta

        worktrees = self._load_worktrees()
        cutoff = datetime.now() - timedelta(days=days)
        removed = []

        for key, wt in list(worktrees.items()):
            last_used = datetime.fromisoformat(wt.last_used or wt.created_at)
            if last_used < cutoff:
                path = Path(wt.path)
                if path.exists():
                    shutil.rmtree(path, ignore_errors=True)
                del worktrees[key]
                removed.append(wt)

        if removed:
            self._save_worktrees(worktrees)

        return removed

    def is_worktree(self, path: Path) -> bool:
        """Check if a path is a pit worktree."""
        return (path / self.WORKTREE_MARKER).exists()

    def get_current_prompt_in_worktree(self, path: Path) -> Optional[tuple[str, Optional[int]]]:
        """Get the (prompt_name, version) currently in a worktree."""
        worktree = self.get_worktree(path)
        if worktree:
            return (worktree.prompt_name, worktree.checked_out_version)
        return None

    def get_prompt_content_path(self, worktree_path: Path, prompt_name: str) -> Path:
        """Get the path where prompt content should be written in a worktree."""
        return worktree_path / f"{prompt_name}.md"
