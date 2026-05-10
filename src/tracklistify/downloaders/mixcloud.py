"""
Mixcloud audio downloader implementation.
"""

# Standard library imports
import asyncio
import os
import tempfile
from pathlib import Path

# Third-party imports
import yt_dlp

# Local/package imports
from tracklistify.core.exceptions import DownloadError
from tracklistify.downloaders.base import Downloader
from tracklistify.utils.logger import get_logger

logger = get_logger(__name__)


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

    async def download(self, url: str) -> str:
        """Asynchronously download audio from Mixcloud URL.

        Args:
            url: Mixcloud track URL

        Returns:
            str: Path to downloaded audio file

        Raises:
            DownloadError: If download fails for any reason
        """
        try:
            # Clean URL before downloading
            logger.info(f"Starting Mixcloud download: {url}")
            ydl_opts = self.get_ydl_opts()

            # Run yt-dlp in a thread pool to avoid blocking
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                logger.debug("Extracting mix information...")
                info = await asyncio.to_thread(ydl.extract_info, url, download=True)

                if info is None:
                    logger.error("Failed to extract video information")
                    raise DownloadError("Failed to extract video information", url=url)

                filename = ydl.prepare_filename(info)
                output_path = str(Path(filename).with_suffix(f".{self.format}"))

                title = info.get("title", "Unknown title")
                uploader = info.get("uploader", "Unknown artist")
                duration = info.get("duration", 0)
                logger.info(f"Downloaded: {title} by {uploader} ({duration}s)")
                logger.debug(f"Output file: {output_path}")
                return output_path

        except DownloadError:
            # Re-raise DownloadError without wrapping
            raise
        except Exception as e:
            error_msg = str(e).lower()
            if "not found" in error_msg or "404" in error_msg:
                logger.error(f"Mix not found: {url}")
                raise DownloadError(f"Mix not found: {url}", url=url, cause=e) from e
            elif "private" in error_msg:
                logger.error(f"Cannot download private mix: {url}")
                raise DownloadError(
                    f"Cannot download private mix: {url}", url=url, cause=e
                ) from e
            elif "premium" in error_msg:
                logger.error(f"Cannot download premium content: {url}")
                raise DownloadError(
                    f"Cannot download premium content: {url}", url=url, cause=e
                ) from e
            else:
                logger.error(f"Failed to download {url}: {str(e)}")
                raise DownloadError(
                    f"Download failed: {str(e)}", url=url, cause=e
                ) from e
