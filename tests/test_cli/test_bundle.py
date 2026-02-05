"""Tests for bundle commands and core logic."""

import json
import pytest
from typer.testing import CliRunner
from pathlib import Path

from pit.cli.main import app
from pit.core.bundle import (
    BundleBuilder, BundleInspector, BundleInstaller,
    BundleManifest, BundledPrompt, BUNDLE_VERSION, BUNDLE_EXTENSION
)
from pit.db.database import get_session
from pit.db.repository import PromptRepository, VersionRepository


runner = CliRunner()


class TestBundleCore:
    """Test core bundle logic."""

    def test_bundle_builder_add_prompt(self):
        """Test adding prompts to a bundle."""
        builder = BundleBuilder(name="test-bundle", description="Test")

        builder.add_prompt(
            name="prompt1",
            description="First prompt",
            versions=[{
                "version_number": 1,
                "content": "v1 content",
                "message": "Initial",
            }],
            current_version=1,
            tags=["tag1"],
        )

        assert len(builder.prompts) == 1
        assert builder.prompts[0].name == "prompt1"

    def test_bundle_build(self, tmp_path):
        """Test building a bundle file."""
        builder = BundleBuilder(name="test-bundle", author="tester")

        builder.add_prompt(
            name="prompt1",
            description="Test prompt",
            versions=[{
                "version_number": 1,
                "content": "Hello world",
                "message": "First version",
            }],
        )

        output_path = tmp_path / "test.bundle"
        result = builder.build(output_path)

        assert result.exists()
        assert result.suffix == BUNDLE_EXTENSION

    def test_bundle_inspector_manifest(self, tmp_path):
        """Test reading bundle manifest."""
        # Build a bundle first
        builder = BundleBuilder(name="my-bundle", description="My bundle")
        builder.add_prompt(
            name="prompt1",
            description="Test",
            versions=[{"version_number": 1, "content": "test", "message": "v1"}],
        )
        bundle_path = builder.build(tmp_path / "test.bundle")

        # Inspect it
        inspector = BundleInspector(bundle_path)
        manifest = inspector.get_manifest()

        assert manifest.name == "my-bundle"
        assert manifest.bundle_version == BUNDLE_VERSION

    def test_bundle_inspector_list_prompts(self, tmp_path):
        """Test listing prompts in bundle."""
        builder = BundleBuilder(name="test")
        builder.add_prompt(name="prompt1", description="First", versions=[])
        builder.add_prompt(name="prompt2", description="Second", versions=[])
        bundle_path = builder.build(tmp_path / "test.bundle")

        inspector = BundleInspector(bundle_path)
        prompts = inspector.list_prompts()

        assert "prompt1" in prompts
        assert "prompt2" in prompts

    def test_bundle_extract_content(self, tmp_path):
        """Test extracting prompt content from bundle."""
        builder = BundleBuilder(name="test")
        builder.add_prompt(
            name="prompt1",
            description="Test",
            versions=[{
                "version_number": 1,
                "content": "Hello world",
                "message": "First",
            }],
        )
        bundle_path = builder.build(tmp_path / "test.bundle")

        inspector = BundleInspector(bundle_path)
        content = inspector.extract_prompt_content("prompt1", 1)

        assert content == "Hello world"

    def test_bundle_extract_nonexistent(self, tmp_path):
        """Test extracting content that doesn't exist."""
        builder = BundleBuilder(name="test")
        builder.add_prompt(name="prompt1", description="Test", versions=[])
        bundle_path = builder.build(tmp_path / "test.bundle")

        inspector = BundleInspector(bundle_path)
        content = inspector.extract_prompt_content("prompt1", 999)

        assert content is None


class TestBundleInstaller:
    """Test bundle installation."""

    def test_install_bundle(self, initialized_project, tmp_path):
        """Test installing a bundle."""
        project_root = initialized_project

        # Create a bundle
        builder = BundleBuilder(name="test-bundle")
        builder.add_prompt(
            name="bundled-prompt",
            description="From bundle",
            versions=[{
                "version_number": 1,
                "content": "Bundled content",
                "message": "Bundled",
            }],
        )
        bundle_path = builder.build(tmp_path / "test.bundle")

        # Install it
        installer = BundleInstaller(project_root)
        installed = installer.install(bundle_path)

        assert "bundled-prompt" in installed

        # Verify it was installed
        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            prompt = prompt_repo.get_by_name("bundled-prompt")
            assert prompt is not None
            assert prompt.description == "From bundle"

    def test_install_with_prefix(self, initialized_project, tmp_path):
        """Test installing with a prefix."""
        project_root = initialized_project

        builder = BundleBuilder(name="test")
        builder.add_prompt(
            name="myprompt",
            description="Test",
            versions=[{"version_number": 1, "content": "test", "message": "v1"}],
        )
        bundle_path = builder.build(tmp_path / "test.bundle")

        installer = BundleInstaller(project_root, prefix="bundle")
        installed = installer.install(bundle_path)

        assert "bundle_myprompt" in installed

    def test_install_skip_existing(self, initialized_project, tmp_path):
        """Test that existing prompts are skipped."""
        project_root = initialized_project

        # Create an existing prompt
        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            prompt_repo.create(name="existing-prompt")

        # Create bundle with same name
        builder = BundleBuilder(name="test")
        builder.add_prompt(
            name="existing-prompt",
            description="From bundle",
            versions=[{"version_number": 1, "content": "test", "message": "v1"}],
        )
        bundle_path = builder.build(tmp_path / "test.bundle")

        installer = BundleInstaller(project_root)
        installed = installer.install(bundle_path)

        assert "existing-prompt" not in installed


class TestBundleCLI:
    """Test bundle CLI commands."""

    def test_bundle_create(self, initialized_project, monkeypatch):
        """Test bundle create command."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        # Create a prompt first
        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            version_repo = VersionRepository(db_session)

            prompt = prompt_repo.create(name="my-prompt")
            version_repo.create(prompt_id=prompt.id, content="v1 content", message="V1")

        result = runner.invoke(app, ["bundle", "create", "my-bundle"])

        assert result.exit_code == 0
        assert "Created bundle" in result.output

        # Verify file exists
        bundle_path = project_root / f"my-bundle{BUNDLE_EXTENSION}"
        assert bundle_path.exists()

    def test_bundle_create_with_prompts(self, initialized_project, monkeypatch):
        """Test bundle create with specific prompts."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            version_repo = VersionRepository(db_session)

            prompt1 = prompt_repo.create(name="prompt1")
            prompt2 = prompt_repo.create(name="prompt2")
            version_repo.create(prompt_id=prompt1.id, content="p1", message="V1")
            version_repo.create(prompt_id=prompt2.id, content="p2", message="V1")

        result = runner.invoke(app, ["bundle", "create", "my-bundle", "--prompts", "prompt1"])

        assert result.exit_code == 0
        assert "Included 1 prompt" in result.output

    def test_bundle_create_missing_prompt_fails(self, initialized_project, monkeypatch):
        """Test bundle create fails for missing prompt."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        result = runner.invoke(app, ["bundle", "create", "my-bundle", "--prompts", "nonexistent"])

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_bundle_inspect(self, initialized_project, monkeypatch):
        """Test bundle inspect command."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        # Create and build a bundle
        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            version_repo = VersionRepository(db_session)

            prompt = prompt_repo.create(name="my-prompt", description="Test prompt")
            version_repo.create(prompt_id=prompt.id, content="v1", message="V1")

        runner.invoke(app, ["bundle", "create", "my-bundle"])
        bundle_path = project_root / f"my-bundle{BUNDLE_EXTENSION}"

        result = runner.invoke(app, ["bundle", "inspect", str(bundle_path)])

        assert result.exit_code == 0
        assert "my-bundle" in result.output
        assert "my-prompt" in result.output

    def test_bundle_inspect_not_found(self, initialized_project, monkeypatch):
        """Test bundle inspect fails for missing file."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        result = runner.invoke(app, ["bundle", "inspect", "nonexistent.bundle"])

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_bundle_install(self, initialized_project, monkeypatch, tmp_path):
        """Test bundle install command."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        # Create a bundle
        from pit.core.bundle import BundleBuilder
        builder = BundleBuilder(name="test-bundle")
        builder.add_prompt(
            name="bundled-prompt",
            description="From bundle",
            versions=[{
                "version_number": 1,
                "content": "Bundled content",
                "message": "V1",
            }],
        )
        bundle_path = builder.build(tmp_path / "test.bundle")

        result = runner.invoke(app, ["bundle", "install", str(bundle_path)])

        assert result.exit_code == 0
        assert "Installed 1 prompt" in result.output
        assert "bundled-prompt" in result.output

    def test_bundle_install_with_prefix(self, initialized_project, monkeypatch, tmp_path):
        """Test bundle install with prefix."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        from pit.core.bundle import BundleBuilder
        builder = BundleBuilder(name="test")
        builder.add_prompt(
            name="myprompt",
            description="Test",
            versions=[{"version_number": 1, "content": "test", "message": "v1"}],
        )
        bundle_path = builder.build(tmp_path / "test.bundle")

        result = runner.invoke(app, ["bundle", "install", str(bundle_path), "--prefix", "ext"])

        assert result.exit_code == 0
        assert "ext_myprompt" in result.output

    def test_bundle_list_contents(self, initialized_project, monkeypatch, tmp_path):
        """Test bundle list-contents command."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        from pit.core.bundle import BundleBuilder
        builder = BundleBuilder(name="test")
        builder.add_prompt(
            name="prompt1",
            description="Test",
            versions=[{"version_number": 1, "content": "test", "message": "v1"}],
        )
        bundle_path = builder.build(tmp_path / "test.bundle")

        result = runner.invoke(app, ["bundle", "list-contents", str(bundle_path)])

        assert result.exit_code == 0
        assert "manifest.json" in result.output

    def test_bundle_export_json(self, initialized_project, monkeypatch, tmp_path):
        """Test bundle export to JSON."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        from pit.core.bundle import BundleBuilder
        builder = BundleBuilder(name="test", description="Test bundle")
        builder.add_prompt(
            name="prompt1",
            description="Test",
            versions=[{"version_number": 1, "content": "test", "message": "v1"}],
        )
        bundle_path = builder.build(tmp_path / "test.bundle")

        result = runner.invoke(app, ["bundle", "export", str(bundle_path), "--format", "json"])

        assert result.exit_code == 0
        # Should print valid JSON
        data = json.loads(result.output)
        assert data["name"] == "test"


class TestBundleData:
    """Test Bundle dataclasses."""

    def test_manifest_to_dict(self):
        """Test manifest serialization."""
        manifest = BundleManifest(
            bundle_version=BUNDLE_VERSION,
            name="test",
            description="Test bundle",
            author="tester",
            created_at="2024-01-01T00:00:00",
            prompts=[{"name": "p1"}],
            test_suites=[],
        )

        data = manifest.to_dict()
        assert data["name"] == "test"
        assert data["bundle_version"] == BUNDLE_VERSION

    def test_manifest_from_dict(self):
        """Test manifest deserialization."""
        data = {
            "bundle_version": BUNDLE_VERSION,
            "name": "test",
            "description": "Test",
            "author": "tester",
            "created_at": "2024-01-01T00:00:00",
            "prompts": [],
            "test_suites": [],
        }

        manifest = BundleManifest.from_dict(data)
        assert manifest.name == "test"
        assert manifest.author == "tester"

    def test_bundled_prompt_to_dict(self):
        """Test bundled prompt serialization."""
        prompt = BundledPrompt(
            name="test",
            description="Test prompt",
            versions=[{"version_number": 1}],
            current_version=1,
            tags=["tag1"],
        )

        data = prompt.to_dict()
        assert data["name"] == "test"
        assert data["tags"] == ["tag1"]

    def test_bundled_prompt_from_dict(self):
        """Test bundled prompt deserialization."""
        data = {
            "name": "test",
            "description": "Test",
            "versions": [{"version_number": 1}],
            "current_version": 2,
            "tags": ["tag1"],
        }

        prompt = BundledPrompt.from_dict(data)
        assert prompt.name == "test"
        assert prompt.current_version == 2
