"""Smoke tests for top-level package imports.

These tests pin the import surface so that future refactors don't silently
re-introduce circular imports. Each test exercises a different public
entry point.
"""

import importlib


def test_package_import():
    importlib.import_module("tracklistify")


def test_core_imports():
    from tracklistify.core import (  # noqa: F401
        ApplicationError,
        AsyncApp,
        Track,
        TrackMatcher,
    )


def test_config_imports():
    from tracklistify.config import get_config  # noqa: F401


def test_provider_imports():
    from tracklistify.providers.spotify import SpotifyProvider  # noqa: F401


def test_downloader_imports():
    import tracklistify.downloaders.spotify  # noqa: F401
