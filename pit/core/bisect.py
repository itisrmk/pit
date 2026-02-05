"""Core bisect logic for finding which version broke behavior."""

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from pit.db.repository import PromptRepository, VersionRepository


class BisectState(Enum):
    """Current state of bisect operation."""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"


class BisectResult(Enum):
    """Result of testing a version."""
    GOOD = "good"
    BAD = "bad"
    SKIP = "skip"


@dataclass
class BisectSession:
    """State of an active bisect session."""
    state: BisectState
    prompt_name: str
    prompt_id: str
    failing_input: str
    good_version: Optional[int] = None
    bad_version: Optional[int] = None
    current_version: Optional[int] = None
    tested_versions: dict = None  # version_num -> BisectResult
    started_at: str = None
    completed_at: Optional[str] = None
    first_bad_version: Optional[int] = None

    def __post_init__(self):
        if self.tested_versions is None:
            self.tested_versions = {}
        if self.started_at is None:
            self.started_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "prompt_name": self.prompt_name,
            "prompt_id": self.prompt_id,
            "failing_input": self.failing_input,
            "good_version": self.good_version,
            "bad_version": self.bad_version,
            "current_version": self.current_version,
            "tested_versions": self.tested_versions,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "first_bad_version": self.first_bad_version,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BisectSession":
        return cls(
            state=BisectState(data.get("state", "idle")),
            prompt_name=data["prompt_name"],
            prompt_id=data["prompt_id"],
            failing_input=data["failing_input"],
            good_version=data.get("good_version"),
            bad_version=data.get("bad_version"),
            current_version=data.get("current_version"),
            tested_versions=data.get("tested_versions", {}),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            first_bad_version=data.get("first_bad_version"),
        )


class BisectManager:
    """Manages bisect sessions for finding problematic versions."""

    STATE_FILE = "bisect_state.json"

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.state_path = project_root / ".pit" / self.STATE_FILE

    def _load_state(self) -> Optional[BisectSession]:
        """Load current bisect session from disk."""
        if not self.state_path.exists():
            return None
        with open(self.state_path) as f:
            return BisectSession.from_dict(json.load(f))

    def _save_state(self, session: BisectSession) -> None:
        """Save bisect session to disk."""
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_path, "w") as f:
            json.dump(session.to_dict(), f, indent=2)

    def _clear_state(self) -> None:
        """Clear bisect session from disk."""
        if self.state_path.exists():
            self.state_path.unlink()

    def get_session(self) -> Optional[BisectSession]:
        """Get current bisect session if any."""
        return self._load_state()

    def start(
        self,
        db_session: Session,
        prompt_name: str,
        failing_input: str,
    ) -> BisectSession:
        """Start a new bisect session."""
        # Check if already running
        existing = self._load_state()
        if existing and existing.state == BisectState.RUNNING:
            raise ValueError("A bisect session is already running. Run 'bisect reset' first.")

        # Find prompt
        prompt_repo = PromptRepository(db_session)
        prompt = prompt_repo.get_by_name(prompt_name)
        if not prompt:
            raise ValueError(f"Prompt '{prompt_name}' not found")

        session = BisectSession(
            state=BisectState.RUNNING,
            prompt_name=prompt_name,
            prompt_id=prompt.id,
            failing_input=failing_input,
        )
        self._save_state(session)
        return session

    def mark_version(
        self,
        db_session: Session,
        result: BisectResult,
        version_num: Optional[int] = None,
    ) -> BisectSession:
        """Mark a version as good, bad, or skip."""
        session = self._load_state()
        if not session or session.state != BisectState.RUNNING:
            raise ValueError("No active bisect session. Run 'bisect start' first.")

        version_repo = VersionRepository(db_session)

        # Get version number if not specified (use current)
        if version_num is None:
            if session.current_version is None:
                # Starting fresh - need to determine range
                raise ValueError("Specify a version: 'bisect good v1' or 'bisect bad v5'")
            version_num = session.current_version

        # Validate version exists
        versions = version_repo.get_by_prompt_id(session.prompt_id)
        version_numbers = [v.version_number for v in versions]
        if version_num not in version_numbers:
            raise ValueError(f"Version {version_num} does not exist for this prompt")

        # Record result
        session.tested_versions[version_num] = result.value

        if result == BisectResult.GOOD:
            # This version works - move bound
            if session.good_version is not None and version_num <= session.good_version:
                raise ValueError(f"Version {version_num} is not newer than current good version {session.good_version}")
            session.good_version = version_num

        elif result == BisectResult.BAD:
            # This version is broken - move bound
            if session.bad_version is not None and version_num >= session.bad_version:
                raise ValueError(f"Version {version_num} is not older than current bad version {session.bad_version}")
            session.bad_version = version_num

        elif result == BisectResult.SKIP:
            # Skip this version - don't use for narrowing
            pass

        # Check if we're done
        if session.good_version is not None and session.bad_version is not None:
            if session.bad_version == session.good_version + 1:
                # Found it!
                session.state = BisectState.COMPLETED
                session.first_bad_version = session.bad_version
                session.completed_at = datetime.now().isoformat()
                self._save_state(session)
                return session

        # Pick next version to test
        next_version = self._pick_next_version(session, version_numbers)
        session.current_version = next_version
        self._save_state(session)

        return session

    def _pick_next_version(
        self,
        session: BisectSession,
        all_versions: list[int],
    ) -> Optional[int]:
        """Pick the next version to test using binary search."""
        if session.good_version is None or session.bad_version is None:
            # Don't have both bounds yet - pick something in the middle
            # or ask user to mark one more version
            return None

        # Binary search between good and bad
        good_idx = all_versions.index(session.good_version)
        bad_idx = all_versions.index(session.bad_version)

        if bad_idx - good_idx <= 1:
            # Adjacent - we're done
            return None

        # Pick middle
        mid_idx = (good_idx + bad_idx) // 2
        next_version = all_versions[mid_idx]

        # Skip already-tested versions
        while next_version in session.tested_versions and good_idx < bad_idx - 1:
            if next_version in session.tested_versions:
                if session.tested_versions[next_version] == BisectResult.GOOD.value:
                    good_idx = mid_idx
                elif session.tested_versions[next_version] == BisectResult.BAD.value:
                    bad_idx = mid_idx
                else:
                    # Skip - move toward bad
                    good_idx = mid_idx
            mid_idx = (good_idx + bad_idx) // 2
            next_version = all_versions[mid_idx]

        return next_version

    def reset(self) -> None:
        """Clear the current bisect session."""
        self._clear_state()

    def get_progress(self) -> dict:
        """Get human-readable progress info."""
        session = self._load_state()
        if not session:
            return {"status": "No active session"}

        if session.state == BisectState.COMPLETED:
            return {
                "status": "completed",
                "first_bad_version": session.first_bad_version,
                "tested_count": len(session.tested_versions),
            }

        # Calculate versions remaining
        if session.good_version and session.bad_version:
            remaining = session.bad_version - session.good_version - 1
        else:
            remaining = "unknown"

        return {
            "status": "running",
            "prompt": session.prompt_name,
            "good": session.good_version,
            "bad": session.bad_version,
            "current": session.current_version,
            "tested": len(session.tested_versions),
            "remaining_approx": remaining,
        }
