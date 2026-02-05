"""Pytest fixtures for pit tests."""

import os
import tempfile
from pathlib import Path
from typing import Generator

import pytest
from sqlalchemy.orm import Session

from pit.config import Config, DEFAULT_DIR
from pit.db.database import init_database, get_session_factory
from pit.db.models import Base


@pytest.fixture(autouse=True)
def ensure_valid_cwd(tmp_path):
    """Ensure each test starts with a valid working directory."""
    # Store the original cwd at fixture definition time
    import pytest
    # At test time, ensure cwd is valid
    try:
        os.getcwd()
    except FileNotFoundError:
        os.chdir(tmp_path)
    yield
    # After test, ensure cwd is valid for next test
    try:
        os.getcwd()
    except FileNotFoundError:
        os.chdir(tmp_path)


@pytest.fixture
def temp_project() -> Generator[Path, None, None]:
    """Create a temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def initialized_project(temp_project: Path) -> Path:
    """Create an initialized pit project."""
    # Create .pit directory and initialize database
    pit_dir = temp_project / DEFAULT_DIR
    pit_dir.mkdir()
    init_database(temp_project)

    # Create default config
    config = Config()
    config.save(temp_project)

    return temp_project


@pytest.fixture
def db_session(initialized_project: Path) -> Generator[Session, None, None]:
    """Get a database session for the initialized project."""
    session_factory = get_session_factory(initialized_project)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture
def sample_prompt_content() -> str:
    """Sample prompt content for testing."""
    return """You are a helpful assistant that summarizes text.

Given the following text:
{{text}}

Please provide a concise summary in {{format}} format.
Keep it under {{max_length}} words."""


@pytest.fixture
def sample_prompt_v2_content() -> str:
    """Updated version of sample prompt for diff testing."""
    return """You are an expert assistant specializing in text summarization.

Given the following text:
{{text}}

Please provide a concise summary in {{format}} format.
Keep it under {{max_length}} words.

Include key points and main ideas only."""
