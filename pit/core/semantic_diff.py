"""Semantic diff analysis for prompt versions."""

from typing import Optional

from pit.config import LLMConfig
from pit.core.llm.provider import get_provider


class SemanticDiffAnalyzer:
    """Analyzes semantic differences between prompt versions.
    
    This class uses LLM providers to detect and categorize changes
    between two versions of a prompt, identifying:
    - Intent changes: Changes to the purpose or goal
    - Scope changes: Changes to coverage or range
    - Constraint changes: Changes to requirements or limitations
    - Tone changes: Changes to style or voice
    - Structure changes: Changes to format or organization
    - Breaking changes: Changes that break existing usage
    """

    def __init__(self, config: LLMConfig):
        """Initialize the analyzer with LLM configuration.

        Args:
            config: The LLM configuration specifying provider, model, etc.
        """
        self.config = config
        self._provider = get_provider(config)

    def analyze_diff(self, old_prompt: str, new_prompt: str) -> dict:
        """Analyze the semantic difference between two prompts.

        Args:
            old_prompt: The previous version of the prompt.
            new_prompt: The new version of the prompt.

        Returns:
            A dictionary containing the semantic analysis with categories:
            - intent_changes: List of changes to intent/purpose
            - scope_changes: List of changes to scope/coverage
            - constraint_changes: List of changes to constraints
            - tone_changes: List of changes to tone/style
            - structure_changes: List of changes to structure
            - breaking_changes: List of breaking changes
            - summary: Human-readable summary

        Raises:
            ValueError: If no LLM provider is configured or available.
            RuntimeError: If the LLM call fails.
        """
        if self._provider is None:
            raise ValueError(
                f"No LLM provider available for '{self.config.provider}'. "
                "Please configure a valid provider in .pit.yaml"
            )

        # Handle edge cases
        if not old_prompt and not new_prompt:
            return {
                "intent_changes": [],
                "scope_changes": [],
                "constraint_changes": [],
                "tone_changes": [],
                "structure_changes": [],
                "breaking_changes": [],
                "summary": "Both prompts are empty.",
            }

        if not old_prompt:
            return {
                "intent_changes": [{"description": "Initial version - new prompt created", "severity": "high"}],
                "scope_changes": [],
                "constraint_changes": [],
                "tone_changes": [],
                "structure_changes": [],
                "breaking_changes": [],
                "summary": "This is the initial version of the prompt.",
            }

        if old_prompt == new_prompt:
            return {
                "intent_changes": [],
                "scope_changes": [],
                "constraint_changes": [],
                "tone_changes": [],
                "structure_changes": [],
                "breaking_changes": [],
                "summary": "No changes detected between versions.",
            }

        try:
            result = self._provider.analyze_diff(old_prompt, new_prompt)
            # Ensure all expected keys are present
            return self._normalize_result(result)
        except Exception as e:
            raise RuntimeError(f"Failed to analyze semantic diff: {e}") from e

    def _normalize_result(self, result: dict) -> dict:
        """Normalize the analysis result to ensure all expected keys.

        Args:
            result: The raw result from the LLM provider.

        Returns:
            A normalized dictionary with all expected keys.
        """
        normalized = {
            "intent_changes": [],
            "scope_changes": [],
            "constraint_changes": [],
            "tone_changes": [],
            "structure_changes": [],
            "breaking_changes": [],
            "summary": "",
        }

        # Map possible key variations
        key_mappings = {
            "intent_changes": ["intent_changes", "intent", "intents"],
            "scope_changes": ["scope_changes", "scope", "scopes"],
            "constraint_changes": ["constraint_changes", "constraints", "constraint"],
            "tone_changes": ["tone_changes", "tone", "tones"],
            "structure_changes": ["structure_changes", "structure", "structural_changes"],
            "breaking_changes": ["breaking_changes", "breaking", "breaks"],
            "summary": ["summary", "overview", "description"],
        }

        for normalized_key, possible_keys in key_mappings.items():
            for key in possible_keys:
                if key in result and result[key]:
                    normalized[normalized_key] = result[key]
                    break

        return normalized

    def is_configured(self) -> bool:
        """Check if the analyzer is properly configured.

        Returns:
            True if a valid LLM provider is configured, False otherwise.
        """
        return self._provider is not None


def format_semantic_diff(semantic_diff: dict) -> str:
    """Format a semantic diff for display.

    Args:
        semantic_diff: The semantic diff dictionary.

    Returns:
        A formatted string representation.
    """
    lines = []

    if summary := semantic_diff.get("summary"):
        lines.append(f"Summary: {summary}")
        lines.append("")

    categories = [
        ("Intent Changes", "intent_changes"),
        ("Scope Changes", "scope_changes"),
        ("Constraint Changes", "constraint_changes"),
        ("Tone Changes", "tone_changes"),
        ("Structure Changes", "structure_changes"),
    ]

    for label, key in categories:
        changes = semantic_diff.get(key, [])
        if changes:
            lines.append(f"{label}:")
            for change in changes:
                if isinstance(change, dict):
                    desc = change.get("description", str(change))
                    severity = change.get("severity", "medium")
                    lines.append(f"  - {desc} ({severity})")
                else:
                    lines.append(f"  - {change}")
            lines.append("")

    if breaking := semantic_diff.get("breaking_changes", []):
        lines.append("Breaking Changes:")
        for change in breaking:
            lines.append(f"  - {change}")
        lines.append("")

    return "\n".join(lines)


def has_significant_changes(semantic_diff: dict, min_severity: str = "medium") -> bool:
    """Check if the semantic diff contains significant changes.

    Args:
        semantic_diff: The semantic diff dictionary.
        min_severity: Minimum severity to consider ("low", "medium", "high").

    Returns:
        True if there are significant changes, False otherwise.
    """
    severity_levels = {"low": 1, "medium": 2, "high": 3}
    min_level = severity_levels.get(min_severity, 2)

    categories = [
        "intent_changes",
        "scope_changes",
        "constraint_changes",
        "tone_changes",
        "structure_changes",
    ]

    for category in categories:
        for change in semantic_diff.get(category, []):
            if isinstance(change, dict):
                severity = change.get("severity", "medium")
                if severity_levels.get(severity, 2) >= min_level:
                    return True

    # Breaking changes are always significant
    if semantic_diff.get("breaking_changes"):
        return True

    return False
