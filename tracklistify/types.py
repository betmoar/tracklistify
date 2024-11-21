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

# Configuration types
class TrackIdentificationConfigDict(TypedDict):
    """Track identification configuration type."""
    # Track identification settings
    segment_length: int
    min_confidence: float
    time_threshold: float
    max_duplicates: int

    # Provider settings
    primary_provider: str
    fallback_enabled: bool
    fallback_providers: List[str]
    acrcloud_host: str
    acrcloud_timeout: int
    shazam_enabled: bool
    shazam_timeout: int
    spotify_timeout: int
    retry_strategy: str
    retry_max_attempts: int
    retry_base_delay: float
    retry_max_delay: float

    # Rate limiting
    rate_limit_enabled: bool
    max_requests_per_minute: int

    # Cache settings
    cache_enabled: bool
    cache_ttl: int
    cache_max_size: int
    cache_storage_format: str
    cache_compression_enabled: bool
    cache_compression_level: int
    cache_cleanup_enabled: bool
    cache_cleanup_interval: int
    cache_max_age: int
    cache_min_free_space: int

    # Output settings
    output_format: str

    # Download settings
    download_quality: str
    download_format: str
    download_max_retries: int

    # Base config settings
    output_dir: str
    cache_dir: str
    temp_dir: str
    verbose: bool
    debug: bool

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
