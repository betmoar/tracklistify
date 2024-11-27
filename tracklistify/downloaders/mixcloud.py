"""
Mixcloud audio downloader implementation.
"""

# Standard library imports
import asyncio
import os
import tempfile
from pathlib import Path
from typing import Optional

# Third-party imports
import yt_dlp

from tracklistify.downloaders.base import Downloader

# Local/package imports
from tracklistify.utils.logger import logger
from tracklistify.utils.validation import clean_url


class MixcloudDownloader(Downloader):
    """Mixcloud audio downloader."""

    def __init__(
        self, verbose: bool = False, quality: str = "192", format: str = "mp3"
    ):
        """Initialize Mixcloud downloader.

        Args:
            verbose: Enable verbose logging
            quality: Audio quality (bitrate)
            format: Output audio format
        """
        self.ffmpeg_path = self.get_ffmpeg_path()
        self.verbose = verbose
        self.quality = quality
        self.format = format
        logger.debug(
            f"Initialized MixcloudDownloader with ffmpeg at: {self.ffmpeg_path}"
        )
        logger.debug(f"Settings - Quality: {quality}kbps, Format: {format}")

    def get_ydl_opts(self) -> dict:
        """Get yt-dlp options with current configuration."""
        return {
            "format": "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": self.format,
                    "preferredquality": self.quality,
                }
            ],
            "ffmpeg_location": self.ffmpeg_path,
            "outtmpl": os.path.join(tempfile.gettempdir(), "%(id)s.%(ext)s"),
            "verbose": self.verbose,
        }

    async def download(self, url: str) -> Optional[str]:
        """Asynchronously download audio from Mixcloud URL.

        Args:
            url: Mixcloud track URL

        Returns:
            str: Path to downloaded audio file, or None if download failed
        """
        try:
            # Clean URL before downloading
            url = clean_url(url)
            logger.info(f"Starting Mixcloud download: {url}")
            ydl_opts = self.get_ydl_opts()

            # Run yt-dlp in a thread pool to avoid blocking
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.debug("Extracting mix information...")
                info = await asyncio.to_thread(ydl.extract_info, url, download=True)
                filename = ydl.prepare_filename(info)
                output_path = str(Path(filename).with_suffix(f".{self.format}"))

                title = info.get("title", "Unknown title")
                uploader = info.get("uploader", "Unknown artist")
                duration = info.get("duration", 0)
                logger.info(f"Downloaded: {title} by {uploader} ({duration}s)")
                logger.debug(f"Output file: {output_path}")
                return output_path

        except Exception as e:
            error_msg = str(e).lower()
            if "not found" in error_msg or "404" in error_msg:
                logger.error(f"Mix not found: {url}")
            elif "private" in error_msg:
                logger.error(f"Cannot download private mix: {url}")
            elif "premium" in error_msg:
                logger.error(f"Cannot download premium content: {url}")
            else:
                logger.error(f"Failed to download {url}: {str(e)}")
            return None
