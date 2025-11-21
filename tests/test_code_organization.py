"""
Tests for Phase 5 Group D: Code Organization

Ensures inline imports are moved to module level where appropriate.
"""

# Standard library imports
import ast
import re
from pathlib import Path

# Third-party imports
import pytest


class TestModuleLevelImports:
    """Tests for proper module-level imports."""

    def test_core_base_has_os_at_module_level(self):
        """core/base.py should import os at module level."""
        file_path = Path("src/tracklistify/core/base.py")

        with open(file_path) as f:
            content = f.read()

        tree = ast.parse(content)

        # Check module-level imports (not inside functions)
        has_os_import = False
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "os":
                        has_os_import = True
                        break

        assert has_os_import, "core/base.py should import os at module level"

    def test_core_base_has_shutil_at_module_level(self):
        """core/base.py should import shutil at module level."""
        file_path = Path("src/tracklistify/core/base.py")

        with open(file_path) as f:
            content = f.read()

        tree = ast.parse(content)

        # Check module-level imports
        has_shutil_import = False
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "shutil":
                        has_shutil_import = True
                        break

        assert has_shutil_import, "core/base.py should import shutil at module level"

    def test_core_base_has_subprocess_at_module_level(self):
        """core/base.py should import subprocess at module level."""
        file_path = Path("src/tracklistify/core/base.py")

        with open(file_path) as f:
            content = f.read()

        tree = ast.parse(content)

        # Check module-level imports
        has_subprocess_import = False
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "subprocess":
                        has_subprocess_import = True
                        break

        assert has_subprocess_import, (
            "core/base.py should import subprocess at module level"
        )

    def test_core_base_has_mutagen_at_module_level(self):
        """core/base.py should import mutagen.File at module level."""
        file_path = Path("src/tracklistify/core/base.py")

        with open(file_path) as f:
            content = f.read()

        tree = ast.parse(content)

        # Check module-level imports (from imports)
        has_mutagen_import = False
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and "mutagen" in node.module:
                    has_mutagen_import = True
                    break

        assert has_mutagen_import, (
            "core/base.py should import File from mutagen at module level"
        )

    def test_cache_index_has_zlib_at_module_level(self):
        """cache/index.py should import zlib at module level."""
        file_path = Path("src/tracklistify/cache/index.py")

        with open(file_path) as f:
            content = f.read()

        tree = ast.parse(content)

        # Check module-level imports
        has_zlib_import = False
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "zlib":
                        has_zlib_import = True
                        break

        assert has_zlib_import, "cache/index.py should import zlib at module level"


class TestNoRedundantInlineImports:
    """Tests to ensure inline imports have been removed where appropriate."""

    def test_core_base_no_inline_os_import(self):
        """core/base.py should not have inline os import in split_audio."""
        file_path = Path("src/tracklistify/core/base.py")

        with open(file_path) as f:
            content = f.read()

        tree = ast.parse(content)

        # Find function definitions
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "split_audio":
                # Check for inline imports inside the function
                for child in ast.walk(node):
                    if isinstance(child, ast.Import):
                        for alias in child.names:
                            if alias.name == "os":
                                pytest.fail(
                                    "Found inline 'import os' in split_audio method"
                                )

    def test_core_base_no_inline_shutil_import_in_cleanup(self):
        """core/base.py should not have inline shutil import in cleanup."""
        file_path = Path("src/tracklistify/core/base.py")

        with open(file_path) as f:
            content = f.read()

        tree = ast.parse(content)

        # Find function definitions
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "cleanup":
                # Check for inline imports inside the function
                for child in ast.walk(node):
                    if isinstance(child, ast.Import):
                        for alias in child.names:
                            if alias.name == "shutil":
                                pytest.fail(
                                    "Found inline 'import shutil' in cleanup method"
                                )

    def test_cache_index_no_inline_zlib_import(self):
        """cache/index.py should not have inline zlib import."""
        file_path = Path("src/tracklistify/cache/index.py")

        with open(file_path) as f:
            content = f.read()

        tree = ast.parse(content)

        # Find function definitions and check for inline imports
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in ast.walk(node):
                    if isinstance(child, ast.Import):
                        for alias in child.names:
                            if alias.name == "zlib":
                                pytest.fail(
                                    f"Found inline 'import zlib' in {node.name}"
                                )
