"""
Error logging system for Tracklistify.

This module provides a comprehensive error logging system with:
- Structured error logging with context
- Error categorization and metrics
- Stack trace handling
- Error reporting utilities
"""

# Standard library imports
import functools
import inspect
import logging
import sys
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Generator, Optional, Type, TypeVar

# Local/package imports
from tracklistify.utils.logger import logger

T = TypeVar("T")


@dataclass
class ErrorContext:
    """Container for error context information."""

    error: Exception
    timestamp: datetime = field(default_factory=datetime.utcnow)
    function: str = ""
    module: str = ""
    line_number: int = 0
    stack_trace: str = ""
    context: Dict[str, Any] = field(default_factory=dict)


class ErrorMetrics:
    """Track error metrics and statistics."""

    def __init__(self) -> None:
        self.error_counts: Dict[str, int] = {}
        self.last_errors: Dict[str, ErrorContext] = {}

    def record_error(self, error_context: ErrorContext) -> None:
        """Record an error occurrence."""
        error_type = error_context.error.__class__.__name__
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
        self.last_errors[error_type] = error_context

    def get_error_stats(self) -> Dict[str, Any]:
        """Get current error statistics."""
        return {
            "counts": self.error_counts.copy(),
            "total_errors": sum(self.error_counts.values()),
            "unique_errors": len(self.error_counts),
        }


# Global error metrics instance
error_metrics = ErrorMetrics()


def create_error_context(
    error: Exception, additional_context: Optional[Dict[str, Any]] = None
) -> ErrorContext:
    """Create error context from an exception."""
    frame = inspect.currentframe()
    while frame:
        if frame.f_back and frame.f_back.f_code.co_name != "create_error_context":
            frame = frame.f_back
            break
        frame = frame.f_back

    if not frame:
        return ErrorContext(error=error, context=additional_context or {})

    return ErrorContext(
        error=error,
        function=frame.f_code.co_name,
        module=frame.f_code.co_filename,
        line_number=frame.f_lineno,
        stack_trace="".join(
            traceback.format_tb(frame.f_back.f_back if frame.f_back else frame)
        ),
        context=additional_context or {},
    )


def log_error(
    error: Exception,
    level: int = logging.ERROR,
    additional_context: Optional[Dict[str, Any]] = None,
) -> None:
    """Log an error with context."""
    error_context = create_error_context(error, additional_context)
    error_metrics.record_error(error_context)

    log_message = (
        f"Error: {error.__class__.__name__}: {str(error)}\n"
        f"Function: {error_context.function}\n"
        f"Module: {error_context.module}\n"
        f"Line: {error_context.line_number}\n"
        f"Time: {error_context.timestamp}\n"
    )

    if error_context.context:
        log_message += f"Context: {error_context.context}\n"

    log_message += f"Stack Trace:\n{error_context.stack_trace}"

    logger.log(level, log_message)


@contextmanager
def error_context(
    context: Dict[str, Any], error_types: Optional[Type[Exception]] = None
) -> Generator[None, None, None]:
    """Context manager for error handling with additional context.

    Args:
        context: Additional context to include in error logs
        error_types: Specific exception types to catch, defaults to Exception

    Example:
        with error_context({'user_id': 123, 'action': 'download'}):
            # Your code here
            pass
    """
    try:
        yield
    except Exception as e:
        if error_types is None or isinstance(e, error_types):
            log_error(e, additional_context=context)
        raise


def log_errors(
    error_types: Optional[Type[Exception]] = None, level: int = logging.ERROR
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator to automatically log errors in functions.

    Args:
        error_types: Specific exception types to catch, defaults to Exception
        level: Logging level for errors

    Example:
        @log_errors(error_types=DownloadError)
        def download_track(url: str) -> str:
            # Your code here
            pass
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if error_types is None or isinstance(e, error_types):
                    context = {
                        "function": func.__name__,
                        "args": args,
                        "kwargs": kwargs,
                    }
                    log_error(e, level=level, additional_context=context)
                raise

        return wrapper

    return decorator


# Convenience functions for different error levels
def log_warning(
    error: Exception, additional_context: Optional[Dict[str, Any]] = None
) -> None:
    """Log a warning-level error."""
    log_error(error, level=logging.WARNING, additional_context=additional_context)


def log_critical(
    error: Exception, additional_context: Optional[Dict[str, Any]] = None
) -> None:
    """Log a critical-level error."""
    log_error(error, level=logging.CRITICAL, additional_context=additional_context)


def get_error_stats() -> Dict[str, Any]:
    """Get current error statistics."""
    return error_metrics.get_error_stats()
