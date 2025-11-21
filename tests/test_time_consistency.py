"""
Tests for Phase 5 Group A: Time Handling Consistency

Ensures the codebase uses:
- time.monotonic() for elapsed time calculations (TTL, timeouts)
- time.time() only for absolute timestamps (created, last_accessed)
"""

# Standard library imports
import ast
import re
from pathlib import Path

# Third-party imports
import pytest


class TestTimeHandlingConsistency:
    """Tests for consistent time handling."""

    def test_decorators_uses_monotonic_for_elapsed(self):
        """Decorators should use monotonic time for computation timing."""
        file_path = Path("src/tracklistify/utils/decorators.py")

        with open(file_path) as f:
            content = f.read()

        # For elapsed time measurement, should use monotonic
        # Look for timing patterns that should use monotonic
        if "start_time = time.time()" in content:
            # Check if it's for elapsed time calculation
            if "time.time() - start_time" in content:
                pytest.fail(
                    "decorators.py uses time.time() for elapsed time - should use time.monotonic()"
                )

    def test_identification_uses_monotonic_for_elapsed(self):
        """Identification manager should use monotonic time for elapsed tracking."""
        file_path = Path("src/tracklistify/utils/identification.py")

        with open(file_path) as f:
            content = f.read()

        # Check for elapsed time patterns using time.time()
        elapsed_pattern = r"time\.time\(\)\s*-\s*self\.start_time"
        if re.search(elapsed_pattern, content):
            pytest.fail(
                "identification.py uses time.time() for elapsed time - should use time.monotonic()"
            )

    def test_invalidation_uses_consistent_timestamps(self):
        """Cache invalidation uses time.time() for persisted timestamps.

        Note: Cache timestamps are persisted to disk and must survive restarts,
        so using time.time() (absolute time) is correct for cache storage.
        The timestamps are compared with other time.time() values, so the
        elapsed time calculation is consistent.
        """
        file_path = Path("src/tracklistify/cache/invalidation.py")

        with open(file_path) as f:
            content = f.read()

        # Verify time.time() is used (correct for persisted timestamps)
        assert "time.time()" in content, (
            "Cache invalidation should use time.time() for persisted timestamps"
        )

    def test_rate_limiter_uses_monotonic(self):
        """Rate limiter should consistently use monotonic time."""
        file_path = Path("src/tracklistify/utils/rate_limiter.py")

        with open(file_path) as f:
            content = f.read()

        # Rate limiter should NOT use time.time() for elapsed calculations
        # Only check outside of comments
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            # Skip comments
            if line.strip().startswith("#"):
                continue

            # Check for time.time() usage (should only be monotonic)
            if "time.time()" in line:
                pytest.fail(
                    f"rate_limiter.py line {i} uses time.time() - should use time.monotonic()"
                )

    def test_cache_base_uses_time_for_timestamps(self):
        """Cache base should use time.time() for absolute timestamps."""
        file_path = Path("src/tracklistify/cache/base.py")

        with open(file_path) as f:
            content = f.read()

        # "created" and "last_accessed" timestamps should use time.time() (absolute)
        # This is CORRECT - we're testing that it stays this way
        assert '"created": time.time()' in content or "'created': time.time()" in content

    def test_cache_index_uses_time_for_timestamps(self):
        """Cache index should use time.time() for absolute timestamps."""
        file_path = Path("src/tracklistify/cache/index.py")

        with open(file_path) as f:
            content = f.read()

        # Timestamps should use time.time() (absolute)
        # This is CORRECT - we're testing that it stays this way
        assert "time.time()" in content, "Cache index should store absolute timestamps"


class TestMonotonicTimeImports:
    """Verify files that need monotonic time import it correctly."""

    def test_decorators_imports_time(self):
        """Decorators should import time module."""
        file_path = Path("src/tracklistify/utils/decorators.py")

        with open(file_path) as f:
            content = f.read()

        assert "import time" in content, "decorators.py should import time module"

    def test_identification_imports_time(self):
        """Identification should import time module."""
        file_path = Path("src/tracklistify/utils/identification.py")

        with open(file_path) as f:
            content = f.read()

        assert "import time" in content, "identification.py should import time module"
