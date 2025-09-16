"""
Input validation utilities for Tracklistify.
"""

# Standard library imports
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse

# Local/package imports
from .logger import get_logger

logger = get_logger(__name__)


def validate_input(input_path: str) -> Optional[Tuple[str, bool]]:
    """
    Validate input as either a URL or a local file path.

    Returns:
        (validated_path, is_local_file) on success, or None if invalid.
        - validated_path: normalized absolute path for local files, or the original URL.
        - is_local_file: True if local file, False if URL.
    """
    if not input_path or not isinstance(input_path, str):
        return None

    s = input_path.strip()
    if not s:
        return None

    parsed = urlparse(s)

    # URL case (http/https)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return s, False

    # file:// URL -> treat as local file
    if parsed.scheme == "file":
        local = Path(parsed.path).expanduser()
        if local.exists() and local.is_file():
            try:
                return str(local.resolve(strict=True)), True
            except Exception:
                return str(local), True
        return None

    # Local file path
    p = Path(s).expanduser()
    if p.exists() and p.is_file():
        try:
            return str(p.resolve(strict=True)), True
        except Exception:
            return str(p), True

    return None


def is_youtube_url(url: str) -> bool:
    """
    Check if a URL is a valid YouTube URL.
    """
    if not url:
        return False

    result = validate_input(url)
    if not result:
        return False

    validated, is_local = result
    if is_local:
        return False

    host = urlparse(validated).netloc.lower()
    return ("youtube.com" in host) or ("youtu.be" in host)


def is_soundcloud_url(url: str) -> bool:
    """
    Check if a URL is a valid Soundcloud URL.
    """
    if not url:
        return False

    result = validate_input(url)
    if not result:
        return False

    validated, is_local = result
    if is_local:
        return False

    host = urlparse(validated).netloc.lower()
    return host.endswith("soundcloud.com")


def is_mixcloud_url(url: str) -> bool:
    """
    Check if a URL is a valid Mixcloud URL.
    """
    if not url:
        return False

    result = validate_input(url)
    if not result:
        return False

    validated, is_local = result
    if is_local:
        return False

    host = urlparse(validated).netloc.lower()
    return host.endswith("mixcloud.com")
