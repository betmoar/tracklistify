"""
YouTube video downloader implementation.
"""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Optional

import yt_dlp

from ..logger import logger
from .base import Downloader

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
        logger.debug(f"Initialized YouTubeDownloader with ffmpeg at: {self.ffmpeg_path}")
        logger.debug(f"Settings - Quality: {quality}kbps, Format: {format}")
        
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
            logger.info(f"Starting YouTube download: {url}")
            ydl_opts = self.get_ydl_opts()
            
            # Run yt-dlp in a thread pool to avoid blocking
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.debug("Extracting video information...")
                info = await asyncio.to_thread(ydl.extract_info, url, download=True)
                filename = ydl.prepare_filename(info)
                output_path = str(Path(filename).with_suffix(f'.{self.format}'))
                
                title = info.get('title', 'Unknown title')
                duration = info.get('duration', 0)
                logger.info(f"Downloaded: {title} ({duration}s)")
                logger.debug(f"Output file: {output_path}")
                return output_path
                
        except Exception as e:
            if "Private video" in str(e):
                logger.error(f"Cannot download private video: {url}")
            elif "Video unavailable" in str(e):
                logger.error(f"Video is unavailable: {url}")
            else:
                logger.error(f"Failed to download {url}: {str(e)}")
            return None