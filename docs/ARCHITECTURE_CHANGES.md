# Architecture Changes & API Documentation

**Version**: Post-Phases 3-6 Implementation
**Date**: 2025-11-22

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [New Modules & Files](#new-modules--files)
3. [Modified Modules](#modified-modules)
4. [New Functions & Classes](#new-functions--classes)
5. [API Changes](#api-changes)
6. [Design Patterns Implemented](#design-patterns-implemented)
7. [Constants Reference](#constants-reference)
8. [Test Architecture](#test-architecture)

---

## Architecture Overview

### High-Level Structure

```
tracklistify/
├── core/                  # Core application logic
│   ├── base.py           # AsyncApp - main orchestrator
│   ├── track.py          # Track data models
│   ├── types.py          # Type definitions & protocols
│   └── exceptions.py     # Centralized exception hierarchy
│
├── providers/            # Track identification providers
│   ├── base.py          # Abstract base with context manager support [MODIFIED]
│   ├── factory.py       # Thread-safe provider factory [MODIFIED]
│   ├── shazam.py        # Shazam integration [MODIFIED]
│   ├── acrcloud.py      # ACRCloud integration
│   └── spotify.py       # Spotify metadata enrichment
│
├── cache/               # Caching system
│   ├── __init__.py     # Cache exports, removed dead code [MODIFIED]
│   ├── base.py         # Core cache implementation
│   ├── factory.py      # Thread-safe cache factory [MODIFIED]
│   ├── index.py        # Cache index [MODIFIED]
│   ├── storage.py      # JSON storage [MODIFIED]
│   └── invalidation.py # Invalidation strategies
│
├── config/              # Configuration management
│   ├── base.py         # Config dataclasses [MODIFIED]
│   ├── factory.py      # Thread-safe config factory [MODIFIED]
│   └── validation.py   # Validation utilities
│
├── utils/               # Utilities
│   ├── constants.py    # Centralized constants [NEW]
│   ├── decorators.py   # Memoization with stable hashing [MODIFIED]
│   ├── identification.py # Track identification [MODIFIED]
│   ├── validation.py   # URL validation with DRY helper [MODIFIED]
│   ├── time_formatter.py # Time formatting [MODIFIED]
│   ├── rate_limiter.py # Rate limiting [MODIFIED]
│   └── logger.py       # Logging utilities
│
└── downloaders/         # Audio downloaders
    ├── spotify.py      # Spotify downloader [MODIFIED]
    └── ...
```

---

## New Modules & Files

### 1. `src/tracklistify/utils/constants.py` [NEW]

Centralized constants module replacing magic numbers throughout the codebase.

```python
"""
Centralized constants for the tracklistify package.
"""

# Time constants
SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600
MILLISECONDS_PER_SECOND = 1000

# Progress display
DEFAULT_PROGRESS_BAR_WIDTH = 30
TERMINAL_LINE_WIDTH = 80
PERCENTAGE_MULTIPLIER = 100

# Audio processing
DEFAULT_SEGMENT_PADDING = 0.5
MIN_SEGMENT_FILE_SIZE = 1000
DEFAULT_THREAD_POOL_WORKERS = 4
FFMPEG_MP3_QUALITY = 5

# Cache defaults
DEFAULT_CACHE_TTL = 3600
DEFAULT_CACHE_MAX_SIZE = 1_000_000

# Rate limiter defaults
DEFAULT_RATE_LIMIT_TIMEOUT = 30.0
CIRCUIT_BREAKER_RESET_TIMEOUT = 60.0
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5
TOKEN_REFILL_SLEEP = 0.01
REFILL_INTERVAL_THRESHOLD = 1.0

# Provider rate limits (RPM)
SHAZAM_DEFAULT_RPM = 25
ACRCLOUD_DEFAULT_RPM = 30
ACRCLOUD_DEFAULT_CONCURRENT = 5
SPOTIFY_DEFAULT_RPM = 120
SPOTIFY_DEFAULT_CONCURRENT = 20
GLOBAL_DEFAULT_RPM = 25
GLOBAL_DEFAULT_CONCURRENT = 2

# Shazam scoring
SHAZAM_COOLDOWN_DEFAULT = 2.25
SHAZAM_SKEW_CAP = 0.1
SHAZAM_SCORE_MULTIPLIER = 100
SHAZAM_FREQ_WEIGHT = 0.6
SHAZAM_TIME_WEIGHT = 0.4

# Security
MIN_PASSWORD_LENGTH = 8
MASK_ASTERISK_COUNT = 5
ROTATION_INTERVAL_DAYS = 90

# Logging
LOG_BACKUP_COUNT = 5
LOG_MAX_SIZE_BYTES = 10 * 1024 * 1024

# API constants
SPOTIFY_BATCH_SIZE = 100
SPOTIFY_SEARCH_LIMIT = 5
SPOTIFY_DEFAULT_RETRY_AFTER = 60
ACRCLOUD_SUCCESS_CODE = 2000
ACRCLOUD_DEFAULT_TIMEOUT = 10

# Confidence
DEFAULT_CONFIDENCE = 100.0
MAX_CONFIDENCE = 100

# Hash
STABLE_HASH_LENGTH = 16
```

---

## Modified Modules

### 1. `providers/base.py` - Async Context Manager Protocol

**New Methods Added:**

```python
class TrackIdentificationProvider(ABC):
    """Abstract base class for track identification providers.

    Supports async context manager protocol for proper resource cleanup:

        async with SomeProvider() as provider:
            result = await provider.identify_track(segment)
    """

    @abstractmethod
    async def identify_track(self, audio_segment) -> Optional[Dict[str, Any]]:
        """Identify a track from an audio segment."""
        pass

    @abstractmethod
    async def enrich_metadata(self, track_info: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich track metadata with additional information."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Cleanup resources."""
        pass

    # NEW: Context manager support
    async def __aenter__(self) -> "TrackIdentificationProvider":
        """Enter async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context manager, ensuring cleanup."""
        await self.close()


class MetadataProvider(ABC):
    """Base interface for metadata providers.

    Supports async context manager protocol for proper resource cleanup.
    """
    # ... same pattern as TrackIdentificationProvider
```

**Usage:**
```python
# Old way (still works)
provider = ShazamProvider()
try:
    result = await provider.identify_track(segment)
finally:
    await provider.close()

# New way (recommended)
async with ShazamProvider() as provider:
    result = await provider.identify_track(segment)
```

---

### 2. `config/factory.py` - Thread-Safe Singleton

**New Implementation:**

```python
import threading

_config_lock = threading.Lock()

class ConfigFactory:
    """Thread-safe configuration factory."""

    _instances: Dict[Type[BaseConfig], BaseConfig] = {}

    @classmethod
    def get_config(
        cls,
        config_type: Type[T] = TrackIdentificationConfig,
        force_refresh: bool = False
    ) -> T:
        """Get configuration instance (thread-safe).

        Uses double-checked locking pattern for thread safety.

        Args:
            config_type: Configuration class to instantiate
            force_refresh: Force recreation of config instance

        Returns:
            Configuration instance
        """
        # Fast path: instance already exists
        if not force_refresh and config_type in cls._instances:
            return cls._instances[config_type]

        # Slow path: need to create (thread-safe)
        with _config_lock:
            # Double-check inside lock
            if force_refresh or config_type not in cls._instances:
                cls._instances[config_type] = config_type()
            return cls._instances[config_type]
```

---

### 3. `cache/factory.py` - Thread-Safe Cache Factory

**New Functions:**

```python
import threading

_cache_instance = None
_cache_lock = threading.Lock()

def get_cache() -> BaseCache:
    """Get global cache instance (thread-safe).

    Uses double-checked locking pattern.

    Returns:
        BaseCache: Global cache instance
    """
    global _cache_instance

    if _cache_instance is not None:
        return _cache_instance

    with _cache_lock:
        if _cache_instance is None:
            _cache_instance = create_cache()

    return _cache_instance


def clear_cache() -> None:
    """Clear the cached instance to force recreation.

    Thread-safe cache clearing.
    """
    global _cache_instance
    with _cache_lock:
        _cache_instance = None
```

---

### 4. `providers/factory.py` - Thread-Safe Provider Factory

**New Functions:**

```python
import threading

_provider_factory = None
_provider_lock = threading.Lock()

def create_provider_factory() -> "ProviderFactory":
    """Create and return a provider factory instance (thread-safe).

    Uses double-checked locking pattern.

    Returns:
        ProviderFactory: Global provider factory instance
    """
    global _provider_factory

    if _provider_factory is not None:
        return _provider_factory

    with _provider_lock:
        if _provider_factory is None:
            _provider_factory = ProviderFactory()

    return _provider_factory


def clear_provider_cache() -> None:
    """Clear cached providers (thread-safe)."""
    global _provider_factory
    with _provider_lock:
        if _provider_factory is not None:
            _provider_factory.clear_cache()
            _provider_factory = None
```

---

### 5. `utils/decorators.py` - Stable Hashing

**New Function:**

```python
import hashlib
from tracklistify.utils.constants import STABLE_HASH_LENGTH, MILLISECONDS_PER_SECOND

def _stable_hash(data: str) -> str:
    """Create a stable hash from string data.

    Uses SHA-256 for deterministic hashing across Python runs.
    Unlike built-in hash(), this is stable and has very low collision risk.

    Args:
        data: String to hash

    Returns:
        Hexadecimal hash string (first 16 chars)
    """
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:STABLE_HASH_LENGTH]
```

**Modified `memoize` decorator:**
```python
def memoize(ttl: Optional[int] = None) -> Callable:
    """Memoize decorator with stable hashing.

    Uses SHA-256 for cache keys instead of built-in hash()
    for consistency across Python runs.
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        _local_cache: Dict[str, Dict[str, Any]] = {}

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            # Generate stable cache key
            args_str = str(args) + str(sorted(kwargs.items()))
            key = f"{func.__name__}_{_stable_hash(args_str)}"

            # ... rest of implementation

            # Use MILLISECONDS_PER_SECOND constant
            computation_time = (time.monotonic() - start_time) * MILLISECONDS_PER_SECOND
```

---

### 6. `utils/validation.py` - DRY URL Validation

**New Constants:**

```python
# Platform domain configurations
YOUTUBE_DOMAINS = ["youtube.com", "youtu.be"]
SOUNDCLOUD_DOMAINS = ["soundcloud.com"]
MIXCLOUD_DOMAINS = ["mixcloud.com"]
```

**New Helper Function:**

```python
def _is_platform_url(url: str, domains: List[str]) -> bool:
    """Check if a URL belongs to a specific platform.

    DRY helper that centralizes URL validation logic.

    Args:
        url: URL to check
        domains: List of base domain names (e.g., ["youtube.com", "youtu.be"])

    Returns:
        True if URL belongs to platform, False otherwise
    """
    if not url:
        return False

    result = validate_input(url)
    if not result:
        return False

    validated, is_local = result
    if is_local:
        return False

    host = urlparse(validated).netloc.lower()

    for domain in domains:
        if host == domain or host == f"www.{domain}":
            return True
        if host.endswith(f".{domain}"):
            return True

    return False
```

**Refactored Functions:**

```python
def is_youtube_url(url: str) -> bool:
    """Check if URL is a valid YouTube URL."""
    return _is_platform_url(url, YOUTUBE_DOMAINS)

def is_soundcloud_url(url: str) -> bool:
    """Check if URL is a valid SoundCloud URL."""
    return _is_platform_url(url, SOUNDCLOUD_DOMAINS)

def is_mixcloud_url(url: str) -> bool:
    """Check if URL is a valid Mixcloud URL."""
    return _is_platform_url(url, MIXCLOUD_DOMAINS)
```

---

### 7. `utils/identification.py` - Safe Array Access

**Modified Code:**

```python
# Before (unsafe)
metadata = track_info.get("metadata", {}).get("music", [{}])[0]
artist = metadata.get("artists", [{}])[0].get("name", "Unknown")

# After (safe)
music_list = track_info.get("metadata", {}).get("music", [])
if not music_list:
    logger.error("No track metadata found")
    continue
metadata = music_list[0] if music_list else {}

artists_list = metadata.get("artists", [])
artist_name = (
    artists_list[0].get("name", "Unknown Artist")
    if artists_list
    else "Unknown Artist"
)
```

---

### 8. `utils/time_formatter.py` - Using Constants

```python
"""Time formatting utilities."""

from tracklistify.utils.constants import SECONDS_PER_HOUR, SECONDS_PER_MINUTE


def format_seconds_to_hhmmss(seconds: float) -> str:
    """Convert seconds to HH:MM:SS format.

    Args:
        seconds: Time in seconds to format

    Returns:
        String in HH:MM:SS format
    """
    hours = int(seconds // SECONDS_PER_HOUR)
    minutes = int((seconds % SECONDS_PER_HOUR) // SECONDS_PER_MINUTE)
    secs = int(seconds % SECONDS_PER_MINUTE)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"
```

---

## New Functions & Classes

### Summary Table

| Module | Function/Class | Type | Description |
|--------|---------------|------|-------------|
| `utils/constants.py` | Multiple constants | Constants | 60+ named constants |
| `utils/decorators.py` | `_stable_hash()` | Function | SHA-256 based stable hashing |
| `utils/validation.py` | `_is_platform_url()` | Function | DRY URL validation helper |
| `utils/validation.py` | `YOUTUBE_DOMAINS` | Constant | YouTube domain list |
| `utils/validation.py` | `SOUNDCLOUD_DOMAINS` | Constant | SoundCloud domain list |
| `utils/validation.py` | `MIXCLOUD_DOMAINS` | Constant | Mixcloud domain list |
| `providers/base.py` | `__aenter__()` | Method | Context manager entry |
| `providers/base.py` | `__aexit__()` | Method | Context manager exit |
| `config/factory.py` | `_config_lock` | Lock | Thread safety lock |
| `cache/factory.py` | `_cache_lock` | Lock | Thread safety lock |
| `cache/factory.py` | `clear_cache()` | Function | Clear cached instance |
| `providers/factory.py` | `_provider_lock` | Lock | Thread safety lock |

---

## API Changes

### Breaking Changes

**None** - All changes are backward compatible.

### New APIs

#### 1. Context Manager Protocol for Providers

```python
# All providers now support async context manager
async with ShazamProvider() as provider:
    result = await provider.identify_track(segment)
# Automatically calls close() on exit
```

#### 2. Thread-Safe Factory Functions

```python
from tracklistify.config import get_config
from tracklistify.cache import get_cache
from tracklistify.providers.factory import create_provider_factory

# All are now thread-safe with double-checked locking
config = get_config()
cache = get_cache()
factory = create_provider_factory()
```

#### 3. Cache Clearing

```python
from tracklistify.cache.factory import clear_cache
from tracklistify.providers.factory import clear_provider_cache

# Force recreation of singletons
clear_cache()
clear_provider_cache()
```

#### 4. Platform URL Validation

```python
from tracklistify.utils.validation import (
    is_youtube_url,
    is_soundcloud_url,
    is_mixcloud_url,
    _is_platform_url,  # For custom platforms
    YOUTUBE_DOMAINS,
    SOUNDCLOUD_DOMAINS,
    MIXCLOUD_DOMAINS,
)

# Use built-in validators
if is_youtube_url(url):
    ...

# Or create custom validator
CUSTOM_DOMAINS = ["custom.com", "www.custom.com"]
if _is_platform_url(url, CUSTOM_DOMAINS):
    ...
```

#### 5. Constants Import

```python
from tracklistify.utils.constants import (
    # Time
    SECONDS_PER_HOUR,
    SECONDS_PER_MINUTE,
    MILLISECONDS_PER_SECOND,

    # Cache
    DEFAULT_CACHE_TTL,
    DEFAULT_CACHE_MAX_SIZE,

    # Rate limiting
    SHAZAM_DEFAULT_RPM,
    CIRCUIT_BREAKER_FAILURE_THRESHOLD,

    # And many more...
)
```

---

## Design Patterns Implemented

### 1. Double-Checked Locking (Thread-Safe Singleton)

**Location**: `config/factory.py`, `cache/factory.py`, `providers/factory.py`

```python
_lock = threading.Lock()
_instance = None

def get_instance():
    global _instance

    # Fast path (no lock needed)
    if _instance is not None:
        return _instance

    # Slow path (thread-safe creation)
    with _lock:
        # Double-check inside lock
        if _instance is None:
            _instance = create_instance()

    return _instance
```

### 2. Async Context Manager Protocol

**Location**: `providers/base.py`

```python
class TrackIdentificationProvider(ABC):
    async def __aenter__(self) -> "TrackIdentificationProvider":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
```

### 3. Template Method Pattern

**Location**: `config/base.py`

```python
class BaseConfig:
    def __post_init__(self):
        self._setup_validation()  # Hook for subclasses
        self._validate()           # Hook for subclasses

    def _setup_validation(self) -> None:
        """Template method - override in subclasses."""
        pass

    def _validate(self) -> None:
        """Template method - override in subclasses."""
        pass
```

### 4. Strategy Pattern (Existing)

**Location**: `cache/invalidation.py`

Already implemented for cache invalidation strategies.

### 5. Factory Pattern (Enhanced)

**Location**: `providers/factory.py`, `cache/factory.py`

Enhanced with thread-safety.

---

## Constants Reference

### Time Constants
| Constant | Value | Usage |
|----------|-------|-------|
| `SECONDS_PER_MINUTE` | 60 | Time conversions |
| `SECONDS_PER_HOUR` | 3600 | Time conversions |
| `MILLISECONDS_PER_SECOND` | 1000 | Performance timing |

### Rate Limiting
| Constant | Value | Usage |
|----------|-------|-------|
| `SHAZAM_DEFAULT_RPM` | 25 | Shazam API limit |
| `ACRCLOUD_DEFAULT_RPM` | 30 | ACRCloud API limit |
| `SPOTIFY_DEFAULT_RPM` | 120 | Spotify API limit |
| `CIRCUIT_BREAKER_FAILURE_THRESHOLD` | 5 | Failures before open |
| `CIRCUIT_BREAKER_RESET_TIMEOUT` | 60.0 | Reset timeout |

### Cache
| Constant | Value | Usage |
|----------|-------|-------|
| `DEFAULT_CACHE_TTL` | 3600 | Default TTL (1 hour) |
| `DEFAULT_CACHE_MAX_SIZE` | 1,000,000 | Max entries |

### Audio Processing
| Constant | Value | Usage |
|----------|-------|-------|
| `DEFAULT_SEGMENT_PADDING` | 0.5 | Segment padding (seconds) |
| `MIN_SEGMENT_FILE_SIZE` | 1000 | Min valid segment (bytes) |
| `FFMPEG_MP3_QUALITY` | 5 | MP3 quality (0-9 scale) |

---

## Test Architecture

### New Test Files

| File | Tests | Coverage |
|------|-------|----------|
| `test_singleton_thread_safety.py` | 14 | Thread-safe singletons |
| `test_phase4_fixes.py` | 7 | Stable hashing, SimpleLimiter |
| `test_time_consistency.py` | 8 | time.monotonic() usage |
| `test_empty_methods.py` | 5 | Template methods |
| `test_type_hints.py` | 7 | Type annotations |
| `test_code_organization.py` | 8 | Module-level imports |
| `test_error_handling.py` | 4 | Exception handling |
| `test_input_validation.py` | 5 | Safe array access |
| `test_resource_management.py` | 8 | Context managers |
| `test_phase6_polish.py` | 17 | Constants, DRY |

### Test Categories

1. **Static Analysis Tests** - Verify code structure without execution
2. **Unit Tests** - Test individual functions/methods
3. **Integration Tests** - Test component interactions
4. **Thread Safety Tests** - Verify concurrent access patterns

---

## Migration Guide

### For Developers

1. **Use context managers for providers**:
   ```python
   async with ShazamProvider() as provider:
       result = await provider.identify_track(segment)
   ```

2. **Import constants instead of magic numbers**:
   ```python
   from tracklistify.utils.constants import DEFAULT_CACHE_TTL
   ```

3. **Use stable hashing for cache keys**:
   ```python
   from tracklistify.utils.decorators import _stable_hash
   key = _stable_hash(data)
   ```

4. **Use time.monotonic() for elapsed time**:
   ```python
   start = time.monotonic()
   # ... operation ...
   elapsed = time.monotonic() - start
   ```

5. **Use time.time() for timestamps**:
   ```python
   timestamp = time.time()  # For storage/persistence
   ```

---

*Documentation generated: 2025-11-22*
