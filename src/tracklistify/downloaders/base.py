"""
Base downloader interface and common utilities.
"""

# Standard library imports
import os
import shutil
from abc import ABC, abstractmethod
from typing import Optional, Dict

# Local/package imports


class Downloader(ABC):
    """Base class for audio downloaders."""

    @abstractmethod
    async def download(self, url: str) -> Optional[str]:
        """Download audio from URL."""
        pass

    def get_last_metadata(self) -> Optional[Dict]:
        """Return the most recent metadata captured during a download, if any.

        Subclasses can set an internal attribute to store metadata obtained
        during the download process (e.g., from an API response) and expose it
        through this method. The default implementation returns None.
        """
        return None

    @staticmethod
    def get_ffmpeg_path() -> str:
        """Find FFmpeg executable path."""
        # Check common locations
        common_paths = [
            "/opt/homebrew/bin/ffmpeg",  # Homebrew on Apple Silicon
            "/usr/local/bin/ffmpeg",  # Homebrew on Intel Mac
            "/usr/bin/ffmpeg",  # Linux
        ]

        for path in common_paths:
            if os.path.isfile(path):
                return path

        # Try finding in PATH
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path:
            return ffmpeg_path

        raise FileNotFoundError("FFmpeg not found. Please install FFmpeg first.")
