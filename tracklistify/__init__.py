"""
Tracklistify - Automatic tracklist generator for DJ mixes and audio streams.
"""

from importlib.metadata import metadata

try:
    from ._version import __version__
except ImportError:
    # Fallback to package metadata if _version.py is not available
    __version__ = metadata("tracklistify")["Version"]

# Get package metadata
_metadata = metadata("tracklistify")

__title__ = _metadata["Name"]
__author__ = _metadata["Author"]
__license__ = _metadata["License"]

__all__ = ["__version__", "__title__", "__author__", "__license__"]
