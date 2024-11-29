import subprocess
import click
import sys
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)  # Default to WARNING level

# Define available tools
TOOLS = {
    "pylint": (
        "pylint",
        "Run pylint code analysis to check code quality and style",
    ),
    "pyreverse": (
        "pyreverse",
        "Generate UML class diagrams for code visualization",
    ),
    "pipdeptree": (
        "pipdeptree",
        "Display dependency tree of the project",
    ),
    "sphinx": (
        "sphinx-build",
        "Generate documentation using Sphinx",
    ),
    "vulture": (
        "vulture",
        "Find dead code in Python source",
    ),
    "pytest": (
        "pytest",
        "Run Python tests",
    ),
    "coverage": (
        "coverage",
        "Measure code coverage of Python programs",
    ),
    "ruff": (
        "ruff",
        "Run Ruff linter for Python code",
    ),
}


def style_help_text(help_text: str) -> str:
    """Add custom styling to help text."""
    # Style the headers
    help_text = help_text.replace("\nOptions:", "\n  \033[1;36mOptions:\033[0m")
    help_text = help_text.replace("\nCommands:", "\n  \033[1;36mCommands:\033[0m")

    # Style each line
    lines = help_text.split("\n")
    formatted_lines = []

    for line in lines:
        if line.strip().startswith("--"):
            # Style option flags
            parts = line.split("  ", 2)
            if len(parts) >= 2:
                option = parts[1]
                desc = parts[2] if len(parts) > 2 else ""
                formatted_line = f"    \033[1;32m{option}\033[0m  {desc}"
                formatted_lines.append(formatted_line)
        elif line.strip() and any(cmd in line.split() for cmd in ["run", "list"]):
            # Style command names
            parts = line.split("  ", 2)
            if len(parts) >= 2:
                cmd = parts[1]
                desc = parts[2] if len(parts) > 2 else ""
                formatted_line = f"    \033[1;32m{cmd}\033[0m  {desc}"
                formatted_lines.append(formatted_line)
        else:
            formatted_lines.append(line)

    return "\n".join(formatted_lines)


def run_command(cmd: str, extra_args: str = "") -> bool:
    """Execute a shell command and handle its output."""
    try:
        full_cmd = f"{cmd} {extra_args}".strip()
        logger.debug(f"Executing command: {full_cmd}")
        subprocess.run(full_cmd, shell=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        click.secho(f"✗ Error running command: {e}", fg="red", err=True)
        return False


class CustomGroup(click.Group):
    def get_help(self, ctx):
        help_text = super().get_help(ctx)
        return style_help_text(help_text)


class PassThroughCommand(click.Command):
    def parse_args(self, ctx, args: List[str]) -> Tuple[List[str], List[str]]:
        # Store the original args
        self._original_args = args
        return super().parse_args(ctx, args)

    def invoke(self, ctx):
        # Get the original args back
        args = getattr(self, "_original_args", [])
        if "--help" in args or "-h" in args:
            # Handle help directly
            tool = ctx.params.get("tool")
            if tool and tool in TOOLS:
                cmd, desc = TOOLS[tool]
                click.echo()
                click.secho("  Help for: ", fg="blue", bold=True, nl=False)
                click.secho(tool, fg="green", bold=True)
                click.secho("  Description: ", fg="blue", nl=False)
                click.echo(desc)
                click.echo()
                click.secho("  Tool Help Output:", fg="blue", bold=True)
                click.echo("  " + "─" * 50)
                click.echo()
                result = subprocess.run(
                    f"{cmd} --help", shell=True, text=True, capture_output=True
                )
                if result.stdout:
                    for line in result.stdout.splitlines():
                        click.echo(f"  {line}")
                if result.stderr:
                    for line in result.stderr.splitlines():
                        click.echo(f"  {line}")
                click.echo()
                click.echo("  " + "─" * 50)
                ctx.exit()
        return super().invoke(ctx)


@click.group(cls=CustomGroup, invoke_without_command=True)
@click.option("--debug", is_flag=True, help="Enable debug output")
@click.pass_context
def cli(ctx, debug):
    """🛠️  Tracklistify DevTools

    \b
    \033[1;36mDescription:\033[0m
      A collection of development tools for the Tracklistify project.

    \b
    \033[1;36mUsage:\033[0m
      dev [OPTIONS] COMMAND [ARGS]...

    \b
    \033[1;36mCommon Commands:\033[0m
      \033[1;32mrun\033[0m TOOL [ARGS]    Run a development tool
      \033[1;32mlist\033[0m               Display available development tools
    """
    if debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[logging.StreamHandler(sys.stderr)],
        )
        logger.setLevel(logging.DEBUG)

    logger.debug("CLI group initialized")
    if ctx.invoked_subcommand is None:
        # Show logo and help
        click.echo(ctx.get_help())
        click.echo()
        click.secho("  Quick Start:", fg="blue", bold=True)
        click.echo("    Run 'dev list' to see available tools")
        click.echo("    Run 'dev run <tool> --help' for tool-specific help")
        click.echo()


@cli.command("list")
def list_tools():
    """List available development tools."""
    logger.debug("Executing 'list' command")

    click.secho("\n  Available Tools:", fg="blue", bold=True)
    click.echo()

    # Calculate max tool name length for alignment
    max_name_length = max(len(tool) for tool in TOOLS.keys())

    for tool, (cmd, desc) in TOOLS.items():
        # Tool name in green
        click.secho(f"    {tool:<{max_name_length}}", fg="green", bold=True, nl=False)
        # Description in white
        click.secho(f"{desc}")
        # Command in dim blue
        click.secho("    command:  ", dim=True, nl=False)
        click.secho(cmd, fg="blue", dim=False)
        click.echo()


@cli.command("run")
@click.argument("tool", type=click.Choice(list(TOOLS.keys())))
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def run_tool(tool, args):
    """Run a development tool."""
    logger.debug(f"Executing 'run' command with tool={tool}, args={args}")
    cmd, desc = TOOLS[tool]

    # Handle help flag
    if len(args) == 0:
        # Show our custom help if no args provided
        click.echo()
        click.secho("  Tool: ", fg="blue", bold=True, nl=False)
        click.secho(tool, fg="green", bold=True)
        click.secho("  Description: ", fg="blue", nl=False)
        click.echo(desc)
        click.echo("\n  Usage: dev run {tool} [ARGS...]")
        click.echo("  For tool-specific help, run: dev run {tool} --help")
        click.echo()
        return

    extra_args = " ".join(args) if args else ""
    full_cmd = f"{cmd} {extra_args}"

    click.echo()
    click.secho("  Running: ", fg="blue", bold=True, nl=False)
    click.secho(tool, fg="green", bold=True)
    click.secho("  Description: ", fg="blue", nl=False)
    click.echo(desc)
    click.secho("  Command: ", fg="blue", nl=False)
    click.echo(full_cmd)
    click.echo()

    # Run the command and capture output
    try:
        result = subprocess.run(full_cmd, shell=True, text=True, capture_output=True)
        if result.stdout:
            click.echo(result.stdout)
        if result.stderr:
            click.echo(result.stderr, err=True)
        success = result.returncode == 0
    except Exception as e:
        click.secho(f"  Error: {str(e)}", fg="red")
        success = False

    if success:
        click.secho("\n  ✓ Command completed successfully", fg="green")
    else:
        click.secho(
            f"\n  ✗ Error runnin cmdg: '{full_cmd}' exit status {result.returncode}.",
            fg="red",
        )
    click.echo()
    exit(0 if success else 1)


def dev():
    """Entry point for the dev command."""
    logger.debug("Starting dev command")
    try:
        cli(prog_name="dev")
    except Exception as e:
        logger.exception(f"Error in dev command: {e}")
        raise


if __name__ == "__main__":
    dev()
