"""
Tracklistify - Automatic tracklist generator for DJ mixes and audio streams.

Exposes the package's distribution metadata (version, title, author,
license) as module attributes. The values come from the installed
distribution, so they always match what was actually installed rather than
a literal duplicated in the source.
"""

# Standard library imports
from typing import Any

# Local/package imports
from .utils.logger import get_logger

# Configure package-level logger
package_logger = get_logger(__name__)

__all__ = ["__version__", "__title__", "__author__", "__license__"]

# distribution metadata field -> module attribute. "License-Expression" is
# PEP 639's replacement for the free-text "License" field; which one is
# populated depends on the build backend, so both are tried in order.
_METADATA_FIELDS = {
    "__version__": ("Version",),
    "__title__": ("Name",),
    "__author__": ("Author", "Author-email"),
    "__license__": ("License-Expression", "License"),
}


def __getattr__(name: str) -> Any:
    """Resolve distribution metadata on first access (PEP 562).

    Deferred rather than read at import time: ``importlib.metadata`` walks
    the filesystem to find the distribution, and every ``import
    tracklistify`` would pay for it — including CLI startup, which reads
    none of these.
    """
    fields = _METADATA_FIELDS.get(name)
    if fields is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from importlib.metadata import PackageNotFoundError, metadata

    try:
        meta = metadata("tracklistify")
    except PackageNotFoundError:  # running from a source tree, not installed
        return "unknown"

    # Subscript, not .get(): PackageMetadata's stub declares no `get`,
    # though the runtime object is an email.Message that has one. A missing
    # header subscripts to None either way.
    for field in fields:
        value = meta[field]
        if value:
            return value
    return "unknown"


def __dir__() -> list:
    """Include the lazy attributes in dir(), which __getattr__ alone omits."""
    return sorted(set(globals()) | set(_METADATA_FIELDS))
