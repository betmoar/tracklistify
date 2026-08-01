# Changelog

All notable changes to Tracklistify will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Release dates are in YYYY-MM-DD format.

## [Unreleased]

## [0.9.0] - 2026-08-01

### Added

- **Richer track metadata in JSON output.** `Track.metadata` existed as a
  field with nothing writing to it and nothing reading it; both ends are now
  wired. The Shazam provider surfaces ISRC, genre, album, label, release
  date, Shazam/Apple Music ids and artwork from the raw payload, and
  `_save_json` serializes them per track. Empty values are dropped rather
  than stored as `null`, and a track with no extras serializes as `null`
  rather than `{}`. Merges [#57](https://github.com/betmoar/tracklistify/pull/57)
  by @fakhavan. Markdown and M3U output are unchanged.
- **Platform search links.** Shazam ships per-platform deeplinks alongside
  every match in `hub.providers` — free, no extra API call. Surfaced as
  `spotify_search_url` / `deezer_search_url`, converted from Shazam's
  app-scheme URIs (`spotify:search:`, `deezer-query://`) to https so they
  are clickable from the JSON. Named `*_search_url` because they are
  searches: Shazam does not resolve a canonical track id. Coverage is
  partial — measured at 12/20 tracks on a real set, since `hub.providers`
  is absent from roughly 40% of responses.
- **`--no-cache`.** Re-downloads and re-identifies, ignoring stored results.
  It is a *refresh*, not a disable: cache reads are skipped while writes
  stay live, so a wrong stored identification is overwritten rather than
  stepped around. Disabling the caches instead would gate the writes too and
  leave the stale entry to be served again on the next run.

### Changed

- **`cache_ttl` 1 hour → 30 days**, with `cache_max_age` raised to match.
  The identification cache is keyed on the segment's content hash, so a
  stored response does not go stale the way a typical HTTP cache entry does
  — a provider improving its catalog is the only real staleness, and weeks
  is the right granularity. At one hour, re-running yesterday's mix re-paid
  the full identification cost. Both values must move together: they are
  independent expiry gates and the shorter one wins.
- **Logging levels reflect outcomes again.** A healthy run printed a wall of
  "No track information found in Shazam response." and nothing about the
  tracks it identified. The per-track success line is back at INFO with its
  timestamp and artist; unmatched segments — the normal case in a DJ mix —
  are now debug. A run where *no* segment matches emits a single warning,
  since a broken request pipeline is otherwise indistinguishable from a set
  of unreleased IDs.
- Running `tracklistify` with no arguments prints help and exits 0 instead
  of an argparse usage error.
- `TrackMatcher.__init__` accepts an optional config, and
  `IdentificationManager` passes its own — previously the matcher always
  re-resolved the global singleton, so an injected config never reached it.

### Fixed

- **Identity chaining could delete a whole play.** Artist Jaccard is not
  transitive, so testing cluster membership against *any* member let a
  collaboration credit bridge two distinct artists: `Artist A` and
  `Artist B` share no tokens, but `Artist A, Artist B` matches both. Each
  hop also refreshed the cluster's proximity anchor, so the chain ran
  unbounded — six detections spanning two separate plays collapsed to one
  row and the second play vanished. Identity is now anchored on `cluster[0]`
  while proximity stays anchored on `cluster[-1]`.
- **Search-URL encoding.** Deezer's deeplink embeds unescaped apostrophes,
  so term extraction truncated at the first one in the text itself
  (`Don't Stop` searched for `Don`). Separately, `quote()`'s default left
  slashes intact, so `AC/DC` injected a path segment into the search URL.
- **A malformed `hub.providers` entry no longer costs the identification.**
  A non-string `type` raised from `.strip()` inside `identify_track`'s outer
  try, escalating to `ShazamError` and discarding a match whose title,
  artist and ISRC were all valid.
- **SoundCloud `/sets/` with no downloadable entries fails loudly.** An
  empty `entries` list fell through, leaving the *set's* metadata in place —
  silently reinstating the bug the unwrap exists to fix — and built an
  output path for a file that was never written.
- **A missing downloaded file is no longer reported as success.** When the
  glob fallback found nothing, the reconstructed path was returned anyway
  and the failure first surfaced several frames later as "Could not read
  audio file".
- **JSON export cannot leave a truncated file.** `json.dump` streams, so a
  serialization error partway through wrote a partial file that looked
  complete — after the entire expensive identification pass. Serialization
  now completes in memory first, with a `default=str` fallback.
- `cz bump` aborted on a `changelog_start_rev` pointing at a tag that does
  not exist in this repository.
- **Dedup now merges artist-string variants.** The same track appeared twice
  in output when Shazam returned different collaboration artist strings on
  adjacent segments (`Berghain (Remix)` at 1900s as
  `Conrad Taylor & ROSALÍA & Björk & Yves Tumor` and at 1950s as
  `ROSALÍA, Björk & Yves Tumor`). `get_unique_tracks` — the shipping dedup
  path — keyed on exact `artist|song` strings and ignored time entirely.
  It now clusters by identity (normalized-title equality + artist token-set
  Jaccard ≥ 0.34) within a proximity window derived from the segmentation
  step (`2 * (segment_length - overlap_duration)`, 100s by default), so
  adjacent-segment detections merge while a track genuinely played twice in
  a set stays two entries. Proximity is measured as the gap to a cluster's
  most recent detection: a long track keeps arriving one segmentation step
  apart so the chain holds, while two distinct plays are separated by
  minutes of other music so it breaks. (Bounding the total span instead
  wrongly splits long tracks; testing against any member is transitively
  unbounded and silently deletes distinct plays.)
- **Stable representative selection.** Cluster representatives were chosen
  by strict `>` on confidence, so Shazam's per-run jitter could change which
  detection won — and therefore the reported `time_in_mix` — between runs of
  identical audio. Selection is now purely `(time, name, artist)`: the
  earliest detection represents the cluster and confidence is not an input,
  because every member is the same track and any confidence-derived term
  reintroduces the jitter.
- **`time_threshold` works again.** It was assigned and never read, while
  `.env.example` advertised it as controlling merge behavior. It is now the
  dedup-window override; the default drops from `30.0` to `0.0`, meaning
  "derive from the segmentation step" (the old 30s default was narrower
  than one 50s step and would have split adjacent-segment detections). Any
  override below the derived window is floored, with a warning, because a
  narrower window cannot merge adjacent detections at all.
- **Multi-track SoundCloud sets warn instead of silently truncating.** Only
  `entries[0]` is processed; previously the discarded count appeared only at
  debug level, so a set silently produced a one-track tracklist and cached
  it under the set's URL.
- **`config.min_confidence` is no longer a no-op.** `TrackMatcher` hardcoded
  a 0 threshold, so the documented (and validated) knob did nothing. It is
  now applied, scaled from the config's 0.0–1.0 range to `Track.confidence`'s
  0–100. The default drops from `0.5` to `0.0` so existing output is
  unchanged until a user raises it.
- **SoundCloud `/sets/` URLs no longer propagate container metadata.** These
  extract as a playlist whose id/ext/duration describe the *set*, not the
  track; the downloader now unwraps to `entries[0]` before anything reads the
  info dict. Previously the wrong title/duration reached the output folder
  name, the M3U, and — via the sidecar — persisted in the download cache.
- **Output path resolution prefers `requested_downloads[0]["filepath"]`**
  (the path yt-dlp actually wrote) over reconstructing it with
  `prepare_filename`, which missed extension changes made during muxing.
- **Download cache entries are version-stamped** (`KEY_VERSION` in the key
  material), invalidating stale pre-fix `/sets/` metadata that would
  otherwise be served indefinitely — the cache has no TTL or eviction.

### Removed

- **`max_duplicates` config field.** It capped how many detections one dedup
  cluster could absorb, but every value that fits a real mix is wrong: a
  track spanning several segments legitimately yields 4+ detections, so any
  low cap splits it back into duplicate rows. It had been dead (assigned,
  never read) and wiring it up broke real output, so the field, its two
  validators, its `TypedDict` mirror and its docs are gone.
- Dead `TrackMatcher.merge_nearby_tracks` and its six private helpers. They
  had no production callers; `get_unique_tracks` is now the sole dedup
  authority and `add_track` only confidence-gates and appends.

## [0.8.2] - 2026-07-31

End-to-end caching and self-contained output: wires the existing
identification cache into the pipeline, adds a URL-keyed download cache so
re-runs skip the network, restructures output into per-set subfolders
(audio + tracklist + playable M3U), and fixes Mixcloud metadata. Builds on
the audit-driven hardening of 0.7.0 (importability, provider ABC
alignment, config bug fixes, test modernisation, lint hygiene).

### Added

- `tracklistify.utils.validation.clean_url` — URL normaliser used by the Spotify
  downloader (strips query/fragment/trailing slash, lowercases scheme + host).
- `Track.metadata: Dict[str, Any]` field for provider enrichment (e.g.
  `spotify_id`), seeded by `field(default_factory=dict)` so every instance
  gets an independent dict via the dataclass-generated `__init__`. Validation
  and config back-fill run in `__post_init__`.
- `SecureConfigLoader.needs_rotation(secret_version)` — previously called by
  `get_secret()` but never defined; now compares secret age against
  `_rotation_interval` (default 90 days).
- Async context-manager protocol (`__aenter__` / `__aexit__`) on
  `TrackIdentificationProvider` and `MetadataProvider` for deterministic
  resource cleanup.
- `tracklistify.utils.constants` module consolidating timeouts, thresholds,
  and other magic numbers previously scattered across the codebase.
- New test modules: `tests/test_imports.py` (smoke-tests every public import),
  `tests/test_security.py`, `tests/test_track_metadata.py`,
  `tests/test_providers_spotify.py`, plus the broader Phase 4 / consistency
  suites added on this branch. Total: **335 passing tests**.
- `docs/archive/` for historical implementation artefacts (audit report,
  multi-phase implementation plans, summaries) with a README explaining
  their status.
- `CLAUDE.md` at repo root with a comprehensive guide for AI-assisted
  development (project layout, conventions, common tasks).
- `TRACKLISTIFY_SHAZAM_PROXY` config option — routes `ShazamProvider`
  identification requests through an HTTP proxy via shazamio's
  `recognize(..., proxy=...)`. Empty by default (direct connection);
  `proxy` added to the sensitive-field patterns so a credential embedded
  in the proxy URL is redacted in logs.
- Identification results are now cached. `IdentificationManager.identify_tracks`
  consults the cache (`get_cache()`) before each provider call, keyed by
  `f"{provider}:{sha256(segment_bytes)}"`, and stores successful responses
  for reuse across reruns. Cache I/O is best-effort (failures degrade to
  live identification, never abort the run); gated by the existing
  `cache_enabled` config flag. Closes the P1 backlog item.
- Downloaded audio is now cached. A new `DownloadCache`
  (`cache_dir/downloads/<sha256>` + `.meta.json` sidecar) keys on a
  per-provider canonical URL + `stream_copy` flag, so re-running the same
  URL skips the network entirely and reads metadata from the sidecar.
  Canonicalization is offline: YouTube URLs (watch?v=, youtu.be/, /shorts/,
  /embed/, /live/, m./music.) collapse to `yt:<video_id>`; SoundCloud to
  `sc:<host><path>`; Mixcloud to `mc:<user>_<slug>`. Also fixes Mixcloud,
  which previously stored no metadata. Gated by new
  `download_cache_enabled` (default `true`).
- Output is now self-contained per set. Each run produces
  `output/[date] Artist - Title/` containing `tracklist.{json,md,m3u}`
  **and the source audio file**, replacing the previous flat layout. The
  uploader (from yt-dlp metadata) now populates the artist slot — folder
  names no longer say "Unknown Artist". The subfolder is movable.
- The M3U playlist is now playable. It points at the real audio file in
  the subfolder and uses VLC `#EXTVLCOPT:start-time` for per-track seeking;
  EXTINF duration is the inter-track gap (last track uses
  `total_duration − last_start`). Previously it emitted only comments with
  no playable URI lines and EXTINF was always `-1`.

### Changed

- **Breaking:** output structure changed from flat
  `output/[date] Artist - Title.{json,md,m3u}` to
  `output/[date] Artist - Title/tracklist.{json,md,m3u}` (+ audio).
- `AsyncApp.save_output` now wires `self.uploader` into `mix_info["artist"]`
  and passes `total_duration`.
- `core/__init__.py` now eager-loads only leaf modules (`exceptions`, `types`)
  and lazy-loads `AsyncApp` / `Track` / `TrackMatcher` via PEP 562
  `__getattr__`. This is what unblocks `import tracklistify` — see Fixed below.
- `SpotifyProvider.search_track` realigned with the `MetadataProvider` ABC:
  `(title, artist=None, album=None, duration=None) -> Dict`. Returns the
  top-match result as a flat dict keyed on `spotify_id` (was: `(query)` →
  `List[Dict]`, which no internal caller actually used).
- `TrackIdentificationConfig.__post_init__` reduced to a single
  `super().__post_init__()` call. The override previously ran
  `_load_from_env`, `_setup_validation`, and `_validate` twice each; virtual
  dispatch ensures the subclass's `_setup_validation` extra rules still run.
- `_is_platform_url` now delegates subdomain matching to the existing
  `_is_domain_or_subdomain` helper instead of reimplementing the logic;
  `allowed_domains` typed as `Iterable[str]` so list/set callers both fit.
- `URLValidationError` reparented under `ValidationError` so
  `except ValidationError:` catches URL failures.
- `mask_sensitive_data` / `is_sensitive_field` casing now consistent —
  `SENSITIVE_FIELDS` holds only lowercase substrings, matching is done after
  `.lower()` so `ACR_ACCESS_KEY` / `acr_access_key` / `secret` all match.
- `CryptoManager` docstrings: replaced "AES-256 in CBC mode" with truthful
  description (PBKDF2-derived key + XOR-block obfuscation; not
  cryptographically secure — for real protection use OS keychain or KMS).
- Singletons (`get_config`, cache factory, rate limiter) made thread-safe via
  `threading.Lock` and stable hashing so concurrent first-access doesn't
  produce duplicate instances.
- Time-elapsed measurements now use `time.monotonic()` consistently across
  rate limiter, decorators, and identification manager.
- `[tool.ruff] include` now points at `src/tracklistify/**/*.py` /
  `tests/**/*.py` — previously pointed at `tracklistify/**/*.py` and was
  silently linting zero files.
- Dependencies bumped: aiohttp 3.13, yt-dlp 2025.11, click 8.3, pytest 8.4,
  pytest-asyncio 1.3, ruff 0.14, plus minor bumps across the dev group.

### Fixed

- **Circular import** that prevented `import tracklistify` from succeeding.
  The chain ran through `utils.identification → config.factory →
  core.exceptions → core/__init__.py → core/base.py → downloaders.factory →
  config` (back to a partially-initialised `config`). Fix: lazy `core`
  re-exports + lazy `get_config` import in `core.base`.
- `core/__init__.py` imported `ApplicationError` from `.base`; the class
  actually lives in `.exceptions`.
- `tracklistify.downloaders.spotify` imported a non-existent `clean_url`
  symbol; the function now exists in `utils.validation`.
- `Track.metadata` was referenced by `exporters/spotify.py` and
  `providers/spotify.py` but never declared on the dataclass.
- `SecureConfigLoader.get_secret` called `self.needs_rotation(secret_version)`
  without that method existing.
- Spotify provider's `search_track` signature didn't match the
  `MetadataProvider` ABC, breaking the internal `enrich_metadata` call.
- `tests/test_to_dict` asserted `verbose=False` while reading from the local
  `.env` (which commonly sets `TRACKLISTIFY_VERBOSE=true`); now uses
  `monkeypatch.delenv` for determinism.
- Logger handler duplication on reconfiguration (each `set_logger` call no
  longer stacks a new handler).
- Downloaders no longer return `None` from exception handlers — they raise
  `DownloadError` so failures propagate.
- `cli` `--verbose` flag default corrected to `False`.
- Various type hints corrected and return-type annotations added.

### Removed

- **Breaking:** `tracklistify.utils.SimpleLimiter` and
  `get_simple_rate_limiter` — the secondary in-process limiter was a parallel
  code path that duplicated `GlobalRateLimiter`. Public callers should migrate
  to `tracklistify.utils.rate_limiter.get_global_rate_limiter()`, which
  returns the singleton token-bucket-plus-circuit-breaker limiter used by
  the rest of the codebase.
- **Breaking:** `TrackMatcher.process_file` — legacy stub that cleared
  `self.tracks` then merged the empty list, so it always returned `[]`
  regardless of input. No callers in `src/` or `tests/`. Use
  `tracklistify.utils.identification.IdentificationManager` for real
  identification.
- Deprecated `mask_sensitive_value_old` (no callers; superseded by the
  key-aware `mask_sensitive_value`).
- Duplicate `ConfigurationError` in `core.exceptions` (the canonical name is
  `ConfigError`; zero importers referenced the duplicate).
- Test/mock code that had leaked into production sources under `core/` and
  `cache/`.
- Five session-artefact MDs from repo root (`AUDIT_REPORT.md`,
  `IMPLEMENTATION_PLAN.md`, `IMPLEMENTATION_PLAN_PHASES_3_6.md`,
  `IMPLEMENTATION_QUICK_REFERENCE.md`, `IMPLEMENTATION_SUMMARY.md`) — moved
  to `docs/archive/` rather than deleted, to preserve the paper trail.

### Deprecated

- `tracklistify.cache.run_async`: now emits `DeprecationWarning`. Prefer
  awaiting coroutines directly or using `asyncio.run`. The body is unchanged
  so existing callers continue to work; removal is deferred to a future
  release.

### Security

- `is_sensitive_field` casing bug fixed (described under Changed).
- `CryptoManager` docstrings no longer claim AES-256 — callers can now make
  informed decisions about whether the obfuscation is fit for purpose.
- Centralised exception consolidation reduces the chance of `except` blocks
  silently missing a divergent error class.

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
    - Vorbis: 96, 160, 320 kbps
    - AAC: 24, 32, 96, 128, 256 kbps
  - Multiple output formats (M4A/OGG/MP3)
  - Rich metadata tagging:
    - Artist and album information
    - Track and disc numbers
    - Release dates and genres
    - Cover art embedding
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
    - /output: Downloaded files
    - /temp: Temporary processing
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
  - Added \_parse_env_value helper for robust type conversion
  - Support for various boolean formats (true/1/yes/on)
  - Proper handling of Path expansion
  - Improved validation error messages
- Improved environment variable handling:
  - Enhanced list parsing with multiple formats support
  - Automatic type conversion for all config fields
  - Better error messages for invalid values
  - Support for single value and comma-separated lists
- Configuration improvements:
  - Added \_parse_env_value helper for robust type conversion
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
