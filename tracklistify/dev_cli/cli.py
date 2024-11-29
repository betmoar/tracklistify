"""
CLI entry point and command registration.
"""

from typing import Optional, Tuple

import click

from .logging import DevCliLogger
from .commands.run import RunCommand
from .commands.list import ListCommand
from .exceptions import DevCliError, ToolExecutionError


@click.group()
@click.option("--debug", is_flag=True, help="Enable debug logging")
@click.option("--log-dir", type=str, help="Directory for log files")
def cli(debug: bool = False, log_dir: Optional[str] = None):
    """Development CLI tools.

    A collection of tools for development tasks.
    """
    # Initialize logging
    logger = DevCliLogger()
    logger.setup(debug=debug, log_dir=log_dir)


@cli.command()
@click.argument("tool_name")
@click.argument("args", nargs=-1)
def run(tool_name: str, args: Tuple[str]):
    """Run a development tool.

    Args:
        tool_name: Name of the tool to run
        args: Additional arguments for the tool
    """
    try:
        cmd = RunCommand()
        cmd.execute(tool_name, list(args))
    except ToolExecutionError as e:
        # Format error message with command details
        error_msg = f"✗ {str(e)}"
        if e.command:
            error_msg += f"\nCommand: {e.command}"
        click.secho(error_msg, fg="red", err=True)
        raise click.Abort() from e
    except DevCliError as e:
        click.secho(f"✗ {str(e)}", fg="red", err=True)
        raise click.Abort() from e
    except Exception as e:
        click.secho(f"✗ Unexpected error: {str(e)}", fg="red", err=True)
        raise click.Abort() from e


@cli.command()
def list_tools():
    """List available development tools."""
    try:
        cmd = ListCommand()
        cmd.execute()
    except DevCliError as e:
        click.secho(f"✗ {str(e)}", fg="red", err=True)
        raise click.Abort() from e
    except Exception as e:
        click.secho(f"✗ Unexpected error: {str(e)}", fg="red", err=True)
        raise click.Abort() from e


if __name__ == "__main__":
    cli()
