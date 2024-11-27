# Standard library imports
import argparse
import asyncio
import sys
from typing import List, Optional

# Local/package imports
from tracklistify.downloaders import DownloaderFactory
from tracklistify.providers.factory import create_provider_factory
from tracklistify.utils.identification import IdentificationManager
from tracklistify.utils.logger import logger

# Relative imports (to avoid circular dependencies)
from .app import App


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Identify tracks in a mix.")
    parser.add_argument("input", help="Path to audio file or YouTube URL")
    parser.add_argument(
        "-f",
        "--formats",
        choices=["json", "markdown", "m3u", "all"],
        help="Output format(s)",
    )
    parser.add_argument(
        "-p", "--provider", help="Specify the primary track identification provider"
    )
    parser.add_argument(
        "-nf",
        "--no-fallback",
        action="store_true",
        help="Disable fallback to secondary providers",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging"
    )
    return parser.parse_args()


async def Cli() -> int:
    """Core CLI execution logic"""
    app = None
    try:
        # Parse command line arguments
        args = parse_args()

        # Configure logging based on verbosity
        if args.verbose:
            logger.setLevel("DEBUG")

        # Get app configuration
        from tracklistify.config import get_config

        config = get_config()

        # Override provider settings if specified
        if args.provider:
            config.primary_provider = args.provider
        if args.no_fallback:
            config.fallback_enabled = False

        # Create app instance with config
        app = App(config)

        # Process the input file/URL
        tracks = await app.process_input(args.input)

        # Handle output formats
        formats = ["json"]
        if args.formats:
            formats = args.formats.split(",") if "," in args.formats else [args.formats]
            if "all" in formats:
                formats = ["json", "markdown", "m3u"]

        # Save outputs
        for fmt in formats:
            await app.save_output(tracks, fmt)

        return 0

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        if logger.getEffectiveLevel() == logger.setLevel("DEBUG"):
            import traceback

            traceback.print_exc()
        return 1

    finally:
        # Ensure cleanup happens
        if app:
            await app.close()


def cli():
    """Main entry point"""
    return asyncio.run(Cli())
