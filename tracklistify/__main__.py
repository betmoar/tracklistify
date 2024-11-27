"""Main entry point for Tracklistify."""

# Standard library imports
import asyncio
import os
import sys
import traceback
from pathlib import Path
from typing import NoReturn

from dotenv import load_dotenv

# Local/package imports
from tracklistify.core.cli import Cli
from tracklistify.core.types import AudioSegment
from tracklistify.utils.logger import logger, setup_logger

__all__ = ["main"]


class AudioProcessor:
    """Audio processing helper."""

    @staticmethod
    def create_segment(
        file_path: str, start_time: int = 0, duration: int = 60
    ) -> AudioSegment:
        """Create audio segment from file."""
        return AudioSegment(
            file_path=file_path, start_time=start_time, duration=duration
        )


async def async_main() -> int:
    """Async main entry point."""
    app = None

    try:
        # Load environment variables first
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            logger.debug(f"Loading environment from {env_path}")
            load_dotenv(env_path)

            # Log loaded environment variables for debugging
            for key, value in os.environ.items():
                if key.startswith("TRACKLISTIFY_"):
                    logger.debug(f"Loaded env var: {key}={value}")

        # Setup logging with environment settings
        setup_logger(
            verbose=os.getenv("TRACKLISTIFY_VERBOSE", "false").lower() == "true",
            debug=os.getenv("TRACKLISTIFY_DEBUG", "false").lower() == "true",
        )

        # Initialize app only once
        from tracklistify.core.app import App

        app = App()
        logger.debug("Starting application...")

        # Run CLI command
        result = await Cli()
        return result or 1

    except Exception as e:
        logger.error(f"Application error: {str(e)}")
        if os.getenv("TRACKLISTIFY_DEBUG", "false").lower() == "true":
            traceback.print_exc()
        return 1

    finally:
        if app:
            await app.cleanup()


def main() -> NoReturn:
    """Main entry point."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.exit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
