"""Core dependencies logic for external prompt dependencies."""

import json
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Any
import urllib.request
import urllib.error


class DependencySource(Enum):
    """Source types for dependencies."""
    GITHUB = "github"
    LOCAL = "local"
    URL = "url"


@dataclass
class Dependency:
    """A dependency specification."""
    name: str
    source: DependencySource
    path: str
    version: str
    resolved_url: Optional[str] = None
    installed_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "source": self.source.value,
            "path": self.path,
            "version": self.version,
            "resolved_url": self.resolved_url,
            "installed_at": self.installed_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Dependency":
        return cls(
            name=data["name"],
            source=DependencySource(data["source"]),
            path=data["path"],
            version=data["version"],
            resolved_url=data.get("resolved_url"),
            installed_at=data.get("installed_at"),
        )


@dataclass
class DependencyLock:
    """Lock file entry for a resolved dependency."""
    name: str
    source: str
    version: str
    resolved_url: str
    checksum: Optional[str] = None
    installed_at: str = None

    def __post_init__(self):
        if self.installed_at is None:
            self.installed_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "source": self.source,
            "version": self.version,
            "resolved_url": self.resolved_url,
            "checksum": self.checksum,
            "installed_at": self.installed_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DependencyLock":
        return cls(
            name=data["name"],
            source=data["source"],
            version=data["version"],
            resolved_url=data["resolved_url"],
            checksum=data.get("checksum"),
            installed_at=data.get("installed_at", datetime.now().isoformat()),
        )


class DependencyResolver:
    """Resolves dependency URLs from specifications."""

    @staticmethod
    def resolve_github(repo: str, path: str, version: str) -> str:
        """Resolve a GitHub dependency to a raw URL."""
        # Convert github repo/path to raw URL
        # e.g., "anthropic/prompts", "citation-format", "v2.1"
        # -> https://raw.githubusercontent.com/anthropic/prompts/v2.1/citation-format.bundle
        return f"https://raw.githubusercontent.com/{repo}/{version}/{path}.bundle"

    @staticmethod
    def resolve_local(path: str) -> str:
        """Resolve a local dependency path."""
        return Path(path).resolve().as_uri()

    @staticmethod
    def resolve_url(url: str) -> str:
        """Resolve a URL dependency."""
        return url


class DependencyManager:
    """Manages prompt dependencies."""

    DEPS_DIR = "deps"
    LOCK_FILE = "deps.lock"
    CONFIG_FILE = ".pit.yaml"

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.deps_dir = project_root / ".pit" / self.DEPS_DIR
        self.lock_file = project_root / ".pit" / self.LOCK_FILE
        self.config_file = project_root / self.CONFIG_FILE

    def _ensure_deps_dir(self) -> None:
        """Ensure the dependencies directory exists."""
        self.deps_dir.mkdir(parents=True, exist_ok=True)

    def list_dependencies(self) -> List[Dependency]:
        """List all configured dependencies."""
        config = self._load_config()
        deps = config.get("dependencies", [])
        return [Dependency.from_dict(d) for d in deps]

    def add_dependency(
        self,
        name: str,
        source: DependencySource,
        path: str,
        version: str,
    ) -> Dependency:
        """Add a new dependency."""
        config = self._load_config()

        if "dependencies" not in config:
            config["dependencies"] = []

        # Check if already exists
        for dep in config["dependencies"]:
            if dep["name"] == name:
                raise ValueError(f"Dependency '{name}' already exists")

        dep = Dependency(
            name=name,
            source=source,
            path=path,
            version=version,
        )

        config["dependencies"].append(dep.to_dict())
        self._save_config(config)

        return dep

    def remove_dependency(self, name: str) -> bool:
        """Remove a dependency."""
        config = self._load_config()

        if "dependencies" not in config:
            return False

        original_len = len(config["dependencies"])
        config["dependencies"] = [d for d in config["dependencies"] if d["name"] != name]

        if len(config["dependencies"]) < original_len:
            self._save_config(config)
            return True
        return False

    def install(self, name: Optional[str] = None) -> List[DependencyLock]:
        """Install dependencies.

        If name is provided, only install that dependency.
        Otherwise, install all dependencies.
        """
        self._ensure_deps_dir()

        deps = self.list_dependencies()
        if name:
            deps = [d for d in deps if d.name == name]
            if not deps:
                raise ValueError(f"Dependency '{name}' not found")

        installed = []
        for dep in deps:
            lock = self._install_dependency(dep)
            if lock:
                installed.append(lock)

        return installed

    def _install_dependency(self, dep: Dependency) -> Optional[DependencyLock]:
        """Install a single dependency."""
        # Resolve URL
        if dep.source == DependencySource.GITHUB:
            resolved_url = DependencyResolver.resolve_github(
                dep.path.split("/")[0] + "/" + dep.path.split("/")[1],
                "/".join(dep.path.split("/")[2:]),
                dep.version,
            )
        elif dep.source == DependencySource.LOCAL:
            resolved_url = DependencyResolver.resolve_local(dep.path)
        elif dep.source == DependencySource.URL:
            resolved_url = DependencyResolver.resolve_url(dep.path)
        else:
            raise ValueError(f"Unknown source: {dep.source}")

        # Download/fetch
        target_path = self.deps_dir / f"{dep.name}.bundle"

        try:
            if dep.source == DependencySource.LOCAL:
                import shutil
                shutil.copy2(dep.path, target_path)
            else:
                urllib.request.urlretrieve(resolved_url, target_path)
        except Exception as e:
            raise ValueError(f"Failed to fetch {dep.name}: {e}")

        # Create lock entry
        lock = DependencyLock(
            name=dep.name,
            source=dep.source.value,
            version=dep.version,
            resolved_url=resolved_url,
        )

        # Update lock file
        self._update_lock_file(lock)

        # Update dependency
        dep.resolved_url = resolved_url
        dep.installed_at = datetime.now().isoformat()
        self._update_dependency(dep)

        return lock

    def update(self, name: Optional[str] = None) -> List[DependencyLock]:
        """Update dependencies to latest versions."""
        # For now, same as install
        # In the future, could check for newer versions
        return self.install(name)

    def get_dependency_tree(self) -> Dict[str, Any]:
        """Get a tree view of dependencies."""
        deps = self.list_dependencies()
        tree = {}

        for dep in deps:
            tree[dep.name] = {
                "source": dep.source.value,
                "version": dep.version,
                "installed": dep.installed_at is not None,
            }

        return tree

    def _load_config(self) -> dict:
        """Load project configuration."""
        if self.config_file.exists():
            import yaml
            return yaml.safe_load(self.config_file.read_text()) or {}
        return {}

    def _save_config(self, config: dict) -> None:
        """Save project configuration."""
        import yaml
        self.config_file.write_text(yaml.dump(config, default_flow_style=False))

    def _update_lock_file(self, lock: DependencyLock) -> None:
        """Update the lock file with a new entry."""
        locks = self._load_lock_file()
        locks[lock.name] = lock.to_dict()

        self.lock_file.write_text(json.dumps(locks, indent=2))

    def _load_lock_file(self) -> dict:
        """Load the lock file."""
        if self.lock_file.exists():
            return json.loads(self.lock_file.read_text())
        return {}

    def _update_dependency(self, dep: Dependency) -> None:
        """Update a dependency in the config."""
        config = self._load_config()

        for i, d in enumerate(config.get("dependencies", [])):
            if d["name"] == dep.name:
                config["dependencies"][i] = dep.to_dict()
                break

        self._save_config(config)
