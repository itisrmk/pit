"""Tests for semantic diff functionality."""

from unittest.mock import Mock, patch

import pytest

from pit.config import LLMConfig
from pit.core.semantic_diff import (
    SemanticDiffAnalyzer,
    format_semantic_diff,
    has_significant_changes,
)
from pit.core.llm.provider import (
    AnthropicProvider,
    OpenAIProvider,
    OllamaProvider,
    get_provider,
)


class TestSemanticDiffAnalyzer:
    """Tests for SemanticDiffAnalyzer."""

    def test_analyze_diff_with_provider(self) -> None:
        """Test analyzing diff with a configured provider."""
        config = LLMConfig(provider="anthropic", model="claude-3")
        
        mock_provider = Mock()
        mock_provider.analyze_diff.return_value = {
            "intent_changes": [{"description": "Changed intent", "severity": "medium"}],
            "scope_changes": [],
            "constraint_changes": [],
            "tone_changes": [],
            "structure_changes": [],
            "breaking_changes": [],
            "summary": "Summary of changes",
        }
        
        with patch("pit.core.semantic_diff.get_provider", return_value=mock_provider):
            analyzer = SemanticDiffAnalyzer(config)
            result = analyzer.analyze_diff("Old prompt", "New prompt")
        
        assert result["summary"] == "Summary of changes"
        assert len(result["intent_changes"]) == 1
        mock_provider.analyze_diff.assert_called_once_with("Old prompt", "New prompt")

    def test_analyze_diff_no_provider(self) -> None:
        """Test that analyzer raises error when no provider configured."""
        config = LLMConfig(provider="anthropic", model="claude-3")
        
        with patch("pit.core.semantic_diff.get_provider", return_value=None):
            analyzer = SemanticDiffAnalyzer(config)
            with pytest.raises(ValueError, match="No LLM provider available"):
                analyzer.analyze_diff("Old", "New")

    def test_analyze_diff_empty_prompts(self) -> None:
        """Test analyzing diff with empty prompts."""
        config = LLMConfig(provider="anthropic")
        
        with patch("pit.core.semantic_diff.get_provider", return_value=Mock()):
            analyzer = SemanticDiffAnalyzer(config)
            result = analyzer.analyze_diff("", "")
        
        assert result["summary"] == "Both prompts are empty."

    def test_analyze_diff_initial_version(self) -> None:
        """Test analyzing diff when old prompt is empty (initial version)."""
        config = LLMConfig(provider="anthropic")
        analyzer = SemanticDiffAnalyzer(config)
        
        result = analyzer.analyze_diff("", "New content")
        
        assert "initial version" in result["summary"].lower()
        assert len(result["intent_changes"]) == 1

    def test_analyze_diff_identical_prompts(self) -> None:
        """Test analyzing diff with identical prompts."""
        config = LLMConfig(provider="anthropic")
        
        with patch("pit.core.semantic_diff.get_provider", return_value=Mock()):
            analyzer = SemanticDiffAnalyzer(config)
            result = analyzer.analyze_diff("Same content", "Same content")
        
        assert "No changes detected" in result["summary"]

    def test_is_configured(self) -> None:
        """Test is_configured method."""
        config = LLMConfig(provider="anthropic")
        
        with patch("pit.core.semantic_diff.get_provider", return_value=Mock()):
            analyzer = SemanticDiffAnalyzer(config)
            assert analyzer.is_configured() is True
        
        with patch("pit.core.semantic_diff.get_provider", return_value=None):
            analyzer = SemanticDiffAnalyzer(config)
            assert analyzer.is_configured() is False

    def test_normalize_result(self) -> None:
        """Test result normalization handles various key formats."""
        config = LLMConfig(provider="anthropic")
        
        with patch("pit.core.semantic_diff.get_provider", return_value=Mock()):
            analyzer = SemanticDiffAnalyzer(config)
            
            # Test with alternative key names
            result = analyzer._normalize_result({
                "intent": [{"description": "test"}],
                "scope": [],
                "constraints": [],
                "tone": [],
                "structure": [],
                "breaking": [],
                "overview": "Test",
            })
            
            assert "intent_changes" in result
            assert "scope_changes" in result
            assert "summary" in result
            assert result["intent_changes"] == [{"description": "test"}]


class TestLLMProviders:
    """Tests for LLM providers."""

    def test_get_provider_anthropic(self) -> None:
        """Test getting Anthropic provider."""
        config = LLMConfig(provider="anthropic", model="claude-3")
        provider = get_provider(config)
        
        assert isinstance(provider, AnthropicProvider)
        assert provider.config == config

    def test_get_provider_openai(self) -> None:
        """Test getting OpenAI provider."""
        config = LLMConfig(provider="openai", model="gpt-4")
        provider = get_provider(config)
        
        assert isinstance(provider, OpenAIProvider)
        assert provider.config == config

    def test_get_provider_ollama(self) -> None:
        """Test getting Ollama provider."""
        config = LLMConfig(provider="ollama", model="llama3.2")
        provider = get_provider(config)
        
        assert isinstance(provider, OllamaProvider)
        assert provider.config == config

    def test_get_provider_unknown(self) -> None:
        """Test getting unknown provider returns None."""
        # Patch PROVIDER_MAP to be empty to simulate unknown provider
        with patch("pit.core.llm.provider.PROVIDER_MAP", {}):
            config = LLMConfig(provider="anthropic")
            provider = get_provider(config)
            assert provider is None

    def test_anthropic_provider_build_prompt(self) -> None:
        """Test Anthropic provider builds correct prompt."""
        config = LLMConfig(provider="anthropic")
        provider = AnthropicProvider(config)
        
        prompt = provider._build_analysis_prompt("Old", "New")
        
        assert "OLD PROMPT" in prompt
        assert "NEW PROMPT" in prompt
        assert "Old" in prompt
        assert "New" in prompt
        assert "JSON" in prompt

    def test_parse_response_with_json_block(self) -> None:
        """Test parsing response with JSON code block."""
        config = LLMConfig(provider="anthropic")
        provider = AnthropicProvider(config)
        
        response = '''```json
{"intent_changes": [{"description": "test"}], "summary": "Test"}
```'''
        
        result = provider._parse_response(response)
        
        assert result["intent_changes"] == [{"description": "test"}]
        assert result["summary"] == "Test"

    def test_parse_response_without_code_block(self) -> None:
        """Test parsing response without code block."""
        config = LLMConfig(provider="anthropic")
        provider = AnthropicProvider(config)
        
        response = '{"intent_changes": [], "summary": "Test"}'
        
        result = provider._parse_response(response)
        
        assert result["summary"] == "Test"

    def test_parse_response_invalid_json(self) -> None:
        """Test parsing invalid JSON response."""
        config = LLMConfig(provider="anthropic")
        provider = AnthropicProvider(config)
        
        response = "Not valid JSON"
        
        result = provider._parse_response(response)
        
        assert "raw_response" in result
        assert "summary" in result


class TestFormatSemanticDiff:
    """Tests for format_semantic_diff function."""

    def test_format_with_summary(self) -> None:
        """Test formatting with summary."""
        semantic_diff = {
            "summary": "This is a summary",
            "intent_changes": [],
        }
        
        result = format_semantic_diff(semantic_diff)
        
        assert "Summary: This is a summary" in result

    def test_format_with_changes(self) -> None:
        """Test formatting with changes."""
        semantic_diff = {
            "summary": "",
            "intent_changes": [
                {"description": "Intent 1", "severity": "high"},
                {"description": "Intent 2", "severity": "low"},
            ],
            "scope_changes": ["Scope change"],
        }
        
        result = format_semantic_diff(semantic_diff)
        
        assert "Intent Changes:" in result
        assert "Intent 1 (high)" in result
        assert "Scope Changes:" in result
        assert "Scope change" in result

    def test_format_with_breaking_changes(self) -> None:
        """Test formatting with breaking changes."""
        semantic_diff = {
            "summary": "",
            "breaking_changes": ["Breaking 1", "Breaking 2"],
        }
        
        result = format_semantic_diff(semantic_diff)
        
        assert "Breaking Changes:" in result
        assert "Breaking 1" in result
        assert "Breaking 2" in result

    def test_format_empty(self) -> None:
        """Test formatting empty diff."""
        semantic_diff = {}
        
        result = format_semantic_diff(semantic_diff)
        
        # Should not crash
        assert isinstance(result, str)


class TestHasSignificantChanges:
    """Tests for has_significant_changes function."""

    def test_has_high_severity_change(self) -> None:
        """Test detecting high severity changes."""
        semantic_diff = {
            "intent_changes": [{"description": "Important", "severity": "high"}],
        }
        
        assert has_significant_changes(semantic_diff, "medium") is True
        assert has_significant_changes(semantic_diff, "high") is True
        assert has_significant_changes(semantic_diff, "low") is True

    def test_has_medium_severity_change(self) -> None:
        """Test detecting medium severity changes."""
        semantic_diff = {
            "intent_changes": [{"description": "Medium", "severity": "medium"}],
        }
        
        assert has_significant_changes(semantic_diff, "low") is True
        assert has_significant_changes(semantic_diff, "medium") is True
        assert has_significant_changes(semantic_diff, "high") is False

    def test_has_only_low_severity(self) -> None:
        """Test with only low severity changes."""
        semantic_diff = {
            "intent_changes": [{"description": "Minor", "severity": "low"}],
        }
        
        assert has_significant_changes(semantic_diff, "low") is True
        assert has_significant_changes(semantic_diff, "medium") is False

    def test_has_breaking_changes(self) -> None:
        """Test that breaking changes are always significant."""
        semantic_diff = {
            "intent_changes": [],
            "breaking_changes": ["API changed"],
        }
        
        # Breaking changes are always significant regardless of min_severity
        assert has_significant_changes(semantic_diff, "high") is True

    def test_no_significant_changes(self) -> None:
        """Test with no significant changes."""
        semantic_diff = {
            "intent_changes": [],
            "scope_changes": [],
        }
        
        assert has_significant_changes(semantic_diff) is False
