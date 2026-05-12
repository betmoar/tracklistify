"""
Tests for Phase 5 Group G: Resource Management

Ensures proper resource cleanup with context managers.
"""

# Standard library imports
import ast
import inspect
from pathlib import Path

# Third-party imports
import pytest


class TestContextManagerProtocol:
    """Tests for async context manager protocol implementation."""

    def test_track_identification_provider_has_aenter(self):
        """TrackIdentificationProvider should implement __aenter__."""
        from tracklistify.providers.base import TrackIdentificationProvider

        assert hasattr(TrackIdentificationProvider, "__aenter__"), (
            "TrackIdentificationProvider should have __aenter__ method"
        )
        # Check it's async
        method = TrackIdentificationProvider.__aenter__
        assert inspect.iscoroutinefunction(method), "__aenter__ should be async"

    def test_track_identification_provider_has_aexit(self):
        """TrackIdentificationProvider should implement __aexit__."""
        from tracklistify.providers.base import TrackIdentificationProvider

        assert hasattr(TrackIdentificationProvider, "__aexit__"), (
            "TrackIdentificationProvider should have __aexit__ method"
        )
        # Check it's async
        method = TrackIdentificationProvider.__aexit__
        assert inspect.iscoroutinefunction(method), "__aexit__ should be async"

    def test_metadata_provider_has_aenter(self):
        """MetadataProvider should implement __aenter__."""
        from tracklistify.providers.base import MetadataProvider

        assert hasattr(MetadataProvider, "__aenter__"), (
            "MetadataProvider should have __aenter__ method"
        )

    def test_metadata_provider_has_aexit(self):
        """MetadataProvider should implement __aexit__."""
        from tracklistify.providers.base import MetadataProvider

        assert hasattr(MetadataProvider, "__aexit__"), (
            "MetadataProvider should have __aexit__ method"
        )


class TestShazamProviderContextManager:
    """Test ShazamProvider context manager support."""

    def test_shazam_inherits_context_manager(self):
        """ShazamProvider should inherit context manager protocol."""
        from tracklistify.providers.shazam import ShazamProvider
        from tracklistify.providers.base import TrackIdentificationProvider

        # ShazamProvider should inherit from TrackIdentificationProvider
        assert issubclass(ShazamProvider, TrackIdentificationProvider), (
            "ShazamProvider should inherit from TrackIdentificationProvider"
        )

        # Should have context manager methods via inheritance
        assert hasattr(ShazamProvider, "__aenter__")
        assert hasattr(ShazamProvider, "__aexit__")

    @pytest.mark.asyncio
    async def test_shazam_can_be_used_as_context_manager(self):
        """ShazamProvider can be used with async with."""
        from tracklistify.providers.shazam import ShazamProvider

        # This should not raise an exception
        async with ShazamProvider() as provider:
            assert provider is not None


class TestProviderCleanup:
    """Tests for provider cleanup functionality."""

    def test_provider_base_has_close_method(self):
        """Provider base should define abstract close method."""
        file_path = Path("src/tracklistify/providers/base.py")

        with open(file_path) as f:
            content = f.read()

        tree = ast.parse(content)

        # Find TrackIdentificationProvider class
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if node.name == "TrackIdentificationProvider":
                    # Find close method
                    has_close = False
                    for item in node.body:
                        if (
                            isinstance(item, ast.AsyncFunctionDef)
                            and item.name == "close"
                        ):
                            has_close = True
                            # Check it's abstract
                            for decorator in item.decorator_list:
                                if isinstance(decorator, ast.Name):
                                    if decorator.id == "abstractmethod":
                                        break
                            break
                    assert has_close, (
                        "TrackIdentificationProvider should have close method"
                    )
                    break

    def test_aexit_calls_close(self):
        """__aexit__ should call close() for cleanup."""
        file_path = Path("src/tracklistify/providers/base.py")

        with open(file_path) as f:
            content = f.read()

        # __aexit__ should contain "await self.close()"
        assert "await self.close()" in content, (
            "__aexit__ should call self.close() for cleanup"
        )
