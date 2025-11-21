# CLAUDE.md - Tracklistify AI Assistant Guide

This document provides comprehensive guidance for AI assistants working with the Tracklistify codebase. It covers project structure, development workflows, coding conventions, and best practices.

## Table of Contents

- [Project Overview](#project-overview)
- [Codebase Structure](#codebase-structure)
- [Architecture and Design Patterns](#architecture-and-design-patterns)
- [Development Workflow](#development-workflow)
- [Code Conventions and Style](#code-conventions-and-style)
- [Key Utilities and Patterns](#key-utilities-and-patterns)
- [Testing Guidelines](#testing-guidelines)
- [Configuration Management](#configuration-management)
- [Common Tasks](#common-tasks)
- [Important Notes](#important-notes)

## Project Overview

**Tracklistify** is an automatic tracklist generator for DJ mixes and audio streams. It identifies tracks using multiple providers (Shazam, ACRCloud) and generates formatted playlists with high accuracy.

### Key Information
- **Language**: Python 3.11-3.13
- **Package Manager**: uv (modern Python package/project manager)
- **Build System**: uv_build
- **License**: MIT
- **Version**: 0.7.0

### Core Capabilities
- Multi-provider track identification (Shazam, ACRCloud, Spotify)
- Smart provider fallback system with rate limiting
- Multiple output formats (JSON, Markdown, M3U, CSV, XML, Rekordbox)
- Asynchronous processing with circuit breaker pattern
- Intelligent caching system with multiple invalidation strategies
- Batch processing for multiple files
- Support for YouTube, Mixcloud, SoundCloud platforms

### System Requirements
- Python 3.11 or higher
- ffmpeg (for audio processing)
- git
- uv package manager

## Codebase Structure

```
tracklistify/
├── src/tracklistify/          # Main package source
│   ├── __init__.py            # Package initialization
│   ├── cli.py                 # Command-line interface (main entry point)
│   ├── dev.py                 # Development utilities
│   │
│   ├── core/                  # Core application logic
│   │   ├── base.py            # AsyncApp - main orchestrator (430 lines)
│   │   ├── track.py           # Track data models & TrackMatcher (367 lines)
│   │   ├── types.py           # Type definitions & protocols (293 lines)
│   │   └── exceptions.py      # Exception hierarchy (184 lines)
│   │
│   ├── providers/             # Track identification providers
│   │   ├── factory.py         # Provider factory with singleton
│   │   ├── base.py            # Abstract base classes & protocols
│   │   ├── shazam.py          # Shazam integration
│   │   ├── acrcloud.py        # ACRCloud integration
│   │   └── spotify.py         # Spotify metadata enrichment
│   │
│   ├── cache/                 # Sophisticated caching system
│   │   ├── base.py            # Core cache implementation (221 lines)
│   │   ├── invalidation.py    # Strategy pattern for cache invalidation (381 lines)
│   │   ├── storage.py         # JSON file storage backend
│   │   ├── index.py           # Cache index for fast lookups
│   │   └── factory.py         # Cache factory with singleton
│   │
│   ├── config/                # Configuration management
│   │   ├── base.py            # Configuration dataclasses (200 lines)
│   │   ├── factory.py         # Config factory with singleton (66 lines)
│   │   ├── validation.py      # Validation rules & utilities
│   │   ├── security.py        # Sensitive data handling
│   │   └── docs.py            # Auto-generated documentation
│   │
│   ├── downloaders/           # Audio download implementations
│   │   ├── factory.py         # Downloader factory
│   │   ├── base.py            # Abstract downloader interface
│   │   ├── ytdlp.py           # YouTube-DL wrapper
│   │   └── mixcloud.py        # Mixcloud downloader
│   │
│   ├── exporters/             # Output formatting
│   │   ├── tracklist.py       # TracklistOutput - multiple formats (249 lines)
│   │   └── spotify.py         # Spotify playlist export
│   │
│   ├── utils/                 # Cross-cutting utilities
│   │   ├── rate_limiter.py    # Advanced rate limiting with circuit breaker (339 lines)
│   │   ├── logger.py          # Centralized logging (97 lines)
│   │   ├── decorators.py      # Function decorators (memoize) (102 lines)
│   │   ├── validation.py      # Input validation (144 lines)
│   │   ├── identification.py  # Track identification orchestration (128 lines)
│   │   ├── time_formatter.py  # Time formatting utilities
│   │   └── strings.py         # String manipulation utilities
│   │
│   └── dev_cli/               # Development CLI tools
│       ├── cli.py             # Dev CLI entry point
│       ├── config.py          # Dev CLI configuration
│       ├── commands/          # CLI command implementations
│       └── execution/         # Command execution logic
│
├── tests/                     # Test suite
│   ├── test_rate_limiter.py   # Rate limiter tests
│   ├── test_cache.py          # Cache system tests
│   ├── test_config.py         # Configuration tests
│   ├── test_app.py            # Application integration tests
│   ├── test_validation.py     # Validation tests
│   ├── test_track_matcher.py  # Track matching tests
│   ├── data/                  # Test data files
│   └── TESTING.md             # Testing documentation
│
├── docs/                      # Documentation
│   ├── CONTRIBUTING.md        # Contribution guidelines
│   ├── CHANGELOG.md           # Version history
│   ├── CHECKLIST.md           # Development checklists
│   └── assets/                # Documentation assets
│
├── pyproject.toml             # Project configuration & dependencies
├── .pre-commit-config.yaml    # Pre-commit hooks configuration
├── .env.example               # Environment variable template
└── README.md                  # Project README
```

## Architecture and Design Patterns

### Design Patterns Used

#### 1. Factory Pattern
Used extensively for creating providers, downloaders, and configurations.

**Provider Factory** (`providers/factory.py`):
```python
# Singleton instance management
factory = ProviderFactory()
shazam = factory.get_identification_provider("shazam")
```

**Config Factory** (`config/factory.py`):
```python
# Type-safe configuration retrieval
config = get_config(force_refresh=False)
```

**Downloader Factory** (`downloaders/factory.py`):
```python
# URL-based downloader selection
downloader = DownloaderFactory().get_downloader(url)
```

#### 2. Strategy Pattern
**Cache Invalidation** (`cache/invalidation.py`):
- Multiple strategies: TTL, LRU, Size-based
- Composable via `CompositeStrategy`
- All implement `InvalidationStrategy` ABC

```python
# Combines multiple invalidation strategies
composite = CompositeStrategy([
    TTLStrategy(ttl=3600),
    LRUStrategy(max_age=1800),
    SizeStrategy(max_size=1000)
])
```

#### 3. Protocol Pattern (Structural Typing)
Type-safe interfaces without runtime overhead:

- `TrackIdentificationProvider` - Provider interface
- `CacheStorage` - Storage backend interface
- `Downloader` - Downloader interface

```python
# From core/types.py
class TrackIdentificationProvider(Protocol):
    async def identify_track(self, audio_segment: AudioSegment) -> Optional[Track]: ...
    async def enrich_metadata(self, track_info: Dict) -> Dict: ...
    async def close(self) -> None: ...
```

#### 4. Singleton Pattern
Global instances for configuration, cache, and rate limiter:

```python
# Global config instance
_config_instance = None

def get_config(force_refresh=False):
    global _config_instance
    if _config_instance is None or force_refresh:
        _config_instance = TrackIdentificationConfig()
    return _config_instance
```

#### 5. Circuit Breaker Pattern
In `rate_limiter.py`:
- States: CLOSED (normal) → OPEN (failing) → HALF_OPEN (testing)
- Threshold-based circuit opening (default: 5 failures)
- Automatic reset after timeout (default: 60s)
- Metrics tracking for observability

### Async Architecture

All I/O operations use async/await:

```python
async def process_input(self, input_path: str):
    """Main processing flow."""
    try:
        # Download audio
        audio_path = await self.download_audio(input_path)

        # Split into segments (uses ThreadPoolExecutor)
        segments = await self.split_audio(audio_path)

        # Identify tracks concurrently
        tracks = await self.identification_manager.identify_tracks(segments)

        # Export results
        await self.save_output(tracks)
    finally:
        await self.cleanup()
```

**Concurrency Control**:
- `asyncio.Semaphore` for rate limiting
- `ThreadPoolExecutor` for FFmpeg operations
- Async context managers for resource cleanup

### Exception Hierarchy

Structured exceptions with rich context:

```python
TracklistifyError (base)
├── APIError(status_code, response)
├── ProviderError(provider, cause)
│   ├── ShazamError(error_code)
│   ├── ACRCloudError(error_code)
│   └── SpotifyError(error_code)
├── DownloadError(url, cause)
├── AudioProcessingError(file_path, cause)
├── ValidationError(field, value, constraint)
└── ConfigError(message)
```

## Development Workflow

### Initial Setup

```bash
# Clone repository
git clone https://github.com/betmoar/tracklistify.git
cd tracklistify

# Install uv (if not already installed)
# See: https://docs.astral.sh/uv/getting-started/installation/

# Install dependencies
uv sync

# Copy environment template
cp .env.example .env

# Edit .env with your API keys and configuration
```

### Development Dependencies

Installed via `uv sync` (dev group):
- `pytest>=8.3.3` - Testing framework
- `pytest-asyncio>=0.23.0` - Async test support
- `pytest-cov>=6.0.0` - Coverage reporting
- `pytest-mock>=3.14.0` - Mocking utilities
- `pytest-httpx>=0.21.0` - HTTP testing
- `pre-commit>=4.0.1` - Pre-commit hooks
- `ruff>=0.8.0` - Linting & formatting
- `commitizen>=4.0.0` - Conventional commits
- `pylint>=3.3.1` - Additional linting
- `vulture>=2.13` - Dead code detection

### Pre-commit Hooks

Configured in `.pre-commit-config.yaml`:

1. **Standard hooks** (v5.0.0):
   - `trailing-whitespace` - Remove trailing whitespace
   - `end-of-file-fixer` - Ensure files end with newline
   - `check-yaml` - Validate YAML files
   - `debug-statements` - Check for debug statements
   - `requirements-txt-fixer` - Sort requirements.txt

2. **Ruff** (v0.8.0):
   - `ruff` - Linting with auto-fix
   - `ruff-format` - Code formatting

3. **Commitizen** (v4.0.0):
   - `commitizen` - Validate commit messages
   - `commitizen-branch` - Validate branch names (pre-push)

**Install hooks**:
```bash
pre-commit install
pre-commit install --hook-type pre-push
```

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=tracklistify tests/

# Run specific test file
uv run pytest tests/test_cache.py

# Run with verbose output
uv run pytest -vv

# Run specific test
uv run pytest tests/test_cache.py::test_basic_cache_operations

# Run with debug output (no capture)
uv run pytest -s tests/test_cache.py
```

### Code Quality

```bash
# Run ruff linting
uv run ruff check .

# Auto-fix linting issues
uv run ruff check --fix .

# Format code
uv run ruff format .

# Run pylint
uv run pylint src/tracklistify

# Check for dead code
uv run vulture src/tracklistify
```

### Running the Application

```bash
# Basic usage
uv run tracklistify <audio_file_or_url>

# With output format
uv run tracklistify -f json mix.mp3
uv run tracklistify -f markdown mix.mp3
uv run tracklistify -f all mix.mp3

# With specific provider
uv run tracklistify --provider shazam mix.mp3

# With debug logging
uv run tracklistify --debug mix.mp3

# Batch processing
uv run tracklistify -b path/to/folder/*.mp3
```

### Commit Message Convention

Uses **Conventional Commits** via Commitizen:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types**:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `style:` - Code style changes (formatting, no logic change)
- `refactor:` - Code refactoring
- `test:` - Adding or updating tests
- `chore:` - Maintenance tasks
- `perf:` - Performance improvements
- `ci:` - CI/CD changes
- `build:` - Build system changes

**Examples**:
```bash
git commit -m "feat(providers): add ACRCloud provider support"
git commit -m "fix(cache): resolve TTL invalidation timing issue"
git commit -m "docs: update CLAUDE.md with architecture details"
git commit -m "refactor(config): streamline project root handling"
```

## Code Conventions and Style

### Python Style Guide

**Tool**: Ruff (replaces Black, isort, flake8)

**Configuration** (`pyproject.toml`):
- Line length: 88 characters (Black-compatible)
- Target: Python 3.11+
- Quote style: Double quotes
- Indent: Spaces (4 spaces)
- Selected rules: E (PEP8), F (PyFlakes), B (flake8-bugbear)

### Naming Conventions

**Files and Modules**:
- Snake case: `rate_limiter.py`, `track_matcher.py`
- Descriptive names: `base.py`, `factory.py`

**Classes**:
- PascalCase: `AsyncApp`, `TrackMatcher`, `RateLimiter`
- Descriptive suffixes: `*Provider`, `*Factory`, `*Strategy`, `*Error`

**Functions and Methods**:
- Snake case: `identify_track()`, `get_config()`, `save_all()`
- Verb-based for actions: `download_audio()`, `split_audio()`
- Boolean predicates: `is_valid()`, `should_invalidate()`

**Constants**:
- UPPER_SNAKE_CASE: `RATE_LIMIT_DETECTION_THRESHOLD_SECONDS`
- Defined at module level

**Private Members**:
- Single underscore prefix: `_provider_limits`, `_validate()`

### Import Organization

Follow this order (enforced by Ruff):

```python
# 1. Standard library imports
import asyncio
import os
from pathlib import Path
from typing import List, Optional

# 2. Third-party imports
import pytest
from shazamio import Shazam

# 3. Local/package imports
from tracklistify.config import get_config
from tracklistify.core import AsyncApp
from tracklistify.utils.logger import get_logger
```

### Type Hints

**REQUIRED** for all functions and methods:

```python
def split_audio(self, file_path: str, segment_length: int = 60) -> List[AudioSegment]:
    """Split audio file into segments."""
    ...

async def identify_track(
    self,
    audio_segment: AudioSegment
) -> Optional[Track]:
    """Identify track from audio segment."""
    ...

def create_cache(
    cache_dir: Optional[Path] = None,
    ttl: int = 3600
) -> BaseCache:
    """Create cache instance."""
    ...
```

### Docstrings

**Format**: Google style

```python
def process_input(self, input_path: str) -> List[Track]:
    """Process audio input and identify tracks.

    Downloads audio if URL provided, splits into segments, and identifies
    each segment using configured providers.

    Args:
        input_path: Path to local file or URL to download

    Returns:
        List of identified Track objects with metadata

    Raises:
        DownloadError: If download fails
        AudioProcessingError: If audio processing fails
        ProviderError: If all providers fail

    Examples:
        >>> app = AsyncApp()
        >>> tracks = await app.process_input("mix.mp3")
        >>> print(f"Found {len(tracks)} tracks")
    """
    ...
```

**Required sections**:
- Summary (one line)
- Detailed description (if needed)
- `Args:` - All parameters
- `Returns:` - Return value and type
- `Raises:` - Exceptions that may be raised
- `Examples:` - Usage examples (optional but encouraged)

### File Structure Template

```python
"""Module docstring explaining purpose.

This module contains...
"""

# Standard library imports
import asyncio
from pathlib import Path
from typing import List, Optional

# Third-party imports
import pytest

# Local/package imports
from tracklistify.config import get_config
from tracklistify.utils.logger import get_logger

# Module constants
DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3

# Module logger
logger = get_logger(__name__)


# Type definitions (if any)
class SomeProtocol(Protocol):
    """Protocol definition."""
    ...


# Classes
class MainClass:
    """Class docstring."""

    def __init__(self, param: str):
        """Initialize instance."""
        self.param = param

    def public_method(self) -> str:
        """Public method."""
        return self._private_method()

    def _private_method(self) -> str:
        """Private method."""
        return self.param


# Module-level functions
def helper_function(arg: str) -> str:
    """Helper function."""
    return arg.upper()


# Module initialization (if needed)
if __name__ == "__main__":
    # Entry point
    pass
```

## Key Utilities and Patterns

### Logging

**Usage**:
```python
from tracklistify.utils.logger import get_logger

logger = get_logger(__name__)

logger.debug("Detailed debugging information")
logger.info("User-facing progress updates")
logger.warning("Warning message")
logger.error(f"Error occurred: {e}", exc_info=True)
logger.critical("Critical failure")
```

**Features**:
- Colored console output (ANSI colors)
- Rotating file handler
- Per-module loggers
- Configurable verbosity

**Colors**:
- DEBUG: Cyan
- INFO: Green
- WARNING: Yellow
- ERROR: Red
- CRITICAL: Magenta

**Configuration**:
```python
from tracklistify.utils.logger import set_logger

set_logger(
    log_level="DEBUG",
    log_file=Path("tracklistify.log"),
    verbose=True,
    debug=True
)
```

### Decorators

**Memoization** (`utils/decorators.py`):

```python
from tracklistify.utils.decorators import memoize

@memoize(ttl=3600)
def expensive_operation(arg1: str, arg2: int) -> str:
    """Cached for 1 hour."""
    # Expensive computation
    return result

# Access statistics
stats = expensive_operation.get_stats()
# {'hits': 10, 'misses': 2, 'hit_rate': 0.83, 'avg_time': 0.05}

# Clear cache
expensive_operation.clear_cache()
```

### Rate Limiting

**Global Rate Limiter** (`utils/rate_limiter.py`):

```python
from tracklistify.utils.rate_limiter import get_global_rate_limiter

limiter = get_global_rate_limiter()

# Register provider
limiter.register_provider(
    provider="shazam",
    max_requests_per_minute=25,
    max_concurrent=10
)

# Acquire token
if await limiter.acquire(provider="shazam", timeout=30.0):
    try:
        # Make API call
        result = await provider.identify_track(segment)
    finally:
        limiter.release(provider="shazam")
else:
    logger.warning("Rate limit timeout")

# Get metrics
metrics = limiter.get_metrics("shazam")
# {
#     'total_requests': 100,
#     'rate_limited_requests': 5,
#     'total_wait_time': 15.3,
#     'circuit_state': 'CLOSED',
#     'circuit_failures': 0
# }
```

**Circuit Breaker States**:
- `CLOSED` - Normal operation
- `OPEN` - Circuit tripped, rejecting requests
- `HALF_OPEN` - Testing if service recovered

### Validation

**Input Validation** (`utils/validation.py`):

```python
from tracklistify.utils.validation import validate_input

# Returns (path, is_local) or None
result = validate_input(path_or_url)
if result:
    validated_path, is_local_file = result
    if is_local_file:
        # Process local file
    else:
        # Process URL
else:
    logger.error("Invalid input")
```

**Supported URLs**:
- YouTube: `youtube.com`, `youtu.be`
- SoundCloud: `soundcloud.com`
- Mixcloud: `mixcloud.com`

### Configuration Access

**Getting Configuration** (`config/factory.py`):

```python
from tracklistify.config import get_config

# Get global config instance
config = get_config()

# Force refresh (reload from env)
config = get_config(force_refresh=True)

# Access settings
segment_length = config.segment_length
cache_dir = config.cache_dir
provider = config.primary_provider
```

**Environment Variables**:
All config fields can be overridden with `TRACKLISTIFY_` prefix:

```bash
# Example .env
TRACKLISTIFY_SEGMENT_LENGTH=60
TRACKLISTIFY_MIN_CONFIDENCE=0.8
TRACKLISTIFY_PRIMARY_PROVIDER=shazam
TRACKLISTIFY_CACHE_DIR=.tracklistify/cache
```

### Error Handling Pattern

**Standard Pattern**:

```python
from tracklistify.core.exceptions import (
    TracklistifyError,
    ProviderError,
    DownloadError
)

async def process_something():
    try:
        # Attempt operation
        result = await operation()
    except ProviderError as e:
        logger.error(f"Provider failed: {e.provider}", exc_info=True)
        # Handle provider-specific error
        raise
    except DownloadError as e:
        logger.error(f"Download failed for {e.url}", exc_info=True)
        # Handle download error
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise TracklistifyError(f"Operation failed: {e}") from e
    finally:
        # Always cleanup
        await cleanup_resources()
```

## Testing Guidelines

### Test Structure

Tests are organized by module in `tests/`:

```
tests/
├── test_rate_limiter.py    # Rate limiter unit tests
├── test_cache.py           # Cache system tests
├── test_config.py          # Configuration tests
├── test_app.py             # Application integration tests
├── test_validation.py      # Input validation tests
├── test_track_matcher.py   # Track matching tests
├── test_environment.py     # Environment setup tests
├── data/                   # Test data files
└── TESTING.md              # Detailed testing documentation
```

### Writing Tests

**Basic Structure**:

```python
import pytest
from tracklistify.core import AsyncApp

class TestAsyncApp:
    """Test suite for AsyncApp."""

    @pytest.fixture
    def app(self):
        """Create app instance for testing."""
        return AsyncApp()

    def test_initialization(self, app):
        """Test app initializes correctly."""
        assert app.config is not None
        assert app.provider_factory is not None

    @pytest.mark.asyncio
    async def test_async_operation(self, app):
        """Test async operation."""
        result = await app.process_something()
        assert result is not None
```

**Fixtures**:

```python
@pytest.fixture
def temp_cache_dir(tmp_path: Path) -> Path:
    """Create temporary cache directory."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    return cache_dir

@pytest.fixture
def mock_provider():
    """Create mock provider for testing."""
    class MockProvider:
        async def identify_track(self, segment):
            return Track(title="Test", artist="Artist")
    return MockProvider()
```

**Async Tests**:

```python
@pytest.mark.asyncio
async def test_rate_limiting(rate_limiter, mock_provider):
    """Test rate limiting functionality."""
    # First request should succeed
    assert await rate_limiter.acquire(mock_provider)

    # Second immediate request should be rate-limited
    assert not await rate_limiter.acquire(mock_provider, timeout=0.001)

    # Release and try again
    rate_limiter.release(mock_provider)
    assert await rate_limiter.acquire(mock_provider)
```

**Parametrized Tests**:

```python
@pytest.mark.parametrize("url,expected", [
    ("https://youtube.com/watch?v=123", True),
    ("https://soundcloud.com/user/track", True),
    ("invalid-url", False),
])
def test_url_validation(url, expected):
    """Test URL validation."""
    result = validate_input(url)
    assert (result is not None) == expected
```

### Test Coverage

**Target**: Maintain or improve coverage (currently high)

**Run with coverage**:
```bash
uv run pytest --cov=tracklistify --cov-report=html tests/
```

**Coverage configuration** (`pyproject.toml`):
```toml
[tool.coverage.run]
source = ["src"]
omit = ["tests/*", "**/dev_cli/*"]
```

### Best Practices

1. **Test naming**: `test_<functionality>_<scenario>`
2. **Arrange-Act-Assert** pattern
3. **One assertion per test** (when possible)
4. **Use fixtures** for common setup
5. **Test both success and failure** paths
6. **Test edge cases** and boundary conditions
7. **Mock external dependencies** (APIs, network)
8. **Clean up resources** in fixtures
9. **Use descriptive docstrings**
10. **Avoid test interdependencies**

## Configuration Management

### Configuration Hierarchy

1. **Code defaults** (in `config/base.py`)
2. **Environment variables** (`TRACKLISTIFY_*`)
3. **CLI arguments** (override config)

### Key Configuration Classes

**BaseConfig** (`config/base.py`):
- `output_dir` - Output directory
- `cache_dir` - Cache directory
- `temp_dir` - Temporary files
- `log_dir` - Log files
- `verbose` - Verbose logging
- `debug` - Debug mode

**TrackIdentificationConfig** (extends BaseConfig):
- `segment_length` - Audio segment length (10-300s)
- `min_confidence` - Minimum confidence threshold (0.0-1.0)
- `time_threshold` - Time between tracks (0-300s)
- `max_duplicates` - Max duplicate tracks (0-10)
- `overlap_duration` - Segment overlap (0-30s)
- `primary_provider` - Primary identification provider
- `fallback_enabled` - Enable fallback providers

### Environment Variables

All config fields support environment variables with `TRACKLISTIFY_` prefix:

```bash
# Base settings
TRACKLISTIFY_OUTPUT_DIR=.tracklistify/output
TRACKLISTIFY_CACHE_DIR=.tracklistify/cache
TRACKLISTIFY_VERBOSE=true
TRACKLISTIFY_DEBUG=false

# Track identification
TRACKLISTIFY_SEGMENT_LENGTH=60
TRACKLISTIFY_MIN_CONFIDENCE=0.8
TRACKLISTIFY_PRIMARY_PROVIDER=shazam

# Rate limiting
TRACKLISTIFY_RATE_LIMIT_ENABLED=true
TRACKLISTIFY_MAX_REQUESTS_PER_MINUTE=25
TRACKLISTIFY_SHAZAM_MAX_RPM=25

# Circuit breaker
TRACKLISTIFY_CIRCUIT_BREAKER_ENABLED=true
TRACKLISTIFY_CIRCUIT_BREAKER_THRESHOLD=5
TRACKLISTIFY_CIRCUIT_BREAKER_RESET_TIMEOUT=60.0

# Cache settings
TRACKLISTIFY_CACHE_ENABLED=true
TRACKLISTIFY_CACHE_TTL=3600
TRACKLISTIFY_CACHE_MAX_SIZE=1000
```

See `.env.example` for complete list of configuration options.

### Type Conversion

Environment variables are automatically converted:

- `bool`: `"true"`, `"false"`, `"1"`, `"0"`, `"yes"`, `"no"`
- `int`: `"123"` → `123`
- `float`: `"1.5"` → `1.5`
- `Path`: `"path/to/dir"` → `Path("path/to/dir")`
- `List[str]`: `'["item1", "item2"]'` → `["item1", "item2"]`

### Validation

Configuration is validated on initialization:

```python
from tracklistify.config import TrackIdentificationConfig

# Will raise ConfigError if invalid
config = TrackIdentificationConfig()

# Validation checks:
# - segment_length: 10 <= value <= 300
# - min_confidence: 0.0 <= value <= 1.0
# - time_threshold: 0.0 <= value <= 300.0
# - paths exist and are writable
```

## Common Tasks

### Adding a New Provider

1. **Create provider class** in `src/tracklistify/providers/`:

```python
# src/tracklistify/providers/new_provider.py
from typing import Optional
from tracklistify.core.types import AudioSegment, Track
from tracklistify.providers.base import TrackIdentificationProvider
from tracklistify.utils.logger import get_logger

logger = get_logger(__name__)


class NewProvider(TrackIdentificationProvider):
    """New track identification provider."""

    def __init__(self, api_key: str, timeout: int = 10):
        self.api_key = api_key
        self.timeout = timeout

    async def identify_track(
        self,
        audio_segment: AudioSegment
    ) -> Optional[Track]:
        """Identify track from audio segment."""
        try:
            # API call logic
            response = await self._call_api(audio_segment)

            if response.success:
                return Track(
                    title=response.title,
                    artist=response.artist,
                    confidence=response.confidence,
                    timestamp=audio_segment.start_time
                )
            return None
        except Exception as e:
            logger.error(f"Provider error: {e}")
            raise ProviderError(f"Failed: {e}", provider="new_provider")

    async def enrich_metadata(self, track_info: dict) -> dict:
        """Enrich track metadata."""
        return track_info

    async def close(self):
        """Cleanup resources."""
        pass
```

2. **Register in factory** (`providers/factory.py`):

```python
def get_identification_provider(self, provider_name: str):
    """Get provider instance."""
    if provider_name == "new_provider":
        from tracklistify.providers.new_provider import NewProvider
        config = get_config()
        return NewProvider(
            api_key=config.new_provider_api_key,
            timeout=config.new_provider_timeout
        )
    # ... existing providers
```

3. **Add configuration** (`config/base.py`):

```python
@dataclass
class TrackIdentificationConfig(BaseConfig):
    # ... existing fields

    new_provider_api_key: str = ""
    new_provider_timeout: int = 10
```

4. **Add tests** (`tests/test_new_provider.py`):

```python
import pytest
from tracklistify.providers.new_provider import NewProvider

class TestNewProvider:
    @pytest.fixture
    def provider(self):
        return NewProvider(api_key="test_key")

    @pytest.mark.asyncio
    async def test_identify_track(self, provider):
        # Test implementation
        pass
```

### Adding a New Output Format

1. **Extend TracklistOutput** (`exporters/tracklist.py`):

```python
def export_new_format(self, output_path: Path) -> None:
    """Export tracklist in new format."""
    with open(output_path, 'w', encoding='utf-8') as f:
        # Format implementation
        for track in self.tracks:
            f.write(f"{track.timestamp}: {track.artist} - {track.title}\n")

    self.logger.info(f"Exported to {output_path}")
```

2. **Add to save_all**:

```python
def save_all(self):
    """Export to all formats."""
    # ... existing formats
    self.export_new_format(base_path.with_suffix('.new'))
```

3. **Update CLI** (`cli.py`):

```python
parser.add_argument(
    "-f", "--formats",
    choices=["json", "markdown", "m3u", "new_format", "all"],
    help="Output format(s)"
)
```

### Adding New Configuration Options

1. **Add field to config class** (`config/base.py`):

```python
@dataclass
class TrackIdentificationConfig(BaseConfig):
    # ... existing fields

    new_option: str = "default_value"
    new_threshold: float = 0.5
```

2. **Add validation** (if needed):

```python
def __post_init__(self):
    """Validate configuration after initialization."""
    # ... existing validation

    if not 0.0 <= self.new_threshold <= 1.0:
        raise ConfigError("new_threshold must be between 0.0 and 1.0")
```

3. **Document in .env.example**:

```bash
# New Feature Settings
TRACKLISTIFY_NEW_OPTION=custom_value    # Description of new option
TRACKLISTIFY_NEW_THRESHOLD=0.5          # Threshold value (0.0 to 1.0)
```

4. **Update documentation** (README.md, CLAUDE.md)

### Running Development Tasks

```bash
# Run main CLI
uv run tracklistify input.mp3

# Run development CLI (if available)
uv run python -m tracklistify.dev_cli

# Run specific module
uv run python -m tracklistify.providers.shazam

# Run with profiling
uv run python -m cProfile -o output.prof -m tracklistify input.mp3

# Format code
uv run ruff format .

# Lint code
uv run ruff check --fix .

# Run tests with markers
uv run pytest -m "not slow"
uv run pytest -m integration

# Generate coverage report
uv run pytest --cov=tracklistify --cov-report=html tests/
open htmlcov/index.html
```

## Important Notes

### Do's and Don'ts

**DO**:
- ✅ Use async/await for all I/O operations
- ✅ Add type hints to all functions
- ✅ Write comprehensive docstrings
- ✅ Use structured logging via `get_logger(__name__)`
- ✅ Handle exceptions with context
- ✅ Clean up resources in `finally` blocks
- ✅ Use factories for object creation
- ✅ Follow existing code patterns
- ✅ Write tests for new features
- ✅ Update documentation when changing APIs
- ✅ Use conventional commit messages
- ✅ Run pre-commit hooks before committing

**DON'T**:
- ❌ Use blocking I/O operations
- ❌ Create instances directly (use factories)
- ❌ Ignore exceptions
- ❌ Leave debug statements in code
- ❌ Commit without running tests
- ❌ Push directly to main
- ❌ Mix sync and async code incorrectly
- ❌ Use global variables (except singletons)
- ❌ Hardcode configuration values
- ❌ Skip type hints or docstrings

### Common Gotchas

1. **Async Context Managers**
   ```python
   # Correct
   async with provider:
       result = await provider.identify_track(segment)

   # Wrong
   with provider:  # Missing async
       result = await provider.identify_track(segment)
   ```

2. **Config Refresh**
   ```python
   # When testing, force refresh to reload env vars
   config = get_config(force_refresh=True)
   ```

3. **Path Resolution**
   ```python
   # Always use get_root() for project-relative paths
   from tracklistify.config import get_root

   config_file = get_root() / ".env"
   ```

4. **Logger Naming**
   ```python
   # Always use __name__ for module-specific logging
   logger = get_logger(__name__)

   # Not: get_logger("tracklistify")
   ```

5. **Rate Limiter Release**
   ```python
   # Always release in finally block
   if await limiter.acquire(provider):
       try:
           result = await api_call()
       finally:
           limiter.release(provider)  # Critical!
   ```

6. **Environment Variable Types**
   ```python
   # Booleans: use "true"/"false", not "True"/"False"
   TRACKLISTIFY_DEBUG=true  # Correct
   TRACKLISTIFY_DEBUG=True  # May not work
   ```

### Performance Considerations

1. **Cache Usage**: Cache is enabled by default with TTL=3600s
2. **Rate Limiting**: Respect provider limits (default: 25 req/min for Shazam)
3. **Concurrent Requests**: Limited by semaphore (default: 2 concurrent)
4. **Segment Length**: Shorter = more API calls, longer = less precision
5. **FFmpeg**: Uses ThreadPoolExecutor (4 workers) for parallel segmentation

### Security Notes

1. **API Keys**: Never commit API keys
   - Use `.env` file (gitignored)
   - Use environment variables in CI/CD

2. **Sensitive Data**: Config security module masks sensitive fields
   - Password, api_key, token, secret fields are auto-masked
   - Logs show `xxx*****xxx` for sensitive values

3. **File Paths**: Validate all user-provided paths
   ```python
   from tracklistify.utils.validation import validate_input
   result = validate_input(user_path)
   if not result:
       raise ValidationError("Invalid path")
   ```

### Useful Resources

- **Project Repository**: https://github.com/betmoar/tracklistify
- **uv Documentation**: https://docs.astral.sh/uv/
- **Ruff Documentation**: https://docs.astral.sh/ruff/
- **Pytest Documentation**: https://docs.pytest.org/
- **Python Type Hints**: https://docs.python.org/3/library/typing.html
- **Async Best Practices**: https://docs.python.org/3/library/asyncio.html

---

## Quick Reference

### Essential Commands

```bash
# Setup
uv sync                          # Install dependencies
cp .env.example .env            # Setup environment

# Development
uv run tracklistify <input>     # Run application
uv run pytest                   # Run tests
uv run ruff format .            # Format code
uv run ruff check --fix .       # Lint and fix

# Testing
uv run pytest -vv               # Verbose tests
uv run pytest --cov=tracklistify # With coverage
uv run pytest -k test_name      # Run specific test

# Quality
pre-commit run --all-files      # Run all hooks
uv run pylint src/tracklistify  # Lint with pylint
uv run vulture src/tracklistify # Find dead code
```

### Project Contact

- **Maintainer**: betmoar
- **Email**: betmoar@mailsecure.me
- **Issues**: https://github.com/betmoar/tracklistify/issues

---

*Last Updated: 2025-11-21*
*Document Version: 1.0*
