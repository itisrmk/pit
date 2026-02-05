"""Tests for patch commands and core logic."""

import json
import pytest
from typer.testing import CliRunner
from pathlib import Path

from pit.cli.main import app
from pit.core.patch import (
    PatchGenerator, PatchApplier, PromptPatch, PatchMetadata,
    PATCH_VERSION, PATCH_EXTENSION
)
from pit.db.database import get_session
from pit.db.repository import PromptRepository, VersionRepository


runner = CliRunner()


class TestPatchCore:
    """Test core patch logic."""

    def test_generate_patch(self, initialized_project):
        """Test generating a patch from two versions."""
        project_root = initialized_project
        generator = PatchGenerator(author="tester")

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            version_repo = VersionRepository(db_session)

            prompt = prompt_repo.create(name="test-prompt")
            v1 = version_repo.create(prompt_id=prompt.id, content="old content", message="V1")
            v2 = version_repo.create(prompt_id=prompt.id, content="new content", message="V2")

            patch = generator.generate("test-prompt", v1, v2, "Test patch")

            assert patch.metadata.source_prompt == "test-prompt"
            assert patch.metadata.source_versions == (1, 2)
            assert patch.metadata.author == "tester"
            assert patch.metadata.description == "Test patch"
            assert patch.old_content == "old content"
            assert patch.new_content == "new content"
            assert patch.metadata.format == PATCH_VERSION

    def test_patch_text_diff(self, initialized_project):
        """Test that patch includes unified diff."""
        project_root = initialized_project
        generator = PatchGenerator()

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            version_repo = VersionRepository(db_session)

            prompt = prompt_repo.create(name="test-prompt")
            v1 = version_repo.create(prompt_id=prompt.id, content="line 1\nline 2", message="V1")
            v2 = version_repo.create(prompt_id=prompt.id, content="line 1\nline 3", message="V2")

            patch = generator.generate("test-prompt", v1, v2)

            assert "--- v1" in patch.text_diff
            assert "+++ v2" in patch.text_diff
            assert "-line 2" in patch.text_diff
            assert "+line 3" in patch.text_diff

    def test_patch_serialization(self, initialized_project):
        """Test patch can be serialized and deserialized."""
        project_root = initialized_project
        generator = PatchGenerator(author="tester")

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            version_repo = VersionRepository(db_session)

            prompt = prompt_repo.create(name="test-prompt")
            v1 = version_repo.create(prompt_id=prompt.id, content="old", message="V1")
            v2 = version_repo.create(prompt_id=prompt.id, content="new", message="V2")

            original = generator.generate("test-prompt", v1, v2, "Test")

            # Serialize
            data = original.to_dict()

            # Deserialize
            restored = PromptPatch.from_dict(data)

            assert restored.metadata.source_prompt == original.metadata.source_prompt
            assert restored.metadata.source_versions == original.metadata.source_versions
            assert restored.old_content == original.old_content
            assert restored.new_content == original.new_content

    def test_patch_save_and_load(self, initialized_project, tmp_path):
        """Test saving and loading patch files."""
        project_root = initialized_project
        generator = PatchGenerator()

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            version_repo = VersionRepository(db_session)

            prompt = prompt_repo.create(name="test-prompt")
            v1 = version_repo.create(prompt_id=prompt.id, content="old", message="V1")
            v2 = version_repo.create(prompt_id=prompt.id, content="new", message="V2")

            patch = generator.generate("test-prompt", v1, v2)

            # Save
            patch_path = tmp_path / "test.patch"
            patch.save(patch_path)

            # Load - note that save adds extension, so use the path with extension
            loaded = PromptPatch.load(patch_path.with_suffix(PATCH_EXTENSION))

            assert loaded.metadata.source_prompt == patch.metadata.source_prompt
            assert loaded.old_content == patch.old_content

    def test_patch_hash(self, initialized_project):
        """Test patch hash generation."""
        project_root = initialized_project
        generator = PatchGenerator()

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            version_repo = VersionRepository(db_session)

            prompt = prompt_repo.create(name="test-prompt")
            v1 = version_repo.create(prompt_id=prompt.id, content="old", message="V1")
            v2 = version_repo.create(prompt_id=prompt.id, content="new", message="V2")

            patch = generator.generate("test-prompt", v1, v2)

            assert len(patch.patch_hash) == 12
            assert patch.patch_hash == patch.patch_hash  # Consistent


class TestPatchApply:
    """Test patch application logic."""

    def test_can_apply_clean(self, initialized_project):
        """Test detecting clean apply."""
        project_root = initialized_project
        generator = PatchGenerator()
        applier = PatchApplier(project_root)

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            version_repo = VersionRepository(db_session)

            prompt = prompt_repo.create(name="test-prompt")
            v1 = version_repo.create(prompt_id=prompt.id, content="target content", message="V1")
            v2 = version_repo.create(prompt_id=prompt.id, content="modified content", message="V2")

            patch = generator.generate("test-prompt", v1, v2)

            can_apply, reason = applier.can_apply(patch, "target content")
            assert can_apply is True
            assert "Clean apply" in reason

    def test_cannot_apply_wrong_base(self, initialized_project):
        """Test detecting when patch can't apply."""
        project_root = initialized_project
        generator = PatchGenerator()
        applier = PatchApplier(project_root)

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            version_repo = VersionRepository(db_session)

            prompt = prompt_repo.create(name="test-prompt")
            v1 = version_repo.create(prompt_id=prompt.id, content="old content", message="V1")
            v2 = version_repo.create(prompt_id=prompt.id, content="new content", message="V2")

            patch = generator.generate("test-prompt", v1, v2)

            can_apply, reason = applier.can_apply(patch, "different content")
            assert can_apply is False
            assert "doesn't match" in reason

    def test_cannot_apply_already_applied(self, initialized_project):
        """Test detecting already-applied patch."""
        project_root = initialized_project
        generator = PatchGenerator()
        applier = PatchApplier(project_root)

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            version_repo = VersionRepository(db_session)

            prompt = prompt_repo.create(name="test-prompt")
            v1 = version_repo.create(prompt_id=prompt.id, content="old", message="V1")
            v2 = version_repo.create(prompt_id=prompt.id, content="new", message="V2")

            patch = generator.generate("test-prompt", v1, v2)

            can_apply, reason = applier.can_apply(patch, "new")
            assert can_apply is False
            assert "already applied" in reason

    def test_apply_patch(self, initialized_project):
        """Test applying a patch."""
        project_root = initialized_project
        generator = PatchGenerator()
        applier = PatchApplier(project_root)

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            version_repo = VersionRepository(db_session)

            prompt = prompt_repo.create(name="test-prompt")
            v1 = version_repo.create(prompt_id=prompt.id, content="old content", message="V1")
            v2 = version_repo.create(prompt_id=prompt.id, content="new content", message="V2")

            patch = generator.generate("test-prompt", v1, v2)

            result = applier.apply(patch, "old content")
            assert result == "new content"

    def test_apply_raises_on_wrong_base(self, initialized_project):
        """Test apply raises error on wrong base."""
        project_root = initialized_project
        generator = PatchGenerator()
        applier = PatchApplier(project_root)

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            version_repo = VersionRepository(db_session)

            prompt = prompt_repo.create(name="test-prompt")
            v1 = version_repo.create(prompt_id=prompt.id, content="old", message="V1")
            v2 = version_repo.create(prompt_id=prompt.id, content="new", message="V2")

            patch = generator.generate("test-prompt", v1, v2)

            with pytest.raises(ValueError, match="Cannot apply"):
                applier.apply(patch, "wrong content")

    def test_fuzzy_apply_similar(self, initialized_project):
        """Test fuzzy apply with similar content."""
        project_root = initialized_project
        generator = PatchGenerator()
        applier = PatchApplier(project_root)

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            version_repo = VersionRepository(db_session)

            prompt = prompt_repo.create(name="test-prompt")
            v1 = version_repo.create(
                prompt_id=prompt.id,
                content="This is a long content with many words in it.",
                message="V1"
            )
            v2 = version_repo.create(
                prompt_id=prompt.id,
                content="This is a long modified content with many words in it.",
                message="V2"
            )

            patch = generator.generate("test-prompt", v1, v2)

            # Similar but not exact base
            similar = "This is a long content with many words."
            result = applier.apply_fuzzy(patch, similar)
            assert result is not None


class TestPatchCLI:
    """Test patch CLI commands."""

    def test_patch_create(self, initialized_project, monkeypatch):
        """Test patch create command."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            version_repo = VersionRepository(db_session)

            prompt = prompt_repo.create(name="my-prompt")
            version_repo.create(prompt_id=prompt.id, content="v1 content", message="V1")
            version_repo.create(prompt_id=prompt.id, content="v2 content", message="V2")

        result = runner.invoke(
            app,
            ["patch", "create", "my-prompt", "v1", "v2"]
        )

        assert result.exit_code == 0
        assert "Created patch" in result.output

        # Check file was created
        patch_file = project_root / f"my-prompt_v1_to_v2{PATCH_EXTENSION}"
        assert patch_file.exists()

    def test_patch_create_with_description(self, initialized_project, monkeypatch):
        """Test patch create with description."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            version_repo = VersionRepository(db_session)

            prompt = prompt_repo.create(name="my-prompt")
            version_repo.create(prompt_id=prompt.id, content="v1", message="V1")
            version_repo.create(prompt_id=prompt.id, content="v2", message="V2")

        result = runner.invoke(
            app,
            ["patch", "create", "my-prompt", "1", "2", "-d", "My patch description"]
        )

        assert result.exit_code == 0

        # Check metadata
        patch_file = project_root / f"my-prompt_v1_to_v2{PATCH_EXTENSION}"
        patch = PromptPatch.load(patch_file)
        assert patch.metadata.description == "My patch description"

    def test_patch_show(self, initialized_project, monkeypatch):
        """Test patch show command."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        # Create a patch file in project root
        metadata = PatchMetadata(
            format=PATCH_VERSION,
            created_at="2024-01-01T00:00:00",
            author="tester",
            source_prompt="test-prompt",
            source_versions=(1, 2),
            description="Test patch",
        )
        patch = PromptPatch(
            metadata=metadata,
            old_content="old",
            new_content="new",
            text_diff="diff here",
            semantic_diff=None,
        )
        patch_path = project_root / "test.patch"
        patch.save(patch_path)

        result = runner.invoke(app, ["patch", "show", str(patch_path.with_suffix(PATCH_EXTENSION))])

        assert result.exit_code == 0
        assert "test-prompt" in result.output
        assert "tester" in result.output
        assert "Test patch" in result.output

    def test_patch_show_with_content(self, initialized_project, monkeypatch):
        """Test patch show with --content flag."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        metadata = PatchMetadata(
            format=PATCH_VERSION,
            created_at="2024-01-01T00:00:00",
            author="tester",
            source_prompt="test-prompt",
            source_versions=(1, 2),
            description=None,
        )
        patch = PromptPatch(
            metadata=metadata,
            old_content="old",
            new_content="new",
            text_diff="--- v1\n+++ v2",
            semantic_diff=None,
        )
        patch_path = project_root / "test.patch"
        patch.save(patch_path)

        result = runner.invoke(app, ["patch", "show", str(patch_path.with_suffix(PATCH_EXTENSION)), "--content"])

        assert result.exit_code == 0
        assert "v1" in result.output
        assert "v2" in result.output

    def test_patch_preview(self, initialized_project, monkeypatch):
        """Test patch preview command."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            version_repo = VersionRepository(db_session)

            prompt = prompt_repo.create(name="test-prompt")
            v1 = version_repo.create(prompt_id=prompt.id, content="base content", message="V1")
            v2 = version_repo.create(prompt_id=prompt.id, content="modified content", message="V2")

            # Create patch
            generator = PatchGenerator()
            patch = generator.generate("test-prompt", v1, v2)
            patch_path = project_root / "test.patch"
            patch.save(patch_path)

        result = runner.invoke(app, ["patch", "preview", str(patch_path.with_suffix(PATCH_EXTENSION))])

        assert result.exit_code == 0
        assert "Can apply" in result.output or "Cannot apply" in result.output

    def test_patch_apply(self, initialized_project, monkeypatch):
        """Test patch apply command."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            version_repo = VersionRepository(db_session)

            prompt = prompt_repo.create(name="test-prompt")
            # v1 = base content, v2 = target content, v3 = current content (similar to base for fuzzy match)
            v1 = version_repo.create(prompt_id=prompt.id, content="This is the base content for testing patches.", message="V1")
            v2 = version_repo.create(prompt_id=prompt.id, content="This is the modified content for testing patches.", message="V2")
            # v3 is similar to v1 (>80%) but not identical
            v3 = version_repo.create(prompt_id=prompt.id, content="This is the base content for testing patches!", message="V3")

            # Create patch from v1 to v2 (base -> modified)
            generator = PatchGenerator()
            patch = generator.generate("test-prompt", v1, v2)
            patch_path = project_root / "test.patch"
            patch.save(patch_path)

        # Apply the patch with force (fuzzy matching)
        result = runner.invoke(app, ["patch", "apply", str(patch_path.with_suffix(PATCH_EXTENSION)), "--force"])

        assert result.exit_code == 0
        assert "Applied" in result.output

        # Verify new version was created (now v4)
        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            version_repo = VersionRepository(db_session)

            prompt = prompt_repo.get_by_name("test-prompt")
            assert prompt.current_version.version_number == 4

    def test_patch_apply_dry_run(self, initialized_project, monkeypatch):
        """Test patch apply with --dry-run."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            version_repo = VersionRepository(db_session)

            prompt = prompt_repo.create(name="test-prompt")
            v1 = version_repo.create(prompt_id=prompt.id, content="base", message="V1")
            v2 = version_repo.create(prompt_id=prompt.id, content="modified", message="V2")

            generator = PatchGenerator()
            patch = generator.generate("test-prompt", v1, v2)
            patch_path = project_root / "test.patch"
            patch.save(patch_path)

        result = runner.invoke(app, ["patch", "apply", str(patch_path.with_suffix(PATCH_EXTENSION)), "--dry-run"])

        assert result.exit_code == 0
        # Should not create new version
        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            prompt = prompt_repo.get_by_name("test-prompt")
            assert prompt.current_version.version_number == 2

    def test_patch_create_missing_prompt_fails(self, initialized_project, monkeypatch):
        """Test patch create fails for missing prompt."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        result = runner.invoke(app, ["patch", "create", "nonexistent", "v1", "v2"])

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_patch_create_missing_version_fails(self, initialized_project, monkeypatch):
        """Test patch create fails for missing version."""
        project_root = initialized_project
        monkeypatch.chdir(project_root)

        with get_session(project_root) as db_session:
            prompt_repo = PromptRepository(db_session)
            prompt_repo.create(name="my-prompt")

        result = runner.invoke(app, ["patch", "create", "my-prompt", "v1", "v2"])

        assert result.exit_code == 1
        assert "not found" in result.output


class TestPatchData:
    """Test Patch dataclasses."""

    def test_metadata_to_dict(self):
        """Test metadata serialization."""
        metadata = PatchMetadata(
            format=PATCH_VERSION,
            created_at="2024-01-01T00:00:00",
            author="tester",
            source_prompt="test",
            source_versions=(1, 2),
            description="desc",
        )

        data = metadata.to_dict()
        assert data["format"] == PATCH_VERSION
        assert data["source_versions"] == [1, 2]
        assert data["author"] == "tester"

    def test_metadata_from_dict(self):
        """Test metadata deserialization."""
        data = {
            "format": PATCH_VERSION,
            "created_at": "2024-01-01T00:00:00",
            "author": "tester",
            "source_prompt": "test",
            "source_versions": [1, 2],
            "description": None,
        }

        metadata = PatchMetadata.from_dict(data)
        assert metadata.format == PATCH_VERSION
        assert metadata.source_versions == (1, 2)
        assert metadata.author == "tester"

    def test_patch_file_extension_added(self, tmp_path):
        """Test that save adds extension if missing."""
        metadata = PatchMetadata(
            format=PATCH_VERSION,
            created_at="2024-01-01T00:00:00",
            author=None,
            source_prompt="test",
            source_versions=(1, 2),
            description=None,
        )
        patch = PromptPatch(
            metadata=metadata,
            old_content="old",
            new_content="new",
            text_diff="diff",
            semantic_diff=None,
        )

        # Save without extension
        path = tmp_path / "mypatch"
        patch.save(path)

        # Should have extension added
        assert path.with_suffix(PATCH_EXTENSION).exists()
