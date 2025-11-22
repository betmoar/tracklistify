"""
Input validation utilities for Tracklistify.
"""

# Standard library imports
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlparse

# Local/package imports
from .logger import get_logger

logger = get_logger(__name__)

# Platform domain configurations for URL validation
YOUTUBE_DOMAINS = ["youtube.com", "youtu.be"]
SOUNDCLOUD_DOMAINS = ["soundcloud.com"]
MIXCLOUD_DOMAINS = ["mixcloud.com"]


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


def _is_platform_url(url: str, domains: List[str]) -> bool:
    """
    Check if a URL belongs to a specific platform.

    This is a DRY helper function that centralizes URL validation logic.

    Args:
        url: URL to check
        domains: List of base domain names for the platform (e.g., ["youtube.com", "youtu.be"])

    Returns:
        bool: True if URL belongs to the platform, False otherwise
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

    # Check exact matches and www variants
    for domain in domains:
        if host == domain or host == f"www.{domain}":
            return True
        if host.endswith(f".{domain}"):
            return True

    return False


def is_youtube_url(url: str) -> bool:
    """
    Check if a URL is a valid YouTube URL.

    Args:
        url: URL to check

    Returns:
        bool: True if URL is a valid YouTube URL, False otherwise
    """
    return _is_platform_url(url, YOUTUBE_DOMAINS)


def is_soundcloud_url(url: str) -> bool:
    """
    Check if a URL is a valid Soundcloud URL.

    Args:
        url: URL to check

    Returns:
        bool: True if URL is a valid Soundcloud URL, False otherwise
    """
    return _is_platform_url(url, SOUNDCLOUD_DOMAINS)


def is_mixcloud_url(url: str) -> bool:
    """
    Check if a URL is a valid Mixcloud URL.

    Args:
        url: URL to check

    Returns:
        bool: True if URL is a valid Mixcloud URL, False otherwise
    """
    return _is_platform_url(url, MIXCLOUD_DOMAINS)
