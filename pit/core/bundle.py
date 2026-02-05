"""Core bundle logic for packaging and sharing prompts."""

import json
import tarfile
import tempfile
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
import shutil


BUNDLE_VERSION = "1.0"
BUNDLE_EXTENSION = ".bundle"


@dataclass
class BundleManifest:
    """Manifest for a prompt bundle."""
    bundle_version: str
    name: str
    description: Optional[str]
    author: Optional[str]
    created_at: str
    prompts: List[Dict[str, Any]]
    test_suites: List[Dict[str, Any]]

    def to_dict(self) -> dict:
        return {
            "bundle_version": self.bundle_version,
            "name": self.name,
            "description": self.description,
            "author": self.author,
            "created_at": self.created_at,
            "prompts": self.prompts,
            "test_suites": self.test_suites,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BundleManifest":
        return cls(
            bundle_version=data["bundle_version"],
            name=data["name"],
            description=data.get("description"),
            author=data.get("author"),
            created_at=data["created_at"],
            prompts=data.get("prompts", []),
            test_suites=data.get("test_suites", []),
        )


@dataclass
class BundledPrompt:
    """A prompt included in a bundle."""
    name: str
    description: Optional[str]
    versions: List[Dict[str, Any]]
    current_version: int
    tags: List[str]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "versions": self.versions,
            "current_version": self.current_version,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BundledPrompt":
        return cls(
            name=data["name"],
            description=data.get("description"),
            versions=data.get("versions", []),
            current_version=data.get("current_version", 1),
            tags=data.get("tags", []),
        )


class BundleBuilder:
    """Builds prompt bundles."""

    def __init__(
        self,
        name: str,
        description: Optional[str] = None,
        author: Optional[str] = None,
    ):
        self.name = name
        self.description = description
        self.author = author
        self.prompts: List[BundledPrompt] = []
        self.test_suites: List[Dict[str, Any]] = []

    def add_prompt(
        self,
        name: str,
        description: Optional[str],
        versions: List[Dict[str, Any]],
        current_version: int = 1,
        tags: Optional[List[str]] = None,
    ) -> None:
        """Add a prompt to the bundle."""
        self.prompts.append(BundledPrompt(
            name=name,
            description=description,
            versions=versions,
            current_version=current_version,
            tags=tags or [],
        ))

    def add_test_suite(self, suite: Dict[str, Any]) -> None:
        """Add a test suite to the bundle."""
        self.test_suites.append(suite)

    def build(self, output_path: Path) -> Path:
        """Build the bundle file."""
        # Ensure correct extension
        if not output_path.suffix == BUNDLE_EXTENSION:
            output_path = output_path.with_suffix(BUNDLE_EXTENSION)

        manifest = BundleManifest(
            bundle_version=BUNDLE_VERSION,
            name=self.name,
            description=self.description,
            author=self.author,
            created_at=datetime.now().isoformat(),
            prompts=[p.to_dict() for p in self.prompts],
            test_suites=self.test_suites,
        )

        # Create bundle as tar.gz
        with tarfile.open(output_path, "w:gz") as tar:
            # Add manifest
            manifest_json = json.dumps(manifest.to_dict(), indent=2)
            manifest_bytes = manifest_json.encode("utf-8")

            import io
            manifest_info = tarfile.TarInfo(name="manifest.json")
            manifest_info.size = len(manifest_bytes)
            tar.addfile(manifest_info, io.BytesIO(manifest_bytes))

            # Add each prompt's versions
            for prompt in self.prompts:
                for version in prompt.versions:
                    content = version.get("content", "")
                    content_bytes = content.encode("utf-8")

                    version_path = f"prompts/{prompt.name}/v{version['version_number']}.txt"
                    version_info = tarfile.TarInfo(name=version_path)
                    version_info.size = len(content_bytes)
                    tar.addfile(version_info, io.BytesIO(content_bytes))

                    # Add metadata
                    meta = {
                        "version_number": version["version_number"],
                        "message": version.get("message", ""),
                        "author": version.get("author"),
                        "created_at": version.get("created_at"),
                        "semantic_diff": version.get("semantic_diff"),
                    }
                    meta_json = json.dumps(meta, indent=2)
                    meta_bytes = meta_json.encode("utf-8")
                    meta_path = f"prompts/{prompt.name}/v{version['version_number']}.json"
                    meta_info = tarfile.TarInfo(name=meta_path)
                    meta_info.size = len(meta_bytes)
                    tar.addfile(meta_info, io.BytesIO(meta_bytes))

        return output_path


class BundleInspector:
    """Inspects bundle contents without extracting."""

    def __init__(self, bundle_path: Path):
        self.bundle_path = bundle_path
        self._manifest: Optional[BundleManifest] = None

    def _load_manifest(self) -> BundleManifest:
        """Load the manifest from the bundle."""
        if self._manifest is None:
            with tarfile.open(self.bundle_path, "r:gz") as tar:
                manifest_file = tar.extractfile("manifest.json")
                if manifest_file is None:
                    raise ValueError("Bundle missing manifest.json")
                data = json.loads(manifest_file.read().decode("utf-8"))
                self._manifest = BundleManifest.from_dict(data)
        return self._manifest

    def get_manifest(self) -> BundleManifest:
        """Get the bundle manifest."""
        return self._load_manifest()

    def list_prompts(self) -> List[str]:
        """List all prompts in the bundle."""
        manifest = self._load_manifest()
        return [p["name"] for p in manifest.prompts]

    def get_prompt_info(self, prompt_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific prompt."""
        manifest = self._load_manifest()
        for prompt in manifest.prompts:
            if prompt["name"] == prompt_name:
                return prompt
        return None

    def extract_prompt_content(self, prompt_name: str, version: int) -> Optional[str]:
        """Extract content for a specific prompt version."""
        with tarfile.open(self.bundle_path, "r:gz") as tar:
            path = f"prompts/{prompt_name}/v{version}.txt"
            try:
                member = tar.getmember(path)
                file = tar.extractfile(member)
                if file:
                    return file.read().decode("utf-8")
            except KeyError:
                pass
        return None


class BundleInstaller:
    """Installs bundles into a pit project."""

    def __init__(self, project_root: Path, prefix: Optional[str] = None):
        self.project_root = project_root
        self.prefix = prefix

    def install(
        self,
        bundle_path: Path,
        prompt_names: Optional[List[str]] = None,
    ) -> List[str]:
        """Install prompts from a bundle.

        Returns list of installed prompt names.
        """
        from pit.db.database import get_session
        from pit.db.repository import PromptRepository, VersionRepository

        inspector = BundleInspector(bundle_path)
        manifest = inspector.get_manifest()

        installed = []

        with get_session(self.project_root) as session:
            prompt_repo = PromptRepository(session)
            version_repo = VersionRepository(session)

            for prompt_data in manifest.prompts:
                name = prompt_data["name"]

                # Apply prefix if specified
                if self.prefix:
                    name = f"{self.prefix}_{name}"

                # Skip if not in requested list
                if prompt_names and prompt_data["name"] not in prompt_names:
                    continue

                # Check if prompt already exists
                if prompt_repo.get_by_name(name):
                    # Skip existing prompts
                    continue

                # Create prompt
                prompt = prompt_repo.create(
                    name=name,
                    description=prompt_data.get("description"),
                )

                # Create versions
                for version_data in prompt_data.get("versions", []):
                    content = inspector.extract_prompt_content(
                        prompt_data["name"],
                        version_data["version_number"],
                    )
                    if content:
                        version_repo.create(
                            prompt_id=prompt.id,
                            content=content,
                            message=version_data.get("message", f"v{version_data['version_number']}"),
                            author=version_data.get("author"),
                        )

                installed.append(name)

        return installed
