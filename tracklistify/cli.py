# Standard library imports
import argparse
import asyncio
import os
import signal
import sys
from pathlib import Path

from dotenv import load_dotenv

from .config import ConfigError, get_config
from .core import ApplicationError, AsyncApp

# Local/package imports
from .utils.logger import get_logger, setup_logger

logger = get_logger(__name__)


async def main(args: argparse.Namespace) -> int:
    """Main entry point."""
    try:
        # Load configuration
        config = get_config()

        # Create and run application
        app = AsyncApp(config)

        # Setup signal handlers
        def signal_handler():
            logger.info("Received shutdown signal")
            app.cleanup()

        for sig in (signal.SIGTERM, signal.SIGINT):
            asyncio.get_event_loop().add_signal_handler(sig, signal_handler)

        # Sample items for processing
        await app.process_input(args.input)

        return 0

    except ConfigError as e:
        logger.error(f"Configuration error: {e}")
        return 1
    except ApplicationError as e:
        logger.error(f"Application error: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1
    finally:
        if app:
            await app.close()


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Identify tracks in a mix.")

    parser.add_argument(
        "input",
        help="Path to audio file or YouTube URL",
    )

    parser.add_argument(
        "-f",
        "--formats",
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
        help="Disable fallback to secondary providers",
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level",
    )

    parser.add_argument(
        "--log-file",
        type=Path,
        help="Log file path",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    return parser.parse_args()


def cli() -> None:
    """Core CLI execution logic"""
    args = parse_args()

    # Load environment variables first
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    # Setup logging
    setup_logger(
        log_level=args.log_level,
        log_file=args.log_file,
        verbose=os.getenv("TRACKLISTIFY_VERBOSE", "false").lower() == "true",
        debug=os.getenv("TRACKLISTIFY_DEBUG", "false").lower() == "true",
    )

    # Log after logger is initialized
    if env_path.exists():
        logger.info(f"Loaded environment from {env_path}")

        # Log loaded environment variables for debugging
        for key, value in os.environ.items():
            if key.startswith("TRACKLISTIFY_"):
                logger.debug(f"Loaded env var: {key}={value}")

    try:
        exit_code = asyncio.run(main(args))
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(1)


if __name__ == "__main__":
    """Main entry point"""
    cli()
