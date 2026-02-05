"""Tests for database models."""

import pytest
from sqlalchemy.orm import Session

from pit.db.models import Prompt, Version, Fragment


class TestPromptModel:
    """Tests for the Prompt model."""

    def test_create_prompt(self, db_session: Session) -> None:
        """Test creating a basic prompt."""
        prompt = Prompt(name="test-prompt", description="A test prompt")
        db_session.add(prompt)
        db_session.flush()

        assert prompt.id is not None
        assert prompt.name == "test-prompt"
        assert prompt.description == "A test prompt"
        assert prompt.current_version_id is None
        assert prompt.created_at is not None
        assert prompt.updated_at is not None

    def test_prompt_name_unique(self, db_session: Session) -> None:
        """Test that prompt names must be unique."""
        from sqlalchemy.exc import IntegrityError

        prompt1 = Prompt(name="unique-name")
        db_session.add(prompt1)
        db_session.flush()

        prompt2 = Prompt(name="unique-name")
        db_session.add(prompt2)

        with pytest.raises(IntegrityError):
            db_session.flush()

        # Roll back to clean up the failed transaction
        db_session.rollback()

    def test_prompt_repr(self, db_session: Session) -> None:
        """Test the string representation of a prompt."""
        prompt = Prompt(name="my-prompt")
        db_session.add(prompt)
        db_session.flush()

        repr_str = repr(prompt)
        assert "my-prompt" in repr_str
        assert prompt.id[:8] in repr_str


class TestVersionModel:
    """Tests for the Version model."""

    def test_create_version(self, db_session: Session) -> None:
        """Test creating a version."""
        prompt = Prompt(name="test-prompt")
        db_session.add(prompt)
        db_session.flush()

        version = Version(
            prompt_id=prompt.id,
            version_number=1,
            content="This is a test prompt",
            message="Initial version",
        )
        db_session.add(version)
        db_session.flush()

        assert version.id is not None
        assert version.prompt_id == prompt.id
        assert version.version_number == 1
        assert version.content == "This is a test prompt"
        assert version.message == "Initial version"
        assert version.variables == []
        assert version.tags == []

    def test_version_with_variables(self, db_session: Session) -> None:
        """Test version with extracted variables."""
        prompt = Prompt(name="test-prompt")
        db_session.add(prompt)
        db_session.flush()

        version = Version(
            prompt_id=prompt.id,
            version_number=1,
            content="Hello {{name}}, today is {{day}}",
            message="Added variables",
            variables=["name", "day"],
        )
        db_session.add(version)
        db_session.flush()

        assert version.variables == ["name", "day"]

    def test_version_with_tags(self, db_session: Session) -> None:
        """Test version with tags."""
        prompt = Prompt(name="test-prompt")
        db_session.add(prompt)
        db_session.flush()

        version = Version(
            prompt_id=prompt.id,
            version_number=1,
            content="Test",
            message="Production ready",
            tags=["production", "stable"],
        )
        db_session.add(version)
        db_session.flush()

        assert "production" in version.tags
        assert "stable" in version.tags

    def test_version_prompt_relationship(self, db_session: Session) -> None:
        """Test the relationship between version and prompt."""
        prompt = Prompt(name="test-prompt")
        db_session.add(prompt)
        db_session.flush()

        version = Version(
            prompt_id=prompt.id,
            version_number=1,
            content="Test content",
            message="Test",
        )
        db_session.add(version)
        db_session.flush()

        # Refresh to load relationships
        db_session.refresh(prompt)
        db_session.refresh(version)

        assert version.prompt.name == "test-prompt"
        assert len(prompt.versions) == 1
        assert prompt.versions[0].id == version.id


class TestFragmentModel:
    """Tests for the Fragment model."""

    def test_create_fragment(self, db_session: Session) -> None:
        """Test creating a fragment."""
        fragment = Fragment(
            name="json-output",
            content="Output your response as valid JSON.",
            description="Fragment for JSON output instruction",
        )
        db_session.add(fragment)
        db_session.flush()

        assert fragment.id is not None
        assert fragment.name == "json-output"
        assert "JSON" in fragment.content
        assert fragment.created_at is not None
