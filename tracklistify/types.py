"""Type definitions for Tracklistify.

This module defines all type definitions used throughout the application, including:
- Type variables for generic typing
- TypedDict definitions for configuration and data structures
- Protocol definitions for core interfaces
- Comprehensive type hints and documentation
"""

from typing import TypeVar, Dict, List, Optional, TypedDict, Literal, Protocol, AsyncIterator
from pathlib import Path

# Generic type variables
T = TypeVar('T')
ProviderT = TypeVar('ProviderT', bound='TrackIdentificationProvider')
DownloaderT = TypeVar('DownloaderT', bound='Downloader')

# Provider configuration types
class ProviderConfigDict(TypedDict):
    """Provider configuration type."""
    primary_provider: str
    fallback_enabled: bool
    fallback_providers: List[str]
    acrcloud_host: str
    acrcloud_timeout: int
    shazam_enabled: bool
    shazam_timeout: int
    spotify_timeout: int

class TrackConfigDict(TypedDict):
    """Track configuration type."""
    segment_length: int
    min_confidence: float
    time_threshold: int
    max_duplicates: int

class CacheConfigDict(TypedDict):
    """Cache configuration type."""
    enabled: bool
    ttl: int
    max_size: int

class OutputConfigDict(TypedDict):
    """Output configuration type."""
    directory: str
    format: Literal["json", "markdown", "m3u"]

class DownloadConfigDict(TypedDict):
    """Download configuration type."""
    quality: str
    format: str
    temp_dir: str
    max_retries: int

class AppConfigDict(TypedDict):
    """Application configuration type."""
    log_level: str
    log_file: Optional[str]

class ConfigDict(TypedDict):
    """Global configuration type."""
    providers: ProviderConfigDict
    track: TrackConfigDict
    cache: CacheConfigDict
    output: OutputConfigDict
    app: AppConfigDict
    download: DownloadConfigDict

# Track types
class TrackMetadata(TypedDict):
    """Track metadata type."""
    song_name: str
    artist: str
    album: Optional[str]
    duration: Optional[float]
    genre: Optional[str]
    year: Optional[int]
    confidence: float
    time_in_mix: str

class ProviderResponse(TypedDict):
    """Provider response type."""
    success: bool
    error: Optional[str]
    metadata: Optional[TrackMetadata]
    raw_response: Dict

# Downloader types
class DownloadResult(TypedDict):
    """Download result type."""
    success: bool
    file_path: Optional[str]
    error: Optional[str]
    duration: Optional[float]
    format: str
    size: int

class DownloadProgress(TypedDict):
    """Download progress type."""
    status: Literal["downloading", "converting", "complete", "error"]
    progress: float  # 0-100
    speed: Optional[str]  # e.g., "1.2MB/s"
    eta: Optional[str]  # e.g., "00:01:23"
    size: Optional[str]  # e.g., "12.3MB"
    error: Optional[str]

# Protocol definitions
class TrackIdentificationProvider(Protocol):
    """Protocol defining the interface for track identification providers."""
    
    async def identify_track(self, audio_path: Path, start_time: float = 0) -> ProviderResponse:
        """Identify a track from an audio file.
        
        Args:
            audio_path: Path to the audio file
            start_time: Start time in seconds for identification
            
        Returns:
            ProviderResponse containing identification results
        """
        ...

    async def validate_credentials(self) -> bool:
        """Validate provider credentials.
        
        Returns:
            True if credentials are valid, False otherwise
        """
        ...

class Downloader(Protocol):
    """Protocol defining the interface for audio downloaders."""
    
    async def download(self, url: str, output_path: Path) -> DownloadResult:
        """Download audio from a URL.
        
        Args:
            url: URL to download from
            output_path: Path to save the downloaded file
            
        Returns:
            DownloadResult containing download status and metadata
        """
        ...
    
    async def get_progress(self) -> AsyncIterator[DownloadProgress]:
        """Get download progress updates.
        
        Yields:
            DownloadProgress updates
        """
        ...

class Cache(Protocol):
    """Protocol defining the interface for caching."""
    
    async def get(self, key: str) -> Optional[T]:
        """Get a value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value if exists, None otherwise
        """
        ...
    
    async def set(self, key: str, value: T, ttl: Optional[int] = None) -> None:
        """Set a value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds
        """
        ...
    
    async def delete(self, key: str) -> None:
        """Delete a value from cache.
        
        Args:
            key: Cache key to delete
        """
        ...
    
    async def clear(self) -> None:
        """Clear all cached values."""
        ...
