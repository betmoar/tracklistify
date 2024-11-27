"""
Tracklistify - Automatic tracklist generator for DJ mixes and audio streams.

This module provides the main entry point for the Tracklistify package. It includes
metadata about the package such as version, title, author, and license. The version
information is retrieved from the _version.py file if available, otherwise it falls
back to the package metadata.
"""

# Standard library imports
import importlib.metadata


def get_metadata():
    """
    Extract version and metadata from package distribution.

    This function is used in the generated `__init__.py` to extract the package
    version and metadata from the distribution. It is used as a fallback when the
    `importlib.metadata` module is not available.

    Returns
    -------
    list
        A list of strings containing the version, title, author, and license of
        the package.
    """
    from importlib.metadata import metadata, version

    _meta = metadata("tracklistify")
    __version__ = version("tracklistify")
    __title__ = _meta.get("Name", "Unknown")
    __author__ = _meta.get("Author", "Unknown")
    __license__ = _meta.get("License", "Unknown")

    __all__ = ["__version__", "__title__", "__author__", "__license__"]
    return __all__


__all__ = get_metadata()
