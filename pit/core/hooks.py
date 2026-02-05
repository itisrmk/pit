"""Core hooks logic for git-style prompt hooks."""

import os
import stat
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Optional, List, Dict, Any


class HookType(Enum):
    """Types of hooks supported by PIT."""
    PRE_COMMIT = "pre-commit"
    POST_COMMIT = "post-commit"
    PRE_CHECKOUT = "pre-checkout"
    POST_CHECKOUT = "post-checkout"
    PRE_MERGE = "pre-merge"
    POST_MERGE = "post-merge"

    @classmethod
    def all(cls) -> List["HookType"]:
        return [cls.PRE_COMMIT, cls.POST_COMMIT, cls.PRE_CHECKOUT,
                cls.POST_CHECKOUT, cls.PRE_MERGE, cls.POST_MERGE]


@dataclass
class HookScript:
    """A hook script with metadata."""
    hook_type: HookType
    path: Path
    content: str
    created_at: datetime
    is_executable: bool


@dataclass
class HookResult:
    """Result of running a hook."""
    success: bool
    hook_type: HookType
    stdout: str
    stderr: str
    exit_code: int
    message: Optional[str] = None


class HookManager:
    """Manages git-style hooks for prompts."""

    HOOKS_DIR = "hooks"

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.hooks_dir = project_root / ".pit" / self.HOOKS_DIR

    def _ensure_hooks_dir(self) -> None:
        """Ensure the hooks directory exists."""
        self.hooks_dir.mkdir(parents=True, exist_ok=True)

    def _get_hook_path(self, hook_type: HookType) -> Path:
        """Get the path for a hook script."""
        return self.hooks_dir / hook_type.value

    def list_hooks(self) -> Dict[HookType, Optional[HookScript]]:
        """List all hooks and their status."""
        result = {}
        for hook_type in HookType.all():
            hook_path = self._get_hook_path(hook_type)
            if hook_path.exists():
                result[hook_type] = self._load_hook(hook_type)
            else:
                result[hook_type] = None
        return result

    def get_hook(self, hook_type: HookType) -> Optional[HookScript]:
        """Get a specific hook if it exists."""
        hook_path = self._get_hook_path(hook_type)
        if not hook_path.exists():
            return None
        return self._load_hook(hook_type)

    def _load_hook(self, hook_type: HookType) -> HookScript:
        """Load a hook script from disk."""
        hook_path = self._get_hook_path(hook_type)
        content = hook_path.read_text()
        stat_info = hook_path.stat()
        is_executable = bool(stat_info.st_mode & stat.S_IXUSR)

        return HookScript(
            hook_type=hook_type,
            path=hook_path,
            content=content,
            created_at=datetime.fromtimestamp(stat_info.st_mtime),
            is_executable=is_executable,
        )

    def install_hook(
        self,
        hook_type: HookType,
        content: str,
        make_executable: bool = True,
    ) -> HookScript:
        """Install a hook script."""
        self._ensure_hooks_dir()
        hook_path = self._get_hook_path(hook_type)

        # Write script
        hook_path.write_text(content)

        # Make executable if requested
        if make_executable:
            current_mode = hook_path.stat().st_mode
            hook_path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        return self._load_hook(hook_type)

    def install_hook_from_file(
        self,
        hook_type: HookType,
        source_path: Path,
    ) -> HookScript:
        """Install a hook from a file."""
        content = source_path.read_text()
        return self.install_hook(hook_type, content)

    def uninstall_hook(self, hook_type: HookType) -> bool:
        """Remove a hook script."""
        hook_path = self._get_hook_path(hook_type)
        if hook_path.exists():
            hook_path.unlink()
            return True
        return False

    def run_hook(
        self,
        hook_type: HookType,
        env_vars: Optional[Dict[str, str]] = None,
        timeout: int = 30,
    ) -> HookResult:
        """Run a hook script with environment variables."""
        hook = self.get_hook(hook_type)
        if not hook:
            return HookResult(
                success=True,  # No hook is not an error
                hook_type=hook_type,
                stdout="",
                stderr="",
                exit_code=0,
                message=f"No {hook_type.value} hook installed",
            )

        if not hook.is_executable:
            return HookResult(
                success=False,
                hook_type=hook_type,
                stdout="",
                stderr="",
                exit_code=1,
                message=f"Hook {hook_type.value} is not executable",
            )

        # Prepare environment
        run_env = os.environ.copy()
        run_env["PROMPTVC_HOOK"] = hook_type.value
        run_env["PROMPTVC_PROJECT_ROOT"] = str(self.project_root)

        if env_vars:
            for key, value in env_vars.items():
                run_env[key] = value

        # Run the hook
        import subprocess

        try:
            result = subprocess.run(
                [str(hook.path)],
                capture_output=True,
                text=True,
                env=run_env,
                timeout=timeout,
                cwd=self.project_root,
            )

            return HookResult(
                success=result.returncode == 0,
                hook_type=hook_type,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                message="Hook executed successfully" if result.returncode == 0 else f"Hook failed with exit code {result.returncode}",
            )

        except subprocess.TimeoutExpired:
            return HookResult(
                success=False,
                hook_type=hook_type,
                stdout="",
                stderr="",
                exit_code=1,
                message=f"Hook {hook_type.value} timed out after {timeout}s",
            )
        except Exception as e:
            return HookResult(
                success=False,
                hook_type=hook_type,
                stdout="",
                stderr=str(e),
                exit_code=1,
                message=f"Error running hook: {e}",
            )

    def create_sample_hook(self, hook_type: HookType) -> str:
        """Create a sample hook script."""
        samples = {
            HookType.PRE_COMMIT: '''#!/bin/bash
# Pre-commit hook - validates prompt before committing
# Environment variables:
#   PROMPT_NAME - name of the prompt being committed
#   VERSION_NUMBER - version number being created
#   PROMPTVC_PROJECT_ROOT - project root directory

echo "Validating prompt: $PROMPT_NAME"

# Example: Check for forbidden words
# if grep -qi "forbidden" "$PROMPTVC_PROJECT_ROOT/prompts/$PROMPT_NAME.txt"; then
#     echo "Error: Prompt contains forbidden words"
#     exit 1
# fi

exit 0
''',
            HookType.POST_COMMIT: '''#!/bin/bash
# Post-commit hook - runs after a commit is made
# Environment variables:
#   PROMPT_NAME - name of the prompt
#   VERSION_NUMBER - version number created
#   PROMPTVC_PROJECT_ROOT - project root directory

echo "Committed $PROMPT_NAME v$VERSION_NUMBER"

# Example: Send notification
# curl -X POST "$WEBHOOK_URL" -d "prompt=$PROMPT_NAME&version=$VERSION_NUMBER"

exit 0
''',
            HookType.PRE_CHECKOUT: '''#!/bin/bash
# Pre-checkout hook - warns about uncommitted changes
# Environment variables:
#   PROMPT_NAME - name of the prompt
#   TARGET_VERSION - version being checked out
#   PROMPTVC_PROJECT_ROOT - project root directory

echo "Checking out $PROMPT_NAME v$TARGET_VERSION"

# Example: Check for uncommitted changes
# if [ -f "$PROMPTVC_PROJECT_ROOT/.pit/uncommitted/$PROMPT_NAME" ]; then
#     echo "Warning: Uncommitted changes exist"
#     exit 1
# fi

exit 0
''',
            HookType.POST_CHECKOUT: '''#!/bin/bash
# Post-checkout hook - runs after checkout
# Environment variables:
#   PROMPT_NAME - name of the prompt
#   CHECKED_OUT_VERSION - version that was checked out
#   PROMPTVC_PROJECT_ROOT - project root directory

echo "Checked out $PROMPT_NAME v$CHECKED_OUT_VERSION"

# Example: Run regression tests
# pit test run "$PROMPT_NAME"

exit 0
''',
            HookType.PRE_MERGE: '''#!/bin/bash
# Pre-merge hook - checks semantic compatibility
# Environment variables:
#   SOURCE_PROMPT - source prompt name
#   TARGET_PROMPT - target prompt name
#   SOURCE_VERSION - source version
#   TARGET_VERSION - target version
#   PROMPTVC_PROJECT_ROOT - project root directory

echo "Merging $SOURCE_PROMPT v$SOURCE_VERSION into $TARGET_PROMPT v$TARGET_VERSION"

# Example: Check for semantic conflicts
# pit diff "$SOURCE_PROMPT@$SOURCE_VERSION" "$TARGET_PROMPT@$TARGET_VERSION" --semantic

exit 0
''',
            HookType.POST_MERGE: '''#!/bin/bash
# Post-merge hook - runs after a merge
# Environment variables:
#   SOURCE_PROMPT - source prompt name
#   TARGET_PROMPT - target prompt name
#   MERGED_VERSION - new merged version
#   PROMPTVC_PROJECT_ROOT - project root directory

echo "Merged into $TARGET_PROMPT v$MERGED_VERSION"

# Example: Update downstream dependencies
# pit deps update --dependents-of "$TARGET_PROMPT"

exit 0
''',
        }

        return samples.get(hook_type, "#!/bin/bash\n# Hook script\nexit 0\n")
