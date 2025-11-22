"""
Tests for Phase 6: Low Priority Polish

Ensures code style, constants, and documentation improvements.
"""

# Standard library imports
import ast
import re
from pathlib import Path

# Third-party imports
import pytest


class TestConstantsModule:
    """Tests for the centralized constants module."""

    def test_constants_module_exists(self):
        """Constants module should exist."""
        constants_path = Path("src/tracklistify/utils/constants.py")
        assert constants_path.exists(), "utils/constants.py should exist"

    def test_time_constants_defined(self):
        """Time constants should be defined."""
        from tracklistify.utils.constants import (
            SECONDS_PER_HOUR,
            SECONDS_PER_MINUTE,
            MILLISECONDS_PER_SECOND,
        )

        assert SECONDS_PER_HOUR == 3600
        assert SECONDS_PER_MINUTE == 60
        assert MILLISECONDS_PER_SECOND == 1000

    def test_cache_constants_defined(self):
        """Cache constants should be defined."""
        from tracklistify.utils.constants import (
            DEFAULT_CACHE_TTL,
            DEFAULT_CACHE_MAX_SIZE,
        )

        assert DEFAULT_CACHE_TTL == 3600
        assert DEFAULT_CACHE_MAX_SIZE == 1_000_000

    def test_rate_limiter_constants_defined(self):
        """Rate limiter constants should be defined."""
        from tracklistify.utils.constants import (
            SHAZAM_DEFAULT_RPM,
            ACRCLOUD_DEFAULT_RPM,
            SPOTIFY_DEFAULT_RPM,
            CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        )

        assert SHAZAM_DEFAULT_RPM == 25
        assert ACRCLOUD_DEFAULT_RPM == 30
        assert SPOTIFY_DEFAULT_RPM == 120
        assert CIRCUIT_BREAKER_FAILURE_THRESHOLD == 5

    def test_hash_constants_defined(self):
        """Hash constants should be defined."""
        from tracklistify.utils.constants import STABLE_HASH_LENGTH

        assert STABLE_HASH_LENGTH == 16


class TestConstantsUsage:
    """Tests that constants are used in the codebase."""

    def test_time_formatter_uses_constants(self):
        """time_formatter.py should use time constants."""
        file_path = Path("src/tracklistify/utils/time_formatter.py")

        with open(file_path) as f:
            content = f.read()

        assert "SECONDS_PER_HOUR" in content, (
            "time_formatter should use SECONDS_PER_HOUR constant"
        )
        assert "SECONDS_PER_MINUTE" in content, (
            "time_formatter should use SECONDS_PER_MINUTE constant"
        )

    def test_decorators_uses_constants(self):
        """decorators.py should use hash and time constants."""
        file_path = Path("src/tracklistify/utils/decorators.py")

        with open(file_path) as f:
            content = f.read()

        assert "STABLE_HASH_LENGTH" in content, (
            "decorators should use STABLE_HASH_LENGTH constant"
        )
        assert "MILLISECONDS_PER_SECOND" in content, (
            "decorators should use MILLISECONDS_PER_SECOND constant"
        )


class TestNoCommentedCode:
    """Tests for removal of commented-out code."""

    def test_cache_init_no_commented_class(self):
        """cache/__init__.py should not have commented-out Cache class."""
        file_path = Path("src/tracklistify/cache/__init__.py")

        with open(file_path) as f:
            content = f.read()

        # Should not have large block of commented code
        assert "# class Cache:" not in content, (
            "Commented-out Cache class should be removed"
        )
        assert "#     def get(self, key: str)" not in content, (
            "Commented-out methods should be removed"
        )


class TestNoRedundantComments:
    """Tests for removal of redundant comments."""

    def test_no_path_comments(self):
        """Files should not have redundant path comments at top."""
        file_path = Path("src/tracklistify/utils/time_formatter.py")

        with open(file_path) as f:
            first_line = f.readline()

        # Should not start with path comment
        assert not first_line.startswith("# tracklistify/"), (
            "Redundant path comment should be removed"
        )


class TestTimeFormatterFunctionality:
    """Test that time_formatter still works after refactoring."""

    def test_format_seconds_to_hhmmss_basic(self):
        """Basic time formatting should work."""
        from tracklistify.utils.time_formatter import format_seconds_to_hhmmss

        assert format_seconds_to_hhmmss(0) == "00:00:00"
        assert format_seconds_to_hhmmss(61) == "00:01:01"
        assert format_seconds_to_hhmmss(3661) == "01:01:01"
        assert format_seconds_to_hhmmss(7200) == "02:00:00"

    def test_format_seconds_handles_float(self):
        """Time formatting should handle float input."""
        from tracklistify.utils.time_formatter import format_seconds_to_hhmmss

        assert format_seconds_to_hhmmss(90.5) == "00:01:30"
        assert format_seconds_to_hhmmss(3661.9) == "01:01:01"
