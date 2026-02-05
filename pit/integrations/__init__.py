"""Framework integrations for PIT.

Supports importing and exporting prompts to various frameworks
including LangChain and OpenAI Assistants.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml

from pit.db.models import Prompt, Version


@dataclass
class ExportedPrompt:
    """A standardized prompt export format."""
    name: str
    content: str
    description: Optional[str] = None
    variables: list[str] = None
    metadata: dict = None

    def __post_init__(self):
        if self.variables is None:
            self.variables = []
        if self.metadata is None:
            self.metadata = {}


class FrameworkIntegration(ABC):
    """Base class for framework integrations."""

    @abstractmethod
    def export_prompt(self, prompt: Prompt, version: Optional[Version] = None) -> str:
        """Export a prompt to the framework's format."""
        pass

    @abstractmethod
    def import_prompt(self, data: str, name: Optional[str] = None) -> ExportedPrompt:
        """Import a prompt from the framework's format."""
        pass

    @abstractmethod
    def get_file_extension(self) -> str:
        """Get the file extension for this format."""
        pass


class LangChainIntegration(FrameworkIntegration):
    """Integration with LangChain prompt templates."""

    def export_prompt(self, prompt: Prompt, version: Optional[Version] = None) -> str:
        """Export a prompt as LangChain PromptTemplate JSON."""
        if version is None:
            version = prompt.current_version

        if not version:
            raise ValueError("No version to export")

        # Convert Jinja2 style variables to LangChain format
        template = version.content
        input_variables = version.variables or []

        # Convert {{var}} to {var}
        for var in input_variables:
            template = template.replace(f"{{{{{var}}}}}", f"{{{var}}}")

        data = {
            "input_variables": input_variables,
            "template": template,
            "template_format": "f-string",
            "validate_template": True,
            "_type": "prompt",
        }

        import json
        return json.dumps(data, indent=2)

    def import_prompt(self, data: str, name: Optional[str] = None) -> ExportedPrompt:
        """Import a LangChain prompt template."""
        import json
        import re

        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            # Try YAML
            parsed = yaml.safe_load(data)

        template = parsed.get("template", "")
        input_variables = parsed.get("input_variables", [])

        # Convert {var} back to {{var}} for internal storage
        for var in input_variables:
            template = template.replace(f"{{{var}}}", f"{{{{{var}}}}}")

        return ExportedPrompt(
            name=name or parsed.get("name", "imported"),
            content=template,
            description=parsed.get("description"),
            variables=input_variables,
            metadata={"source": "langchain", "original_type": parsed.get("_type")},
        )

    def get_file_extension(self) -> str:
        return ".json"


class OpenAIAssistantsIntegration(FrameworkIntegration):
    """Integration with OpenAI Assistants API."""

    def export_prompt(self, prompt: Prompt, version: Optional[Version] = None) -> str:
        """Export a prompt for OpenAI Assistants API."""
        if version is None:
            version = prompt.current_version

        if not version:
            raise ValueError("No version to export")

        # OpenAI Assistants use a simple instructions format
        # We add metadata as comments at the top
        lines = [
            "# OpenAI Assistant Instructions",
            f"# Prompt: {prompt.name}",
            f"# Description: {prompt.description or 'No description'}",
            "#",
        ]

        if version.variables:
            lines.append("# Variables:")
            for var in version.variables:
                lines.append(f"#   - {var}")
            lines.append("#")

        lines.append("")
        lines.append(version.content)

        return "\n".join(lines)

    def import_prompt(self, data: str, name: Optional[str] = None) -> ExportedPrompt:
        """Import OpenAI Assistant instructions."""
        lines = data.split("\n")

        # Extract metadata from comments
        description = None
        content_lines = []
        in_metadata = True

        for line in lines:
            stripped = line.strip()
            if in_metadata:
                if stripped.startswith("#"):
                    if "Description:" in stripped:
                        description = stripped.split("Description:", 1)[1].strip()
                    continue
                elif stripped == "":
                    continue
                else:
                    in_metadata = False

            content_lines.append(line)

        content = "\n".join(content_lines).strip()

        # Extract variables from content
        import re
        variables = list(dict.fromkeys(re.findall(r"\{\{(\w+)\}\}", content)))

        return ExportedPrompt(
            name=name or "imported_assistant",
            content=content,
            description=description,
            variables=variables,
            metadata={"source": "openai_assistants"},
        )

    def get_file_extension(self) -> str:
        return ".md"


class GenericJSONIntegration(FrameworkIntegration):
    """Generic JSON format integration."""

    def export_prompt(self, prompt: Prompt, version: Optional[Version] = None) -> str:
        """Export a prompt as generic JSON."""
        if version is None:
            version = prompt.current_version

        if not version:
            raise ValueError("No version to export")

        data = {
            "name": prompt.name,
            "description": prompt.description,
            "version": version.version_number,
            "content": version.content,
            "variables": version.variables or [],
            "tags": version.tags,
            "author": version.author,
            "created_at": version.created_at.isoformat() if version.created_at else None,
        }

        import json
        return json.dumps(data, indent=2)

    def import_prompt(self, data: str, name: Optional[str] = None) -> ExportedPrompt:
        """Import a generic JSON prompt."""
        import json

        parsed = json.loads(data)

        return ExportedPrompt(
            name=name or parsed.get("name", "imported"),
            content=parsed.get("content", ""),
            description=parsed.get("description"),
            variables=parsed.get("variables", []),
            metadata={"source": "json", "version": parsed.get("version")},
        )

    def get_file_extension(self) -> str:
        return ".json"


class YAMLIntegration(FrameworkIntegration):
    """YAML format integration."""

    def export_prompt(self, prompt: Prompt, version: Optional[Version] = None) -> str:
        """Export a prompt as YAML."""
        if version is None:
            version = prompt.current_version

        if not version:
            raise ValueError("No version to export")

        data = {
            "name": prompt.name,
            "description": prompt.description,
            "version": version.version_number,
            "content": version.content,
            "variables": version.variables or [],
            "tags": version.tags,
            "author": version.author,
        }

        return yaml.dump(data, default_flow_style=False, sort_keys=False)

    def import_prompt(self, data: str, name: Optional[str] = None) -> ExportedPrompt:
        """Import a YAML prompt."""
        parsed = yaml.safe_load(data)

        return ExportedPrompt(
            name=name or parsed.get("name", "imported"),
            content=parsed.get("content", ""),
            description=parsed.get("description"),
            variables=parsed.get("variables", []),
            metadata={"source": "yaml", "version": parsed.get("version")},
        )

    def get_file_extension(self) -> str:
        return ".yaml"


# Registry of integrations
INTEGRATIONS = {
    "langchain": LangChainIntegration,
    "openai": OpenAIAssistantsIntegration,
    "json": GenericJSONIntegration,
    "yaml": YAMLIntegration,
}


def get_integration(name: str) -> FrameworkIntegration:
    """Get an integration by name."""
    if name not in INTEGRATIONS:
        raise ValueError(f"Unknown integration: {name}. Available: {list(INTEGRATIONS.keys())}")
    return INTEGRATIONS[name]()


def export_prompt(
    prompt: Prompt,
    format: str,
    version: Optional[Version] = None,
) -> str:
    """Export a prompt to the specified format."""
    integration = get_integration(format)
    return integration.export_prompt(prompt, version)


def import_prompt(
    data: str,
    format: str,
    name: Optional[str] = None,
) -> ExportedPrompt:
    """Import a prompt from the specified format."""
    integration = get_integration(format)
    return integration.import_prompt(data, name)
