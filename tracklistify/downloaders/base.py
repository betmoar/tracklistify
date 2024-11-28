"""
Base downloader interface and common utilities.
"""

# Standard library imports
import os
import shutil
from abc import ABC, abstractmethod
from typing import Optional

# Local/package imports


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
