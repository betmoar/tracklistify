"""
Tests for Phase 5 Group C: Type Hints

Ensures the codebase uses:
- Uppercase Any from typing (not lowercase any)
- Consistent return type annotations
"""

# Standard library imports
import ast
import re
from pathlib import Path

# Third-party imports
import pytest


class TestAnyTypeUsage:
    """Tests for proper Any type usage."""

    def test_cache_index_uses_uppercase_any(self):
        """Cache index should use typing.Any, not lowercase any."""
        file_path = Path("src/tracklistify/cache/index.py")

        with open(file_path) as f:
            content = f.read()

        # Check imports include Any
        assert "from typing import" in content and "Any" in content, (
            "cache/index.py should import Any from typing"
        )

        # Check no lowercase any in type hints
        # Pattern matches ": any" or "any]" in type annotations
        lowercase_any_pattern = r"Dict\[str,\s*any\]|List\[any\]|: any\s*[,\)]"
        matches = re.findall(lowercase_any_pattern, content)
        assert not matches, f"Found lowercase 'any' in type hints: {matches}"

    def test_cache_storage_uses_uppercase_any(self):
        """Cache storage should use typing.Any, not lowercase any."""
        file_path = Path("src/tracklistify/cache/storage.py")

        with open(file_path) as f:
            content = f.read()

        # Check imports include Any
        assert "from typing import" in content and "Any" in content, (
            "cache/storage.py should import Any from typing"
        )

        # Check no lowercase any in type hints
        lowercase_any_pattern = r"Dict\[str,\s*any\]"
        matches = re.findall(lowercase_any_pattern, content)
        assert not matches, f"Found lowercase 'any' in type hints: {matches}"


class TestReturnTypeAnnotations:
    """Tests for consistent return type annotations."""

    def test_close_methods_have_return_type(self):
        """All close() methods should have -> None return type."""
        files_to_check = [
            "src/tracklistify/providers/base.py",
            "src/tracklistify/providers/shazam.py",
            "src/tracklistify/providers/factory.py",
            "src/tracklistify/core/base.py",
            "src/tracklistify/downloaders/spotify.py",
        ]

        for file_path in files_to_check:
            path = Path(file_path)
            if not path.exists():
                continue

            with open(path) as f:
                content = f.read()

            # Find close methods without return type
            # Pattern: "async def close(self):" without "-> None"
            close_without_return = re.findall(
                r"async def close\(self\):\s*$", content, re.MULTILINE
            )
            assert not close_without_return, (
                f"{file_path}: close() method missing return type annotation"
            )

    def test_cleanup_methods_have_return_type(self):
        """All cleanup() methods should have -> None return type."""
        file_path = Path("src/tracklistify/core/base.py")

        with open(file_path) as f:
            content = f.read()

        # Check cleanup has return type
        cleanup_pattern = r"async def cleanup\(self\)\s*->\s*None:"
        assert re.search(cleanup_pattern, content), (
            "core/base.py: cleanup() should have -> None return type"
        )

    def test_factory_methods_have_return_types(self):
        """Factory clear methods should have -> None return type."""
        file_path = Path("src/tracklistify/providers/factory.py")

        with open(file_path) as f:
            content = f.read()

        # Check clear_provider_cache has return type
        assert "def clear_provider_cache() -> None:" in content, (
            "clear_provider_cache() should have -> None return type"
        )

        # Check clear_cache has return type
        assert "def clear_cache(self) -> None:" in content, (
            "ProviderFactory.clear_cache() should have -> None return type"
        )


class TestTypingImports:
    """Tests for proper typing module imports."""

    def test_cache_index_imports_any(self):
        """cache/index.py should import Any from typing."""
        file_path = Path("src/tracklistify/cache/index.py")

        with open(file_path) as f:
            content = f.read()

        tree = ast.parse(content)

        has_any_import = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "typing":
                for alias in node.names:
                    if alias.name == "Any":
                        has_any_import = True
                        break

        assert has_any_import, "cache/index.py should import Any from typing"

    def test_cache_storage_imports_any(self):
        """cache/storage.py should import Any from typing."""
        file_path = Path("src/tracklistify/cache/storage.py")

        with open(file_path) as f:
            content = f.read()

        tree = ast.parse(content)

        has_any_import = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "typing":
                for alias in node.names:
                    if alias.name == "Any":
                        has_any_import = True
                        break

        assert has_any_import, "cache/storage.py should import Any from typing"
