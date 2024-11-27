"""
Custom exceptions for Tracklistify.

This module defines specific exception types for different error scenarios
in the Tracklistify application, making error handling more precise and
informative. The exception hierarchy is organized as follows:

Base Exceptions:
- TracklistifyError: Base exception for all Tracklistify errors
  - APIError: API request failures
  - DownloadError: Download operation failures
  - ConfigError: Configuration issues
  - AudioProcessingError: Audio processing failures
  - TrackIdentificationError: Track identification failures
  - ValidationError: Input validation failures
  - RetryExceededError: Maximum retry attempts exceeded
  - TimeoutError: Operation timeouts
  - ProviderError: Base for provider-specific errors
  - DownloaderError: Base for downloader-specific errors

Provider-Specific Exceptions:
- ACRCloudError: ACRCloud API specific errors
- ShazamError: Shazam API specific errors
- SpotifyError: Spotify API specific errors

Downloader-Specific Exceptions:
- YouTubeError: YouTube download specific errors
- SoundCloudError: SoundCloud download specific errors
"""


class TracklistifyError(Exception):
    """Base exception class for Tracklistify."""

    pass


class APIError(TracklistifyError):
    """Raised when an API request fails."""

    def __init__(self, message: str, status_code: int = None, response: str = None):
        self.status_code = status_code
        self.response = response
        super().__init__(message)


class DownloadError(TracklistifyError):
    """Raised when a download operation fails."""

    def __init__(self, message: str, url: str = None, cause: Exception = None):
        self.url = url
        self.cause = cause
        super().__init__(message)


class ConfigError(TracklistifyError):
    """Raised when there's a configuration error."""

    pass


class AudioProcessingError(TracklistifyError):
    """Raised when audio processing fails."""

    def __init__(self, message: str, file_path: str = None, cause: Exception = None):
        self.file_path = file_path
        self.cause = cause
        super().__init__(message)


class TrackIdentificationError(TracklistifyError):
    """Raised when track identification fails."""

    def __init__(self, message: str, segment: int = None, cause: Exception = None):
        self.segment = segment
        self.cause = cause
        super().__init__(message)


class ValidationError(TracklistifyError):
    """Raised when input validation fails."""

    pass


class RetryExceededError(TracklistifyError):
    """Raised when maximum retry attempts are exceeded."""

    def __init__(
        self, message: str, attempts: int = None, last_error: Exception = None
    ):
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(message)


class TimeoutError(TracklistifyError):
    """Raised when an operation times out."""

    def __init__(self, message: str, timeout: float = None, operation: str = None):
        self.timeout = timeout
        self.operation = operation
        super().__init__(message)


# Provider-specific exceptions
class ProviderError(TracklistifyError):
    """Base exception for provider-specific errors."""

    def __init__(self, message: str, provider: str = None, cause: Exception = None):
        self.provider = provider
        self.cause = cause
        super().__init__(message)


class ACRCloudError(ProviderError):
    """Raised when ACRCloud API operations fail."""

    def __init__(self, message: str, error_code: str = None, cause: Exception = None):
        self.error_code = error_code
        super().__init__(message, provider="ACRCloud", cause=cause)


class ShazamError(ProviderError):
    """Raised when Shazam API operations fail."""

    def __init__(self, message: str, error_code: str = None, cause: Exception = None):
        self.error_code = error_code
        super().__init__(message, provider="Shazam", cause=cause)


class SpotifyError(ProviderError):
    """Raised when Spotify API operations fail."""

    def __init__(self, message: str, error_code: str = None, cause: Exception = None):
        self.error_code = error_code
        super().__init__(message, provider="Spotify", cause=cause)


# Downloader-specific exceptions
class DownloaderError(TracklistifyError):
    """Base exception for downloader-specific errors."""

    def __init__(self, message: str, service: str = None, cause: Exception = None):
        self.service = service
        self.cause = cause
        super().__init__(message)


class YouTubeError(DownloaderError):
    """Raised when YouTube download operations fail."""

    def __init__(self, message: str, video_id: str = None, cause: Exception = None):
        self.video_id = video_id
        super().__init__(message, service="YouTube", cause=cause)


class SoundCloudError(DownloaderError):
    """Raised when SoundCloud download operations fail."""

    def __init__(self, message: str, track_id: str = None, cause: Exception = None):
        self.track_id = track_id
        super().__init__(message, service="SoundCloud", cause=cause)


class URLValidationError(TracklistifyError):
    """Raised when URL validation fails."""

    pass


class ConfigurationError(TracklistifyError):
    """Raised when configuration is invalid."""

    pass


class AuthenticationError(TracklistifyError):
    """Raised when authentication fails."""

    def __init__(self, message: str, service: str = None, cause: Exception = None):
        self.service = service
        self.cause = cause
        super().__init__(message)


class ExportError(TracklistifyError):
    """Raised when exporting data fails."""

    def __init__(self, message: str, format: str = None, cause: Exception = None):
        self.format = format
        self.cause = cause
        super().__init__(message)
