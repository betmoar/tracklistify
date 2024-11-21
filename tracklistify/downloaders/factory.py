"""
Factory for creating appropriate downloader instances.
"""

from typing import Dict, Optional
from ..logger import logger
from ..validation import is_youtube_url, is_mixcloud_url
from ..config import TrackIdentificationConfig, get_config
from .base import Downloader
from .mixcloud import MixcloudDownloader
from .youtube import YouTubeDownloader

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
