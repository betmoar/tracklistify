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


def set_logger(
    log_level: str = "INFO",
    log_file: Optional[Path] = None,
    max_bytes: int = 10_000_000,
    backup_count: int = 5,
    verbose: bool = False,
    debug: bool = False,
) -> logging.Logger:
    """Configure and return a logger instance.

    This function can be called multiple times safely. Existing handlers
    will be removed before adding new ones to prevent duplicate log messages.

    Args:
        log_level: Base log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file for file-based logging
        max_bytes: Maximum size of log file before rotation (default: 10MB)
        backup_count: Number of backup log files to keep (default: 5)
        verbose: Enable verbose output (sets INFO level)
        debug: Enable debug output (sets DEBUG level)

    Returns:
        Configured root logger instance
    """
    logger = logging.getLogger()

    # Close existing handlers before clearing to avoid leaked file descriptors
    # (e.g. a previously attached RotatingFileHandler keeping a log file open).
    # `handlers.clear()` alone removes references but doesn't close streams.
    for existing in list(logger.handlers):
        try:
            existing.close()
        except Exception:  # noqa: BLE001 - best-effort close on shutdown path
            pass
        logger.removeHandler(existing)

    # Set base level: debug > verbose > log_level (string parameter).
    if debug:
        base_level: int = logging.DEBUG
    elif verbose:
        base_level = logging.INFO
    else:
        # logging.getLevelName returns the int for known names ("DEBUG" -> 10),
        # or the string "Level <name>" for unknown inputs. Fall back to
        # WARNING for anything unrecognised (preserves the prior default).
        resolved = logging.getLevelName(log_level.upper())
        base_level = resolved if isinstance(resolved, int) else logging.WARNING
    logger.setLevel(base_level)

    # Cap known-noisy third-party loggers at ERROR. symphonia (shazamio's
    # Rust audio decoder) emits a WARNING for every non-MP3 byte stretch
    # when it falls back to the MP3 demuxer on non-MP3 containers — most
    # visible under ``tracklistify --stream-copy`` where segments are
    # webm/m4a. Genuine decode ERRORs still propagate.
    for _noisy_logger in ("symphonia_bundle_mp3", "symphonia_core"):
        logging.getLogger(_noisy_logger).setLevel(logging.ERROR)

    console_formatter = ColoredFormatter(
        "%(asctime)s %(levelname)s - %(name)s - %(message)s",
        datefmt="%H:%M:%S",
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
