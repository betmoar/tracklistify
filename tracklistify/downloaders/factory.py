"""
Factory for creating appropriate downloader instances.
"""

# Standard library imports
from typing import Dict, Optional

# Local/package imports
from tracklistify.config import TrackIdentificationConfig, get_config
from tracklistify.utils.logger import get_logger
from tracklistify.utils.validation import is_mixcloud_url, is_youtube_url

from .base import Downloader
from .mixcloud import MixcloudDownloader
from .youtube import YouTubeDownloader

logger = get_logger(__name__)


class DownloaderFactory:
    """Factory class for creating appropriate downloader instances."""

    def __init__(self, config: Optional[TrackIdentificationConfig] = None):
        """Initialize factory with configuration.

        Args:
            config: Optional configuration object
        """
        self._config = config or get_config()
        self._downloaders: Dict[str, Downloader] = {}

    @staticmethod
    def create_downloader(url: str, **kwargs) -> Downloader:
        """Create appropriate downloader based on URL.

        Args:
            url: URL to download from
            **kwargs: Additional arguments to pass to downloader

        Returns:
            Downloader: Appropriate downloader instance

        Raises:
            ValueError: If URL is not supported
        """
        logger.debug(f"Creating downloader for URL: {url}")

        if is_youtube_url(url):
            logger.debug("URL identified as YouTube")
            return YouTubeDownloader(**kwargs)
        elif is_mixcloud_url(url):
            logger.debug("URL identified as Mixcloud")
            return MixcloudDownloader(**kwargs)
        else:
            error_msg = f"Unsupported URL format: {url}"
            logger.error(error_msg)
            raise ValueError(error_msg)
