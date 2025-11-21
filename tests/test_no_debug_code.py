"""
Tests for Issue #7: Remove Test/Mock Code from Production

Ensures no debug/test/mock code exists in production source files.
"""

# Standard library imports
from pathlib import Path

# Third-party imports
import pytest


class TestNoDebugCode:
    """Ensure no debug/test/mock code in production."""

    def test_no_print_statements_in_core_track(self):
        """Ensure no print() statements in core/track.py."""
        track_file = Path("src/tracklistify/core/track.py")

        with open(track_file) as f:
            content = f.read()
            lines = content.split("\n")

            for i, line in enumerate(lines, 1):
                # Skip comments
                if line.strip().startswith("#"):
                    continue
                if "print(" in line:
                    pytest.fail(
                        f"print() statement found in core/track.py:{i}\n{line}"
                    )

    def test_no_some_method_debug_function(self):
        """Ensure no debug 'some_method' function exists."""
        track_file = Path("src/tracklistify/core/track.py")

        with open(track_file) as f:
            content = f.read()

            if "def some_method(self):" in content:
                pytest.fail(
                    "Debug method 'some_method' found in core/track.py - should be removed"
                )

    def test_no_mock_classes_in_cache(self):
        """Ensure no Mock classes in cache/base.py."""
        cache_file = Path("src/tracklistify/cache/base.py")

        with open(cache_file) as f:
            content = f.read()

            if "class MockConfig" in content:
                pytest.fail(
                    "MockConfig class found in cache/base.py - should use real config"
                )

    def test_no_test_specific_conditions_in_track(self):
        """Ensure no test-specific if conditions in core/track.py."""
        track_file = Path("src/tracklistify/core/track.py")

        with open(track_file) as f:
            content = f.read()

            test_patterns = [
                'if audio_file.name == "test_mix.mp3"',
                'if file_path == "test',
                'if filename == "test',
            ]

            for pattern in test_patterns:
                if pattern in content:
                    pytest.fail(
                        f"Test-specific condition found in core/track.py: {pattern}"
                    )

    def test_no_mock_data_in_production(self):
        """Ensure no hardcoded test data in production."""
        track_file = Path("src/tracklistify/core/track.py")

        with open(track_file) as f:
            content = f.read()

            # Check for obvious test data
            test_data_patterns = [
                '"Test Track 1"',
                '"Test Artist 1"',
                '"Test Track 2"',
                '"Test Artist 2"',
            ]

            for pattern in test_data_patterns:
                if pattern in content:
                    pytest.fail(
                        f"Test data found in core/track.py: {pattern}"
                    )


class TestProductionCodeQuality:
    """Test production code quality standards."""

    def test_cache_uses_real_config(self):
        """Ensure cache uses real configuration, not mocks."""
        cache_file = Path("src/tracklistify/cache/base.py")

        with open(cache_file) as f:
            content = f.read()

            # Should import get_config
            assert "from tracklistify.config" in content or "get_config" in content, (
                "cache/base.py should use real config from get_config()"
            )

    def test_track_matcher_no_not_implemented(self):
        """Ensure identify_tracks doesn't have NotImplementedError."""
        track_file = Path("src/tracklistify/core/track.py")

        with open(track_file) as f:
            content = f.read()

            # Check for NotImplementedError in identify_tracks method
            if "def identify_tracks" in content and "NotImplementedError" in content:
                # More specific check - ensure it's not in identify_tracks
                lines = content.split("\n")
                in_identify_tracks = False
                for line in lines:
                    if "def identify_tracks" in line:
                        in_identify_tracks = True
                    elif in_identify_tracks and line.strip().startswith("def "):
                        in_identify_tracks = False
                    elif in_identify_tracks and "NotImplementedError" in line:
                        pytest.fail(
                            "NotImplementedError found in identify_tracks method"
                        )
