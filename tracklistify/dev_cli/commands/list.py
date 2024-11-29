"""
List available development tools.
"""

import click

from ..config import ToolsConfiguration
from .base import DevCommand


class ListCommand(DevCommand):
    """Command to list available development tools."""

    def __init__(self):
        super().__init__()
        self.config = ToolsConfiguration()

    def execute(self) -> bool:
        """Execute list command.

        Returns:
            bool: True if successful, False otherwise
        """
        tools = self.config.list_tools()
        if not tools:
            click.echo("No tools configured.")
            return False

        click.echo("\nAvailable development tools:")
        click.echo("-" * 40)

        for tool_name, tool_config in tools.items():
            description = tool_config.get("description", "No description available")
            args = tool_config.get("args", "")
            env = tool_config.get("env", {})

            click.echo(f"\n{tool_name}:")
            click.echo(f"  Description: {description}")
            if args:
                click.echo(f"  Default args: {args}")
            if env:
                click.echo("  Environment:")
                for key, value in env.items():
                    click.echo(f"    {key}={value}")

        click.echo("\n")
        return True
