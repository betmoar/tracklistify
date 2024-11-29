"""
Configuration management for development tools.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional

from .exceptions import ConfigurationError
from .logging import DevCliLogger


@dataclass
class Tool:
    """Configuration for a development tool.

    Attributes:
        command: The command to execute
        description: Description of what the tool does
        args: Optional default arguments for the tool
    """

    command: str
    description: str
    args: Optional[str] = None


class ToolsConfiguration:
    """Manages configuration for development tools."""

    DEFAULT_CONFIG_PATH = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "tools.json"
    )

    def __init__(self, config_path: Optional[str] = None):
        """Initialize configuration.

        Args:
            config_path: Optional path to configuration file
        """
        self.logger = DevCliLogger().get_context_logger(
            config_class=self.__class__.__name__
        )
        self.config_path = config_path or self.DEFAULT_CONFIG_PATH
        self._config: Dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from file.

        Raises:
            ConfigurationError: If configuration file cannot be loaded
        """
        try:
            config_path = Path(self.config_path)
            if not config_path.exists():
                raise ConfigurationError(
                    f"Configuration file not found: {self.config_path}"
                )

            with open(config_path, "r", encoding="utf-8") as f:
                self._config = json.load(f)

            self.logger.debug(
                "Loaded configuration from %s",
                self.config_path,
                extra={"config": self._config},
            )

        except FileNotFoundError:
            self.load_default_config()
        except json.JSONDecodeError as e:
            raise ConfigurationError(
                f"Invalid JSON in configuration file: {str(e)}"
            ) from e
        except Exception as e:
            raise ConfigurationError(f"Failed to load configuration: {str(e)}") from e

    def load_default_config(self):
        """Load the default tool configuration."""
        default_config = {
            "pylint": {
                "command": "pylint",
                "description": "Python code linter",
                "args": "--rcfile=.pylintrc",
            },
            "black": {
                "command": "black",
                "description": "Python code formatter",
                "args": "--line-length=88",
            },
            "mypy": {
                "command": "mypy",
                "description": "Static type checker",
                "args": "--strict",
            },
            "pytest": {
                "command": "pytest",
                "description": "Python test runner",
                "args": "-v",
            },
        }
        self._config.update(default_config)

    def list_tools(self) -> Dict[str, Any]:
        """List all available tools.

        Returns:
            Dict of tool configurations
        """
        return self._config.copy()

    def get_tool(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific tool.

        Args:
            tool_name: Name of the tool

        Returns:
            Tool configuration if found, None otherwise
        """
        tool_config = self._config.get(tool_name)
        if tool_config:
            self.logger.debug(
                "Found configuration for tool: %s",
                tool_name,
                extra={"tool_config": tool_config},
            )
        else:
            self.logger.debug("No configuration found for tool: %s", tool_name)
        return tool_config

    def validate_tool_config(self, tool_config: Dict[str, Any]) -> bool:
        """Validate tool configuration.

        Args:
            tool_config: Tool configuration to validate

        Returns:
            True if configuration is valid

        Raises:
            ConfigurationError: If configuration is invalid
        """
        required_fields = ["command", "description"]
        missing_fields = [
            field for field in required_fields if field not in tool_config
        ]

        if missing_fields:
            raise ConfigurationError(
                f"Missing required fields in tool configuration: {missing_fields}"
            )

        if not isinstance(tool_config["command"], str):
            raise ConfigurationError("Tool command must be a string")

        if not isinstance(tool_config["description"], str):
            raise ConfigurationError("Tool description must be a string")

        # Optional fields validation
        if "args" in tool_config and not isinstance(tool_config["args"], str):
            raise ConfigurationError("Tool args must be a string")

        if "env" in tool_config and not isinstance(tool_config["env"], dict):
            raise ConfigurationError("Tool env must be a dictionary")

        return True


# Global configuration instance
tools_config = ToolsConfiguration()
tools_config.load_default_config()
