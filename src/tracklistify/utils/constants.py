"""
Centralized constants for the tracklistify package.

This module provides named constants for magic numbers used throughout
the codebase, improving maintainability and readability.
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
DEFAULT_SEGMENT_PADDING = 0.5  # seconds before/after segment
MIN_SEGMENT_FILE_SIZE = 1000  # bytes - minimum valid segment size
DEFAULT_THREAD_POOL_WORKERS = 4  # for audio segmentation
FFMPEG_MP3_QUALITY = 5  # 0-9 scale, lower is better quality

# Cache defaults
DEFAULT_CACHE_TTL = 3600  # 1 hour
DEFAULT_CACHE_MAX_SIZE = 1_000_000  # 1 million entries

# Rate limiter defaults
DEFAULT_RATE_LIMIT_TIMEOUT = 30.0  # seconds
CIRCUIT_BREAKER_RESET_TIMEOUT = 60.0  # seconds
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5
TOKEN_REFILL_SLEEP = 0.01  # seconds between refill checks
REFILL_INTERVAL_THRESHOLD = 1.0  # seconds

# Provider rate limits (requests per minute)
SHAZAM_DEFAULT_RPM = 25
ACRCLOUD_DEFAULT_RPM = 30
ACRCLOUD_DEFAULT_CONCURRENT = 5
SPOTIFY_DEFAULT_RPM = 120
SPOTIFY_DEFAULT_CONCURRENT = 20
GLOBAL_DEFAULT_RPM = 25
GLOBAL_DEFAULT_CONCURRENT = 2

# Shazam scoring constants
SHAZAM_COOLDOWN_DEFAULT = 2.25  # seconds between calls
SHAZAM_SKEW_CAP = 0.1  # maximum skew value
SHAZAM_SCORE_MULTIPLIER = 100
SHAZAM_FREQ_WEIGHT = 0.6
SHAZAM_TIME_WEIGHT = 0.4

# Security constants
MIN_PASSWORD_LENGTH = 8
MASK_ASTERISK_COUNT = 5
ROTATION_INTERVAL_DAYS = 90

# Logging constants
LOG_BACKUP_COUNT = 5
LOG_MAX_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

# API constants
SPOTIFY_BATCH_SIZE = 100
SPOTIFY_SEARCH_LIMIT = 5
SPOTIFY_DEFAULT_RETRY_AFTER = 60  # seconds
ACRCLOUD_SUCCESS_CODE = 2000
ACRCLOUD_DEFAULT_TIMEOUT = 10  # seconds

# Confidence scoring
DEFAULT_CONFIDENCE = 100.0
MAX_CONFIDENCE = 100

# Hash/digest constants
STABLE_HASH_LENGTH = 16  # characters from SHA256 digest
