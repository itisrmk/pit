"""Database connection and session management."""

from pathlib import Path
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from pit.db.models import Base

# Default database location
DEFAULT_DB_DIR = ".pit"
DEFAULT_DB_NAME = "pit.db"


def get_database_url(project_path: Path | None = None) -> str:
    """Get the SQLite database URL for the project.

    Args:
        project_path: Root path of the project. If None, uses current directory.

    Returns:
        SQLite connection URL.
    """
    if project_path is None:
        project_path = Path.cwd()

    db_path = project_path / DEFAULT_DB_DIR / DEFAULT_DB_NAME
    return f"sqlite:///{db_path}"


def create_db_engine(database_url: str):
    """Create a SQLAlchemy engine.

    Args:
        database_url: The database URL to connect to.

    Returns:
        SQLAlchemy Engine instance.
    """
    return create_engine(
        database_url,
        echo=False,
        connect_args={"check_same_thread": False},  # SQLite specific
    )


def init_database(project_path: Path | None = None) -> None:
    """Initialize the database and create all tables.

    Args:
        project_path: Root path of the project. If None, uses current directory.
    """
    if project_path is None:
        project_path = Path.cwd()

    # Ensure .pit directory exists
    db_dir = project_path / DEFAULT_DB_DIR
    db_dir.mkdir(parents=True, exist_ok=True)

    # Create engine and tables
    database_url = get_database_url(project_path)
    engine = create_db_engine(database_url)
    Base.metadata.create_all(engine)


def get_session_factory(project_path: Path | None = None) -> sessionmaker[Session]:
    """Get a session factory for the project database.

    Args:
        project_path: Root path of the project. If None, uses current directory.

    Returns:
        SQLAlchemy sessionmaker instance.
    """
    database_url = get_database_url(project_path)
    engine = create_db_engine(database_url)
    return sessionmaker(bind=engine)


@contextmanager
def get_session(project_path: Path | None = None) -> Generator[Session, None, None]:
    """Get a database session as a context manager.

    Args:
        project_path: Root path of the project. If None, uses current directory.

    Yields:
        SQLAlchemy Session instance.

    Example:
        with get_session() as session:
            prompts = session.query(Prompt).all()
    """
    session_factory = get_session_factory(project_path)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
