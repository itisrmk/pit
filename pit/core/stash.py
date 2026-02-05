"""Core stash logic for saving WIP prompt changes."""

import json
import hashlib
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class StashEntry:
    """A single stashed prompt state."""
    index: int  # Position in stash stack
    prompt_name: str
    prompt_id: str
    content: str  # The prompt content at stash time
    message: str  # User's stash message
    test_input: Optional[str] = None  # Associated test case
    created_at: str = None
    author: Optional[str] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "prompt_name": self.prompt_name,
            "prompt_id": self.prompt_id,
            "content": self.content,
            "message": self.message,
            "test_input": self.test_input,
            "created_at": self.created_at,
            "author": self.author,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StashEntry":
        return cls(
            index=data["index"],
            prompt_name=data["prompt_name"],
            prompt_id=data["prompt_id"],
            content=data["content"],
            message=data["message"],
            test_input=data.get("test_input"),
            created_at=data.get("created_at"),
            author=data.get("author"),
        )

    @property
    def content_hash(self) -> str:
        """Get a short hash of the content for identification."""
        return hashlib.sha256(self.content.encode()).hexdigest()[:8]


class StashManager:
    """Manages stashed prompt states."""

    STASH_DIR = "stash"
    INDEX_FILE = "index.json"

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.stash_dir = project_root / ".pit" / self.STASH_DIR
        self.index_path = self.stash_dir / self.INDEX_FILE

    def _ensure_stash_dir(self) -> None:
        """Ensure stash directory exists."""
        self.stash_dir.mkdir(parents=True, exist_ok=True)

    def _load_index(self) -> list[dict]:
        """Load the stash index."""
        if not self.index_path.exists():
            return []
        with open(self.index_path) as f:
            return json.load(f)

    def _save_index(self, entries: list[StashEntry]) -> None:
        """Save the stash index."""
        self._ensure_stash_dir()
        data = [e.to_dict() for e in entries]
        with open(self.index_path, "w") as f:
            json.dump(data, f, indent=2)

    def _save_stash_content(self, entry: StashEntry) -> None:
        """Save stash content to a separate file for large content."""
        content_path = self.stash_dir / f"stash_{entry.index}.md"
        content_path.write_text(entry.content)

    def _load_stash_content(self, entry: StashEntry) -> str:
        """Load stash content from file."""
        content_path = self.stash_dir / f"stash_{entry.index}.md"
        if content_path.exists():
            return content_path.read_text()
        return entry.content  # Fallback to inline content

    def list_stashes(self) -> list[StashEntry]:
        """List all stash entries."""
        data = self._load_index()
        entries = []
        for d in data:
            entry = StashEntry.from_dict(d)
            # Load full content from file if available
            entry.content = self._load_stash_content(entry)
            entries.append(entry)
        return entries

    def save_stash(
        self,
        prompt_name: str,
        prompt_id: str,
        content: str,
        message: str,
        test_input: Optional[str] = None,
        author: Optional[str] = None,
    ) -> StashEntry:
        """Save current state to stash."""
        entries = self.list_stashes()

        # New index is next position
        new_index = len(entries)

        entry = StashEntry(
            index=new_index,
            prompt_name=prompt_name,
            prompt_id=prompt_id,
            content=content,
            message=message,
            test_input=test_input,
            author=author,
        )

        entries.append(entry)
        self._save_index(entries)
        self._save_stash_content(entry)

        return entry

    def pop_stash(self, index: int = 0) -> Optional[StashEntry]:
        """Remove and return a stash entry (default: top of stack)."""
        entries = self.list_stashes()

        if not entries:
            return None

        # Map logical index to position
        if index < 0 or index >= len(entries):
            return None

        entry = entries.pop(index)

        # Renumber remaining entries
        for i, e in enumerate(entries):
            old_index = e.index
            e.index = i
            # Rename content file if exists
            old_path = self.stash_dir / f"stash_{old_index}.md"
            new_path = self.stash_dir / f"stash_{i}.md"
            if old_path.exists():
                old_path.rename(new_path)

        self._save_index(entries)

        # Remove old content file
        old_content_path = self.stash_dir / f"stash_{len(entries)}.md"
        if old_content_path.exists():
            old_content_path.unlink()

        return entry

    def apply_stash(self, index: int = 0) -> Optional[StashEntry]:
        """Get a stash entry without removing it."""
        entries = self.list_stashes()

        if not entries or index < 0 or index >= len(entries):
            return None

        return entries[index]

    def drop_stash(self, index: int = 0) -> bool:
        """Drop a stash entry without applying."""
        result = self.pop_stash(index)
        return result is not None

    def clear_all(self) -> int:
        """Clear all stashes. Returns number cleared."""
        entries = self.list_stashes()
        count = len(entries)

        # Remove all content files
        for entry in entries:
            content_path = self.stash_dir / f"stash_{entry.index}.md"
            if content_path.exists():
                content_path.unlink()

        # Clear index
        self._save_index([])

        return count

    def get_stash_count(self) -> int:
        """Get number of stashed entries."""
        return len(self._load_index())

    def show_stash(self, index: int = 0) -> Optional[StashEntry]:
        """Show details of a specific stash."""
        return self.apply_stash(index)
