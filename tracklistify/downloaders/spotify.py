"""
Spotify audio downloader implementation.
"""

# Standard library imports
import asyncio
import os
import re
import subprocess
from enum import Enum
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Any, Dict, Optional

# Third-party imports
import aiohttp
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggvorbis import OggVorbis

# Local/package imports
from tracklistify.core.exceptions import DownloadError
from tracklistify.utils.logger import logger
from tracklistify.utils.validation import clean_url

from .base import Downloader

# Environment variable names
ENV_PREFIX = "TRACKLISTIFY_"
ENV_SPOTIFY_COOKIES = f"{ENV_PREFIX}SPOTIFY_COOKIES"
ENV_SPOTIFY_QUALITY = f"{ENV_PREFIX}SPOTIFY_QUALITY"
ENV_SPOTIFY_FORMAT = f"{ENV_PREFIX}SPOTIFY_FORMAT"
ENV_OUTPUT_DIR = f"{ENV_PREFIX}OUTPUT_DIR"
ENV_TEMP_DIR = f"{ENV_PREFIX}TEMP_DIR"
ENV_VERBOSE = f"{ENV_PREFIX}VERBOSE"

# Default paths
DEFAULT_OUTPUT_DIR = "./.tracklistify/output"
DEFAULT_TEMP_DIR = "./.tracklistify/temp"

# Illegal characters in filenames
ILLEGAL_CHARS_REGEX = r'[\\/:*?"<>|;]'
ILLEGAL_CHARS_REPLACEMENT = "_"


class AudioQuality(str, Enum):
    """Audio quality options."""

    VORBIS_96 = "VORBIS_96"
    VORBIS_160 = "VORBIS_160"
    VORBIS_320 = "VORBIS_320"
    AAC_24 = "AAC_24"
    AAC_32 = "AAC_32"
    AAC_96 = "AAC_96"
    AAC_128 = "AAC_128"
    AAC_256 = "AAC_256"

    @classmethod
    def from_env(cls, value: Optional[str] = None) -> "AudioQuality":
        """Create from environment variable value."""
        if not value:
            value = os.getenv(ENV_SPOTIFY_QUALITY, "AAC_256")
        try:
            return cls(value)
        except ValueError:
            logger.warning(f"Invalid audio quality '{value}', using AAC_256")
            return cls.AAC_256


class AudioFormat(str, Enum):
    """Audio format options."""

    OGG = "ogg"
    M4A = "m4a"
    MP3 = "mp3"

    @classmethod
    def from_env(cls, value: Optional[str] = None) -> "AudioFormat":
        """Create from environment variable value."""
        if not value:
            value = os.getenv(ENV_SPOTIFY_FORMAT, "m4a")
        try:
            return cls(value.lower())
        except ValueError:
            logger.warning(f"Invalid audio format '{value}', using m4a")
            return cls.M4A


# Audio quality to format ID mapping
QUALITY_FORMAT_MAP = {
    AudioQuality.VORBIS_96: "OGG_VORBIS_96",
    AudioQuality.VORBIS_160: "OGG_VORBIS_160",
    AudioQuality.VORBIS_320: "OGG_VORBIS_320",
    AudioQuality.AAC_24: "AAC_24",
    AudioQuality.AAC_32: "AAC_32",
    AudioQuality.AAC_96: "AAC_96",
    AudioQuality.AAC_128: "AAC_128",
    AudioQuality.AAC_256: "AAC_256",
}

# Metadata tag mappings
MP4_TAGS = {
    "album": "\xa9alb",
    "album_artist": "aART",
    "artist": "\xa9ART",
    "composer": "\xa9wrt",
    "copyright": "cprt",
    "lyrics": "\xa9lyr",
    "release_date": "\xa9day",
    "title": "\xa9nam",
    "url": "\xa9url",
    "genre": "\xa9gen",
    "track_number": "trkn",
    "disc_number": "disk",
    "compilation": "cpil",
    "comment": "\xa9cmt",
}

VORBIS_TAGS = {
    "album": "ALBUM",
    "album_artist": "ALBUMARTIST",
    "artist": "ARTIST",
    "composer": "COMPOSER",
    "copyright": "COPYRIGHT",
    "lyrics": "LYRICS",
    "release_date": "YEAR",
    "title": "TITLE",
    "url": "URL",
    "genre": "GENRE",
    "track_number": "TRACKNUMBER",
    "disc_number": "DISCNUMBER",
    "compilation": "COMPILATION",
    "comment": "COMMENT",
}


class SpotifyDownloader(Downloader):
    """Spotify audio downloader."""

    # API endpoints
    SPOTIFY_HOME_URL = "https://open.spotify.com/"
    METADATA_API_URL = "https://api.spotify.com/v1/{type}/{item_id}"
    STREAM_API_URL = (
        "https://gue1-spclient.spotify.com/storage-resolve/v2/files/audio/interactive/11/"
        "{file_id}?version=10000000&product=9&platform=39&alt=json"
    )

    @classmethod
    def from_env(cls) -> "SpotifyDownloader":
        """Create SpotifyDownloader instance from environment variables."""
        return cls(
            cookies_path=os.getenv(ENV_SPOTIFY_COOKIES),
            quality=AudioQuality.from_env(),
            format=AudioFormat.from_env(),
            output_dir=os.getenv(ENV_OUTPUT_DIR, DEFAULT_OUTPUT_DIR),
            verbose=os.getenv(ENV_VERBOSE, "false").lower() == "true",
        )

    def __init__(
        self,
        cookies_path: Optional[str] = None,
        verbose: bool = False,
        quality: AudioQuality = AudioQuality.AAC_256,
        format: AudioFormat = AudioFormat.M4A,
        output_dir: Optional[str] = None,
    ):
        """Initialize Spotify downloader.

        Args:
            cookies_path: Path to Firefox/Chrome cookies file with Spotify cookies
            verbose: Enable verbose logging
            quality: Audio quality (from AudioQuality enum)
            format: Output audio format (from AudioFormat enum)
            output_dir: Optional output directory for downloaded files
        """
        self.ffmpeg_path = self.get_ffmpeg_path()
        self.verbose = verbose
        self.quality = quality
        self.format = format

        # Setup directories
        self.output_dir = Path(
            output_dir if output_dir else DEFAULT_OUTPUT_DIR
        ).expanduser()
        self.temp_dir = Path(os.getenv(ENV_TEMP_DIR, DEFAULT_TEMP_DIR)).expanduser()

        # Create directories if they don't exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        self._session = None
        self._cookies = None

        if cookies_path:
            cookies_path = Path(cookies_path).expanduser()
            self._cookies = MozillaCookieJar(str(cookies_path))
            self._cookies.load(ignore_discard=True, ignore_expires=True)

        logger.debug(
            f"Initialized SpotifyDownloader with ffmpeg at: {self.ffmpeg_path}"
        )
        logger.debug(f"Settings - Quality: {quality}, Format: {format}")
        logger.debug(f"Directories - Output: {self.output_dir}, Temp: {self.temp_dir}")

    async def _ensure_session(self):
        """Ensure aiohttp session exists with cookies."""
        if self._session is None:
            self._session = aiohttp.ClientSession(cookies=self._cookies)

    async def _get_track_metadata(self, track_id: str) -> Dict[str, Any]:
        """Get track metadata from Spotify API."""
        await self._ensure_session()
        url = self.METADATA_API_URL.format(type="tracks", item_id=track_id)

        async with self._session.get(url) as response:
            if response.status != 200:
                raise DownloadError(f"Failed to get track metadata: {response.status}")
            return await response.json()

    async def _get_stream_url(self, file_id: str) -> str:
        """Get audio stream URL."""
        await self._ensure_session()
        url = self.STREAM_API_URL.format(file_id=file_id)

        async with self._session.get(url) as response:
            if response.status != 200:
                raise DownloadError(f"Failed to get stream URL: {response.status}")
            data = await response.json()
            return data["cdnurl"][0]

    def _extract_track_id(self, url: str) -> str:
        """Extract track ID from Spotify URL."""
        patterns = [
            r"spotify:track:([a-zA-Z0-9]+)",  # URI
            r"spotify\.com/track/([a-zA-Z0-9]+)",  # Web URL
            r"spotify\.com/embed/track/([a-zA-Z0-9]+)",  # Embed URL
        ]

        for pattern in patterns:
            if match := re.search(pattern, url):
                return match.group(1)

        raise DownloadError(f"Invalid Spotify URL: {url}")

    def _clean_filename(self, filename: str) -> str:
        """Clean filename by removing illegal characters."""
        return re.sub(ILLEGAL_CHARS_REGEX, ILLEGAL_CHARS_REPLACEMENT, filename)

    def _set_metadata(self, file_path: str, metadata: Dict[str, Any]):
        """Set audio file metadata tags."""
        if self.format == AudioFormat.M4A:
            audio = MP4(file_path)
            tags = MP4_TAGS
        else:
            audio = OggVorbis(file_path)
            tags = VORBIS_TAGS

        # Map metadata to tags
        for key, tag in tags.items():
            if key == "artist":
                value = ", ".join(artist["name"] for artist in metadata["artists"])
            elif key == "album_artist":
                value = metadata["album"]["artists"][0]["name"]
            elif key == "album":
                value = metadata["album"]["name"]
            elif key == "release_date":
                value = metadata["album"]["release_date"]
            elif key == "url":
                value = metadata["external_urls"]["spotify"]
            elif key == "track_number":
                value = (metadata["track_number"], metadata["album"]["total_tracks"])
            elif key == "disc_number":
                value = (
                    metadata["disc_number"],
                    metadata["album"].get("total_discs", 1),
                )
            elif key == "genre":
                value = metadata.get("genres", [])
            else:
                value = metadata.get(key)

            if value:
                if self.format == AudioFormat.M4A:
                    if key in ("track_number", "disc_number"):
                        audio[tag] = [value]
                    else:
                        audio[tag] = [str(value)]
                else:
                    if key in ("track_number", "disc_number"):
                        audio[tag] = f"{value[0]}/{value[1]}"
                    else:
                        audio[tag] = str(value)

        # Add cover art if available
        if metadata["album"].get("images"):
            cover_url = metadata["album"]["images"][0]["url"]

            async def get_cover():
                async with self._session.get(cover_url) as response:
                    return await response.read()

            cover_data = asyncio.run(get_cover())
            if self.format == AudioFormat.M4A:
                audio["covr"] = [MP4Cover(cover_data, imageformat=MP4Cover.FORMAT_JPEG)]

        audio.save()

    async def download(self, url: str) -> Optional[str]:
        """Asynchronously download audio from Spotify URL.

        Args:
            url: Spotify track URL or URI

        Returns:
            Optional[str]: Path to downloaded audio file, or None if download failed

        Raises:
            DownloadError: If download fails
        """
        if not self._cookies:
            raise DownloadError(
                "Spotify cookies required. Please provide cookies_path."
            )

        try:
            # Clean and validate URL
            url = clean_url(url)
            track_id = self._extract_track_id(url)

            # Get track metadata
            metadata = await self._get_track_metadata(track_id)

            # Get stream URL
            stream_url = await self._get_stream_url(track_id)

            # Prepare output path
            filename = self._clean_filename(
                f"{metadata['artists'][0]['name']} - {metadata['name']}.{self.format}"
            )
            output_path = self.output_dir / filename

            # Download audio stream
            temp_path = self.temp_dir / f"{track_id}.temp.{self.format}"
            async with self._session.get(stream_url) as response:
                if response.status != 200:
                    raise DownloadError(f"Failed to download audio: {response.status}")

                with open(temp_path, "wb") as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)

            # Convert to desired format if needed
            if self.format != AudioFormat.OGG:
                cmd = [
                    self.ffmpeg_path,
                    "-i",
                    str(temp_path),
                    "-c:a",
                    "aac" if self.format == AudioFormat.M4A else "libmp3lame",
                    "-b:a",
                    self.quality.value.split("_")[-1] + "k",
                    "-metadata",
                    f"title={metadata['name']}",
                    "-metadata",
                    f"artist={metadata['artists'][0]['name']}",
                    "-y",
                    str(output_path),
                ]
                subprocess.run(cmd, check=True, capture_output=True)
                temp_path.unlink()
            else:
                temp_path.rename(output_path)

            # Set metadata
            self._set_metadata(output_path, metadata)

            logger.info(
                f"Downloaded: {metadata['name']} by {metadata['artists'][0]['name']}"
            )
            return str(output_path)

        except Exception as e:
            raise DownloadError(f"Failed to download from Spotify: {str(e)}")

    async def close(self):
        """Close the downloader session."""
        if self._session:
            await self._session.close()
            self._session = None
