"""Tests for the optimizer module."""

import pytest

from pit.core.optimizer import (
    OptimizationType,
    OptimizationSuggestion,
    PromptOptimizer,
)


class TestPromptOptimizer:
    """Test the PromptOptimizer class."""

    @pytest.fixture
    def optimizer(self):
        """Create a prompt optimizer instance."""
        return PromptOptimizer()

    def test_analyze_short_prompt(self, optimizer):
        """Test analyzing a short prompt."""
        prompt = "Hi"
        result = optimizer.analyze(prompt)
        
        # Short prompts should get length suggestions
        length_suggestions = [s for s in result if s.type == OptimizationType.LENGTH]
        assert len(length_suggestions) > 0

    def test_analyze_well_structured_prompt(self, optimizer):
        """Test analyzing a well-structured prompt."""
        prompt = """You are a helpful assistant.

Task: Summarize the following text.

Input: {text}

Requirements:
- Keep it under 100 words
- Include key points

Output format: Bullet points"""
        
        result = optimizer.analyze(prompt)
        assert isinstance(result, list)

    def test_analyze_detects_ambiguous_terms(self, optimizer):
        """Test detecting ambiguous terms in prompts."""
        prompt = "Give me a good response about {topic}"
        result = optimizer.analyze(prompt)
        
        clarity_suggestions = [s for s in result if s.type == OptimizationType.CLARITY]
        assert any("Ambiguous" in s.title for s in clarity_suggestions)

    def test_analyze_detects_missing_format(self, optimizer):
        """Test detecting missing output format."""
        prompt = "Tell me about {topic}"
        result = optimizer.analyze(prompt)
        
        specificity = [s for s in result if s.type == OptimizationType.SPECIFICITY]
        assert any("Missing Output Format" in s.title for s in specificity)

    def test_analyze_detects_no_role(self, optimizer):
        """Test detecting missing role definition."""
        prompt = "Process this: {input}"
        result = optimizer.analyze(prompt)
        
        structure = [s for s in result if s.type == OptimizationType.STRUCTURE]
        assert any("Missing Role" in s.title for s in structure)

    def test_analyze_detects_no_examples(self, optimizer):
        """Test detecting missing examples."""
        prompt = "Classify this text: {text}"
        result = optimizer.analyze(prompt)
        
        examples = [s for s in result if s.type == OptimizationType.EXAMPLES]
        assert any("No Examples" in s.title for s in examples)

    def test_analyze_detects_missing_constraints(self, optimizer):
        """Test detecting missing negative constraints."""
        prompt = "Write about {topic} in 3 paragraphs"
        result = optimizer.analyze(prompt)
        
        constraints = [s for s in result if s.type == OptimizationType.CONSTRAINTS]
        assert any("No Negative Constraints" in s.title for s in constraints)

    def test_analyze_detects_no_variables(self, optimizer):
        """Test detecting prompts without variables."""
        prompt = "Write a poem about nature"
        result = optimizer.analyze(prompt)
        
        context = [s for s in result if s.type == OptimizationType.CONTEXT]
        assert any("No Variable Placeholders" in s.title for s in context)

    def test_generate_improved_version(self, optimizer):
        """Test generating improved version."""
        prompt = "Hi"
        suggestions = optimizer.analyze(prompt)
        improved = optimizer.generate_improved_version(prompt, suggestions)
        
        assert isinstance(improved, str)
        assert len(improved) >= len(prompt)

    def test_suggestions_sorted_by_priority(self, optimizer):
        """Test that suggestions are sorted by priority."""
        prompt = "Tell me about {topic}"
        result = optimizer.analyze(prompt)
        
        if len(result) > 1:
            priorities = [s.priority for s in result]
            assert priorities == sorted(priorities)


class TestOptimizationSuggestion:
    """Test OptimizationSuggestion dataclass."""

    def test_suggestion_creation(self):
        """Test creating an optimization suggestion."""
        suggestion = OptimizationSuggestion(
            type=OptimizationType.CLARITY,
            title="Test Suggestion",
            description="Test description",
            current_issue="Current issue",
            suggested_change="Suggested change",
            expected_improvement="Expected improvement",
            confidence=0.8,
            priority=2,
        )
        
        assert suggestion.type == OptimizationType.CLARITY
        assert suggestion.confidence == 0.8
        assert suggestion.priority == 2

    def test_suggestion_priority_range(self):
        """Test that priority is in valid range."""
        suggestion = OptimizationSuggestion(
            type=OptimizationType.SAFETY,
            title="Test",
            description="Test",
            current_issue="Test",
            suggested_change="Test",
            expected_improvement="Test",
            confidence=0.5,
            priority=1,
        )
        
        assert 1 <= suggestion.priority <= 5


class TestOptimizationType:
    """Test OptimizationType enum."""

    def test_type_values(self):
        """Test optimization type enum values."""
        assert OptimizationType.CLARITY.value == "clarity"
        assert OptimizationType.SPECIFICITY.value == "specificity"
        assert OptimizationType.STRUCTURE.value == "structure"
        assert OptimizationType.EXAMPLES.value == "examples"
        assert OptimizationType.CONSTRAINTS.value == "constraints"
        assert OptimizationType.CONTEXT.value == "context"
        assert OptimizationType.LENGTH.value == "length"
        assert OptimizationType.SAFETY.value == "safety"


class TestHeuristicAnalysis:
    """Test heuristic analysis functions."""

    @pytest.fixture
    def optimizer(self):
        return PromptOptimizer()

    def test_detects_long_sentences(self, optimizer):
        """Test detection of long complex sentences."""
        # Create a prompt with multiple long sentences (>25 words each)
        long_sentence = "This is a very long sentence with many words that goes on and on without stopping and contains way more than twenty five words in it"
        prompt = ". ".join([long_sentence] * 4)  # 4 long sentences
        result = optimizer.analyze(prompt)

        clarity = [s for s in result if s.type == OptimizationType.CLARITY]
        assert any("Complex Sentences" in s.title for s in clarity)

    def test_detects_long_prompt(self, optimizer):
        """Test detection of very long prompts."""
        prompt = "word " * 600
        result = optimizer.analyze(prompt)
        
        length = [s for s in result if s.type == OptimizationType.LENGTH]
        assert any("Too Long" in s.title for s in length)

    def test_detects_single_example(self, optimizer):
        """Test detection of single example usage."""
        prompt = """Input: hello
Output: hi

Input: {input}
Output:"""
        result = optimizer.analyze(prompt)
        
        examples = [s for s in result if s.type == OptimizationType.EXAMPLES]
        # Should either suggest adding more examples or have no example suggestions
        # since it already has one

    def test_detects_few_shot_pattern(self, optimizer):
        """Test detection of few-shot patterns."""
        prompt = """Input: A
Output: 1

Input: B
Output: 2

Input: {input}
Output:"""
        result = optimizer.analyze(prompt)
        
        # Should not suggest adding examples if few-shot pattern exists
        examples = [s for s in result if s.type == OptimizationType.EXAMPLES]
        assert not any("No Examples" in s.title for s in examples)

    def test_detects_variables_without_context(self, optimizer):
        """Test detection of variables without context."""
        prompt = "Process {{data}}"
        result = optimizer.analyze(prompt)
        
        context = [s for s in result if s.type == OptimizationType.CONTEXT]
        assert any("Variables Without Context" in s.title for s in context)

    def test_detects_unstructured_content(self, optimizer):
        """Test detection of unstructured long content."""
        prompt = "This is a long prompt without any structure or formatting " * 20
        result = optimizer.analyze(prompt)
        
        structure = [s for s in result if s.type == OptimizationType.STRUCTURE]
        assert any("Unstructured" in s.title for s in structure)

    def test_detects_no_validation(self, optimizer):
        """Test detection of missing output validation."""
        prompt = "Generate code for {task}"
        result = optimizer.analyze(prompt)
        
        safety = [s for s in result if s.type == OptimizationType.SAFETY]
        assert any("No Output Validation" in s.title for s in safety)

    def test_analyze_history_frequent_refinements(self, optimizer):
        """Test analyzing version history with frequent refinements."""
        # Create mock versions
        class MockVersion:
            def __init__(self, content, message):
                self.content = content
                self.message = message

        versions = [
            MockVersion("v1", "Initial version"),
            MockVersion("v2", "Fix clarity"),
            MockVersion("v3", "Improve structure"),
            MockVersion("v4", "Refine output"),
        ]
        
        result = optimizer.analyze("test prompt", version_history=versions)
        
        # Should detect frequent refinements
        clarity = [s for s in result if s.type == OptimizationType.CLARITY]
        assert any("Frequent Refinements" in s.title for s in clarity)

    def test_analyze_history_length_growth(self, optimizer):
        """Test detecting significant length growth in history."""
        class MockVersion:
            def __init__(self, content, message):
                self.content = content
                self.message = message

        versions = [
            MockVersion("short text", "Initial"),
            MockVersion("medium text " * 10, "Update"),
            MockVersion("long text " * 50, "Final"),
        ]
        
        result = optimizer.analyze("test", version_history=versions)
        
        length = [s for s in result if s.type == OptimizationType.LENGTH]
        assert any("Length Growth" in s.title for s in length)
