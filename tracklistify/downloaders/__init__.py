"""
Audio download functionality.
"""

from .base import Downloader
from .factory import DownloaderFactory
from .spotify import SpotifyDownloader
from .youtube import YouTubeDownloader

__all__ = ["Downloader", "DownloaderFactory", "YouTubeDownloader", "SpotifyDownloader"]
