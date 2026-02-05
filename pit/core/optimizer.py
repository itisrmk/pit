"""Auto-optimization engine for prompt improvement suggestions."""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from pit.db.models import Version


class OptimizationType(Enum):
    """Types of optimization suggestions."""
    CLARITY = "clarity"
    SPECIFICITY = "specificity"
    STRUCTURE = "structure"
    EXAMPLES = "examples"
    CONSTRAINTS = "constraints"
    CONTEXT = "context"
    LENGTH = "length"
    SAFETY = "safety"


@dataclass
class OptimizationSuggestion:
    """A suggestion for prompt optimization."""
    type: OptimizationType
    title: str
    description: str
    current_issue: str
    suggested_change: str
    expected_improvement: str
    confidence: float  # 0.0 to 1.0
    priority: int  # 1 (highest) to 5 (lowest)


class PromptOptimizer:
    """Analyzes prompts and suggests improvements."""

    def __init__(self):
        """Initialize the optimizer."""
        self.suggestions: list[OptimizationSuggestion] = []

    def analyze(self, content: str, version_history: Optional[list[Version]] = None) -> list[OptimizationSuggestion]:
        """Analyze a prompt and return optimization suggestions.

        Args:
            content: The prompt content to analyze.
            version_history: Optional list of previous versions for context.

        Returns:
            List of optimization suggestions sorted by priority.
        """
        self.suggestions = []

        # Run all analysis heuristics
        self._analyze_clarity(content)
        self._analyze_specificity(content)
        self._analyze_structure(content)
        self._analyze_examples(content)
        self._analyze_constraints(content)
        self._analyze_context(content)
        self._analyze_length(content)
        self._analyze_safety(content)

        # Add historical insights if version history is provided
        if version_history and len(version_history) > 1:
            self._analyze_history(content, version_history)

        # Sort by priority and confidence
        return sorted(
            self.suggestions,
            key=lambda s: (s.priority, -s.confidence),
        )

    def _analyze_clarity(self, content: str) -> None:
        """Analyze clarity of the prompt."""
        # Check for ambiguous terms
        ambiguous_terms = [
            (r"\bgood\b", "The term 'good' is subjective"),
            (r"\bbad\b", "The term 'bad' is subjective"),
            (r"\bbetter\b", "The term 'better' needs quantification"),
            (r"\bappropriate\b", "The term 'appropriate' is vague"),
            (r"\breasonable\b", "The term 'reasonable' is subjective"),
            (r"\bsome\b", "The term 'some' is imprecise"),
            (r"\bmany\b", "The term 'many' needs quantification"),
            (r"\bseveral\b", "The term 'several' is imprecise"),
        ]

        for pattern, issue in ambiguous_terms:
            if re.search(pattern, content, re.IGNORECASE):
                self.suggestions.append(OptimizationSuggestion(
                    type=OptimizationType.CLARITY,
                    title="Ambiguous Language Detected",
                    description="Replace vague terms with specific, measurable criteria.",
                    current_issue=issue,
                    suggested_change="Use specific metrics or criteria instead of subjective terms.",
                    expected_improvement="More consistent and predictable outputs",
                    confidence=0.8,
                    priority=2,
                ))

        # Check for complex sentences
        sentences = content.split(".")
        long_sentences = [s for s in sentences if len(s.split()) > 25]
        if len(long_sentences) > 2:
            self.suggestions.append(OptimizationSuggestion(
                type=OptimizationType.CLARITY,
                title="Complex Sentences Detected",
                description=f"Found {len(long_sentences)} long sentences that may be hard to follow.",
                current_issue="Sentences are too long and complex",
                suggested_change="Break long sentences into shorter, clearer instructions.",
                expected_improvement="Better comprehension and adherence to instructions",
                confidence=0.7,
                priority=3,
            ))

    def _analyze_specificity(self, content: str) -> None:
        """Analyze specificity of the prompt."""
        # Check for format specification
        format_indicators = [
            "format:", "output:", "return:", "structure:", "json", "markdown", "xml"
        ]
        has_format = any(indicator in content.lower() for indicator in format_indicators)

        if not has_format:
            self.suggestions.append(OptimizationSuggestion(
                type=OptimizationType.SPECIFICITY,
                title="Missing Output Format",
                description="No clear output format is specified.",
                current_issue="The prompt doesn't specify how the output should be structured",
                suggested_change="Add an explicit format specification (e.g., JSON, markdown, bullet points).",
                expected_improvement="More consistent and parseable outputs",
                confidence=0.85,
                priority=1,
            ))

        # Check for length constraints
        length_indicators = [
            r"\d+\s*(?:words?|characters?|sentences?|paragraphs?)",
            r"(?:short|brief|concise|detailed|comprehensive)",
        ]
        has_length = any(re.search(pattern, content, re.IGNORECASE) for pattern in length_indicators)

        if not has_length:
            self.suggestions.append(OptimizationSuggestion(
                type=OptimizationType.SPECIFICITY,
                title="Missing Length Constraints",
                description="No length constraints are specified.",
                current_issue="The prompt doesn't specify expected output length",
                suggested_change="Add explicit length constraints (e.g., 'in 3-5 sentences').",
                expected_improvement="More appropriately sized outputs",
                confidence=0.75,
                priority=3,
            ))

    def _analyze_structure(self, content: str) -> None:
        """Analyze structure of the prompt."""
        # Check for clear sections
        section_indicators = ["##", "**", "1.", "2.", "- ", "* "]
        has_structure = any(indicator in content for indicator in section_indicators)

        if not has_structure and len(content.split()) > 50:
            self.suggestions.append(OptimizationSuggestion(
                type=OptimizationType.STRUCTURE,
                title="Unstructured Content",
                description="Long prompt without clear sections or organization.",
                current_issue="The prompt lacks visual structure",
                suggested_change="Use headings, bullet points, or numbered lists to organize instructions.",
                expected_improvement="Better instruction following and output organization",
                confidence=0.8,
                priority=2,
            ))

        # Check for role definition
        role_patterns = [
            r"you\s+are\s+(?:a|an)\s+",
            r"act\s+as\s+(?:a|an)\s+",
            r"your\s+role\s+is",
        ]
        has_role = any(re.search(pattern, content, re.IGNORECASE) for pattern in role_patterns)

        if not has_role:
            self.suggestions.append(OptimizationSuggestion(
                type=OptimizationType.STRUCTURE,
                title="Missing Role Definition",
                description="No persona or role is assigned to the AI.",
                current_issue="The prompt doesn't establish who the AI should be",
                suggested_change="Add a role definition (e.g., 'You are an expert in...').",
                expected_improvement="More context-appropriate responses",
                confidence=0.7,
                priority=3,
            ))

    def _analyze_examples(self, content: str) -> None:
        """Analyze for presence of examples."""
        # Check for examples
        example_indicators = [
            r"example:",
            r"for\s+example",
            r"e\.g\.,",
            r"such\s+as",
        ]
        has_examples = any(re.search(pattern, content, re.IGNORECASE) for pattern in example_indicators)

        # Check for few-shot pattern (input/output pairs)
        has_few_shot = "input:" in content.lower() and "output:" in content.lower()

        if not has_examples and not has_few_shot:
            self.suggestions.append(OptimizationSuggestion(
                type=OptimizationType.EXAMPLES,
                title="No Examples Provided",
                description="The prompt lacks example inputs and outputs.",
                current_issue="Without examples, the model may interpret instructions differently",
                suggested_change="Add 1-2 examples of expected input/output pairs.",
                expected_improvement="Improved instruction following and output quality",
                confidence=0.75,
                priority=2,
            ))

        # Check for few-shot quantity
        if has_few_shot:
            input_count = len(re.findall(r"input:", content, re.IGNORECASE))
            if input_count == 1:
                self.suggestions.append(OptimizationSuggestion(
                    type=OptimizationType.EXAMPLES,
                    title="Single Example Only",
                    description="Only one example is provided.",
                    current_issue="A single example may not capture the full range of expected behavior",
                    suggested_change="Add more examples (2-5) covering different scenarios.",
                    expected_improvement="More consistent behavior across diverse inputs",
                    confidence=0.7,
                    priority=4,
                ))

    def _analyze_constraints(self, content: str) -> None:
        """Analyze constraints in the prompt."""
        # Check for negative constraints (what NOT to do)
        negative_patterns = [
            r"do\s+not",
            r"don't",
            r"never",
            r"avoid",
            r"without",
        ]
        negative_count = sum(
            len(re.findall(pattern, content, re.IGNORECASE))
            for pattern in negative_patterns
        )

        if negative_count == 0:
            self.suggestions.append(OptimizationSuggestion(
                type=OptimizationType.CONSTRAINTS,
                title="No Negative Constraints",
                description="The prompt only specifies what TO do, not what NOT to do.",
                current_issue="Missing boundary definitions can lead to unwanted outputs",
                suggested_change="Add constraints about what to avoid or exclude.",
                expected_improvement="Reduced unwanted content and edge cases",
                confidence=0.65,
                priority=4,
            ))

        # Check for edge case handling
        edge_patterns = [
            r"if\s+",
            r"when\s+",
            r"unless\s+",
            r"otherwise",
        ]
        has_edge_cases = any(re.search(pattern, content, re.IGNORECASE) for pattern in edge_patterns)

        if not has_edge_cases:
            self.suggestions.append(OptimizationSuggestion(
                type=OptimizationType.CONSTRAINTS,
                title="No Edge Case Handling",
                description="The prompt doesn't specify behavior for special cases.",
                current_issue="Edge cases may produce unexpected results",
                suggested_change="Add conditional instructions for edge cases.",
                expected_improvement="More robust handling of unexpected inputs",
                confidence=0.6,
                priority=5,
            ))

    def _analyze_context(self, content: str) -> None:
        """Analyze context requirements."""
        # Check for context variables
        variable_pattern = r"\{\{\s*(\w+)\s*\}\}"
        variables = re.findall(variable_pattern, content)

        if not variables:
            self.suggestions.append(OptimizationSuggestion(
                type=OptimizationType.CONTEXT,
                title="No Variable Placeholders",
                description="The prompt uses no dynamic variables.",
                current_issue="Static prompts can't adapt to different contexts",
                suggested_change="Add variable placeholders (e.g., {{user_input}}) for dynamic content.",
                expected_improvement="More flexible and reusable prompts",
                confidence=0.5,
                priority=5,
            ))

        # Check for context setting
        context_indicators = [
            r"given\s+",
            r"context:",
            r"background:",
            r"here\s+is",
        ]
        has_context = any(re.search(pattern, content, re.IGNORECASE) for pattern in context_indicators)

        if not has_context and variables:
            self.suggestions.append(OptimizationSuggestion(
                type=OptimizationType.CONTEXT,
                title="Variables Without Context",
                description="Variables are used without explaining their purpose.",
                current_issue="Unclear variable usage can lead to incorrect substitutions",
                suggested_change="Add descriptions for what each variable should contain.",
                expected_improvement="Better understanding and correct usage of variables",
                confidence=0.6,
                priority=3,
            ))

    def _analyze_length(self, content: str) -> None:
        """Analyze prompt length."""
        word_count = len(content.split())

        if word_count < 20:
            self.suggestions.append(OptimizationSuggestion(
                type=OptimizationType.LENGTH,
                title="Prompt Too Short",
                description=f"The prompt is only {word_count} words, which may be insufficient.",
                current_issue="Very short prompts often lack necessary context",
                suggested_change="Add more context, examples, or specific instructions.",
                expected_improvement="More detailed and appropriate outputs",
                confidence=0.7,
                priority=3,
            ))
        elif word_count > 500:
            self.suggestions.append(OptimizationSuggestion(
                type=OptimizationType.LENGTH,
                title="Prompt Too Long",
                description=f"The prompt is {word_count} words, which may be overwhelming.",
                current_issue="Very long prompts can exceed context limits or dilute instructions",
                suggested_change="Consider breaking into smaller prompts or using a template system.",
                expected_improvement="Better performance and clearer instruction following",
                confidence=0.6,
                priority=4,
            ))

    def _analyze_safety(self, content: str) -> None:
        """Analyze safety considerations."""
        # Check for output validation
        validation_patterns = [
            r"validate",
            r"verify",
            r"check",
            r"ensure",
        ]
        has_validation = any(re.search(pattern, content, re.IGNORECASE) for pattern in validation_patterns)

        if not has_validation:
            self.suggestions.append(OptimizationSuggestion(
                type=OptimizationType.SAFETY,
                title="No Output Validation",
                description="The prompt doesn't mention validating outputs.",
                current_issue="LLM outputs should be validated before use",
                suggested_change="Add instructions to validate or sanitize outputs.",
                expected_improvement="Safer integration with downstream systems",
                confidence=0.5,
                priority=4,
            ))

    def _analyze_history(self, content: str, versions: list[Version]) -> None:
        """Analyze version history for patterns."""
        if len(versions) < 2:
            return

        # Check for repeated refinements in similar areas
        messages = [v.message.lower() for v in versions]

        # Look for patterns in commit messages
        refinement_keywords = ["fix", "improve", "clarify", "update", "refine"]
        refinement_count = sum(
            1 for msg in messages
            for kw in refinement_keywords
            if kw in msg
        )

        if refinement_count > len(versions) * 0.5:
            self.suggestions.append(OptimizationSuggestion(
                type=OptimizationType.CLARITY,
                title="Frequent Refinements Detected",
                description=f"{refinement_count} out of {len(versions)} versions were refinements.",
                current_issue="The prompt may be inherently unstable or unclear",
                suggested_change="Consider a more fundamental restructuring with clearer base instructions.",
                expected_improvement="More stable prompt requiring fewer iterations",
                confidence=0.6,
                priority=2,
            ))

        # Check content growth
        lengths = [len(v.content.split()) for v in versions if v.content]
        if len(lengths) >= 2 and lengths[-1] > lengths[0] * 1.5:
            growth_pct = ((lengths[-1] - lengths[0]) / lengths[0]) * 100
            self.suggestions.append(OptimizationSuggestion(
                type=OptimizationType.LENGTH,
                title="Significant Length Growth",
                description=f"Prompt has grown {growth_pct:.0f}% since first version.",
                current_issue="Continuous additions may have created bloat",
                suggested_change="Review and consolidate instructions; remove redundancies.",
                expected_improvement="Cleaner, more focused prompt",
                confidence=0.65,
                priority=3,
            ))

    def generate_improved_version(self, content: str, suggestions: list[OptimizationSuggestion]) -> str:
        """Generate an improved version of the prompt based on suggestions.

        Args:
            content: Original prompt content.
            suggestions: List of optimization suggestions.

        Returns:
            Improved prompt content with comments showing changes.
        """
        improved = content

        # Apply high-confidence, high-priority suggestions
        high_impact = [s for s in suggestions if s.confidence >= 0.7 and s.priority <= 2]

        if high_impact:
            # Add a header comment with suggestions
            header = "# IMPROVED VERSION - Based on optimization analysis\n"
            header += "# Key improvements to consider:\n"
            for s in high_impact[:5]:
                header += f"# - {s.title}: {s.suggested_change}\n"
            header += "\n"
            improved = header + improved

        return improved
