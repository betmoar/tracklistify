"""
Tests for Phase 5 Group F: Input Validation

Ensures proper input validation and safe data access.
"""

# Standard library imports
import ast
import re
from pathlib import Path

# Third-party imports
import pytest


class TestSafeArrayAccess:
    """Tests for safe array/list access patterns."""

    def test_identification_uses_safe_array_access(self):
        """identification.py should safely access arrays with length checks."""
        file_path = Path("src/tracklistify/utils/identification.py")

        with open(file_path) as f:
            content = f.read()

        # Should not have unsafe [0] access on potentially empty lists
        # Look for patterns like: .get("music", [])[0] without length check
        unsafe_pattern = r'\.get\([^)]+,\s*\[\]\)\[0\]'
        matches = re.findall(unsafe_pattern, content)

        # Filter out false positives (the old pattern was removed)
        assert not matches, (
            f"Found unsafe array access patterns: {matches}. "
            f"Use length checks before accessing [0]"
        )

    def test_identification_checks_artists_list(self):
        """identification.py should check artists list before accessing."""
        file_path = Path("src/tracklistify/utils/identification.py")

        with open(file_path) as f:
            content = f.read()

        # Should have artists_list variable with safe access
        assert "artists_list = metadata.get" in content, (
            "Should extract artists_list safely"
        )
        assert "if artists_list" in content or "artists_list else" in content, (
            "Should check if artists_list is non-empty before access"
        )


class TestProgressValidation:
    """Tests for numeric range validation."""

    def test_progress_bar_clamps_value(self):
        """create_progress_bar should clamp progress to valid range."""
        file_path = Path("src/tracklistify/utils/identification.py")

        with open(file_path) as f:
            content = f.read()

        # Should clamp progress value
        assert "max(0.0, min(1.0, progress))" in content or \
               "progress = max(0.0" in content, (
            "Progress bar should clamp progress to 0.0-1.0 range"
        )

    def test_progress_bar_handles_edge_cases(self):
        """create_progress_bar should handle edge cases correctly."""
        from tracklistify.utils.identification import create_progress_bar

        # Test with out-of-range values
        bar_negative = create_progress_bar(-0.5, 10)
        bar_over = create_progress_bar(1.5, 10)
        bar_zero = create_progress_bar(0.0, 10)
        bar_one = create_progress_bar(1.0, 10)

        # All bars should have the correct format
        assert bar_negative.startswith("[")
        assert bar_negative.endswith("]")
        assert bar_over.startswith("[")
        assert bar_over.endswith("]")

        # Edge cases should be handled
        assert "█" not in bar_negative or bar_negative == bar_zero  # -0.5 should be clamped to 0
        assert "░" not in bar_over or bar_over == bar_one  # 1.5 should be clamped to 1


class TestMetadataAccess:
    """Tests for safe metadata access patterns."""

    def test_identification_validates_music_list(self):
        """identification.py should validate music list before access."""
        file_path = Path("src/tracklistify/utils/identification.py")

        with open(file_path) as f:
            content = f.read()

        # Should check if music_list is empty
        assert "music_list" in content, "Should use music_list variable"
        assert "if not music_list" in content, (
            "Should check if music_list is empty"
        )
