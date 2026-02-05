"""Semantic merge logic for categorizing changes and detecting conflicts."""

from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional, Dict, Any, Tuple
from difflib import SequenceMatcher


class ChangeCategory(Enum):
    """Categories of semantic changes."""
    TONE = "tone"  # Personality, voice changes
    CONSTRAINTS = "constraints"  # Rules and limitations
    EXAMPLES = "examples"  # Few-shot examples
    STRUCTURE = "structure"  # Output format/instructions
    VARIABLES = "variables"  # Template variable changes
    CONTEXT = "context"  # Background information
    INTENT = "intent"  # Purpose or goal changes


class ChangeSeverity(Enum):
    """Severity levels for changes."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BREAKING = "breaking"


@dataclass
class SemanticChange:
    """A single semantic change."""
    category: ChangeCategory
    description: str
    severity: ChangeSeverity
    old_text: Optional[str] = None
    new_text: Optional[str] = None
    line_numbers: Optional[Tuple[int, int]] = None


@dataclass
class MergeConflict:
    """A merge conflict between two sets of changes."""
    category: ChangeCategory
    description: str
    base_content: str
    branch_a_content: str
    branch_b_content: str
    resolution_hint: Optional[str] = None


@dataclass
class MergeResult:
    """Result of a semantic merge."""
    success: bool
    merged_content: Optional[str] = None
    conflicts: List[MergeConflict] = None
    changes: List[SemanticChange] = None
    auto_merged: bool = False

    def __post_init__(self):
        if self.conflicts is None:
            self.conflicts = []
        if self.changes is None:
            self.changes = []


class SemanticCategorizer:
    """Categorizes changes in prompt text."""

    # Keywords that indicate change categories
    CATEGORY_INDICATORS = {
        ChangeCategory.TONE: [
            "tone", "voice", "personality", "style", "manner", "approach",
            "friendly", "professional", "casual", "formal", "enthusiastic",
            "empathetic", "direct", "polite", "conversational", "clinical"
        ],
        ChangeCategory.CONSTRAINTS: [
            "must", "should", "cannot", "don't", "never", "always",
            "limit", "maximum", "minimum", "exactly", "at most", "at least",
            "no more than", "at least", "strictly", "prohibited", "required"
        ],
        ChangeCategory.EXAMPLES: [
            "example", "for instance", "e.g.", "such as", "like",
            "here's an example", "following example", "sample"
        ],
        ChangeCategory.STRUCTURE: [
            "format", "structure", "layout", "organize", "section",
            "output as", "return as", "json", "markdown", "xml",
            "numbered list", "bullet points", "table"
        ],
        ChangeCategory.VARIABLES: [
            "{{", "}}", "variable", "placeholder", "substitute",
            "input", "parameter", "argument"
        ],
        ChangeCategory.CONTEXT: [
            "context", "background", "assume", "given that", "provided",
            "you are a", "acting as", "role", "expertise"
        ],
        ChangeCategory.INTENT: [
            "purpose", "goal", "objective", "aim", "intended",
            "task", "job", "function", "role", "responsibility"
        ],
    }

    def categorize_change(
        self,
        old_text: Optional[str],
        new_text: Optional[str],
        context_lines: Optional[List[str]] = None,
    ) -> List[SemanticChange]:
        """Categorize a change between old and new text."""
        changes = []

        # Determine what changed
        text_to_analyze = new_text or old_text or ""

        # Check each category
        for category, indicators in self.CATEGORY_INDICATORS.items():
            score = self._calculate_category_score(text_to_analyze, indicators)
            if score > 0:
                severity = self._determine_severity(old_text, new_text, score)
                changes.append(SemanticChange(
                    category=category,
                    description=self._generate_description(category, old_text, new_text),
                    severity=severity,
                    old_text=old_text,
                    new_text=new_text,
                ))

        return changes if changes else [
            SemanticChange(
                category=ChangeCategory.CONTEXT,
                description="Content change",
                severity=ChangeSeverity.LOW,
                old_text=old_text,
                new_text=new_text,
            )
        ]

    def _calculate_category_score(self, text: str, indicators: List[str]) -> int:
        """Calculate how strongly a text matches a category."""
        text_lower = text.lower()
        score = 0
        for indicator in indicators:
            if indicator.lower() in text_lower:
                score += 1
        return score

    def _determine_severity(
        self,
        old_text: Optional[str],
        new_text: Optional[str],
        category_score: int,
    ) -> ChangeSeverity:
        """Determine the severity of a change."""
        if not old_text:
            return ChangeSeverity.MEDIUM  # Addition
        if not new_text:
            return ChangeSeverity.HIGH  # Deletion

        # Calculate similarity
        similarity = SequenceMatcher(None, old_text, new_text).ratio()

        if similarity > 0.8:
            return ChangeSeverity.LOW
        elif similarity > 0.5:
            return ChangeSeverity.MEDIUM if category_score < 3 else ChangeSeverity.HIGH
        else:
            return ChangeSeverity.HIGH if category_score < 3 else ChangeSeverity.BREAKING

    def _generate_description(
        self,
        category: ChangeCategory,
        old_text: Optional[str],
        new_text: Optional[str],
    ) -> str:
        """Generate a human-readable description of the change."""
        if not old_text:
            return f"Added {category.value}"
        if not new_text:
            return f"Removed {category.value}"

        change_type = "Modified" if len(new_text) > len(old_text) * 0.5 else "Significantly changed"
        return f"{change_type} {category.value}"


class SemanticMergeAnalyzer:
    """Analyzes semantic compatibility for merging."""

    def __init__(self):
        self.categorizer = SemanticCategorizer()

    def analyze_merge(
        self,
        base_content: str,
        branch_a_content: str,
        branch_b_content: str,
    ) -> MergeResult:
        """Analyze whether two branches can be merged semantically."""
        # Categorize changes from base to each branch
        changes_a = self._get_changes(base_content, branch_a_content)
        changes_b = self._get_changes(base_content, branch_b_content)

        # Check for conflicts
        conflicts = self._detect_conflicts(changes_a, changes_b, base_content)

        if conflicts:
            return MergeResult(
                success=False,
                conflicts=conflicts,
                changes=changes_a + changes_b,
                auto_merged=False,
            )

        # Auto-merge if no conflicts
        merged = self._auto_merge(base_content, changes_a, changes_b)

        return MergeResult(
            success=True,
            merged_content=merged,
            changes=changes_a + changes_b,
            auto_merged=True,
        )

    def _get_changes(
        self,
        base: str,
        branch: str,
    ) -> List[SemanticChange]:
        """Get list of semantic changes between base and branch."""
        changes = []

        # Simple line-by-line diff
        base_lines = base.split('\n')
        branch_lines = branch.split('\n')

        import difflib
        diff = list(difflib.unified_diff(base_lines, branch_lines, lineterm=''))

        # Parse diff and categorize changes
        i = 0
        while i < len(diff):
            if diff[i].startswith('+') and not diff[i].startswith('+++'):
                # Addition
                new_text = diff[i][1:]
                changes.extend(self.categorizer.categorize_change(None, new_text))
            elif diff[i].startswith('-') and not diff[i].startswith('---'):
                # Deletion
                old_text = diff[i][1:]
                changes.extend(self.categorizer.categorize_change(old_text, None))
            i += 1

        return changes

    def _detect_conflicts(
        self,
        changes_a: List[SemanticChange],
        changes_b: List[SemanticChange],
        base_content: str,
    ) -> List[MergeConflict]:
        """Detect conflicts between two sets of changes."""
        conflicts = []

        # Group changes by category
        categories_a = {}
        categories_b = {}

        for change in changes_a:
            if change.category not in categories_a:
                categories_a[change.category] = []
            categories_a[change.category].append(change)

        for change in changes_b:
            if change.category not in categories_b:
                categories_b[change.category] = []
            categories_b[change.category].append(change)

        # Check for conflicts in same category
        for category in set(categories_a.keys()) & set(categories_b.keys()):
            # If both branches modified the same category, it's a potential conflict
            changes_in_category = categories_a[category] + categories_b[category]

            # Check if any are high severity
            high_severity = any(
                c.severity in (ChangeSeverity.HIGH, ChangeSeverity.BREAKING)
                for c in changes_in_category
            )

            if high_severity:
                # Create conflict
                conflict = MergeConflict(
                    category=category,
                    description=f"Both branches modified {category.value}",
                    base_content=base_content,
                    branch_a_content="\n".join(
                        c.new_text or "" for c in categories_a[category]
                    ),
                    branch_b_content="\n".join(
                        c.new_text or "" for c in categories_b[category]
                    ),
                    resolution_hint=f"Review {category.value} changes and manually merge",
                )
                conflicts.append(conflict)

        return conflicts

    def _auto_merge(
        self,
        base: str,
        changes_a: List[SemanticChange],
        changes_b: List[SemanticChange],
    ) -> str:
        """Attempt to auto-merge non-conflicting changes."""
        # Start with base
        merged = base

        # Apply changes from both branches
        # This is a simplified merge - in practice would need more sophisticated logic
        for change in changes_a + changes_b:
            if change.new_text and change.old_text:
                merged = merged.replace(change.old_text, change.new_text)
            elif change.new_text:
                merged += "\n" + change.new_text

        return merged

    def can_auto_merge(
        self,
        changes_a: List[SemanticChange],
        changes_b: List[SemanticChange],
    ) -> bool:
        """Check if changes can be auto-merged."""
        categories_a = {c.category for c in changes_a}
        categories_b = {c.category for c in changes_b}

        # Check for overlapping categories with high severity
        for category in categories_a & categories_b:
            high_sev_a = any(
                c.severity in (ChangeSeverity.HIGH, ChangeSeverity.BREAKING)
                for c in changes_a if c.category == category
            )
            high_sev_b = any(
                c.severity in (ChangeSeverity.HIGH, ChangeSeverity.BREAKING)
                for c in changes_b if c.category == category
            )
            if high_sev_a or high_sev_b:
                return False

        return True


def categorize_semantic_diff(semantic_diff: Dict[str, Any]) -> Dict[ChangeCategory, List[str]]:
    """Convert semantic diff output to categorized changes."""
    categorized = {cat: [] for cat in ChangeCategory}

    # Map semantic diff keys to categories
    category_mapping = {
        "tone_changes": ChangeCategory.TONE,
        "constraint_changes": ChangeCategory.CONSTRAINTS,
        "scope_changes": ChangeCategory.CONTEXT,
        "structure_changes": ChangeCategory.STRUCTURE,
        "intent_changes": ChangeCategory.INTENT,
        "breaking_changes": ChangeCategory.INTENT,
    }

    for key, category in category_mapping.items():
        if key in semantic_diff:
            for change in semantic_diff[key]:
                if isinstance(change, dict):
                    desc = change.get("description", str(change))
                else:
                    desc = str(change)
                categorized[category].append(desc)

    return categorized
