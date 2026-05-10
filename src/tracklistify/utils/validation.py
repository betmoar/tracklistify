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
    """Return True if hostname equals domain or is a proper subdomain of domain."""
    hostname = _normalize_hostname(hostname)
    domain = domain.lower()

    if not hostname or not domain:
        return False

    # Exact match
    if hostname == domain:
        return True

    # Check for proper subdomain (domain must be at the end, preceded by a dot)
    # This allows arbitrary subdomain sequences like "api.music.youtube.com"
    if hostname.endswith("." + domain):
        # Ensure the character before the dot is not a dot (to prevent "..")
        # and that we're not dealing with something like "youtube.com.evil.com"
        dot_index = hostname.rfind("." + domain)
        if dot_index > 0:
            # Check that the character before the dot is not a dot
            return hostname[dot_index - 1] != "."

    return False


def _is_platform_url(url: str, allowed_domains: Iterable[str]) -> bool:
    """Return True if the URL's hostname matches one of the allowed domains.

    A match is either an exact hostname match (e.g. "youtu.be") or a proper
    subdomain (e.g. "m.youtube.com" for "youtube.com"). Subdomain logic is
    delegated to ``_is_domain_or_subdomain`` to keep both helpers in lockstep.
    """
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    host = parsed.hostname
    if not host:
        return False
    return any(_is_domain_or_subdomain(host, d) for d in allowed_domains)


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


def clean_url(url: str) -> str:
    """Normalize a URL: strip query/fragment/trailing slash; lowercase scheme + host.

    Args:
        url: URL to normalize. May be empty or unparseable.

    Returns:
        str: Normalized URL, or the input unchanged if it is not an absolute URL
        with both scheme and netloc. Returns ``""`` for empty input.
    """
    if not url:
        return ""
    try:
        parsed = urlparse(url)
    except Exception:
        return url
    if not parsed.scheme or not parsed.netloc:
        return url
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"
