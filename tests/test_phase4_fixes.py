"""
Tests for Phase 4 additional issues.

Issue #13: Hash collision risk in memoize decorator
"""

# Standard library imports
import ast
from pathlib import Path

# Third-party imports
import pytest


class TestMemoizeHashStability:
    """Tests for Issue #13: Hash collision risk."""

    def test_memoize_uses_stable_hash(self):
        """Ensure memoize decorator uses stable hash, not built-in hash()."""
        decorators_file = Path("src/tracklistify/utils/decorators.py")

        with open(decorators_file) as f:
            content = f.read()

        # The key generation should NOT use Python's built-in hash()
        # because it's not stable across runs and has collision risk
        tree = ast.parse(content)

        # Find the key generation line
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "key":
                        # Check if it uses built-in hash() function directly
                        source_segment = ast.get_source_segment(content, node)
                        if source_segment:
                            # Match the built-in hash() function call: "hash("
                            # not preceded by an underscore or letter (so we
                            # skip "_hash(" / "stable_hash(" / similar names).
                            import re

                            builtin_hash_pattern = r"(?<![_a-zA-Z])hash\("
                            if re.search(builtin_hash_pattern, source_segment):
                                pytest.fail(
                                    "Memoize key uses unstable built-in "
                                    f"hash(): {source_segment}"
                                )

    def test_memoize_hash_is_deterministic(self):
        """Ensure memoize produces same key for same inputs."""
        from tracklistify.utils.decorators import memoize

        @memoize()
        def test_func(a, b):
            return a + b

        # Call multiple times with same args
        test_func(1, 2)
        test_func(1, 2)

        # If hash is stable, cache should have exactly one entry for these args
        stats = test_func.get_stats()
        assert stats["hits"] >= 1, "Cache should be hit on second call"

    def test_different_args_produce_different_keys(self):
        """Ensure different arguments produce different cache keys."""
        from tracklistify.utils.decorators import memoize

        call_count = 0

        @memoize()
        def counting_func(a, b):
            nonlocal call_count
            call_count += 1
            return a + b

        # Call with different args
        counting_func(1, 2)
        counting_func(2, 3)
        counting_func(3, 4)

        # Each call should compute (no cache hits)
        assert call_count == 3, "Each unique arg combination should compute"


class TestHashlibUsage:
    """Test hashlib is used for stable hashing."""

    def test_decorators_imports_hashlib(self):
        """Ensure decorators.py imports hashlib for stable hashing."""
        decorators_file = Path("src/tracklistify/utils/decorators.py")

        with open(decorators_file) as f:
            content = f.read()

        tree = ast.parse(content)

        # Check for hashlib import
        has_hashlib_import = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "hashlib":
                        has_hashlib_import = True
            elif isinstance(node, ast.ImportFrom):
                if node.module == "hashlib":
                    has_hashlib_import = True

        assert has_hashlib_import, (
            "decorators.py should import hashlib for stable hashing"
        )

    def test_memoize_key_generation_uses_hashlib(self):
        """Verify memoize uses hashlib for key generation."""
        decorators_file = Path("src/tracklistify/utils/decorators.py")

        with open(decorators_file) as f:
            content = f.read()

        # Should use hashlib.sha256 or similar
        assert "hashlib" in content and ("sha256" in content or "md5" in content), (
            "Memoize should use hashlib.sha256 or md5 for stable key generation"
        )
