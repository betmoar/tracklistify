"""Type definitions for Tracklistify.

This module defines all type definitions used throughout the application, including:
- Type variables for generic typing
- TypedDict definitions for configuration and data structures
- Protocol definitions for core interfaces
- Comprehensive type hints and documentation
"""

# Standard library imports
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Dict,
    Generic,
    List,
    Optional,
    Protocol,
    TypedDict,
    TypeVar,
)

# Generic type variables
T = TypeVar("T")
ProviderT = TypeVar("ProviderT", bound="TrackIdentificationProvider")


# Configuration types
class TrackIdentificationConfigDict(TypedDict):
    """Track identification configuration type."""

    # Track identification settings
    segment_length: int
    min_confidence: float
    time_threshold: float

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
    cache_max_age: int
    cache_min_free_space: int

    # Output settings
    output_format: str

    # Download settings
    download_quality: str
    download_format: str
    download_max_retries: int
    download_cache_enabled: bool

    # Base config settings
    output_dir: str
    cache_dir: str
    temp_dir: str
    verbose: bool
    debug: bool


# Track types
class TrackLinks(TypedDict, total=False):
    """Canonical per-platform track URLs nested under ``Track.metadata['links']``.

    ``spotify`` / ``deezer`` / ``tidal`` / ``apple`` / ``beatport`` are
    *resolved canonical* links (set by the enrichment passes); ``shazam`` is
    Shazam's own track page. ``spotify_search`` / ``deezer_search`` are the
    *search* URLs Shazam ships with a match — kept distinct from the
    canonical keys so a consumer can tell a resolved track link from a
    search. ``apple_music_id`` stays flat on ``TrackMetadata`` (an id, not a
    URL). All optional: a track with no links omits ``links`` entirely.
    """

    shazam: str
    spotify: str
    spotify_search: str
    deezer: str
    deezer_search: str
    tidal: str
    apple: str
    beatport: str


class TrackMetadata(TypedDict, total=False):
    """The contract for ``Track.metadata`` — the per-track extras dict.

    ``total=False``: no provider fills every key, and a track with no extras
    has an empty dict. This TypedDict names the keys and types in one place
    so writers (``_extra_metadata``, the three enrichment passes) go through
    a checked name and a typo is a mypy error rather than a silent new key
    in the JSON output (Q2, 2026-08 code-quality review).

    Flat keys plus a nested ``links`` object. The Beatport enrichment fields
    (``bpm``, ``key``, ``genre``, ``sub_genre``, ``remixers``,
    ``catalog_number``, ``beatport_id``) are DJ metadata no other source
    carries. ``*_match`` values record which lookup path set the
    corresponding link/id (``'isrc'`` / ``'search'`` / ``'musicbrainz'``)
    so a consumer can weigh a fuzzy hit.
    """

    # --- identification (Shazam / ACRCloud via _extra_metadata) ---
    isrc: str
    album: str
    label: str
    release_date: str
    genres: List[str]
    shazam_id: str
    apple_music_id: str
    artwork_url: str

    # --- Spotify enrichment ---
    spotify_id: str
    spotify_match: str

    # --- MusicBrainz enrichment (writes into links; may set spotify_match) ---

    # --- Beatport enrichment ---
    beatport_id: str
    bpm: int
    key: str
    genre: str
    sub_genre: str
    remixers: List[str]
    catalog_number: str
    beatport_match: str

    # --- nested canonical links (all optional) ---
    links: TrackLinks


class ProviderResponse(TypedDict):
    """Provider response type."""

    success: bool
    error: Optional[str]
    # Provider-response payloads are third-party JSON of varying shape; this
    # is the raw enrichment dict _extra_metadata consumes, NOT a TrackMetadata.
    metadata: Optional[Dict[str, object]]
    raw_response: Dict


# Cache types
class CacheMetadata(TypedDict, total=False):
    """Cache entry metadata."""

    created_at: str
    created: float
    last_accessed: float
    accessed_at: Optional[str]
    size: int
    hits: int
    ttl: Optional[int]
    access_count: int
    compression: bool


class CacheEntry(Dict, Generic[T]):
    """Cache entry with metadata that maintains dict interface."""

    def __init__(self, key: str, value: T, metadata: CacheMetadata):
        """Initialize cache entry."""
        super().__init__()
        self["key"] = key
        self["value"] = value
        self["metadata"] = metadata

    @property
    def key(self) -> str:
        """Get cache key."""
        return self["key"]

    @key.setter
    def key(self, value: str) -> None:
        """Set cache key."""
        self["key"] = value

    @property
    def value(self) -> T:
        """Get cache value."""
        return self["value"]

    @value.setter
    def value(self, value: T) -> None:
        """Set cache value."""
        self["value"] = value

    @property
    def metadata(self) -> CacheMetadata:
        """Get cache metadata."""
        return self["metadata"]

    @metadata.setter
    def metadata(self, value: CacheMetadata) -> None:
        """Set cache metadata."""
        self["metadata"] = value


class CacheStorage(Protocol[T]):
    """Cache storage protocol."""

    async def get(self, key: str) -> Optional[CacheEntry[T]]: ...
    async def set(
        self, key: str, entry: CacheEntry[T], compression: bool = False
    ) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def clear(self) -> None: ...
    async def cleanup(self, max_age: Optional[int] = None) -> int: ...
    async def read(self, key: str) -> Optional[CacheEntry[T]]: ...
    async def write(self, key: str, entry: CacheEntry[T]) -> None: ...
    async def list_keys(self) -> List[str]: ...


class InvalidationStrategy(Protocol):
    """Cache invalidation strategy protocol."""

    async def is_valid(self, entry: CacheEntry) -> bool: ...
    async def update_metadata(self, entry: CacheEntry) -> CacheEntry: ...
    async def cleanup(self, storage: CacheStorage) -> None: ...
    def should_invalidate(self, entry: CacheEntry) -> bool: ...


class Cache(Protocol[T]):
    """Cache protocol."""

    def get(self, key: str) -> Optional[T]: ...
    def set(self, key: str, value: T) -> None: ...
    def delete(self, key: str) -> None: ...
    def clear(self) -> None: ...


# Protocol definitions
class TrackIdentificationProvider(Protocol):
    """Protocol defining the interface for track identification providers."""

    async def identify_track(
        self, audio_path: Path, start_time: float = 0
    ) -> ProviderResponse:
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


class ConfigProvider(Protocol):
    """Config provider interface to break circular dependencies"""

    @property
    def primary_provider(self) -> str: ...
    @property
    def fallback_enabled(self) -> bool: ...
    @property
    def fallback_providers(self) -> list[str]: ...


@dataclass
class AudioSegment:
    """Represents an audio segment for processing."""

    file_path: str
    start_time: int = 0
    duration: int = 60
