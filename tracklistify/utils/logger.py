"""
Centralized logging configuration for Tracklistify.
"""

# Standard library imports
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# ANSI color codes for console output
COLORS = {
    "DEBUG": "\033[36m",  # Cyan
    "INFO": "\033[32m",  # Green
    "WARNING": "\033[33m",  # Yellow
    "ERROR": "\033[31m",  # Red
    "CRITICAL": "\033[35m",  # Magenta
    "RESET": "\033[0m",  # Reset
}


class ColoredFormatter(logging.Formatter):
    """Custom formatter adding colors to console output."""

    def __init__(self, fmt: Optional[str] = None, datefmt: Optional[str] = None):
        super().__init__(fmt, datefmt)

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with color."""
        # Save original levelname
        orig_levelname = record.levelname
        # Add color to levelname
        if record.levelname in COLORS:
            record.levelname = (
                f"{COLORS[record.levelname]}{record.levelname}{COLORS['RESET']}"
            )

        # Format the message
        result = super().format(record)

        # Restore original levelname
        record.levelname = orig_levelname
        return result


# Create the logger instance
logger = logging.getLogger("tracklistify")
logger.setLevel(logging.INFO)

# Prevent duplicate logging
logger.propagate = False

# Add default console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(ColoredFormatter("%(levelname)s: %(message)s"))
logger.addHandler(console_handler)


def setup_logger(
    name: str = "tracklistify",
    log_dir: Optional[Path] = None,
    verbose: bool = False,
    debug: bool = False,
) -> logging.Logger:
    """Configure and return a logger instance."""
    logger = logging.getLogger(name)

    # Clear any existing handlers
    logger.handlers.clear()

    # Set base level
    base_level = (
        logging.DEBUG if debug else (logging.INFO if verbose else logging.WARNING)
    )
    logger.setLevel(base_level)

    # Console handler with colored output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ColoredFormatter("%(levelname)s: %(message)s"))
    logger.addHandler(console_handler)

    # Add file logging if directory is specified
    if log_dir:
        add_file_logging(log_dir)

    return logger


def add_file_logging(log_dir: Path):
    """Add file logging to the logger."""
    logger = logging.getLogger("tracklistify")

    # Create log directory
    log_dir.mkdir(parents=True, exist_ok=True)

    # Create log file with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"tracklistify_{timestamp}.log"

    # File handler with detailed output
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    logger.addHandler(file_handler)
    logger.info(f"Logging to file: {log_file}")


def set_verbose(verbose: bool = True) -> None:
    """Set logger verbosity level."""
    for handler in logging.getLogger("tracklistify").handlers:
        if isinstance(handler, logging.StreamHandler):
            handler.setLevel(logging.DEBUG if verbose else logging.INFO)
