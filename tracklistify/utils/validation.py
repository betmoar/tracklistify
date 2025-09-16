"""
Input validation utilities for Tracklistify.
"""

# Standard library imports
from typing import Optional

# Third-party imports
from yt_dlp import DownloadError, YoutubeDL

# Local/package imports
from .logger import get_logger

logger = get_logger(__name__)


def validate_input(input_path: str) -> Optional[str]:
    """
    Validate and clean a URL or local file path.

    Args:
        input_path: Input URL or local file path to validate

    Returns:
        Cleaned URL or validated file path if valid, None if invalid
    """
    from pathlib import Path

    # First check if it's a local file path
    if Path(input_path).exists():
        logger.info(f"Validated local file path: {input_path}")
        return input_path

    # If not a local file, try to validate as URL using yt-dlp
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "force_generic_extractor": True,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(input_path, download=False)
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
