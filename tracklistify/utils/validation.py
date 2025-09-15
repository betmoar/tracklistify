"""
Input validation utilities for Tracklistify.
"""

# Standard library imports
from typing import Optional

# Third-party imports
from yt_dlp import YoutubeDL, DownloadError

# Local/package imports
from .logger import get_logger

logger = get_logger(__name__)


def validate_input(url: str) -> Optional[str]:
    """
    Validate and clean a URL using yt-dlp.

    Args:
        url: Input URL to validate and clean

    Returns:
        Cleaned URL if valid, None if invalid
    """
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "force_generic_extractor": True,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
            if info_dict is not None:
                logger.info(f"Extracted info from URL: {info_dict.get('webpage_url')}")
                return info_dict.get("webpage_url", None)
            else:
                logger.error("Failed to extract info from URL")
                return None

    except DownloadError as e:
        logger.error(f"URL validation failed: {e}")
        return None


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

    cleaned_url = validate_input(url)
    if not cleaned_url:
        return False

    return "youtube.com/watch?v=" in cleaned_url


def is_soundcloud_url(url: str) -> bool:
    """
    Check if a URL is a valid Soundcloud URL.

    Args:
        url: URL to check

    Returns:
        bool: True if URL is a valid Soundcloud URL, False otherwise
    """
    if not url:
        return False

    cleaned_url = validate_input(url)
    if not cleaned_url:
        return False

    return "soundcloud.com/" in cleaned_url


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

    cleaned_url = validate_input(url)
    if not cleaned_url:
        return False

    return "mixcloud.com/" in cleaned_url
