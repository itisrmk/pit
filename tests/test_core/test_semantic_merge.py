"""Tests for semantic merge functionality."""

import pytest

from pit.core.semantic_merge import (
    SemanticCategorizer, SemanticMergeAnalyzer,
    ChangeCategory, ChangeSeverity,
    SemanticChange, MergeConflict,
    categorize_semantic_diff,
)


class TestSemanticCategorizer:
    """Test semantic categorization."""

    def test_categorize_tone_change(self):
        """Test categorizing tone changes."""
        categorizer = SemanticCategorizer()

        changes = categorizer.categorize_change(
            old_text="Be professional",
            new_text="Be friendly and conversational",
        )

        categories = [c.category for c in changes]
        assert ChangeCategory.TONE in categories

    def test_categorize_constraint_change(self):
        """Test categorizing constraint changes."""
        categorizer = SemanticCategorizer()

        changes = categorizer.categorize_change(
            old_text="Answer questions",
            new_text="Answer questions. Maximum 100 words.",
        )

        categories = [c.category for c in changes]
        # Constraint keywords like "maximum" should trigger CONSTRAINTS
        assert ChangeCategory.CONSTRAINTS in categories

    def test_categorize_structure_change(self):
        """Test categorizing structure changes."""
        categorizer = SemanticCategorizer()

        changes = categorizer.categorize_change(
            old_text="Provide an answer",
            new_text="Provide the answer in JSON format",
        )

        categories = [c.category for c in changes]
        assert ChangeCategory.STRUCTURE in categories

    def test_categorize_addition(self):
        """Test categorizing additions."""
        categorizer = SemanticCategorizer()

        changes = categorizer.categorize_change(
            old_text=None,
            new_text="For example: sample output",
        )

        categories = [c.category for c in changes]
        assert ChangeCategory.EXAMPLES in categories

    def test_severity_calculation_low(self):
        """Test low severity changes."""
        categorizer = SemanticCategorizer()

        changes = categorizer.categorize_change(
            old_text="Hello world",
            new_text="Hello there world",
        )

        assert all(c.severity == ChangeSeverity.LOW for c in changes)

    def test_severity_calculation_high(self):
        """Test high severity changes."""
        categorizer = SemanticCategorizer()

        changes = categorizer.categorize_change(
            old_text="Be helpful",
            new_text="Be extremely formal and use technical jargon exclusively",
        )

        # Should have at least one high severity
        assert any(c.severity in (ChangeSeverity.HIGH, ChangeSeverity.BREAKING) for c in changes)


class TestSemanticMergeAnalyzer:
    """Test semantic merge analysis."""

    def test_no_conflict_different_categories(self):
        """Test merge of orthogonal changes."""
        analyzer = SemanticMergeAnalyzer()

        base = "Answer questions"
        branch_a = "Answer questions. Be friendly."
        branch_b = "Answer questions. Respond in JSON format."

        result = analyzer.analyze_merge(base, branch_a, branch_b)

        assert result.success is True
        assert result.auto_merged is True
        assert len(result.conflicts) == 0

    def test_conflict_same_category(self):
        """Test conflict detection for same category changes."""
        analyzer = SemanticMergeAnalyzer()

        # Use a longer base text so replacements have enough context for similarity calculation
        base = "You are a helpful assistant. Be helpful to users."
        branch_a = "You are a helpful assistant. Be extremely formal and professional."  # Tone change
        branch_b = "You are a helpful assistant. Be casual and use emojis."  # Also tone change

        result = analyzer.analyze_merge(base, branch_a, branch_b)

        # Both changed tone significantly - should be conflict
        assert result.success is False
        assert len(result.conflicts) > 0

    def test_can_auto_merge_orthogonal(self):
        """Test auto-merge detection for orthogonal changes."""
        analyzer = SemanticMergeAnalyzer()

        changes_a = [
            SemanticChange(ChangeCategory.TONE, "Tone change", ChangeSeverity.LOW),
        ]
        changes_b = [
            SemanticChange(ChangeCategory.STRUCTURE, "Structure change", ChangeSeverity.LOW),
        ]

        assert analyzer.can_auto_merge(changes_a, changes_b) is True

    def test_cannot_auto_merge_same_high_severity(self):
        """Test auto-merge detection for conflicting high severity changes."""
        analyzer = SemanticMergeAnalyzer()

        changes_a = [
            SemanticChange(ChangeCategory.TONE, "Tone A", ChangeSeverity.HIGH),
        ]
        changes_b = [
            SemanticChange(ChangeCategory.TONE, "Tone B", ChangeSeverity.HIGH),
        ]

        assert analyzer.can_auto_merge(changes_a, changes_b) is False

    def test_get_changes_detects_additions(self):
        """Test change detection for additions."""
        analyzer = SemanticMergeAnalyzer()

        base = "Original content"
        branch = "Original content\nAdded content"

        changes = analyzer._get_changes(base, branch)

        assert len(changes) > 0


class TestCategorizeSemanticDiff:
    """Test converting semantic diff to categories."""

    def test_categorize_tone_changes(self):
        """Test categorizing tone changes from semantic diff."""
        semantic_diff = {
            "tone_changes": [{"description": "More friendly", "severity": "medium"}],
        }

        categorized = categorize_semantic_diff(semantic_diff)

        assert ChangeCategory.TONE in categorized
        assert len(categorized[ChangeCategory.TONE]) > 0

    def test_categorize_constraint_changes(self):
        """Test categorizing constraint changes."""
        semantic_diff = {
            "constraint_changes": ["Added word limit"],
        }

        categorized = categorize_semantic_diff(semantic_diff)

        assert ChangeCategory.CONSTRAINTS in categorized

    def test_categorize_structure_changes(self):
        """Test categorizing structure changes."""
        semantic_diff = {
            "structure_changes": ["Changed output format"],
        }

        categorized = categorize_semantic_diff(semantic_diff)

        assert ChangeCategory.STRUCTURE in categorized


class TestSemanticChange:
    """Test SemanticChange dataclass."""

    def test_change_creation(self):
        """Test creating a semantic change."""
        change = SemanticChange(
            category=ChangeCategory.TONE,
            description="More friendly tone",
            severity=ChangeSeverity.MEDIUM,
            old_text="Be formal",
            new_text="Be friendly",
        )

        assert change.category == ChangeCategory.TONE
        assert change.severity == ChangeSeverity.MEDIUM


class TestMergeConflict:
    """Test MergeConflict dataclass."""

    def test_conflict_creation(self):
        """Test creating a merge conflict."""
        conflict = MergeConflict(
            category=ChangeCategory.TONE,
            description="Both changed tone",
            base_content="Be helpful",
            branch_a_content="Be formal",
            branch_b_content="Be casual",
            resolution_hint="Choose one tone",
        )

        assert conflict.category == ChangeCategory.TONE
        assert conflict.resolution_hint is not None


class TestChangeCategory:
    """Test ChangeCategory enum."""

    def test_category_values(self):
        """Test category enum values."""
        assert ChangeCategory.TONE.value == "tone"
        assert ChangeCategory.CONSTRAINTS.value == "constraints"
        assert ChangeCategory.STRUCTURE.value == "structure"


class TestChangeSeverity:
    """Test ChangeSeverity enum."""

    def test_severity_ordering(self):
        """Test severity levels."""
        severities = [
            ChangeSeverity.LOW,
            ChangeSeverity.MEDIUM,
            ChangeSeverity.HIGH,
            ChangeSeverity.BREAKING,
        ]

        assert len(severities) == 4
