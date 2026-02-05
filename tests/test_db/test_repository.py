"""Tests for repository classes."""

import pytest
from sqlalchemy.orm import Session

from pit.db.repository import PromptRepository, VersionRepository, FragmentRepository


class TestPromptRepository:
    """Tests for PromptRepository."""

    def test_create_prompt(self, db_session: Session) -> None:
        """Test creating a prompt through the repository."""
        repo = PromptRepository(db_session)

        prompt = repo.create(name="summarize", description="Summarizes text")

        assert prompt.id is not None
        assert prompt.name == "summarize"
        assert prompt.description == "Summarizes text"

    def test_get_by_name(self, db_session: Session) -> None:
        """Test getting a prompt by name."""
        repo = PromptRepository(db_session)
        repo.create(name="test-prompt")

        found = repo.get_by_name("test-prompt")
        not_found = repo.get_by_name("nonexistent")

        assert found is not None
        assert found.name == "test-prompt"
        assert not_found is None

    def test_get_by_id(self, db_session: Session) -> None:
        """Test getting a prompt by ID."""
        repo = PromptRepository(db_session)
        created = repo.create(name="test-prompt")

        found = repo.get_by_id(created.id)

        assert found is not None
        assert found.id == created.id

    def test_list_all(self, db_session: Session) -> None:
        """Test listing all prompts."""
        repo = PromptRepository(db_session)
        repo.create(name="prompt-a")
        repo.create(name="prompt-b")
        repo.create(name="prompt-c")

        prompts = repo.list_all()

        assert len(prompts) == 3
        # Should be ordered by name
        assert prompts[0].name == "prompt-a"
        assert prompts[1].name == "prompt-b"
        assert prompts[2].name == "prompt-c"

    def test_update_prompt(self, db_session: Session) -> None:
        """Test updating a prompt."""
        repo = PromptRepository(db_session)
        prompt = repo.create(name="test-prompt")

        repo.update(prompt, description="Updated description")

        assert prompt.description == "Updated description"

    def test_delete_prompt(self, db_session: Session) -> None:
        """Test deleting a prompt."""
        repo = PromptRepository(db_session)
        prompt = repo.create(name="to-delete")

        repo.delete(prompt)
        found = repo.get_by_name("to-delete")

        assert found is None


class TestVersionRepository:
    """Tests for VersionRepository."""

    def test_create_version(
        self, db_session: Session, sample_prompt_content: str
    ) -> None:
        """Test creating a version."""
        prompt_repo = PromptRepository(db_session)
        version_repo = VersionRepository(db_session)

        prompt = prompt_repo.create(name="test-prompt")
        version = version_repo.create(
            prompt_id=prompt.id,
            content=sample_prompt_content,
            message="Initial version",
            author="Test Author",
        )

        assert version.id is not None
        assert version.version_number == 1
        assert version.message == "Initial version"
        assert version.author == "Test Author"

    def test_auto_increment_version_number(self, db_session: Session) -> None:
        """Test that version numbers auto-increment."""
        prompt_repo = PromptRepository(db_session)
        version_repo = VersionRepository(db_session)

        prompt = prompt_repo.create(name="test-prompt")
        v1 = version_repo.create(prompt_id=prompt.id, content="v1", message="First")
        v2 = version_repo.create(prompt_id=prompt.id, content="v2", message="Second")
        v3 = version_repo.create(prompt_id=prompt.id, content="v3", message="Third")

        assert v1.version_number == 1
        assert v2.version_number == 2
        assert v3.version_number == 3

    def test_extract_variables(self, db_session: Session) -> None:
        """Test that variables are extracted from content."""
        prompt_repo = PromptRepository(db_session)
        version_repo = VersionRepository(db_session)

        prompt = prompt_repo.create(name="test-prompt")
        version = version_repo.create(
            prompt_id=prompt.id,
            content="Hello {{name}}, today is {{day}}. Your score is {{score}}.",
            message="With variables",
        )

        assert "name" in version.variables
        assert "day" in version.variables
        assert "score" in version.variables
        assert len(version.variables) == 3

    def test_updates_current_version(self, db_session: Session) -> None:
        """Test that creating a version updates the prompt's current version."""
        prompt_repo = PromptRepository(db_session)
        version_repo = VersionRepository(db_session)

        prompt = prompt_repo.create(name="test-prompt")
        v1 = version_repo.create(prompt_id=prompt.id, content="v1", message="First")

        db_session.refresh(prompt)
        assert prompt.current_version_id == v1.id

        v2 = version_repo.create(prompt_id=prompt.id, content="v2", message="Second")

        db_session.refresh(prompt)
        assert prompt.current_version_id == v2.id

    def test_get_by_number(self, db_session: Session) -> None:
        """Test getting a version by version number."""
        prompt_repo = PromptRepository(db_session)
        version_repo = VersionRepository(db_session)

        prompt = prompt_repo.create(name="test-prompt")
        version_repo.create(prompt_id=prompt.id, content="v1", message="First")
        version_repo.create(prompt_id=prompt.id, content="v2", message="Second")

        found = version_repo.get_by_number(prompt.id, 1)
        not_found = version_repo.get_by_number(prompt.id, 99)

        assert found is not None
        assert found.content == "v1"
        assert not_found is None

    def test_get_latest(self, db_session: Session) -> None:
        """Test getting the latest version."""
        prompt_repo = PromptRepository(db_session)
        version_repo = VersionRepository(db_session)

        prompt = prompt_repo.create(name="test-prompt")
        version_repo.create(prompt_id=prompt.id, content="v1", message="First")
        version_repo.create(prompt_id=prompt.id, content="v2", message="Second")
        version_repo.create(prompt_id=prompt.id, content="v3", message="Third")

        latest = version_repo.get_latest(prompt.id)

        assert latest is not None
        assert latest.version_number == 3
        assert latest.content == "v3"

    def test_list_by_prompt(self, db_session: Session) -> None:
        """Test listing all versions of a prompt."""
        prompt_repo = PromptRepository(db_session)
        version_repo = VersionRepository(db_session)

        prompt = prompt_repo.create(name="test-prompt")
        version_repo.create(prompt_id=prompt.id, content="v1", message="First")
        version_repo.create(prompt_id=prompt.id, content="v2", message="Second")

        versions = version_repo.list_by_prompt(prompt.id)

        assert len(versions) == 2
        # Should be ordered by version number descending
        assert versions[0].version_number == 2
        assert versions[1].version_number == 1

    def test_add_tag(self, db_session: Session) -> None:
        """Test adding a tag to a version."""
        prompt_repo = PromptRepository(db_session)
        version_repo = VersionRepository(db_session)

        prompt = prompt_repo.create(name="test-prompt")
        version = version_repo.create(prompt_id=prompt.id, content="test", message="Test")

        version_repo.add_tag(version, "production")
        version_repo.add_tag(version, "stable")

        assert "production" in version.tags
        assert "stable" in version.tags

    def test_remove_tag(self, db_session: Session) -> None:
        """Test removing a tag from a version."""
        prompt_repo = PromptRepository(db_session)
        version_repo = VersionRepository(db_session)

        prompt = prompt_repo.create(name="test-prompt")
        version = version_repo.create(
            prompt_id=prompt.id,
            content="test",
            message="Test",
            tags=["production", "stable"],
        )

        version_repo.remove_tag(version, "production")

        assert "production" not in version.tags
        assert "stable" in version.tags


class TestFragmentRepository:
    """Tests for FragmentRepository."""

    def test_create_fragment(self, db_session: Session) -> None:
        """Test creating a fragment."""
        repo = FragmentRepository(db_session)

        fragment = repo.create(
            name="json-output",
            content="Output as JSON",
            description="JSON format instruction",
        )

        assert fragment.id is not None
        assert fragment.name == "json-output"

    def test_list_all_fragments(self, db_session: Session) -> None:
        """Test listing all fragments."""
        repo = FragmentRepository(db_session)
        repo.create(name="frag-a", content="Content A")
        repo.create(name="frag-b", content="Content B")

        fragments = repo.list_all()

        assert len(fragments) == 2
