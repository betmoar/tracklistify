"""
YouTube video downloader implementation.
"""

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Optional
import yt_dlp
from ..logger import logger, COLORS
from .base import Downloader
from ..config import get_config

class YTDLPLogger:
    """Custom logger for yt-dlp that integrates with our logging system."""
    
    def __init__(self):
        self._last_progress = 0
        self._show_progress = True
    
    def debug(self, msg):
        """Handle debug messages."""
        # Skip all debug messages
        pass

    def info(self, msg):
        """Handle info messages with proper formatting."""
        # Extract and format important messages
        if msg.startswith('[youtube] Extracting URL:'):
            logger.info(f"Extracting URL: {msg.split('URL: ')[1]}")
        elif msg.startswith('[download] Destination:'):
            logger.info(f"Destination: {msg.split('Destination: ')[1]}")
        elif '[ExtractAudio] Destination:' in msg:
            logger.info(f"Destination: {msg.split('Destination: ')[1]}")
        # Skip all other messages
        
    def warning(self, msg):
        """Handle warning messages."""
        logger.warning(msg)

    def error(self, msg):
        """Handle error messages."""
        logger.error(msg)

class DownloadProgress:
    """Handles download progress display."""
    
    def __init__(self):
        self.last_line_length = 0
    
    def update(self, d):
        """Update progress display."""
        if d['status'] == 'downloading':
            # Only show progress for meaningful updates
            if '_percent_str' in d and d.get('_percent_str', '0%')[:-1] != '0':
                progress = f"{d['_percent_str']} of {d.get('_total_bytes_str', 'Unknown size')} at {d.get('_speed_str', 'Unknown speed')}"
                # Clear previous line and show progress
                print('\r' + ' ' * self.last_line_length, end='')
                print(f"\rDownloading: {progress}", end='')
                self.last_line_length = len(progress) + 12  # account for "Downloading: "
        elif d['status'] == 'finished':
            # Clear progress line and log completion
            print('\r' + ' ' * self.last_line_length + '\r', end='')
            if '_total_bytes_str' in d and '_elapsed_str' in d and '_speed_str' in d:
                logger.info(f"Downloaded {d['_total_bytes_str']} in {d['_elapsed_str']} at {d['_speed_str']}")

_progress_handler = DownloadProgress()

def progress_hook(d):
    """Handle download progress updates."""
    _progress_handler.update(d)

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
        self.config = get_config()
        logger.debug(f"Initialized YouTubeDownloader with ffmpeg at: {self.ffmpeg_path}")
        logger.debug(f"Settings - Quality: {quality}kbps, Format: {format}")
        
    def get_ydl_opts(self) -> dict:
        """Get yt-dlp options with current configuration."""
        # Use configured temp directory or fall back to system temp
        temp_dir = self.config.temp_dir or tempfile.gettempdir()
        
        # Ensure temp directory exists
        os.makedirs(temp_dir, exist_ok=True)
        
        return {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': self.format,
                'preferredquality': self.quality,
            }],
            'ffmpeg_location': self.ffmpeg_path,
            'outtmpl': os.path.join(temp_dir, '%(id)s.%(ext)s'),
            'verbose': True,  # Always set to False to control output
            'logger': YTDLPLogger(),
            'progress_hooks': [progress_hook],
            'no_warnings': True,  # Suppress unnecessary warnings
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
                logger.error(f"Download failed: {str(e)}")
            return None
