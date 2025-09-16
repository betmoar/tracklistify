"""
Custom exceptions for the development CLI tools.
"""

from typing import Optional, Any, Dict


class DevCliError(Exception):
    """Base exception for all development CLI errors."""

    def __init__(
        self,
        message: str,
        *args: Any,
        error_code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.error_code = error_code or "DEV_CLI_ERROR"
        self.context = context or {}
        super().__init__(message, *args)

    def __str__(self) -> str:
        error_msg = f"[{self.error_code}] {self.message}"
        if self.context:
            error_msg += f"\nContext: {self.context}"
        return error_msg


class ToolNotFoundError(DevCliError):
    """Raised when a requested tool is not found."""

    def __init__(self, tool_name: str, *args: Any):
        super().__init__(
            f"Tool '{tool_name}' not found",
            *args,
            error_code="TOOL_NOT_FOUND",
            context={"tool_name": tool_name},
        )


class ToolExecutionError(DevCliError):
    """Error raised when a tool execution fails."""

    def __init__(
        self, command: str, exit_code: int, error_output: str, tool_name: str = None
    ):
        """Initialize with command details.

        Args:
            command: The command that failed
            exit_code: The exit code from the command
            error_output: Error output from the command
            tool_name: Name of the tool that failed
        """
        self.command = command
        self.exit_code = exit_code
        self.error_output = error_output
        self.tool_name = tool_name

        message = f"Command failed with exit code {exit_code}"
        if tool_name:
            message = f"Tool '{tool_name}' failed: {message}"
        if error_output:
            message = f"{message}\nError: {error_output}"

        super().__init__(
            message,
            error_code="TOOL_EXECUTION_ERROR",
            context={
                "tool_name": tool_name,
                "command": command,
                "exit_code": exit_code,
                "error_output": error_output,
            },
        )


class ConfigurationError(DevCliError):
    """Raised when there's an error in the configuration."""

    def __init__(self, message: str, *args: Any, config_path: Optional[str] = None):
        super().__init__(
            message,
            *args,
            error_code="CONFIG_ERROR",
            context={"config_path": config_path} if config_path else None,
        )


class ValidationError(DevCliError):
    """Raised when validation fails."""

    def __init__(self, message: str, field: str, value: Any, *args: Any):
        super().__init__(
            message,
            *args,
            error_code="VALIDATION_ERROR",
            context={"field": field, "value": value},
        )
