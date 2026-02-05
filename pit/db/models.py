"""SQLAlchemy ORM models for pit."""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, Integer, Float, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class Prompt(Base):
    """A prompt entity being versioned."""

    __tablename__ = "prompts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    current_version_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("versions.id", use_alter=True), nullable=True
    )
    base_template_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("prompts.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    versions: Mapped[list["Version"]] = relationship(
        "Version",
        back_populates="prompt",
        foreign_keys="Version.prompt_id",
        order_by="Version.version_number",
    )
    current_version: Mapped[Optional["Version"]] = relationship(
        "Version",
        foreign_keys=[current_version_id],
        post_update=True,
    )
    base_template: Mapped[Optional["Prompt"]] = relationship(
        "Prompt",
        remote_side=[id],
        foreign_keys=[base_template_id],
    )
    test_suites: Mapped[list["TestSuite"]] = relationship(
        "TestSuite",
        back_populates="prompt",
        cascade="all, delete-orphan",
    )
    ab_test_results: Mapped[list["ABTestResult"]] = relationship(
        "ABTestResult",
        back_populates="prompt",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Prompt(name={self.name!r}, id={self.id[:8]})>"


class Version(Base):
    """An immutable snapshot of a prompt at a point in time."""

    __tablename__ = "versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    prompt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("prompts.id"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[list] = mapped_column(JSON, default=list)
    semantic_diff: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    author: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    parent_version_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("versions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )

    # Performance metrics (Phase 4)
    avg_token_usage: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    avg_latency_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    success_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_cost_per_1k: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_invocations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    prompt: Mapped["Prompt"] = relationship(
        "Prompt",
        back_populates="versions",
        foreign_keys=[prompt_id],
    )
    parent_version: Mapped[Optional["Version"]] = relationship(
        "Version",
        remote_side=[id],
        foreign_keys=[parent_version_id],
    )
    test_runs: Mapped[list["TestRun"]] = relationship(
        "TestRun",
        back_populates="version",
        cascade="all, delete-orphan",
    )
    ab_test_results_a: Mapped[list["ABTestResult"]] = relationship(
        "ABTestResult",
        foreign_keys="ABTestResult.version_a_id",
        back_populates="version_a",
    )
    ab_test_results_b: Mapped[list["ABTestResult"]] = relationship(
        "ABTestResult",
        foreign_keys="ABTestResult.version_b_id",
        back_populates="version_b",
    )

    def __repr__(self) -> str:
        return f"<Version(prompt={self.prompt_id[:8]}, v{self.version_number})>"


class Fragment(Base):
    """A reusable prompt component."""

    __tablename__ = "fragments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Parent fragment for composition trees (Phase 4)
    parent_fragment_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("fragments.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    parent_fragment: Mapped[Optional["Fragment"]] = relationship(
        "Fragment",
        remote_side=[id],
        foreign_keys=[parent_fragment_id],
    )
    child_fragments: Mapped[list["Fragment"]] = relationship(
        "Fragment",
        back_populates="parent_fragment",
    )

    def __repr__(self) -> str:
        return f"<Fragment(name={self.name!r})>"


class VersionFragment(Base):
    """Junction table linking versions to fragments."""

    __tablename__ = "version_fragments"

    version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("versions.id"), primary_key=True
    )
    fragment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("fragments.id"), primary_key=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


# Phase 4: Testing Framework Models


class TestSuite(Base):
    """A collection of test cases for a prompt."""

    __tablename__ = "test_suites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("prompts.id"), nullable=False, index=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )

    # Relationships
    prompt: Mapped["Prompt"] = relationship("Prompt", back_populates="test_suites")
    test_cases: Mapped[list["TestCase"]] = relationship(
        "TestCase",
        back_populates="suite",
        cascade="all, delete-orphan",
        order_by="TestCase.created_at",
    )
    test_runs: Mapped[list["TestRun"]] = relationship(
        "TestRun",
        back_populates="suite",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<TestSuite(name={self.name!r}, prompt={self.prompt_id[:8]})>"


class TestCase(Base):
    """A single test case with input and expected criteria."""

    __tablename__ = "test_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    suite_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_suites.id"), nullable=False, index=True
    )
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    input_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    expected_criteria: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )

    # Relationships
    suite: Mapped["TestSuite"] = relationship("TestSuite", back_populates="test_cases")

    def __repr__(self) -> str:
        return f"<TestCase(id={self.id[:8]}, suite={self.suite_id[:8]})>"


class TestRun(Base):
    """Results from running a test suite against a version."""

    __tablename__ = "test_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("versions.id"), nullable=False, index=True
    )
    suite_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("test_suites.id"), nullable=False, index=True
    )
    results: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(50), default="running", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )

    # Relationships
    version: Mapped["Version"] = relationship("Version", back_populates="test_runs")
    suite: Mapped["TestSuite"] = relationship("TestSuite", back_populates="test_runs")

    def __repr__(self) -> str:
        return f"<TestRun(version={self.version_id[:8]}, suite={self.suite_id[:8]})>"


class ABTestResult(Base):
    """Results from an A/B test between two versions."""

    __tablename__ = "ab_test_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    prompt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("prompts.id"), nullable=False, index=True
    )
    version_a_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("versions.id"), nullable=False, index=True
    )
    version_b_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("versions.id"), nullable=False, index=True
    )
    winner_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("versions.id"), nullable=True
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    test_suite_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("test_suites.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )

    # Relationships
    prompt: Mapped["Prompt"] = relationship("Prompt", back_populates="ab_test_results")
    version_a: Mapped["Version"] = relationship(
        "Version",
        foreign_keys=[version_a_id],
        back_populates="ab_test_results_a",
    )
    version_b: Mapped["Version"] = relationship(
        "Version",
        foreign_keys=[version_b_id],
        back_populates="ab_test_results_b",
    )
    winner: Mapped[Optional["Version"]] = relationship(
        "Version",
        foreign_keys=[winner_id],
    )

    def __repr__(self) -> str:
        return f"<ABTestResult(prompt={self.prompt_id[:8]}, confidence={self.confidence:.2f})>"
