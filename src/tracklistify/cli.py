# Standard library imports
import argparse
import asyncio
import os
import shutil
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
            "Received shutdown signal — cancelling (press Ctrl+C again to force exit)"
        )
        if main_task is not None and not main_task.done():
            main_task.cancel()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            asyncio.get_event_loop().add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Windows' ProactorEventLoop has no add_signal_handler. Ctrl+C
            # still works through Python's default KeyboardInterrupt path;
            # what is lost is the two-stage cancel-then-force-exit behaviour.
            logger.debug(
                "add_signal_handler unavailable on this platform (%s) — "
                "falling back to default KeyboardInterrupt handling",
                sig.name,
            )
            break

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
            # Same pattern: None leaves the configured value alone.
            cache_enabled=False if args.no_cache else None,
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
        # Gate the traceback on --debug. Download errors (notably yt-dlp
        # 403s) carry a deep __cause__ chain into yt-dlp internals; logging
        # exc_info unconditionally dumps that whole chain into the log — the
        # flood an operator sees on a transient 403. At default verbosity
        # one clean line is enough; --debug keeps the full chain. Matches
        # base.process_input's `if self.config.debug` traceback gating.
        logger.error(f"Unexpected error: {e}", exc_info=args.debug)
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
    parser = argparse.ArgumentParser(
        prog="tracklistify",
        description="Identify tracks in a DJ mix.",
        # Typing the bare command is the most common way to ask "what does
        # this do?", and argparse answers it with a usage block and
        # "error: the following arguments are required: input" — technically
        # correct, useless as a first impression. Show a worked example.
        epilog=(
            "examples:\n"
            "  tracklistify https://soundcloud.com/artist/some-mix\n"
            "  tracklistify https://www.youtube.com/watch?v=VIDEO_ID\n"
            "  tracklistify ~/Music/recorded-set.mp3\n"
            "  tracklistify --no-cache <url>   # re-identify, ignore stored results\n"
            "  tracklistify -sc <url>          # skip the MP3 transcode (faster)\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

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
        "--no-cache",
        action="store_true",
        default=None,
        help=(
            "Bypass both caches for this run: re-download the audio and "
            "re-identify every segment, ignoring and overwriting any stored "
            "results. Use when a cached identification is wrong — entries "
            "are keyed by content hash and live for 30 days, so a bad match "
            "is otherwise reproduced on every re-run."
        ),
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

    # A bare invocation is a question ("what is this?"), not a mistake.
    # argparse would answer it with a usage line and exit 2; full help and
    # exit 0 is the useful reading. An argv with actual content still gets
    # normal argparse error handling, since that IS a mistake.
    if not (sys.argv[1:] if argv is None else argv):
        parser.print_help()
        parser.exit(0)

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

    # Fail fast with an actionable message: every pipeline stage (download
    # post-processing, segmentation, shazamio decoding via pydub) needs
    # ffmpeg. Without this check the failure surfaces much later as a
    # cryptic per-segment subprocess error.
    if shutil.which("ffmpeg") is None:
        logger.error(
            "ffmpeg is required but was not found on PATH. Install it first "
            "(e.g. `apt install ffmpeg`, `brew install ffmpeg`) and re-run."
        )
        sys.exit(1)

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
