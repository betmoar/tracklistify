"""
Factory for creating appropriate downloader instances.
"""

from typing import Dict, Optional

from ..config import get_config
from ..logger import logger
from ..validation import is_youtube_url
from .base import Downloader
from .youtube import YouTubeDownloader

class DownloaderFactory:
    """Factory for creating appropriate downloader instances."""
    
    def __init__(self, config=None):
        """Initialize factory with configuration.
        
        Args:
            config: Optional configuration object
        """
        self._config = config or get_config()
        self._downloaders: Dict[str, Downloader] = {}
    
    def create_downloader(self, url: str) -> Optional[Downloader]:
        """Create appropriate downloader based on URL.
        
        Args:
            url: Media URL
            
        Returns:
            Downloader: Appropriate downloader instance, or None if unsupported
        """
        if is_youtube_url(url):
            if 'youtube' not in self._downloaders:
                self._downloaders['youtube'] = YouTubeDownloader(
                    verbose=getattr(self._config.app, 'verbose', False),
                    quality=getattr(self._config.download, 'quality', '192'),
                    format=getattr(self._config.download, 'format', 'mp3')
                )
            return self._downloaders['youtube']
        
        # Support for other platforms can be added here
        logger.warning(f"No downloader available for URL: {url}")
        return None
