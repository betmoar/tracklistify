"""
Logging configuration for the development CLI.
"""

import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Optional, Dict, Any


class DevCliLogger:
    """Logger for the development CLI."""

    def __init__(self):
        """Initialize the logger."""
        self.logger = logging.getLogger("dev_cli")
        self.logger.setLevel(logging.DEBUG)
        self._setup_done = False

    def setup(self, debug: bool = False, log_dir: Optional[str] = None) -> None:
        """Set up logging handlers.

        Args:
            debug: Enable debug logging
            log_dir: Directory for log files
        """
        if self._setup_done:
            return

        # Set up console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG if debug else logging.INFO)
        console_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s \033[0;36m%(levelname)-8s\033[0m %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        self.logger.addHandler(console_handler)

        # Set up file handler if log directory is provided
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            log_file = os.path.join(log_dir, f"dev-cli-{timestamp}.log")

            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=5,
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s [%(levelname)s] %(message)s\n" "%(extra)s\n",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            self.logger.addHandler(file_handler)
            self.logger.debug("Log file created at: %s", log_file, extra={"extra": ""})

        self._setup_done = True

    def get_context_logger(self, **context) -> "ContextLogger":
        """Get a logger with context.

        Args:
            **context: Context key-value pairs

        Returns:
            ContextLogger instance
        """
        return ContextLogger(self.logger, context)


class ContextLogger:
    """Logger that includes context with each log message."""

    def __init__(self, logger: logging.Logger, context: Dict[str, Any]):
        """Initialize with logger and context.

        Args:
            logger: Logger instance
            context: Context dictionary
        """
        self.logger = logger
        self.context = context

    def _format_context(self, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Format context dictionary for logging.

        Args:
            extra: Additional context to include

        Returns:
            Combined context dictionary
        """
        context = self.context.copy()
        if extra:
            # Rename 'args' to avoid conflict with LogRecord
            if "args" in extra:
                extra["cli_args"] = extra.pop("args")
            context.update(extra)
        context_str = "\n".join(f"{k}: {v}" for k, v in context.items())
        return {"extra": f"Context:\n{context_str}" if context_str else ""}

    def debug(self, msg: str, *args, extra: Optional[Dict[str, Any]] = None, **kwargs):
        """Log a debug message with context."""
        self.logger.debug(msg, *args, extra=self._format_context(extra), **kwargs)

    def info(self, msg: str, *args, extra: Optional[Dict[str, Any]] = None, **kwargs):
        """Log an info message with context."""
        self.logger.info(msg, *args, extra=self._format_context(extra), **kwargs)

    def warning(
        self, msg: str, *args, extra: Optional[Dict[str, Any]] = None, **kwargs
    ):
        """Log a warning message with context."""
        self.logger.warning(msg, *args, extra=self._format_context(extra), **kwargs)

    def error(self, msg: str, *args, extra: Optional[Dict[str, Any]] = None, **kwargs):
        """Log an error message with context."""
        self.logger.error(msg, *args, extra=self._format_context(extra), **kwargs)

    def critical(
        self, msg: str, *args, extra: Optional[Dict[str, Any]] = None, **kwargs
    ):
        """Log a critical message with context."""
        self.logger.critical(msg, *args, extra=self._format_context(extra), **kwargs)
