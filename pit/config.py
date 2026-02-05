"""Configuration management for pit."""

import os
from pathlib import Path
from typing import Optional, Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

# Config file name
CONFIG_FILE = ".pit.yaml"
DEFAULT_DIR = ".pit"


class LLMConfig(BaseModel):
    """LLM provider configuration."""

    provider: Literal["anthropic", "openai", "ollama"] = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    api_key_env: str = "ANTHROPIC_API_KEY"
    base_url: Optional[str] = None  # For Ollama or custom endpoints

    def get_api_key(self) -> Optional[str]:
        """Get the API key from environment."""
        return os.environ.get(self.api_key_env)


class ProjectConfig(BaseModel):
    """Project-level configuration."""

    name: str = "pit-project"
    default_author: Optional[str] = None


class Config(BaseSettings):
    """Main configuration for pit."""

    project: ProjectConfig = Field(default_factory=ProjectConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)

    @classmethod
    def load(cls, project_path: Path | None = None) -> "Config":
        """Load configuration from .pit.yaml file.

        Args:
            project_path: Project root directory. If None, uses cwd.

        Returns:
            Config instance with loaded or default values.
        """
        if project_path is None:
            project_path = Path.cwd()

        config_file = project_path / CONFIG_FILE
        if config_file.exists():
            with open(config_file) as f:
                data = yaml.safe_load(f) or {}
            return cls(**data)
        return cls()

    def save(self, project_path: Path | None = None) -> None:
        """Save configuration to .pit.yaml file.

        Args:
            project_path: Project root directory. If None, uses cwd.
        """
        if project_path is None:
            project_path = Path.cwd()

        config_file = project_path / CONFIG_FILE
        with open(config_file, "w") as f:
            yaml.dump(self.model_dump(), f, default_flow_style=False, sort_keys=False)


def is_initialized(project_path: Path | None = None) -> bool:
    """Check if pit is initialized in the given directory.

    Args:
        project_path: Project root directory. If None, uses cwd.

    Returns:
        True if .pit directory exists.
    """
    if project_path is None:
        project_path = Path.cwd()

    pit_dir = project_path / DEFAULT_DIR
    return pit_dir.exists() and pit_dir.is_dir()


def find_project_root(start_path: Path | None = None) -> Optional[Path]:
    """Find the project root by looking for .pit directory.

    Walks up the directory tree from start_path until it finds
    a .pit directory or reaches the filesystem root.

    Args:
        start_path: Starting directory. If None, uses cwd.

    Returns:
        Path to project root, or None if not found.
    """
    if start_path is None:
        start_path = Path.cwd()

    current = start_path.resolve()
    while current != current.parent:
        if (current / DEFAULT_DIR).exists():
            return current
        current = current.parent

    # Check root directory
    if (current / DEFAULT_DIR).exists():
        return current

    return None


def get_default_config_template() -> str:
    """Get the default configuration file template."""
    return """# PIT Configuration
# See documentation for all available options

project:
  name: my-prompts
  default_author: null

llm:
  # Provider: anthropic, openai, or ollama
  provider: anthropic
  model: claude-sonnet-4-20250514
  api_key_env: ANTHROPIC_API_KEY
  # base_url: http://localhost:11434  # Uncomment for Ollama
"""
