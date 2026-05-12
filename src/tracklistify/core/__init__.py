"""
This module initializes the core components of the tracklistify package.

Eager re-exports here are limited to leaf modules (`exceptions`, `types`) that
don't import from `tracklistify.config` or `tracklistify.utils`. Heavy modules
(`base`, `track`) are loaded lazily via PEP 562 ``__getattr__`` so that other
packages can import ``tracklistify.core.exceptions`` without triggering a
circular import through ``config`` or ``downloaders``.
"""

# Local/package imports (using relative imports at package root)
from .exceptions import ApplicationError
from .types import ProviderResponse, TrackIdentificationProvider, TrackMetadata

__all__ = [
    "AsyncApp",
    "ApplicationError",
    "ProviderResponse",
    "Track",
    "TrackIdentificationProvider",
    "TrackMatcher",
    "TrackMetadata",
]


def __getattr__(name: str):
    if name == "AsyncApp":
        from .base import AsyncApp

        return AsyncApp
    if name == "Track":
        from .track import Track

        return Track
    if name == "TrackMatcher":
        from .track import TrackMatcher

        return TrackMatcher
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
