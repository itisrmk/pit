"""Core patch logic for sharing prompt changes."""

import json
import hashlib
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from pit.db.models import Version


PATCH_VERSION = "pit-patch-v1"
PATCH_EXTENSION = ".promptpatch"


@dataclass
class PatchMetadata:
    """Metadata for a patch."""
    format: str
    created_at: str
    author: Optional[str]
    source_prompt: str
    source_versions: tuple[int, int]  # (from, to)
    description: Optional[str]

    def to_dict(self) -> dict:
        return {
            "format": self.format,
            "created_at": self.created_at,
            "author": self.author,
            "source_prompt": self.source_prompt,
            "source_versions": list(self.source_versions),
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PatchMetadata":
        return cls(
            format=data["format"],
            created_at=data["created_at"],
            author=data.get("author"),
            source_prompt=data["source_prompt"],
            source_versions=tuple(data["source_versions"]),
            description=data.get("description"),
        )


@dataclass
class PromptPatch:
    """A patch containing prompt changes."""
    metadata: PatchMetadata
    old_content: str
    new_content: str
    text_diff: str  # Unified diff format
    semantic_diff: Optional[dict]  # Semantic analysis of changes

    def to_dict(self) -> dict:
        return {
            "metadata": self.metadata.to_dict(),
            "old_content": self.old_content,
            "new_content": self.new_content,
            "text_diff": self.text_diff,
            "semantic_diff": self.semantic_diff,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PromptPatch":
        return cls(
            metadata=PatchMetadata.from_dict(data["metadata"]),
            old_content=data["old_content"],
            new_content=data["new_content"],
            text_diff=data["text_diff"],
            semantic_diff=data.get("semantic_diff"),
        )

    @property
    def patch_hash(self) -> str:
        """Get a hash identifying this patch."""
        content = f"{self.metadata.source_prompt}:{self.metadata.source_versions}"
        return hashlib.sha256(content.encode()).hexdigest()[:12]

    def save(self, path: Path) -> None:
        """Save patch to file."""
        if not path.suffix == PATCH_EXTENSION:
            path = path.with_suffix(PATCH_EXTENSION)
        path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: Path) -> "PromptPatch":
        """Load patch from file."""
        data = json.loads(path.read_text())
        return cls.from_dict(data)


class PatchGenerator:
    """Generates patches from version differences."""

    def __init__(self, author: Optional[str] = None):
        self.author = author

    def generate(
        self,
        prompt_name: str,
        old_version: Version,
        new_version: Version,
        description: Optional[str] = None,
    ) -> PromptPatch:
        """Generate a patch from two versions."""
        # Generate unified diff
        text_diff = self._generate_diff(
            old_version.content,
            new_version.content,
            old_version.version_number,
            new_version.version_number,
        )

        metadata = PatchMetadata(
            format=PATCH_VERSION,
            created_at=datetime.now().isoformat(),
            author=self.author,
            source_prompt=prompt_name,
            source_versions=(old_version.version_number, new_version.version_number),
            description=description,
        )

        return PromptPatch(
            metadata=metadata,
            old_content=old_version.content,
            new_content=new_version.content,
            text_diff=text_diff,
            semantic_diff=new_version.semantic_diff,
        )

    def _generate_diff(
        self,
        old_content: str,
        new_content: str,
        old_version: int,
        new_version: int,
    ) -> str:
        """Generate unified diff between two contents."""
        import difflib

        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        # Ensure lines end with newline for proper diff
        if old_lines and not old_lines[-1].endswith("\n"):
            old_lines[-1] += "\n"
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"

        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"v{old_version}",
            tofile=f"v{new_version}",
        )

        return "".join(diff)


class PatchApplier:
    """Applies patches to prompts."""

    def __init__(self, project_root: Path):
        self.project_root = project_root

    def can_apply(
        self,
        patch: PromptPatch,
        target_content: str,
    ) -> tuple[bool, str]:
        """Check if patch can be applied to target content."""
        # Check if target matches patch's old_content
        if target_content == patch.old_content:
            return True, "Clean apply possible"

        # Check if already applied
        if target_content == patch.new_content:
            return False, "Patch already applied (content matches new_content)"

        # Could try fuzzy matching here in the future
        return False, "Target content doesn't match patch base"

    def apply(
        self,
        patch: PromptPatch,
        target_content: str,
    ) -> str:
        """Apply patch to target content."""
        can_apply, reason = self.can_apply(patch, target_content)

        if not can_apply:
            raise ValueError(f"Cannot apply patch: {reason}")

        return patch.new_content

    def apply_fuzzy(
        self,
        patch: PromptPatch,
        target_content: str,
    ) -> Optional[str]:
        """Try to apply patch with fuzzy matching (best effort)."""
        import difflib

        # If exact match, apply directly
        if target_content == patch.old_content:
            return patch.new_content

        # Try to apply line-by-line diff
        try:
            old_lines = patch.old_content.splitlines()
            new_lines = patch.new_content.splitlines()
            target_lines = target_content.splitlines()

            # Simple heuristic: if structure is similar enough, apply
            similarity = difflib.SequenceMatcher(None, patch.old_content, target_content).ratio()

            if similarity > 0.8:
                # High similarity - try to merge
                # For now, just return new_content as best effort
                return patch.new_content

        except Exception:
            pass

        return None

    def preview(
        self,
        patch: PromptPatch,
        target_content: str,
    ) -> str:
        """Generate a preview of what the patch would do."""
        can_apply, reason = self.can_apply(patch, target_content)

        if can_apply:
            return f"✓ Can apply cleanly\n\nResult preview:\n{patch.new_content[:500]}..."
        else:
            return f"✗ Cannot apply: {reason}"
