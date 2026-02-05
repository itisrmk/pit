"""LLM Provider abstraction for semantic diffing."""

from abc import ABC, abstractmethod
from typing import Optional

from pit.config import LLMConfig


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(self, config: LLMConfig):
        self.config = config

    @abstractmethod
    def analyze_diff(self, old_prompt: str, new_prompt: str) -> dict:
        """Analyze the difference between two prompt versions.

        Args:
            old_prompt: The previous version of the prompt.
            new_prompt: The new version of the prompt.

        Returns:
            A dictionary containing semantic analysis with keys like:
            - intent_changes: List of changes to the prompt's intent/purpose
            - scope_changes: List of changes to the scope/coverage
            - constraint_changes: List of changes to constraints/requirements
            - tone_changes: List of changes to tone/style
            - structure_changes: List of changes to structure/format
            - breaking_changes: List of breaking changes
            - summary: Human-readable summary of changes
        """
        pass

    @abstractmethod
    def _call_llm(self, prompt: str) -> str:
        """Make the actual LLM call.

        Args:
            prompt: The formatted prompt to send to the LLM.

        Returns:
            The LLM response text.
        """
        pass

    def _build_analysis_prompt(self, old_prompt: str, new_prompt: str) -> str:
        """Build the analysis prompt for the LLM.

        Args:
            old_prompt: The previous version of the prompt.
            new_prompt: The new version of the prompt.

        Returns:
            A formatted prompt string for the LLM.
        """
        return f"""You are an expert at analyzing changes to LLM prompts. Your task is to analyze the semantic differences between two versions of a prompt and provide a structured analysis.

## OLD PROMPT:
```
{old_prompt}
```

## NEW PROMPT:
```
{new_prompt}
```

## INSTRUCTIONS:
Analyze the changes between these two prompts. Focus on:
1. **Intent Changes**: Has the purpose or goal of the prompt changed?
2. **Scope Changes**: Has the coverage or range of tasks changed?
3. **Constraint Changes**: Have any requirements, limitations, or rules changed?
4. **Tone Changes**: Has the style, voice, or manner changed?
5. **Structure Changes**: Has the format, organization, or layout changed?
6. **Breaking Changes**: Are there changes that would break existing usage?

## OUTPUT FORMAT:
Return your analysis as a JSON object with the following structure:
{{
    "intent_changes": [
        {{"description": "string", "severity": "low|medium|high"}}
    ],
    "scope_changes": [
        {{"description": "string", "severity": "low|medium|high"}}
    ],
    "constraint_changes": [
        {{"description": "string", "severity": "low|medium|high"}}
    ],
    "tone_changes": [
        {{"description": "string", "severity": "low|medium|high"}}
    ],
    "structure_changes": [
        {{"description": "string", "severity": "low|medium|high"}}
    ],
    "breaking_changes": ["string describing each breaking change"],
    "summary": "A concise paragraph summarizing the overall changes"
}}

If a category has no changes, return an empty array for that category. Be specific and descriptive in your analysis."""

    def _parse_response(self, response: str) -> dict:
        """Parse the LLM response into a structured dictionary.

        Args:
            response: The raw LLM response text.

        Returns:
            A dictionary containing the parsed analysis.
        """
        import json
        import re

        # Try to extract JSON from the response
        # The LLM might wrap JSON in markdown code blocks
        # Match content between ```json ... ``` or ``` ... ```
        json_match = re.search(r'```(?:json)?\s*\n?(\{[\s\S]*?\})\s*```', response)
        if json_match:
            response = json_match.group(1).strip()

        # Try to find JSON directly if not in code block
        elif not response.strip().startswith('{'):
            json_match = re.search(r'(\{[\s\S]*\})', response)
            if json_match:
                response = json_match.group(1).strip()

        try:
            return json.loads(response)
        except json.JSONDecodeError as e:
            # Return a fallback structure if parsing fails
            return {
                "intent_changes": [],
                "scope_changes": [],
                "constraint_changes": [],
                "tone_changes": [],
                "structure_changes": [],
                "breaking_changes": [],
                "summary": f"Could not parse LLM response: {e}",
                "raw_response": response,
            }


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider for semantic diff analysis."""

    def analyze_diff(self, old_prompt: str, new_prompt: str) -> dict:
        """Analyze diff using Anthropic Claude."""
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "anthropic package is required. Install with: pip install anthropic"
            )

        api_key = self.config.get_api_key()
        if not api_key:
            raise ValueError(
                f"Anthropic API key not found in environment variable {self.config.api_key_env}"
            )

        prompt = self._build_analysis_prompt(old_prompt, new_prompt)
        response_text = self._call_llm(prompt)
        return self._parse_response(response_text)

    def _call_llm(self, prompt: str) -> str:
        """Call Anthropic Claude API."""
        import anthropic

        client = anthropic.Anthropic(api_key=self.config.get_api_key())

        response = client.messages.create(
            model=self.config.model or "claude-sonnet-4-20250514",
            max_tokens=2000,
            temperature=0.1,  # Low temperature for consistent analysis
            messages=[
                {"role": "user", "content": prompt}
            ],
        )

        # Extract text from response
        content_blocks = response.content
        if content_blocks and len(content_blocks) > 0:
            return content_blocks[0].text
        return ""


class OpenAIProvider(LLMProvider):
    """OpenAI GPT provider for semantic diff analysis."""

    def analyze_diff(self, old_prompt: str, new_prompt: str) -> dict:
        """Analyze diff using OpenAI GPT."""
        try:
            import openai
        except ImportError:
            raise ImportError(
                "openai package is required. Install with: pip install openai"
            )

        api_key = self.config.get_api_key()
        if not api_key:
            raise ValueError(
                f"OpenAI API key not found in environment variable {self.config.api_key_env}"
            )

        prompt = self._build_analysis_prompt(old_prompt, new_prompt)
        response_text = self._call_llm(prompt)
        return self._parse_response(response_text)

    def _call_llm(self, prompt: str) -> str:
        """Call OpenAI API."""
        from openai import OpenAI

        client = OpenAI(
            api_key=self.config.get_api_key(),
            base_url=self.config.base_url,  # Allows for custom endpoints
        )

        response = client.chat.completions.create(
            model=self.config.model or "gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert at analyzing LLM prompt changes."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=2000,
            temperature=0.1,
        )

        return response.choices[0].message.content or ""


class OllamaProvider(LLMProvider):
    """Ollama provider for local LLM semantic diff analysis."""

    def analyze_diff(self, old_prompt: str, new_prompt: str) -> dict:
        """Analyze diff using Ollama local models."""
        try:
            import requests
        except ImportError:
            raise ImportError(
                "requests package is required. Install with: pip install requests"
            )

        prompt = self._build_analysis_prompt(old_prompt, new_prompt)
        response_text = self._call_llm(prompt)
        return self._parse_response(response_text)

    def _call_llm(self, prompt: str) -> str:
        """Call Ollama API."""
        import requests

        base_url = self.config.base_url or "http://localhost:11434"
        model = self.config.model or "llama3.2"

        response = requests.post(
            f"{base_url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 2000,
                }
            },
            timeout=120,
        )
        response.raise_for_status()

        return response.json().get("response", "")


# Provider mapping for factory function
PROVIDER_MAP = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "ollama": OllamaProvider,
}


def get_provider(config: LLMConfig) -> Optional[LLMProvider]:
    """Factory function to get the appropriate LLM provider.

    Args:
        config: The LLM configuration.

    Returns:
        An instance of the appropriate LLM provider, or None if no provider is configured.
    """
    provider_class = PROVIDER_MAP.get(config.provider)
    if provider_class is None:
        return None

    return provider_class(config)
