"""
Audio download functionality.
"""

from .base import Downloader
from .factory import DownloaderFactory
from .youtube import YouTubeDownloader
from .spotify import SpotifyDownloader

__all__ = ['Downloader', 'DownloaderFactory', 'YouTubeDownloader', 'SpotifyDownloader']
