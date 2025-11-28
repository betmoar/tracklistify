"""
Input validation utilities for Tracklistify.
"""

# Standard library imports
from pathlib import Path
from typing import Iterable, Optional, Tuple
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


def _normalize_hostname(hostname: Optional[str]) -> str:
    """Lowercase and strip trailing dots to normalize the hostname."""
    if hostname is None:
        return ""
    # strip any trailing dots that could be used to bypass checks
    return hostname.strip().lower().rstrip(".")


def _is_domain_or_subdomain(hostname: str, domain: str) -> bool:
    """Return True if hostname equals domain or is a subdomain of domain."""
    hostname = _normalize_hostname(hostname)
    domain = domain.lower()
    if not hostname:
        return False
    return hostname == domain or hostname.endswith("." + domain)


def _is_platform_url(url: str, allowed_domains: Iterable[str]) -> bool:
    """
    Parse URL and ensure its hostname matches one of the allowed domains
    or is a proper subdomain. This avoids substring matching on the full URL.
    """
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    hostname = parsed.hostname  # urlparse gives hostname without port
    if not hostname:
        return False

    for domain in allowed_domains:
        if _is_domain_or_subdomain(hostname, domain):
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
