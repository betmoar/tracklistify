"""
Base command class for development CLI."""

import os
import subprocess
import traceback
import shlex
import shutil
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple, List

import click

from tracklistify.dev_cli.exceptions import ToolExecutionError, ToolNotFoundError
from tracklistify.dev_cli.logging import DevCliLogger
from tracklistify.dev_cli.config import ToolsConfiguration


class DevCommand(ABC):
    """Base command class."""

    def __init__(self):
        """Initialize command."""
        self.logger = DevCliLogger().get_context_logger(
            command_class=self.__class__.__name__
        )
        self.tools_config = ToolsConfiguration()

    @abstractmethod
    def execute(self, *args, **kwargs) -> bool:
        """Execute the command."""
        raise NotImplementedError("Subclasses must implement execute()")

    def _check_command_exists(self, cmd: str) -> Tuple[bool, Optional[str]]:
        """Check if a command exists in PATH."""
        cmd_path = shutil.which(cmd)
        if cmd_path:
            return True, cmd_path
        return False, None

    def _format_error_context(
        self, error: subprocess.CalledProcessError
    ) -> Dict[str, Any]:
        """Format error context for logging."""
        return {
            "exit_code": error.returncode,
            "stdout": (
                error.stdout
                if isinstance(error.stdout, str)
                else error.stdout.decode("utf-8")
                if error.stdout
                else ""
            ),
            "stderr": (
                error.stderr
                if isinstance(error.stderr, str)
                else error.stderr.decode("utf-8")
                if error.stderr
                else ""
            ),
            "cwd": os.getcwd(),
            "env_path": os.environ.get("PATH", ""),
            "traceback": traceback.format_exc(),
        }

    # pylint: disable=too-many-positional-arguments
    def run_shell_command(
        self,
        cmd: str,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
        shell: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        """Run a shell command.

        Args:
            cmd: Command to run
            env: Environment variables for the command
            cwd: Working directory for the command
            shell: Whether to run command in shell
            check: Whether to check return code

        Returns:
            CompletedProcess: Result of the command

        Raises:
            ToolExecutionError: If command execution fails
        """
        try:
            result = subprocess.run(
                cmd if shell else shlex.split(cmd),
                env=env,
                cwd=cwd,
                shell=shell,
                check=check,
                capture_output=True,
                text=True,
            )
            if result.stdout:
                click.echo(result.stdout)
            return result

        except subprocess.CalledProcessError as e:
            error_context = self._format_error_context(e)
            self.logger.error(
                "Command execution failed", extra={"error_context": error_context}
            )
            if e.stdout:
                click.echo(e.stdout)
            if e.stderr:
                click.secho(e.stderr, fg="red", err=True)
            raise ToolExecutionError(
                command=cmd,
                exit_code=e.returncode,
                error_output=e.stderr or e.stdout or str(e),
            ) from e

    def run_tool(self, tool_name: str, args: List[str]) -> None:
        """Run a development tool with the given arguments.

        Args:
            tool_name: Name of the tool to run
            args: Arguments for the tool

        Raises:
            ToolNotFoundError: If the tool is not found
            ToolExecutionError: If the tool execution fails
        """
        tool_config = self.tools_config.get_tool(tool_name)
        if not tool_config:
            raise ToolNotFoundError(tool_name)

        cmd_exists, cmd_path = self._check_command_exists(tool_config["command"])
        if not cmd_exists:
            raise ToolNotFoundError(tool_config["command"])

        cmd_args = tool_config.get("default_args", []) + args
        full_cmd = [cmd_path] + cmd_args

        try:
            result = subprocess.run(
                full_cmd, check=True, capture_output=True, text=True
            )
            if result.stdout:
                click.echo(result.stdout)

        except subprocess.CalledProcessError as e:
            error_context = self._format_error_context(e)
            self.logger.error(
                f"Tool execution failed: {tool_name}",
                extra={"error_context": error_context},
            )
            if e.stdout:
                click.echo(
                    e.stdout if isinstance(e.stdout, str) else e.stdout.decode("utf-8")
                )
            if e.stderr:
                click.secho(
                    e.stderr if isinstance(e.stderr, str) else e.stderr.decode("utf-8"),
                    fg="red",
                    err=True,
                )
            raise ToolExecutionError(
                command=" ".join(full_cmd),
                exit_code=e.returncode,
                error_output=(
                    e.stderr
                    if isinstance(e.stderr, str)
                    else e.stderr.decode("utf-8")
                    if e.stderr
                    else ""
                ),
                tool_name=tool_name,
            ) from e
