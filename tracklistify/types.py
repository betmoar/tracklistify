"""Type definitions for Tracklistify.

This module defines all type definitions used throughout the application, including:
- Type variables for generic typing
- TypedDict definitions for configuration and data structures
- Protocol definitions for core interfaces
- Comprehensive type hints and documentation
"""

from typing import TypeVar, Dict, List, Optional, TypedDict, Literal, Protocol, AsyncIterator, Any
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

# Cache types
CacheMetadata = TypedDict('CacheMetadata', {
    'ttl': int,
    'compression': bool,
    'compression_level': int,
    'format': str,
    'created_at': float,
    'last_accessed': float,
    'access_count': int,
    'size_bytes': int
})

CacheEntry = TypedDict('CacheEntry', {
    'value': T,
    'timestamp': float,
    'metadata': CacheMetadata
})

class CacheStorage(Protocol[T]):
    """Protocol for cache storage backends."""
    
    async def read(self, key: str) -> Optional[CacheEntry[T]]:
        """Read value from storage."""
        ...
        
    async def write(self, key: str, entry: CacheEntry[T]) -> None:
        """Write value to storage."""
        ...
        
    async def delete(self, key: str) -> None:
        """Delete value from storage."""
        ...
        
    async def clear(self) -> None:
        """Clear all values from storage."""
        ...
        
    async def cleanup(self, max_age: Optional[int] = None) -> int:
        """Clean up old entries."""
        ...

class InvalidationStrategy(Protocol):
    """Protocol for cache invalidation strategies."""
    
    def should_invalidate(self, entry: CacheEntry[Any]) -> bool:
        """Check if entry should be invalidated."""
        ...
        
    def cleanup(self, storage: CacheStorage[Any]) -> None:
        """Clean up invalid entries."""
        ...

class Cache(Protocol[T]):
    """Enhanced cache interface with comprehensive type hints."""
    
    async def get(self, key: str) -> Optional[T]:
        """Get value from cache with type safety."""
        ...
        
    async def set(
        self, 
        key: str, 
        value: T, 
        ttl: Optional[int] = None,
        compression: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Set value in cache with validation."""
        ...
        
    async def delete(self, key: str) -> None:
        """Delete value from cache."""
        ...
        
    async def clear(self) -> None:
        """Clear all values from cache."""
        ...
        
    async def cleanup(self, max_age: Optional[int] = None) -> int:
        """Clean up old entries.
        
        Returns:
            Number of entries cleaned up
        """
        ...
        
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        ...

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
