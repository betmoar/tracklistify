"""
Audio download and processing functionality.
"""

import asyncio
import os
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional
import yt_dlp

from .logger import logger
from .config import get_config
from .validation import is_youtube_url

@dataclass
class DownloadConfig:
    """Download configuration settings."""
    quality: str = '192'
    format: str = 'mp3'
    temp_dir: str = tempfile.gettempdir()
    max_retries: int = 3

class Downloader(ABC):
    """Base class for audio downloaders."""
    
    @abstractmethod
    async def download(self, url: str) -> Optional[str]:
        """Download audio from URL."""
        pass
        
    @staticmethod
    def get_ffmpeg_path() -> str:
        """Find FFmpeg executable path."""
        # Check common locations
        common_paths = [
            '/opt/homebrew/bin/ffmpeg',  # Homebrew on Apple Silicon
            '/usr/local/bin/ffmpeg',     # Homebrew on Intel Mac
            '/usr/bin/ffmpeg',           # Linux
        ]
        
        for path in common_paths:
            if os.path.isfile(path):
                return path
                
        # Try finding in PATH
        import shutil
        ffmpeg_path = shutil.which('ffmpeg')
        if ffmpeg_path:
            return ffmpeg_path
            
        raise FileNotFoundError("FFmpeg not found. Please install FFmpeg first.")

class YouTubeDownloader(Downloader):
    """YouTube video downloader."""
    
    def __init__(self, verbose: bool = False, quality: str = '192', format: str = 'mp3'):
        """Initialize YouTube downloader.
        
        Args:
            verbose: Enable verbose logging
            quality: Audio quality (bitrate)
            format: Output audio format
        """
        self.ffmpeg_path = self.get_ffmpeg_path()
        self.verbose = verbose
        self.quality = quality
        self.format = format
        logger.info(f"Using FFmpeg from: {self.ffmpeg_path}")
        
    def get_ydl_opts(self) -> dict:
        """Get yt-dlp options with current configuration."""
        return {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': self.format,
                'preferredquality': self.quality,
            }],
            'ffmpeg_location': self.ffmpeg_path,
            'outtmpl': os.path.join(tempfile.gettempdir(), '%(id)s.%(ext)s'),
            'verbose': self.verbose,
        }
        
    async def download(self, url: str) -> Optional[str]:
        """Asynchronously download audio from YouTube URL.
        
        Args:
            url: YouTube video URL
            
        Returns:
            str: Path to downloaded audio file, or None if download failed
        """
        try:
            ydl_opts = self.get_ydl_opts()
            
            # Run yt-dlp in a thread pool to avoid blocking
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, url, download=True)
                filename = ydl.prepare_filename(info)
                output_path = str(Path(filename).with_suffix(f'.{self.format}'))
                logger.info(f"Downloaded: {info.get('title', 'Unknown title')}")
                return output_path
                
        except Exception as e:
            logger.error(f"Failed to download {url}: {str(e)}")
            return None

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
