"""
Tests for Issue #8: Fix Logger Handler Duplication

Validates that set_logger() doesn't duplicate handlers on multiple calls.
"""

# Standard library imports
import logging
import re

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

    def test_console_format_includes_timestamp(self):
        """Console output must start with HH:MM:SS so users can correlate
        log lines. Pins the format so future edits can't silently strip
        the asctime placeholder again (the original console format had a
        ``datefmt`` configured but no ``%(asctime)s`` token consuming it)."""
        set_logger(log_level="INFO")
        console = next(
            h
            for h in logging.getLogger().handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
        )
        record = logging.LogRecord(
            name="t",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="hello",
            args=(),
            exc_info=None,
        )
        rendered = console.formatter.format(record)
        assert re.match(r"^\d{2}:\d{2}:\d{2} ", rendered), rendered

    def test_set_logger_clears_existing_handlers(self):
        """Test that set_logger clears existing handlers."""
        # First call
        set_logger(log_level="INFO")
        logger = logging.getLogger()
        handler_count_1 = len(logger.handlers)

        # Second call should not add more handlers
        set_logger(log_level="DEBUG")
        handler_count_2 = len(logger.handlers)

        assert (
            handler_count_1 == handler_count_2
        ), f"Handlers duplicated: {handler_count_1} vs {handler_count_2}"

    def test_multiple_calls_dont_duplicate_handlers(self):
        """Test that multiple set_logger calls don't duplicate handlers."""
        # Call set_logger multiple times
        for _ in range(5):
            set_logger(log_level="INFO")

        logger = logging.getLogger()

        # Should only have 1 console handler
        assert (
            len(logger.handlers) == 1
        ), f"Expected 1 handler, got {len(logger.handlers)}"

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

    def test_default_level_honors_log_level_param(self):
        """When neither verbose nor debug is set, the log_level parameter
        (default 'INFO') determines the effective level. Previous behaviour
        silently dropped log_level and used WARNING; the new contract
        respects the documented default."""
        set_logger()
        logger = logging.getLogger()
        assert logger.level == logging.INFO


class TestSetLoggerLogLevelParameter:
    """Regression: --log-level must be honored when --debug/--verbose absent."""

    def test_log_level_debug_is_applied_without_debug_flag(self):
        """set_logger(log_level='DEBUG') must produce DEBUG effective level."""
        set_logger(log_level="DEBUG")
        assert logging.getLogger().level == logging.DEBUG

    def test_log_level_info_is_applied(self):
        set_logger(log_level="INFO")
        assert logging.getLogger().level == logging.INFO

    def test_log_level_error_is_applied(self):
        set_logger(log_level="ERROR")
        assert logging.getLogger().level == logging.ERROR

    def test_log_level_critical_is_applied(self):
        set_logger(log_level="CRITICAL")
        assert logging.getLogger().level == logging.CRITICAL

    def test_debug_flag_overrides_log_level(self):
        """debug=True must win over log_level='ERROR'."""
        set_logger(log_level="ERROR", debug=True)
        assert logging.getLogger().level == logging.DEBUG

    def test_verbose_flag_overrides_log_level(self):
        """verbose=True must win over log_level='ERROR'."""
        set_logger(log_level="ERROR", verbose=True)
        assert logging.getLogger().level == logging.INFO

    def test_invalid_log_level_falls_back_to_warning(self):
        """Unknown string for log_level falls back to WARNING (prior default)."""
        set_logger(log_level="NOT_A_LEVEL")
        assert logging.getLogger().level == logging.WARNING

    def test_log_level_case_insensitive(self):
        """log_level='debug' (lowercase) is accepted."""
        set_logger(log_level="debug")
        assert logging.getLogger().level == logging.DEBUG


class TestThirdPartyLoggerSuppression:
    """Cap noisy third-party loggers so they don't drown user output."""

    def test_set_logger_caps_symphonia_loggers(self):
        """symphonia (shazamio's Rust decoder) emits a WARNING for every
        non-MP3 byte under --stream-copy. Cap them at ERROR."""
        set_logger(log_level="INFO")
        assert logging.getLogger("symphonia_bundle_mp3").level == logging.ERROR
        assert logging.getLogger("symphonia_core").level == logging.ERROR

    def test_third_party_cap_survives_debug_mode(self):
        """Even with --debug the cap holds — the scanning-noise WARNINGs
        from symphonia don't help anyone diagnose anything."""
        set_logger(debug=True)
        assert logging.getLogger("symphonia_bundle_mp3").level == logging.ERROR
        assert logging.getLogger("symphonia_core").level == logging.ERROR
