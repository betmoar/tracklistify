"""
Tests for Issue #6: Consolidate Exception Definitions

Validates that exception classes are defined only in core/exceptions.py
and that isinstance() checks work across modules.
"""

# Standard library imports
import importlib
import inspect
from pathlib import Path

# Third-party imports
import pytest


class TestExceptionConsolidation:
    """Test that exceptions are defined only in core/exceptions.py."""

    def test_no_duplicate_exception_definitions_in_providers(self):
        """Ensure no exception classes defined in providers/base.py."""
        from tracklistify.providers import base as providers_base

        # Check that ProviderError, AuthenticationError, etc. are imported, not defined
        for name in ["ProviderError", "AuthenticationError", "RateLimitError"]:
            if hasattr(providers_base, name):
                obj = getattr(providers_base, name)
                if inspect.isclass(obj) and issubclass(obj, Exception):
                    # Should be imported from core.exceptions, not defined here
                    assert obj.__module__ == "tracklistify.core.exceptions", (
                        f"{name} should be imported from core.exceptions, "
                        f"not defined in {obj.__module__}"
                    )

    def test_no_duplicate_exception_definitions_in_core_base(self):
        """Ensure no exception classes defined in core/base.py."""
        from tracklistify.core import base as core_base

        # These should be imported, not defined
        for name in ["ApplicationError", "TrackIdentificationError"]:
            if hasattr(core_base, name):
                obj = getattr(core_base, name)
                if inspect.isclass(obj) and issubclass(obj, Exception):
                    assert obj.__module__ == "tracklistify.core.exceptions", (
                        f"{name} should be imported from core.exceptions, "
                        f"not defined in {obj.__module__}"
                    )

    def test_no_duplicate_config_error_in_factory(self):
        """Ensure ConfigError is not defined in config/factory.py."""
        from tracklistify.config import factory as config_factory

        if hasattr(config_factory, "ConfigError"):
            obj = getattr(config_factory, "ConfigError")
            if inspect.isclass(obj) and issubclass(obj, Exception):
                assert obj.__module__ == "tracklistify.core.exceptions", (
                    f"ConfigError should be imported from core.exceptions, "
                    f"not defined in {obj.__module__}"
                )

    def test_isinstance_works_for_provider_error(self):
        """Test that isinstance() works for ProviderError across modules."""
        from tracklistify.core.exceptions import ProviderError

        # Create a ProviderError
        error = ProviderError("Test error", provider="shazam")

        # isinstance should work
        assert isinstance(error, ProviderError)
        assert isinstance(error, Exception)

    def test_isinstance_works_for_application_error(self):
        """Test that isinstance() works for ApplicationError across modules."""
        from tracklistify.core.exceptions import ApplicationError

        error = ApplicationError("Test error")

        assert isinstance(error, ApplicationError)
        assert isinstance(error, Exception)

    def test_exception_hierarchy_complete(self):
        """Test that all exceptions inherit from TracklistifyError or ApplicationError."""
        from tracklistify.core import exceptions as core_exceptions
        from tracklistify.core.exceptions import TracklistifyError, ApplicationError

        # Get all exception classes from core.exceptions
        for name in dir(core_exceptions):
            obj = getattr(core_exceptions, name)
            if inspect.isclass(obj) and issubclass(obj, Exception):
                if obj is TracklistifyError or obj is ApplicationError:
                    continue
                if obj.__module__ == "tracklistify.core.exceptions":
                    # Should inherit from TracklistifyError or ApplicationError
                    assert issubclass(obj, (TracklistifyError, ApplicationError)), (
                        f"{name} should inherit from TracklistifyError or ApplicationError"
                    )

    def test_all_expected_exceptions_exist(self):
        """Test that all expected exceptions are defined in core.exceptions."""
        from tracklistify.core import exceptions as core_exceptions

        expected_exceptions = [
            "TracklistifyError",
            "APIError",
            "DownloadError",
            "ConfigError",
            "AudioProcessingError",
            "TrackIdentificationError",
            "ValidationError",
            "ProviderError",
            "AuthenticationError",
            "RateLimitError",
            "ApplicationError",
        ]

        for name in expected_exceptions:
            assert hasattr(core_exceptions, name), (
                f"Expected exception {name} not found in core.exceptions"
            )
            obj = getattr(core_exceptions, name)
            assert inspect.isclass(obj) and issubclass(obj, Exception), (
                f"{name} should be an Exception class"
            )

    def test_provider_error_has_provider_attribute(self):
        """Test that ProviderError stores provider name."""
        from tracklistify.core.exceptions import ProviderError

        error = ProviderError("Test", provider="shazam", cause=ValueError("inner"))

        assert error.provider == "shazam"
        assert error.cause is not None
        assert isinstance(error.cause, ValueError)

    def test_authentication_error_has_service_attribute(self):
        """Test that AuthenticationError stores service name."""
        from tracklistify.core.exceptions import AuthenticationError

        error = AuthenticationError("Test", service="spotify")

        assert error.service == "spotify"


class TestExceptionImports:
    """Test that modules correctly import exceptions."""

    def test_cli_imports_from_core_exceptions(self):
        """Test that CLI module imports exceptions from core."""
        from tracklistify import cli

        # ApplicationError should be available (imported from core)
        assert hasattr(cli, "ApplicationError")

    def test_providers_can_raise_core_exceptions(self):
        """Test that provider modules can use core exceptions."""
        from tracklistify.core.exceptions import ProviderError, ShazamError

        # Should be able to catch ShazamError as ProviderError
        error = ShazamError("Test error", error_code="ERR001")

        assert isinstance(error, ProviderError)
        assert error.provider == "Shazam"


class TestNoOrphanExceptionDefinitions:
    """Test for orphan exception definitions that should be removed."""

    def test_scan_src_for_orphan_definitions(self):
        """Scan source files for orphan exception definitions."""
        src_path = Path("src/tracklistify")

        # Files allowed to define exceptions
        allowed_files = {
            src_path / "core" / "exceptions.py",
            # Domain-specific exceptions that are intentionally separate
            src_path / "config" / "security.py",
            src_path / "config" / "validation.py",
            src_path / "dev_cli" / "exceptions.py",
        }

        # Exceptions that should NOT be defined outside core/exceptions.py
        # (because they have duplicates or belong in core)
        disallowed_definitions = [
            "class ProviderError",
            "class AuthenticationError",
            "class RateLimitError",
            "class IdentificationError",
            "class ApplicationError",
            "class TrackIdentificationError(ApplicationError)",
            "class ConfigError(Exception)",
        ]

        violations = []

        for py_file in src_path.rglob("*.py"):
            if py_file in allowed_files:
                continue
            if "test" in str(py_file):
                continue

            try:
                with open(py_file) as f:
                    content = f.read()

                for pattern in disallowed_definitions:
                    if pattern in content:
                        violations.append(f"{py_file}: {pattern}")
            except Exception:
                pass

        if violations:
            pytest.fail(
                f"Found orphan exception definitions that should be removed:\n"
                + "\n".join(violations)
            )
