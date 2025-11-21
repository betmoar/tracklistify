"""
Tests for Issue #8: Fix Logger Handler Duplication

Validates that set_logger() doesn't duplicate handlers on multiple calls.
"""

# Standard library imports
import logging
from pathlib import Path

# Third-party imports
import pytest

# Local/package imports
from tracklistify.utils.logger import set_logger, get_logger


@pytest.fixture(autouse=True)
def reset_logger():
    """Reset root logger before each test."""
    logger = logging.getLogger()
    logger.handlers.clear()
    logger.setLevel(logging.WARNING)
    yield
    # Cleanup after test
    logger.handlers.clear()


class TestLoggerConfiguration:
    """Test logger configuration."""

    def test_set_logger_clears_existing_handlers(self):
        """Test that set_logger clears existing handlers."""
        # First call
        set_logger(log_level="INFO")
        logger = logging.getLogger()
        handler_count_1 = len(logger.handlers)

        # Second call should not add more handlers
        set_logger(log_level="DEBUG")
        handler_count_2 = len(logger.handlers)

        assert handler_count_1 == handler_count_2, (
            f"Handlers duplicated: {handler_count_1} vs {handler_count_2}"
        )

    def test_multiple_calls_dont_duplicate_handlers(self):
        """Test that multiple set_logger calls don't duplicate handlers."""
        # Call set_logger multiple times
        for _ in range(5):
            set_logger(log_level="INFO")

        logger = logging.getLogger()

        # Should only have 1 console handler
        assert len(logger.handlers) == 1, (
            f"Expected 1 handler, got {len(logger.handlers)}"
        )

    def test_file_handler_added_when_specified(self, tmp_path):
        """Test that file handler is added when log_file specified."""
        log_file = tmp_path / "test.log"

        set_logger(log_level="INFO", log_file=log_file)

        logger = logging.getLogger()

        # Should have console + file handlers
        assert len(logger.handlers) == 2

    def test_file_handler_not_duplicated(self, tmp_path):
        """Test that file handler is not duplicated on multiple calls."""
        log_file = tmp_path / "test.log"

        set_logger(log_level="INFO", log_file=log_file)
        set_logger(log_level="INFO", log_file=log_file)
        set_logger(log_level="INFO", log_file=log_file)

        logger = logging.getLogger()

        # Should still have only 2 handlers
        assert len(logger.handlers) == 2

    def test_handler_cleanup_on_reconfigure(self, tmp_path):
        """Test that handlers are properly cleaned up."""
        log_file_1 = tmp_path / "test1.log"
        log_file_2 = tmp_path / "test2.log"

        # First configuration
        set_logger(log_level="INFO", log_file=log_file_1)
        assert len(logging.getLogger().handlers) == 2

        # Second configuration with different file
        set_logger(log_level="INFO", log_file=log_file_2)
        assert len(logging.getLogger().handlers) == 2

    def test_log_level_changes_applied(self):
        """Test that log level changes are applied correctly."""
        set_logger(log_level="DEBUG", debug=True)
        logger = logging.getLogger()
        assert logger.level == logging.DEBUG

        set_logger(log_level="INFO", verbose=True)
        assert logger.level == logging.INFO

    def test_get_logger_returns_named_logger(self):
        """Test that get_logger returns a named logger."""
        logger = get_logger("test_module")
        assert logger.name == "test_module"

    def test_verbose_sets_info_level(self):
        """Test that verbose=True sets INFO level."""
        set_logger(verbose=True)
        logger = logging.getLogger()
        assert logger.level == logging.INFO

    def test_debug_sets_debug_level(self):
        """Test that debug=True sets DEBUG level."""
        set_logger(debug=True)
        logger = logging.getLogger()
        assert logger.level == logging.DEBUG

    def test_no_verbose_no_debug_sets_warning(self):
        """Test default level is WARNING when no flags set."""
        set_logger()
        logger = logging.getLogger()
        assert logger.level == logging.WARNING
