#!/usr/bin/env python3
"""
Development tools entry point for Tracklistify.

This script provides a command-line interface for various development tools
and utilities used in the Tracklistify project.
"""

import sys

from tracklistify.dev_cli import cli
from tracklistify.dev_cli.logging import DevCliLogger


def main():
    """Main entry point for the development tools CLI."""
    try:
        # Initialize logger with default settings
        DevCliLogger().setup()

        # Run the CLI
        cli()
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
