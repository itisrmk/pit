"""Repository pattern for data access."""

import re
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from pit.db.database import get_session
from pit.db.models import (
    ABTestResult,
    Fragment,
    Prompt,
    TestCase,
    TestRun,
    TestSuite,
    Version,
)


class PromptRepository:
    """Repository for Prompt CRUD operations."""

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        name: str,
        description: Optional[str] = None,
        base_template_id: Optional[str] = None,
    ) -> Prompt:
        """Create a new prompt.

        Args:
            name: Unique name for the prompt.
            description: Optional description.
            base_template_id: Optional parent prompt ID for composition.

        Returns:
            The created Prompt instance.
        """
        prompt = Prompt(
            name=name,
            description=description,
            base_template_id=base_template_id,
        )
        self.session.add(prompt)
        self.session.flush()
        return prompt

    def get_by_id(self, prompt_id: str) -> Optional[Prompt]:
        """Get a prompt by its ID."""
        return self.session.query(Prompt).filter(Prompt.id == prompt_id).first()

    def get_by_name(self, name: str) -> Optional[Prompt]:
        """Get a prompt by its name."""
        return self.session.query(Prompt).filter(Prompt.name == name).first()

    def list_all(self) -> list[Prompt]:
        """List all prompts."""
        return self.session.query(Prompt).order_by(Prompt.name).all()

    def update(self, prompt: Prompt, **kwargs) -> Prompt:
        """Update a prompt with the given fields."""
        for key, value in kwargs.items():
            if hasattr(prompt, key):
                setattr(prompt, key, value)
        self.session.flush()
        return prompt

    def delete(self, prompt: Prompt) -> None:
        """Delete a prompt and all its versions."""
        self.session.delete(prompt)
        self.session.flush()


class VersionRepository:
    """Repository for Version CRUD operations."""

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        prompt_id: str,
        content: str,
        message: str,
        author: Optional[str] = None,
        tags: Optional[list[str]] = None,
        parent_version_id: Optional[str] = None,
    ) -> Version:
        """Create a new version for a prompt.

        Args:
            prompt_id: ID of the prompt this version belongs to.
            content: The prompt content.
            message: Commit message describing the change.
            author: Optional author name.
            tags: Optional list of tags.
            parent_version_id: Optional parent version for branching.

        Returns:
            The created Version instance.
        """
        # Get next version number
        latest = self.get_latest(prompt_id)
        version_number = (latest.version_number + 1) if latest else 1

        # Extract variables from content (Jinja2 style: {{variable}})
        variables = self._extract_variables(content)

        version = Version(
            prompt_id=prompt_id,
            version_number=version_number,
            content=content,
            variables=variables,
            message=message,
            author=author,
            tags=tags or [],
            parent_version_id=parent_version_id or (latest.id if latest else None),
        )
        self.session.add(version)
        self.session.flush()

        # Update prompt's current version
        prompt = self.session.query(Prompt).filter(Prompt.id == prompt_id).first()
        if prompt:
            prompt.current_version_id = version.id
            self.session.flush()

        return version

    def get_by_id(self, version_id: str) -> Optional[Version]:
        """Get a version by its ID."""
        return self.session.query(Version).filter(Version.id == version_id).first()

    def get_by_number(self, prompt_id: str, version_number: int) -> Optional[Version]:
        """Get a specific version by prompt ID and version number."""
        return (
            self.session.query(Version)
            .filter(Version.prompt_id == prompt_id, Version.version_number == version_number)
            .first()
        )

    def get_by_prompt_and_number(self, prompt_id: str, version_number: int) -> Optional[Version]:
        """Alias for get_by_number for clarity."""
        return self.get_by_number(prompt_id, version_number)

    def get_by_prompt_id(self, prompt_id: str) -> list[Version]:
        """Get all versions for a prompt by ID."""
        return (
            self.session.query(Version)
            .filter(Version.prompt_id == prompt_id)
            .order_by(Version.version_number.asc())
            .all()
        )

    def get_latest(self, prompt_id: str) -> Optional[Version]:
        """Get the latest version of a prompt."""
        return (
            self.session.query(Version)
            .filter(Version.prompt_id == prompt_id)
            .order_by(Version.version_number.desc())
            .first()
        )

    def list_by_prompt(self, prompt_id: str) -> list[Version]:
        """List all versions of a prompt."""
        return (
            self.session.query(Version)
            .filter(Version.prompt_id == prompt_id)
            .order_by(Version.version_number.desc())
            .all()
        )

    def update_tags(self, version: Version, tags: list[str]) -> Version:
        """Update the tags on a version."""
        version.tags = tags
        self.session.flush()
        return version

    def add_tag(self, version: Version, tag: str) -> Version:
        """Add a tag to a version."""
        if tag not in version.tags:
            version.tags = version.tags + [tag]
            self.session.flush()
        return version

    def remove_tag(self, version: Version, tag: str) -> Version:
        """Remove a tag from a version."""
        if tag in version.tags:
            version.tags = [t for t in version.tags if t != tag]
            self.session.flush()
        return version

    def update_semantic_diff(self, version: Version, semantic_diff: dict) -> Version:
        """Update the semantic diff on a version."""
        version.semantic_diff = semantic_diff
        self.session.flush()
        return version

    def update_metrics(
        self,
        version: Version,
        token_usage: Optional[int] = None,
        latency_ms: Optional[float] = None,
        success: bool = True,
        cost: Optional[float] = None,
    ) -> Version:
        """Update performance metrics for a version."""
        n = version.total_invocations

        if token_usage is not None:
            # Rolling average
            if version.avg_token_usage is None:
                version.avg_token_usage = token_usage
            else:
                version.avg_token_usage = (version.avg_token_usage * n + token_usage) // (n + 1)

        if latency_ms is not None:
            if version.avg_latency_ms is None:
                version.avg_latency_ms = latency_ms
            else:
                version.avg_latency_ms = (version.avg_latency_ms * n + latency_ms) / (n + 1)

        if cost is not None:
            if version.avg_cost_per_1k is None:
                version.avg_cost_per_1k = cost
            else:
                version.avg_cost_per_1k = (version.avg_cost_per_1k * n + cost) / (n + 1)

        # Update success rate
        if version.success_rate is None:
            version.success_rate = 1.0 if success else 0.0
        else:
            version.success_rate = (version.success_rate * n + (1.0 if success else 0.0)) / (n + 1)

        version.total_invocations += 1
        self.session.flush()
        return version

    def _extract_variables(self, content: str) -> list[str]:
        """Extract Jinja2-style variables from prompt content.

        Finds patterns like {{variable}} or {{ variable }}.
        """
        pattern = r"\{\{\s*(\w+)\s*\}\}"
        matches = re.findall(pattern, content)
        return list(dict.fromkeys(matches))  # Unique, preserving order


class FragmentRepository:
    """Repository for Fragment CRUD operations."""

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        name: str,
        content: str,
        description: Optional[str] = None,
        parent_fragment_id: Optional[str] = None,
    ) -> Fragment:
        """Create a new fragment."""
        fragment = Fragment(
            name=name,
            content=content,
            description=description,
            parent_fragment_id=parent_fragment_id,
        )
        self.session.add(fragment)
        self.session.flush()
        return fragment

    def get_by_id(self, fragment_id: str) -> Optional[Fragment]:
        """Get a fragment by its ID."""
        return self.session.query(Fragment).filter(Fragment.id == fragment_id).first()

    def get_by_name(self, name: str) -> Optional[Fragment]:
        """Get a fragment by its name."""
        return self.session.query(Fragment).filter(Fragment.name == name).first()

    def list_all(self) -> list[Fragment]:
        """List all fragments."""
        return self.session.query(Fragment).order_by(Fragment.name).all()

    def get_children(self, fragment_id: str) -> list[Fragment]:
        """Get all child fragments for a given fragment."""
        return (
            self.session.query(Fragment)
            .filter(Fragment.parent_fragment_id == fragment_id)
            .all()
        )

    def get_descendants(self, fragment_id: str) -> list[Fragment]:
        """Get all descendants of a fragment recursively."""
        descendants = []
        children = self.get_children(fragment_id)
        for child in children:
            descendants.append(child)
            descendants.extend(self.get_descendants(child.id))
        return descendants

    def update(self, fragment: Fragment, **kwargs) -> Fragment:
        """Update a fragment with the given fields."""
        for key, value in kwargs.items():
            if hasattr(fragment, key):
                setattr(fragment, key, value)
        self.session.flush()
        return fragment

    def delete(self, fragment: Fragment) -> None:
        """Delete a fragment."""
        self.session.delete(fragment)
        self.session.flush()


# Phase 4: Test Framework Repositories


class TestSuiteRepository:
    """Repository for TestSuite CRUD operations."""

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        name: str,
        prompt_id: str,
        description: Optional[str] = None,
    ) -> TestSuite:
        """Create a new test suite for a prompt."""
        suite = TestSuite(
            name=name,
            prompt_id=prompt_id,
            description=description,
        )
        self.session.add(suite)
        self.session.flush()
        return suite

    def get_by_id(self, suite_id: str) -> Optional[TestSuite]:
        """Get a test suite by its ID."""
        return self.session.query(TestSuite).filter(TestSuite.id == suite_id).first()

    def list_by_prompt(self, prompt_id: str) -> list[TestSuite]:
        """List all test suites for a prompt."""
        return (
            self.session.query(TestSuite)
            .filter(TestSuite.prompt_id == prompt_id)
            .order_by(TestSuite.created_at.desc())
            .all()
        )

    def update(self, suite: TestSuite, **kwargs) -> TestSuite:
        """Update a test suite with the given fields."""
        for key, value in kwargs.items():
            if hasattr(suite, key):
                setattr(suite, key, value)
        self.session.flush()
        return suite

    def delete(self, suite: TestSuite) -> None:
        """Delete a test suite and all its test cases."""
        self.session.delete(suite)
        self.session.flush()


class TestCaseRepository:
    """Repository for TestCase CRUD operations."""

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        suite_id: str,
        input_data: dict,
        expected_criteria: Optional[dict] = None,
        name: Optional[str] = None,
    ) -> TestCase:
        """Create a new test case."""
        test_case = TestCase(
            suite_id=suite_id,
            input_data=input_data,
            expected_criteria=expected_criteria,
            name=name,
        )
        self.session.add(test_case)
        self.session.flush()
        return test_case

    def get_by_id(self, case_id: str) -> Optional[TestCase]:
        """Get a test case by its ID."""
        return self.session.query(TestCase).filter(TestCase.id == case_id).first()

    def list_by_suite(self, suite_id: str) -> list[TestCase]:
        """List all test cases in a suite."""
        return (
            self.session.query(TestCase)
            .filter(TestCase.suite_id == suite_id)
            .order_by(TestCase.created_at)
            .all()
        )

    def update(self, test_case: TestCase, **kwargs) -> TestCase:
        """Update a test case with the given fields."""
        for key, value in kwargs.items():
            if hasattr(test_case, key):
                setattr(test_case, key, value)
        self.session.flush()
        return test_case

    def delete(self, test_case: TestCase) -> None:
        """Delete a test case."""
        self.session.delete(test_case)
        self.session.flush()


class TestRunRepository:
    """Repository for TestRun CRUD operations."""

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        version_id: str,
        suite_id: str,
        status: str = "running",
    ) -> TestRun:
        """Create a new test run."""
        test_run = TestRun(
            version_id=version_id,
            suite_id=suite_id,
            status=status,
            results={},
            metrics={},
        )
        self.session.add(test_run)
        self.session.flush()
        return test_run

    def get_by_id(self, run_id: str) -> Optional[TestRun]:
        """Get a test run by its ID."""
        return self.session.query(TestRun).filter(TestRun.id == run_id).first()

    def list_by_version(self, version_id: str) -> list[TestRun]:
        """List all test runs for a version."""
        return (
            self.session.query(TestRun)
            .filter(TestRun.version_id == version_id)
            .order_by(TestRun.created_at.desc())
            .all()
        )

    def list_by_suite(self, suite_id: str) -> list[TestRun]:
        """List all test runs for a suite."""
        return (
            self.session.query(TestRun)
            .filter(TestRun.suite_id == suite_id)
            .order_by(TestRun.created_at.desc())
            .all()
        )

    def update_results(
        self,
        test_run: TestRun,
        results: dict,
        metrics: dict,
        status: str = "completed",
    ) -> TestRun:
        """Update the results of a test run."""
        test_run.results = results
        test_run.metrics = metrics
        test_run.status = status
        self.session.flush()
        return test_run

    def delete(self, test_run: TestRun) -> None:
        """Delete a test run."""
        self.session.delete(test_run)
        self.session.flush()


class ABTestResultRepository:
    """Repository for ABTestResult CRUD operations."""

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        prompt_id: str,
        version_a_id: str,
        version_b_id: str,
        confidence: float,
        winner_id: Optional[str] = None,
        metrics: Optional[dict] = None,
        test_suite_id: Optional[str] = None,
    ) -> ABTestResult:
        """Create a new A/B test result."""
        ab_result = ABTestResult(
            prompt_id=prompt_id,
            version_a_id=version_a_id,
            version_b_id=version_b_id,
            confidence=confidence,
            winner_id=winner_id,
            metrics=metrics or {},
            test_suite_id=test_suite_id,
        )
        self.session.add(ab_result)
        self.session.flush()
        return ab_result

    def get_by_id(self, result_id: str) -> Optional[ABTestResult]:
        """Get an A/B test result by its ID."""
        return self.session.query(ABTestResult).filter(ABTestResult.id == result_id).first()

    def list_by_prompt(self, prompt_id: str) -> list[ABTestResult]:
        """List all A/B test results for a prompt."""
        return (
            self.session.query(ABTestResult)
            .filter(ABTestResult.prompt_id == prompt_id)
            .order_by(ABTestResult.created_at.desc())
            .all()
        )

    def list_by_version(self, version_id: str) -> list[ABTestResult]:
        """List all A/B test results involving a version."""
        return (
            self.session.query(ABTestResult)
            .filter(
                (ABTestResult.version_a_id == version_id)
                | (ABTestResult.version_b_id == version_id)
            )
            .order_by(ABTestResult.created_at.desc())
            .all()
        )

    def delete(self, ab_result: ABTestResult) -> None:
        """Delete an A/B test result."""
        self.session.delete(ab_result)
        self.session.flush()


def get_repositories(
    project_path: Path | None = None,
) -> tuple[PromptRepository, VersionRepository, FragmentRepository]:
    """Get repository instances with a shared session.

    Note: This is a convenience function. For better control,
    use get_session() and create repositories manually.
    """
    with get_session(project_path) as session:
        return (
            PromptRepository(session),
            VersionRepository(session),
            FragmentRepository(session),
        )
