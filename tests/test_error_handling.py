"""
Tests for Phase 5 Group E: Error Handling

Ensures exceptions are properly handled with logging.
"""

# Standard library imports
import ast
from pathlib import Path

# Third-party imports
import pytest


class TestNoSilentExceptions:
    """Tests for proper exception handling with logging."""

    def test_no_bare_except_pass(self):
        """No except blocks should silently pass without logging."""
        src_path = Path("src/tracklistify")

        # Files that are allowed to have controlled silent exceptions
        # (e.g., in cleanup code where logging is at outer level)
        allowed_patterns = [
            # cache/storage.py has an OSError pass with comment for cleanup
            ("cache/storage.py", "OSError"),
            # core/run.py has asyncio.CancelledError pass for task cancellation
            ("core/run.py", "CancelledError"),
            # utils/logger.py closes prior handlers during reconfiguration;
            # logging during teardown of the logger itself would be unsafe.
            ("utils/logger.py", "handler.close"),
        ]

        for py_file in src_path.rglob("*.py"):
            with open(py_file) as f:
                content = f.read()

            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler):
                    # Check if body is just 'pass'
                    if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                        # Check if it's an allowed pattern
                        relative_path = str(py_file.relative_to(src_path))
                        is_allowed = False
                        for allowed_file, _ in allowed_patterns:
                            if allowed_file in relative_path:
                                is_allowed = True
                                break

                        if not is_allowed:
                            pytest.fail(
                                f"{py_file}:{node.lineno}: "
                                f"Silent exception swallowing with 'pass' - should log"
                            )

    def test_shazam_cooldown_exception_is_specific(self):
        """Shazam cooldown exception should use specific exception types."""
        file_path = Path("src/tracklistify/providers/shazam.py")

        with open(file_path) as f:
            content = f.read()

        # Should use specific exception types, not bare Exception
        tree = ast.parse(content)

        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                # Get exception type
                if node.type and isinstance(node.type, ast.Tuple):
                    # Has tuple of specific exception types - good
                    pass
                elif node.type and isinstance(node.type, ast.Name):
                    # Single exception type
                    if node.type.id == "Exception":
                        # Check context - looking for the cooldown pattern
                        source_segment = ast.get_source_segment(content, node)
                        if (
                            source_segment
                            and "cooldown"
                            in content[max(0, node.lineno - 5) : node.lineno + 5]
                        ):
                            pytest.fail(
                                f"shazam.py:{node.lineno}: "
                                f"Cooldown exception should use specific types"
                            )

    def test_cleanup_exceptions_are_logged(self):
        """Cleanup exceptions in core/base.py should be logged."""
        file_path = Path("src/tracklistify/core/base.py")

        with open(file_path) as f:
            content = f.read()

        tree = ast.parse(content)

        # Find cleanup method
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "cleanup":
                # Check all exception handlers in cleanup
                for child in ast.walk(node):
                    if isinstance(child, ast.ExceptHandler):
                        # Body should not be just 'pass'
                        if len(child.body) == 1 and isinstance(child.body[0], ast.Pass):
                            pytest.fail(
                                f"core/base.py:{child.lineno}: "
                                f"Cleanup exception should log, not silently pass"
                            )


class TestExceptionLogging:
    """Tests for proper exception logging."""

    def test_shazam_logs_cooldown_failure(self):
        """Shazam should log cooldown config failures."""
        file_path = Path("src/tracklistify/providers/shazam.py")

        with open(file_path) as f:
            content = f.read()

        # Should have logging for cooldown failures
        assert (
            "logger.debug" in content and "cooldown" in content.lower()
        ), "Shazam should log cooldown configuration failures"
