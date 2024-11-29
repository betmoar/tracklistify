import subprocess
from typing import Optional

import click

TOOLS = {
    "pylint": (
        "pylint tracklistify --full-documentation",
        "Run pylint code analysis to check code quality and style",
    ),
    "pyreverse": (
        "pyreverse -o png -p tracklistify tracklistify",
        "Generate UML class diagrams for code visualization",
    ),
    "pipdeptree": (
        "pipdeptree",
        "Display project dependency tree in a hierarchical format",
    ),
    "sphinx": (
        "sphinx-build -b html docs/ _build/html",
        "Build HTML documentation from Sphinx source files",
    ),
    "vulture": ("vulture tracklistify", "Find and report potentially dead Python code"),
}

VERSION = "1.0.0"


def run_command(
    cmd: str, tool_name: str, verbose: bool = False, extra_args: str = ""
) -> bool:
    """Run a shell command and handle its output."""
    full_cmd = f"{cmd} {extra_args}".strip()
    if verbose:
        click.secho(f"Running command: {full_cmd}", fg="blue")

    try:
        result = subprocess.run(
            full_cmd,
            shell=True,
            check=True,
            capture_output=not verbose,
            text=True,
        )
        click.secho(f"✓ {tool_name} completed successfully", fg="green")
        if result.stdout and not verbose:
            click.echo(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        click.secho(f"✗ {tool_name} failed", fg="red", err=True)
        if e.stderr and not verbose:
            click.echo(e.stderr, err=True)
        return False


@click.group(invoke_without_command=True)
@click.option("-v", "--version", is_flag=True, help="Display version information.")
@click.option("--verbose", is_flag=True, help="Enable verbose output.")
@click.option("-h", "--help", is_flag=True, help="Show this help message.")
@click.pass_context
def cli(ctx, version, verbose, help):
    """Tracklistify Development Tools 🛠️

    Description:
      A collection of development tools for the Tracklistify project.

    Usage:
      dev [OPTIONS] COMMAND [ARGS]...

    Common Commands:
      dev             Run development tools (pylint, sphinx, etc.)
      list            Display available development tools
    """
    # Always ensure ctx.obj exists
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose

    if help:
        click.echo(ctx.get_help())
        ctx.exit()
    if version:
        click.secho(f"🎵 Tracklistify Dev Tools v{VERSION}", fg="blue")
        ctx.exit()
    elif ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command()
@click.pass_context
@click.option(
    "-t",
    "--tool",
    type=click.Choice(list(TOOLS.keys()), case_sensitive=False),
    help="Specific tool to run",
)
@click.option("-q", "--quiet", is_flag=True, help="Suppress output")
@click.option("-a", "--all", is_flag=True, help="Run all tools")
@click.option("--args", help="Additional arguments to pass to the tool")
def dev(ctx, tool: Optional[str], quiet: bool, all: bool, args: Optional[str]):
    """Tracklistify Development Tools.

    \b
    Description:
      A collection of development tools for the Tracklistify project.

    \b
    Usage Examples:
      dev                                       Show this help message
      dev -t pylint                             Run only pylint
      dev -t pylint -q                          Run pylint quietly
      dev -t pylint --args="--disable=C0111"    Run pylint with custom arguments
      dev -a                                    Run all tools
    """
    ctx.ensure_object(dict)
    verbose = ctx.obj.get("verbose", False) and not quiet
    if not tool and not all:
        click.echo(ctx.get_help())
        return

    if all:
        success = True
        for name, (cmd, desc) in TOOLS.items():
            if not quiet:
                click.secho(f"\nRunning {name}: {desc}", fg="blue")
            if not run_command(cmd, name, verbose=verbose, extra_args=args or ""):
                success = False
        ctx.exit(0 if success else 1)

    cmd, desc = TOOLS[tool]
    if not quiet:
        click.secho(f"Running {tool}: {desc}", fg="blue")
    success = run_command(cmd, tool, verbose=verbose, extra_args=args or "")
    ctx.exit(0 if success else 1)


@click.command()
@click.option("--verbose", is_flag=True, help="Show detailed information")
def list(verbose: bool):
    """List available development tools.

    Display a list of all available development tools and their descriptions.
    """
    click.secho("Available Tools:", fg="blue", bold=True)
    click.echo()

    for tool, (cmd, desc) in TOOLS.items():
        click.secho(f"  {tool:<20}", fg="green", nl=False)
        click.echo(desc)
        if verbose:
            click.echo(f"    Command: {cmd}")
            click.echo()


if __name__ == "__main__":
    cli()
