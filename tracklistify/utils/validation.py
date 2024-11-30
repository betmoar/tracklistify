"""
Input validation utilities for Tracklistify.
"""

# Standard library imports
import re
from typing import Optional
from urllib.error import URLError
from urllib.parse import unquote, urlparse

# Local/package imports
from tracklistify.core.exceptions import URLValidationError


def validate_and_clean_url(url: str) -> Optional[str]:
    """
    Validate and clean a URL.

    Args:
        url: Input URL to validate and clean

    Returns:
        Cleaned URL if valid, None if invalid

    Features:
        - Strips backslashes and whitespace
        - Validates URL format
        - Supports YouTube and other video platforms
        - Unescapes URL-encoded characters
    """
    if not url:
        return None

    # Strip whitespace and backslashes
    url = url.strip().replace("\\", "")

    # Unescape URL-encoded characters
    url = unquote(url)

    try:
        # Parse URL
        parsed = urlparse(url)

        # Check basic URL validity
        if not all([parsed.scheme, parsed.netloc]):
            return None

        # Validate YouTube URLs
        if "youtube.com" in parsed.hostname or "youtu.be" in parsed.hostname:
            # Extract video ID
            if "youtube.com" in parsed.hostname:
                video_id = re.search(r"[?&]v=([^&]+)", url)
            else:  # youtu.be
                video_id = re.search(r"youtu\.be/([^?&]+)", url)

            if not video_id:
                return None

            # Reconstruct clean YouTube URL
            return f"https://www.youtube.com/watch?v={video_id.group(1)}"

        # Validate Mixcloud URLs
        if "mixcloud.com" in parsed.hostname:
            # Remove trailing slash and query parameters
            path = parsed.path.rstrip("/")
            if not path or path == "/":
                return None
            return f"https://www.mixcloud.com{path}"

        # For other URLs, return cleaned version
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    except Exception:
        return None


def is_valid_url(url: str) -> bool:
    """
    Check if a URL is valid.

    Args:
        url: URL to validate

    Returns:
        bool: True if URL is valid, False otherwise
    """
    return validate_and_clean_url(url) is not None


def is_youtube_url(url: str) -> bool:
    """
    Check if a URL is a valid YouTube URL.

    Args:
        url: URL to check

    Returns:
        bool: True if URL is a valid YouTube URL, False otherwise
    """
    if not url:
        return False

    cleaned_url = validate_and_clean_url(url)
    if not cleaned_url:
        return False

    return "youtube.com/watch?v=" in cleaned_url


def is_mixcloud_url(url: str) -> bool:
    """
    Check if a URL is a valid Mixcloud URL.

    Args:
        url: URL to check

    Returns:
        bool: True if URL is a valid Mixcloud URL, False otherwise
    """
    if not url:
        return False

    try:
        parsed = urlparse(url)
        return parsed.netloc.endswith("mixcloud.com") and len(parsed.path) > 1
    except (ValueError, URLError):
        return False


def clean_url(url: str) -> str:
    """
    Clean a URL by removing unnecessary parameters and normalizing format.

    Args:
        url: Input URL to clean

    Returns:
        Cleaned URL

    Raises:
        URLValidationError: If URL is invalid
    """
    if not url:
        raise URLValidationError("URL cannot be empty")

    # Strip whitespace and backslashes
    url = url.strip().replace("\\", "")

    # Unescape URL-encoded characters
    url = unquote(url)

    try:
        parsed = urlparse(url)
        # Further cleaning logic can be added here
        return parsed.geturl()
    except (ValueError, URLError) as e:
        raise URLValidationError(f"Invalid URL: {e}") from e


def validate_url(url: str) -> bool:
    """
    Validate a URL.

    Args:
        url: URL to validate

    Returns:
        bool: True if URL is valid

    Raises:
        URLValidationError: If URL is invalid
    """
    try:
        cleaned = clean_url(url)
        parsed = urlparse(cleaned)

        # Check for supported platforms
        domain = parsed.netloc.lower()
        if not any(
            platform in domain
            for platform in ["youtube.com", "mixcloud.com", "soundcloud.com"]
        ):
            raise URLValidationError("Unsupported platform")

        return True
    except URLValidationError:
        raise
    except Exception as e:
        raise URLValidationError(f"Invalid URL: {str(e)}") from e
