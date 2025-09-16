"""
Run command implementation for executing development tools.
"""

import os
from typing import List, Dict, Any

import click

from ..config import ToolsConfiguration
from ..exceptions import ToolNotFoundError, ToolExecutionError
from .base import DevCommand


class RunCommand(DevCommand):
    """Command for running development tools."""

    def __init__(self):
        super().__init__()
        self.config = ToolsConfiguration()

    def execute(self, tool_name: str, args: List[str]) -> bool:
        """Execute a development tool.

        Args:
            tool_name: Name of the tool to run
            args: Additional arguments for the tool

        Returns:
            bool: True if tool executed successfully

        Raises:
            ToolNotFoundError: If the specified tool is not found
            ToolExecutionError: If the tool execution fails
        """
        try:
            tool_config = self._get_tool_config(tool_name)
            return self._run_tool(tool_name, tool_config, args)
        except ToolNotFoundError as e:
            self.logger.error(
                "Tool not found: %s",
                tool_name,
                extra={"available_tools": self.config.list_tools()},
            )
            raise click.ClickException(str(e)) from e
        except ToolExecutionError as e:
            self.logger.error(
                "Tool execution failed: %s",
                str(e),
                extra={
                    "tool_name": tool_name,
                    "args": args,
                    "exit_code": e.exit_code,
                    "error_output": e.error_output,
                },
            )
            raise click.ClickException(str(e)) from e
        except Exception as e:
            self.logger.error(
                "Unexpected error running tool: %s",
                str(e),
                extra={"tool_name": tool_name, "args": args},
            )
            raise click.ClickException(str(e)) from e

    def _get_tool_config(self, tool_name: str) -> Dict[str, Any]:
        """Get tool configuration.

        Args:
            tool_name: Name of the tool

        Returns:
            Dict[str, Any]: Tool configuration

        Raises:
            ToolNotFoundError: If tool is not found
        """
        tool_config = self.config.get_tool(tool_name)
        if not tool_config:
            raise ToolNotFoundError(tool_name)
        return tool_config

    def _run_tool(
        self, tool_name: str, tool_config: Dict[str, Any], args: List[str]
    ) -> bool:
        """Run a specific tool with given configuration and arguments.

        Args:
            tool_name: Name of the tool
            tool_config: Tool configuration dictionary
            args: Additional arguments for the tool

        Returns:
            bool: True if tool executed successfully

        Raises:
            ToolExecutionError: If the tool execution fails
        """
        command = tool_config.get("command")
        if not command:
            raise ToolExecutionError(
                command="",
                exit_code=1,
                error_output=f"No command specified for tool '{tool_name}'",
                tool_name=tool_name,
            )

        # Build command with arguments
        cmd_args = tool_config.get("args", "").split() + args
        full_cmd = f"{command} {' '.join(cmd_args)}"
        env = self._prepare_environment(tool_config.get("env", {}))

        self.logger.info(
            "Running tool: %s",
            tool_name,
            extra={"command": command, "args": cmd_args, "config": tool_config},
        )

        try:
            result = self.run_shell_command(
                cmd=full_cmd, env=env, shell=True, check=True
            )
            if result.stdout:
                click.echo(result.stdout)
            return True
        except ToolExecutionError as e:
            e.tool_name = tool_name
            raise

    def _prepare_environment(self, tool_env: Dict[str, str]) -> Dict[str, str]:
        """Prepare environment variables for tool execution.

        Args:
            tool_env: Tool-specific environment variables

        Returns:
            Dict[str, str]: Combined environment variables
        """
        env = os.environ.copy()
        env.update(tool_env)
        return env
