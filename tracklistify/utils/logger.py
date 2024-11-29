"""
Centralized logging configuration for Tracklistify.
"""

# Standard library imports
import logging
import sys
from logging.handlers import RotatingFileHandler
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


def setup_logger(
    log_level: str = "INFO",
    log_file: Optional[Path] = None,
    max_bytes: int = 10_000_000,
    backup_count: int = 5,
    verbose: bool = False,
    debug: bool = False,
) -> logging.Logger:
    """Configure and return a logger instance."""
    logger = logging.getLogger()

    # Set base level
    base_level = (
        logging.DEBUG if debug else (logging.INFO if verbose else logging.WARNING)
    )
    logger.setLevel(base_level)  # getattr(logging, log_level.upper())

    console_formatter = ColoredFormatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_formatter = logging.Formatter(
        (
            "%(asctime)s - %(name)s - %(levelname)s - "
            "%(filename)s:%(lineno)d - %(message)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler with colored output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # Add file logging if directory is specified
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)
