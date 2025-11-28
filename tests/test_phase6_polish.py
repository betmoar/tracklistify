"""
Tests for Phase 6: Low Priority Polish

Ensures code style, constants, and documentation improvements.
"""

# Standard library imports
from pathlib import Path


class TestConstantsModule:
    """Tests for the centralized constants module."""

    def test_constants_module_exists(self):
        """Constants module should exist."""
        constants_path = Path("src/tracklistify/utils/constants.py")
        assert constants_path.exists(), "utils/constants.py should exist"

    def test_time_constants_defined(self):
        """Time constants should be defined."""
        from tracklistify.utils.constants import (
            MILLISECONDS_PER_SECOND,
            SECONDS_PER_HOUR,
            SECONDS_PER_MINUTE,
        )

        assert SECONDS_PER_HOUR == 3600
        assert SECONDS_PER_MINUTE == 60
        assert MILLISECONDS_PER_SECOND == 1000

    def test_cache_constants_defined(self):
        """Cache constants should be defined."""
        from tracklistify.utils.constants import (
            DEFAULT_CACHE_MAX_SIZE,
            DEFAULT_CACHE_TTL,
        )

        assert DEFAULT_CACHE_TTL == 3600
        assert DEFAULT_CACHE_MAX_SIZE == 1_000_000

    def test_rate_limiter_constants_defined(self):
        """Rate limiter constants should be defined."""
        from tracklistify.utils.constants import (
            ACRCLOUD_DEFAULT_RPM,
            CIRCUIT_BREAKER_FAILURE_THRESHOLD,
            SHAZAM_DEFAULT_RPM,
            SPOTIFY_DEFAULT_RPM,
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


class TestDRYRefactoring:
    """Tests for DRY refactoring improvements."""

    def test_platform_domains_defined(self):
        """Platform domain constants should be defined."""
        from tracklistify.utils.validation import (
            MIXCLOUD_DOMAINS,
            SOUNDCLOUD_DOMAINS,
            YOUTUBE_DOMAINS,
        )

        assert "youtube.com" in YOUTUBE_DOMAINS
        assert "youtu.be" in YOUTUBE_DOMAINS
        assert "soundcloud.com" in SOUNDCLOUD_DOMAINS
        assert "mixcloud.com" in MIXCLOUD_DOMAINS

    def test_platform_helper_exists(self):
        """DRY helper function _is_platform_url should exist."""
        file_path = Path("src/tracklistify/utils/validation.py")

        with open(file_path) as f:
            content = f.read()

        assert "def _is_platform_url" in content, (
            "DRY helper function should exist"
        )

    def test_url_validators_use_helper(self):
        """URL validation functions should use the DRY helper."""
        file_path = Path("src/tracklistify/utils/validation.py")

        with open(file_path) as f:
            content = f.read()

        # Check that validators delegate to helper
        assert "_is_platform_url(url, YOUTUBE_DOMAINS)" in content
        assert "_is_platform_url(url, SOUNDCLOUD_DOMAINS)" in content
        assert "_is_platform_url(url, MIXCLOUD_DOMAINS)" in content

    def test_youtube_url_validation_works(self):
        """YouTube URL validation should still work after refactoring."""
        from tracklistify.utils.validation import is_youtube_url

        assert is_youtube_url("https://youtube.com/watch?v=test") is True
        assert is_youtube_url("https://www.youtube.com/watch?v=test") is True
        assert is_youtube_url("https://youtu.be/test") is True
        assert is_youtube_url("https://soundcloud.com/test") is False
        assert is_youtube_url("") is False

        # Reject embedded hosts and attackers that fake hosts in path/query
        assert is_youtube_url("https://youtube.com.evil.com") is False
        assert is_youtube_url("https://www.youtube.com.evil.com") is False
        assert is_youtube_url("https://evil.com?redirect=https://youtube.com") is False
        assert is_youtube_url("http://notyoutube.com") is False
        # Accept valid subdomain
        assert is_youtube_url("https://m.youtube.com/watch?v=test") is True

    def test_soundcloud_url_validation_works(self):
        """SoundCloud URL validation should still work after refactoring."""
        from tracklistify.utils.validation import is_soundcloud_url

        assert is_soundcloud_url("https://soundcloud.com/user/track") is True
        assert is_soundcloud_url("https://www.soundcloud.com/user") is True
        assert is_soundcloud_url("https://youtube.com/watch?v=test") is False

    def test_mixcloud_url_validation_works(self):
        """Mixcloud URL validation should still work after refactoring."""
        from tracklistify.utils.validation import is_mixcloud_url

        assert is_mixcloud_url("https://mixcloud.com/user/mix") is True
        assert is_mixcloud_url("https://www.mixcloud.com/user") is True
        assert is_mixcloud_url("https://youtube.com/watch?v=test") is False
