# Changelog

All notable changes to Tracklistify will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Release dates are in YYYY-MM-DD format.

## [Unreleased]
### Added
- Support for additional platforms (Mixcloud, SoundCloud)
- Advanced error recovery strategies
- Batch processing for multiple files
- Progress bar for long operations
- CLI improvements:
  - Interactive mode
  - Configuration wizard
  - Batch processing options
- Web interface for easier usage
- Docker support
- Additional output formats:
  - CSV export
  - XML export
  - Rekordbox compatible format

### Changed
- Enhanced progress display:
  - Single-line progress updates
  - Color-coded INFO prefix
  - Improved readability with newlines
- Improved YouTube downloader:
  - Environment-based download paths
  - Automatic temp directory creation
  - Configurable download locations
- Modernized event loop handling:
  - Removed deprecation warnings
  - Better async cleanup
  - Proper task cancellation
- Enhanced interrupt handling:
  - Graceful Ctrl+C shutdown
  - Resource cleanup on exit
  - User-friendly cancellation messages
- Simplified rate limiter tests to focus on core functionality
- Temporarily skipped complex timing-dependent tests

### Fixed
- Duplicate progress line display
- Event loop deprecation warnings
- Temporary file cleanup
- Interrupt signal handling
- Rate limiter test reliability issues

## [Rate Limiter Enhancements] - 2024-11-25
### Added
- Enhanced rate limiter with metrics collection and monitoring
- Circuit breaker pattern for rate limiting
- Alert system for rate limit events
- Per-provider rate limiting configuration
- Concurrent request limiting
- Async support for rate limiting operations
- Resource cleanup mechanisms
- Comprehensive logging for rate limiter events
- Rate limit configuration validation
- Environment variables for rate limiter configuration
- Comprehensive test suite for rate limiter:
  - Basic rate limiting functionality
  - Concurrent request handling
  - Metrics tracking
  - Circuit breaker behavior
  - Alert system functionality
  - Resource cleanup verification
  - Provider registration
  - Rate limit window tracking
  - Timeout handling

### Changed
- Updated rate limiter implementation with token bucket algorithm
- Enhanced provider limits with metrics tracking
- Improved error handling with circuit breaker pattern

### Fixed
- Rate limiting resource cleanup
- Proper handling of concurrent requests
- Thread-safe rate limit operations

## [Phase 4 - Spotify Integration] - 2024-11-25
### Added
- Spotify downloader implementation:
  - Support for multiple audio qualities:
    * Vorbis: 96, 160, 320 kbps
    * AAC: 24, 32, 96, 128, 256 kbps
  - Multiple output formats (M4A/OGG/MP3)
  - Rich metadata tagging:
    * Artist and album information
    * Track and disc numbers
    * Release dates and genres
    * Cover art embedding
  - Factory method for environment-based creation
- Environment variable configuration:
  - TRACKLISTIFY_SPOTIFY_COOKIES: Browser cookie path
  - TRACKLISTIFY_SPOTIFY_QUALITY: Audio quality setting
  - TRACKLISTIFY_SPOTIFY_FORMAT: Output format selection
  - TRACKLISTIFY_OUTPUT_DIR: Download directory
  - TRACKLISTIFY_TEMP_DIR: Temporary file location
  - TRACKLISTIFY_VERBOSE: Logging verbosity
- Enhanced file management:
  - Structured .tracklistify directory:
    * /output: Downloaded files
    * /temp: Temporary processing
  - Safe filename generation
  - Home directory expansion (~)
  - Automatic directory creation

### Changed
- Project structure improvements:
  - Integrated Spotify downloader with existing base
  - Enhanced environment variable handling
  - Expanded configuration options
  - Improved directory organization
- Audio processing:
  - FFmpeg integration for format conversion
  - Quality-preserving transcoding
  - Metadata preservation during conversion
- Error handling and logging:
  - Detailed debug information
  - Operation progress tracking
  - Comprehensive error messages
  - Clean error recovery

### Fixed
- Path handling:
  - Home directory expansion
  - Illegal character sanitization
  - Unicode filename support
- Temporary file management:
  - Proper cleanup after processing
  - Unique temp file naming
  - Error state cleanup
- Cookie handling:
  - Path expansion support
  - Better error messages
  - Validation checks

## [Phase 3 - Track Identification and Output Enhancement] - 2024-11-24
### Added
- Real-time progress display for track identification:
  - Visual progress bar
  - Segment-by-segment tracking
  - Status updates with current provider
  - File size and timing information
- Multiple output format support:
  - JSON output with detailed analysis info
  - Markdown format with confidence scores
  - M3U playlist generation with timing
- YouTube and Mixcloud URL support:
  - Direct URL processing
  - Metadata extraction
  - Automatic format handling
- Enhanced command-line interface:
  - Provider selection options
  - Format selection flags
  - Verbose logging mode
  - Provider fallback control

### Changed
- Improved identification system:
  - Better provider management
  - Enhanced error handling
  - Caching and rate limiting
  - Track matching refinements
- Enhanced mix info extraction:
  - Better metadata handling
  - Special character support
  - Consistent filename formatting
- Logging system improvements:
  - Detailed debug information
  - Progress tracking
  - Analysis summaries
  - Error reporting

### Fixed
- Resource cleanup in main execution flow
- Provider fallback mechanism
- Special character handling in filenames
- Progress display overlapping

## [Phase 2 - Cache System] - 2024-11-22
### Added
- Enhanced cache management system:
  - Base cache implementation with generic type support
  - Multiple invalidation strategies:
    - TTL (Time-To-Live) based invalidation
    - LRU (Least Recently Used) strategy
    - Size-based cache limits
    - Composite strategy support
  - Asynchronous operations:
    - Async-first design
    - Non-blocking cache operations
    - Concurrent access support
  - Storage backends:
    - JSON file-based storage
    - Atomic file operations
    - Compression support
  - Cache statistics tracking:
    - Hit/miss rates
    - Invalidation counts
    - Storage efficiency metrics
  - Comprehensive test suite:
    - Unit tests for all components
    - Integration tests for cache system
    - Performance benchmarks
    - Timing-sensitive test cases
- Enhanced type system:
  - New type definitions for cache operations:
    - `CacheMetadata` TypedDict
    - `CacheStorage` Protocol
    - `InvalidationStrategy` Protocol
    - `Cache` Protocol with comprehensive type hints
  - Improved configuration types:
    - Added cache-specific configuration options
    - Enhanced type safety for cache operations

### Changed
- Improved cache entry handling:
  - Enhanced metadata management
  - Strict type checking
  - Better error handling
  - Atomic updates
- Refined invalidation logic:
  - More precise timing checks
  - Floating-point comparison fixes
  - Enhanced error recovery
- Updated test framework:
  - Async test support
  - More reliable timing tests
  - Better test isolation
- Restructured cache implementation:
  - Moved cache code to dedicated module
  - Separated concerns into distinct files
  - Improved code organization

### Fixed
- Cache invalidation timing issues
- Metadata update consistency
- Concurrent access race conditions
- File system race conditions
- Type checking in cache operations

### Security
- Implemented atomic file operations
- Added comprehensive error logging
- Enhanced metadata validation
- Secure file permissions handling

### Documentation
- Added detailed cache system documentation
- Created comprehensive testing guide (TESTING.md)
- Added performance benchmarks
- Included troubleshooting tips
- Documented best practices
- Added type hints documentation:
  - Protocol definitions
  - Generic type variables
  - Configuration types
  - Cache-specific types

## [Phase 2 - Configuration Management] - 2024-11-22
### Added
- Enhanced configuration management system:
  - Standardized directory structure:
    - `.tracklistify/output` for output files
    - `.tracklistify/cache` for cache data
    - `.tracklistify/temp` for temporary files
  - Environment variable improvements:
    - `TRACKLISTIFY_` prefix for all variables
    - Type conversion for all config values
    - Home directory expansion for paths
    - Enhanced list parsing with multiple formats support
    - Better error messages for invalid values
    - Support for single value and comma-separated lists
  - Configuration validation:
    - Comprehensive test coverage
    - Directory creation and cleanup
    - Path validation and expansion
    - Custom configuration handling
  - Security enhancements:
    - Sensitive field masking
    - Configurable rate limiting
    - Secure credential handling
- Complete configuration management system implementation:
  - Recognition configuration:
    - Confidence threshold settings
    - Segment length configuration
    - Overlap settings
    - Cache directory configuration
    - Provider configuration
  - Added _parse_env_value helper for robust type conversion
  - Support for various boolean formats (true/1/yes/on)
  - Proper handling of Path expansion
  - Improved validation error messages
- Improved environment variable handling:
  - Enhanced list parsing with multiple formats support
  - Automatic type conversion for all config fields
  - Better error messages for invalid values
  - Support for single value and comma-separated lists
- Configuration improvements:
  - Added _parse_env_value helper for robust type conversion
  - Support for various boolean formats (true/1/yes/on)
  - Proper handling of Path expansion
  - Improved validation error messages

## [Phase 1 Completion] - 2024-11-21
### Added
- Comprehensive development environment setup
  - Black for code formatting
  - isort for import sorting
  - flake8 for linting
  - mypy for type checking
  - pre-commit hooks configuration
- Commit message validation using commitizen
- Type system foundation in types.py
  - TypedDict definitions for configuration and metadata
  - Protocol definitions for providers and downloaders
  - Generic type variables
- Error handling framework in exceptions.py
  - Base exceptions hierarchy
  - Provider-specific exceptions
  - Downloader-specific exceptions
- Environment validation tests
  - Python version validation
  - System dependencies check
  - Virtual environment validation
  - Development tools validation

## [0.6.0] - 2024-03-21
### Added
- Modern Python packaging with pyproject.toml
- Dynamic version management using setuptools_scm
- Improved development tooling:
  - Black for code formatting
  - isort for import sorting
  - mypy for type checking
  - flake8 for linting
  - pytest for testing
  - pre-commit hooks
- Enhanced Shazam provider:
  - Updated to shazamio 0.7.0
  - Improved recognition accuracy
  - Better error handling and retries

### Changed
- Optimized track identification settings:
  - Reduced segment length to 15 seconds for faster processing
  - Set minimum confidence threshold to 50%
  - Improved duplicate handling with single track limit
- Simplified provider configuration:
  - Made Shazam the default provider
  - Streamlined fallback settings
- Enhanced environment setup process
- Updated Python requirement to 3.11+

### Fixed
- Various bug fixes and performance improvements
- Enhanced error handling in audio processing
- More reliable track identification

## [0.5.8] - 2024-01-09

### Changed
- Improved logging system across all downloaders
- Enhanced error handling for unidentified segments
- Reduced segment length to 20 seconds for better identification
- Enabled verbose and debug modes by default

### Added
- Detailed logging for YouTube and Mixcloud downloaders
- Specific error messages for common download failures
- Debug logging for download initialization and settings
- More informative success messages with track details

### Fixed
- Better handling of unidentified segments in identification process
- More appropriate log levels for different types of messages
- Simplified downloader factory implementation

## [0.5.7] - 2024-11-19

### Changed
- Refactored downloader modules into dedicated factory folder structure
- Improved code organization with proper separation of concerns
- Enhanced maintainability and extensibility for future downloaders

### Removed
- Deprecated `downloader.py` module in favor of new `downloaders` package

## [0.5.6] - 2024-11-19

### Added
- New download configuration options in `.env` file:
  - `DOWNLOAD_QUALITY`: Audio quality setting (default: 320kbps)
  - `DOWNLOAD_FORMAT`: Output audio format (default: mp3)
  - `DOWNLOAD_TEMP_DIR`: Custom temporary directory
  - `DOWNLOAD_MAX_RETRIES`: Maximum retry attempts for downloads

### Changed
- Improved downloader implementation with async support
- Enhanced YouTube downloader with better error handling
- Implemented singleton pattern for downloader instances
- Made download quality and format configurable
- Improved thread handling for non-blocking downloads

### Removed
- Redundant download code from main application
- Unused app.py module

## [0.5.5] - 2024-11-19
### Changed
- Cache implementation now uses ttl instead of duration
- Improved cache key generation with byte range support
- Better error handling in cache operations
- Added cache entry deletion method

### Fixed
- Cache configuration error with duration attribute
- Cache expiration handling
- Cache key generation for better segment isolation

## [0.5.4] - 2024-11-19
### Added
- Exponential backoff retry logic for Shazam provider
- Rate limiting with configurable intervals
- Improved session management with automatic recovery
- Better audio format handling with consistent WAV output

### Changed
- Shazam provider completely refactored for better reliability
- Output format handling now properly respects environment variables
- Session management now uses exponential backoff with jitter
- Audio processing standardized to stereo 44.1kHz WAV

### Fixed
- URL validation errors in Shazam provider
- Session expiration handling
- Output format not respecting environment variables
- Audio format inconsistencies causing recognition failures

### Security
- Added rate limiting to prevent API abuse
- Improved session handling to prevent resource leaks

## [0.5.3] - 2024-11-19
### Added
- Configurable provider fallback system
- Enhanced logging for provider selection and usage
- Output configuration with customizable directory and format
- Improved cache error handling with graceful degradation

### Changed
- Provider fallback now respects PROVIDER_FALLBACK_ENABLED setting
- Rate limiter now has configurable timeout (30s default)
- Cache operations now handle errors gracefully
- Improved logging for provider selection and track identification
- Better error messages for provider failures

### Fixed
- Cache enabled check now uses config object correctly
- Rate limiter synchronization issues
- Provider fallback logic to skip duplicate providers
- Cache key now includes provider name for better isolation

## [0.5.2] - 2024-11-17
### Changed
- Migrated ACRCloud to provider interface
- Enhanced provider factory with better configuration
- Improved error handling for providers
- Standardized provider timeouts

## [0.5.1] - 2024-11-17
### Added
- Comprehensive contributing guidelines (CONTRIBUTING.md)
- Detailed development environment setup instructions
- Code style and linting configuration
- Pre-commit hooks setup

### Changed
- Enhanced environment configuration template
- Expanded documentation for API keys and settings
- Improved project structure documentation

## [0.5.0] - 2024-11-17
### Added
- Enhanced Shazam integration:
  - Advanced audio fingerprinting with MFCCs
  - Spectral centroid analysis
  - Pre-emphasis filtering
  - Improved confidence scoring
  - Detailed audio features extraction
  - Extended metadata enrichment
- Audio landmark fingerprinting for track identification
- Advanced audio processing with librosa
- Shazam integration using shazamio package

## [0.4.0] - 2024-11-16
### Added
- Multiple provider support through provider interface
- Spotify integration for metadata enrichment
- Provider factory for managing multiple providers
- Comprehensive test suite for providers
- File-based caching system for API responses
- Token bucket rate limiter for API calls
- Memory-efficient chunk-based audio processing
- Retry mechanism with exponential backoff for API calls
- Timeout handling for long-running operations
- Enhanced logging system with colored console output
- Configurable log file output with timestamps
- Debug-level logging for development
- Custom log formatters for both console and file output
- Enhanced track identification verbosity
- Comprehensive analysis summary in output files
- Additional metadata in M3U playlists
- Modular package structure with dedicated modules
- Type hints throughout the codebase
- Factory pattern for platform-specific downloaders
- Enhanced track identification algorithm
- Cache configuration options:
  - CACHE_ENABLED for toggling caching
  - CACHE_DIR for cache location
  - CACHE_DURATION for cache expiration
- Rate limiting configuration:
  - RATE_LIMIT_ENABLED for toggling rate limiting
  - MAX_REQUESTS_PER_MINUTE for API throttling

### Changed
- Modular provider architecture
- Enhanced metadata enrichment
- Optimized memory usage during audio processing
- Improved Track class with strict validation
- Enhanced TrackMatcher with better error handling
- Refined confidence threshold handling
- More robust MP3 format validation
- Updated environment variable structure
- Enhanced error handling and logging
- Improved configuration management

### Fixed
- Track timestamp ordering
- Confidence threshold validation
- Track metadata validation
- Audio file format validation
- Memory leaks in audio processing
- API rate limiting issues

## [0.3.6] - 2024-11-16

### Fixed
- Fixed track timing calculation using MP3 metadata for accurate timestamps
- Adjusted default segment length to 60 seconds for better track identification
- Removed redundant acrcloud-py dependency in favor of pyacrcloud

### Added
- Added mutagen dependency for MP3 metadata handling
- Added total mix length display in track identification output

### Changed
- Improved segment timing calculation to use actual audio duration
- Enhanced logging with proper time formatting (HH:MM:SS)
- Updated requirements.txt for better dependency management

## [0.3.5] - 2024-11-15

### Fixed
- YouTube download functionality
- Import error handling for yt-dlp
- Downloader factory creation
- Mix information extraction order

### Changed
- Better error messages for missing dependencies
- Improved YouTube URL handling
- More robust downloader initialization
- Cleaner error handling flow

## [0.3.4] - 2024-11-15

### Added
- URL validation and cleaning functionality
- Support for various YouTube URL formats
- Automatic backslash stripping from URLs
- URL unescaping for encoded characters

### Changed
- Improved URL handling in main program
- Enhanced error messages for invalid URLs
- Better logging of URL processing steps
- Cleaner YouTube URL reconstruction

### Fixed
- Issue with backslashes in URLs
- Problems with URL-encoded characters
- Inconsistent YouTube URL formats
- Invalid URL handling

## [0.3.3] - 2024-11-15

### Added
- Comprehensive error handling system with specific exception types
- Retry mechanism with exponential backoff for API calls
- Timeout handling for long-running operations
- Custom exceptions for different error scenarios
- Detailed error logging and reporting

### Changed
- Enhanced API calls with retry logic
- Improved download operations with timeout handling
- Updated error messages with more context
- Added detailed error documentation

## [0.3.2] - 2024-11-15

### Added
- Enhanced logging system with colored console output
- Configurable log file output with timestamps
- Debug-level logging for development
- Custom log formatters for both console and file output

### Changed
- Updated logger module with comprehensive configuration options
- Improved log message formatting
- Added color-coding for different log levels
- Enhanced logging verbosity control

## [0.3.1] - 2024-11-15

### Added
- Enhanced track identification verbosity with detailed progress and status logging
- Comprehensive analysis summary in output files including confidence statistics
- Additional metadata in M3U playlists (artist and date information)

### Changed
- Modified track confidence handling to keep all tracks with confidence > 0
- Updated tracklist filename format to `[YYYYMMDD] Artist - Description.extension`
- Improved track merging process with more detailed debug logging
- Enhanced markdown output with analysis statistics section

### Fixed
- Filename sanitization to preserve spaces and valid punctuation
- Date format handling in filenames for consistency

## [0.3.0] - 2024-11-15

### Added
- Modular package structure with dedicated modules:
  - config.py for configuration management
  - logger.py for centralized logging
  - track.py for track identification
  - downloader.py for audio downloads
- Type hints throughout the codebase
- Proper package installation with setup.py
- Development environment setup
- Comprehensive logging system with file output
- Factory pattern for platform-specific downloaders

### Changed
- Restructured project into proper Python package
- Improved configuration using dataclasses
- Enhanced error handling and logging
- Updated documentation with new structure
- Improved code organization and maintainability

### Fixed
- FFmpeg path detection on different platforms
- Package dependencies and versions
- Installation process

## [0.2.0] - 2024-11-15

### Added
- Enhanced track identification algorithm with confidence-based filtering
- New track merging logic to handle duplicate detections
- Dedicated tracklists directory for organized output
- Additional configuration options in .env for fine-tuning:
  - MIN_CONFIDENCE for match threshold
  - TIME_THRESHOLD for track merging
  - MIN_TRACK_LENGTH for filtering
  - MAX_DUPLICATES for duplicate control
- Improved JSON output format with detailed track information
- Better timestamp handling in track identification

### Changed
- Updated .env.example with new configuration options
- Improved README documentation with output format examples
- Enhanced error handling in track identification process
- Optimized FFmpeg integration

### Fixed
- Duplicate track detection issues
- Timestamp accuracy in track listing
- File naming sanitization

## [0.1.0] - 2024-11-15
### Added
- Core track identification functionality
- Support for YouTube and Mixcloud platforms
- ACRCloud integration for audio recognition
- JSON export of track listings
- Command-line interface
- Configuration file support
- Detailed track information retrieval
- Timestamp tracking
- Confidence scoring
- Duplicate detection and merging
- Error handling and logging
- Documentation and usage examples

### Technical Features
- Abstract base class for stream downloaders
- Factory pattern for platform-specific downloaders
- Modular architecture for easy platform additions
- Temporary file management
- FFmpeg integration
- Configuration validation
- Progress tracking
- Error reporting

## Future Plans
### Planned Features
- Support for additional streaming platforms
- Enhanced duplicate detection algorithms
- Local audio fingerprinting
- Batch processing capabilities
- Web interface
- Playlist export to various formats
- BPM detection and matching
- DJ transition detection
- Genre classification
- Improved confidence scoring
- API rate limiting optimization
- Caching system for recognized tracks

### Technical Improvements
- Unit test coverage
- Performance optimizations
- Memory usage improvements
- Error handling enhancements
- Documentation updates
- Code refactoring
- Configuration system improvements
- Logging system enhancements
