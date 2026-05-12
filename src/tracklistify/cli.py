# Standard library imports
import argparse
import asyncio
import os
import signal
import sys
from pathlib import Path

from dotenv import load_dotenv

from .config import ConfigError, get_config, get_root
from .config.security import mask_sensitive_value
from .core import ApplicationError, AsyncApp

# Local/package imports
from .utils.logger import get_logger, set_logger

# Get the logger for this module
logger = get_logger(__name__)


async def main(args: argparse.Namespace) -> int:
    """Main entry point.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success, 1 for failure, 130 for SIGINT)
    """
    app = None  # Initialize app to None
    main_task = asyncio.current_task()
    interrupt_count = 0

    def signal_handler() -> None:
        """Cancel the main task on first signal; force exit on second.

        The old implementation just scheduled ``app.cleanup()`` as a side
        task and let the main work keep running — so Ctrl+C printed a
        message but didn't actually stop anything. Cancelling the main
        task lets ``CancelledError`` propagate through the await chain,
        the providers' ``async with`` blocks close cleanly, and the
        ``finally`` here runs ``app.close()`` for final teardown.
        """
        nonlocal interrupt_count
        interrupt_count += 1
        if interrupt_count >= 2:
            logger.warning("Second interrupt — forcing exit")
            os._exit(130)
        logger.info(
            "Received shutdown signal — cancelling "
            "(press Ctrl+C again to force exit)"
        )
        if main_task is not None and not main_task.done():
            main_task.cancel()

    for sig in (signal.SIGTERM, signal.SIGINT):
        asyncio.get_event_loop().add_signal_handler(sig, signal_handler)

    try:
        # Load configuration
        config = get_config()

        # Create and run application
        app = AsyncApp(config)

        # Process input with CLI argument overrides
        await app.process_input(
            args.input,
            formats=args.formats,
            provider=args.provider,
            # Only override config when --no-fallback is explicitly set.
            fallback_enabled=False if args.no_fallback else None,
            stream_copy=args.stream_copy,
        )

        return 0

    except asyncio.CancelledError:
        logger.info("Operation cancelled by user")
        return 130
    except ConfigError as e:
        logger.error(f"Configuration error: {e}", exc_info=True)
        return 1
    except ApplicationError as e:
        logger.error(f"Application error: {e}", exc_info=True)
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1
    finally:
        if app:
            try:
                await app.close()
            except asyncio.CancelledError:
                # Second Ctrl+C arrived during teardown — proceed to exit.
                logger.debug("Teardown cancelled by second interrupt")


def parse_args(argv=None) -> argparse.Namespace:
    """Parse command line arguments.

    Args:
        argv: Optional list of arguments for testing. If None, uses sys.argv.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(description="Identify tracks in a mix.")

    parser.add_argument(
        "input",
        help="Path to audio file or yt-dlp URL",
    )

    parser.add_argument(
        "-f",
        "--formats",
        default="all",
        choices=["json", "markdown", "m3u", "all"],
        help="Output format(s)",
    )

    parser.add_argument(
        "-p",
        "--provider",
        help="Specify the primary track identification provider",
    )

    parser.add_argument(
        "--no-fallback",
        action="store_true",
        default=None,
        help="Disable fallback to secondary providers",
    )

    parser.add_argument(
        "-sc",
        "--stream-copy",
        action="store_true",
        default=False,
        help=(
            "Skip yt-dlp's MP3 transcode and let segments stream-copy the "
            "source codec (opus/webm/m4a). Much faster on long mixes. "
            "Shazamio handles any format via ffmpeg; ACRCloud historically "
            "prefers MP3 so identification rates may drop with that provider."
        ),
    )

    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level",
    )

    parser.add_argument(
        "--log-file",
        default=None,
        type=Path,
        help="Log file path",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    parser.add_argument(
        "-d",
        "--debug",
        default=False,
        action="store_true",
        help="Enable debug logging",
    )

    return parser.parse_args(argv)


def load_environment_variables(env_path: Path) -> None:
    """Load environment variables from a file."""
    if env_path.exists():
        load_dotenv(env_path)
        logger.info(f"Loaded environment from {env_path}")

        # Log loaded environment variables for debugging (mask sensitive values)
        for key, value in os.environ.items():
            if key.startswith("TRACKLISTIFY_"):
                # Mask sensitive values to prevent credential exposure
                display_value = mask_sensitive_value(key, value)
                logger.debug(f"Loaded env var: {key}={display_value}")


def cli() -> None:
    """Core CLI execution logic"""
    args = parse_args()

    # Setup logging
    set_logger(
        log_level=args.log_level,
        log_file=args.log_file,
        verbose=args.verbose,
        debug=args.debug,
    )

    # Log at the start of the CLI function
    logger.info("Starting CLI")

    # Load environment variables first
    env_path = get_root() / ".env"
    load_environment_variables(env_path)

    try:
        exit_code = asyncio.run(main(args))
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        print("\nOperation cancelled by user")
        sys.exit(1)


if __name__ == "__main__":
    """Main entry point"""
    cli()
