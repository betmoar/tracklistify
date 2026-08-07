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
  - TracklistifyTimeoutError: Operation timeouts
  - ProviderError: Base for provider-specific errors

Provider-Specific Exceptions:
- ShazamError: Shazam API specific errors
- SpotifyError: Spotify API specific errors
"""

from typing import Optional


class TracklistifyError(Exception):
    """Base exception class for Tracklistify."""

    pass


class ApplicationError(TracklistifyError):
    """Base application error for general application failures."""

    pass


class APIError(TracklistifyError):
    """Raised when an API request fails."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response: Optional[str] = None,
    ):
        self.status_code = status_code
        self.response = response
        super().__init__(message)


class DownloadError(TracklistifyError):
    """Raised when a download operation fails."""

    def __init__(
        self, message: str, url: Optional[str] = None, cause: Optional[Exception] = None
    ):
        self.url = url
        self.cause = cause
        super().__init__(message)


class ConfigError(TracklistifyError):
    """Raised when there's a configuration error."""

    pass


class AudioProcessingError(TracklistifyError):
    """Raised when audio processing fails."""

    def __init__(
        self,
        message: str,
        file_path: Optional[str] = None,
        cause: Optional[Exception] = None,
    ):
        self.file_path = file_path
        self.cause = cause
        super().__init__(message)


class TrackIdentificationError(TracklistifyError):
    """Raised when track identification fails or produces no results."""

    def __init__(
        self,
        message: str,
        segment: Optional[int] = None,
        cause: Optional[Exception] = None,
        context: Optional[dict] = None,
    ):
        self.segment = segment
        self.cause = cause
        self.context = context or {}
        super().__init__(message)


class ValidationError(TracklistifyError):
    """Raised when input validation fails."""

    pass


class TracklistifyTimeoutError(TracklistifyError):
    """Raised when an operation times out.

    Named to avoid shadowing the built-in ``TimeoutError``.
    """

    def __init__(
        self,
        message: str,
        timeout: Optional[float] = None,
        operation: Optional[str] = None,
    ):
        self.timeout = timeout
        self.operation = operation
        super().__init__(message)


# Provider-specific exceptions
class ProviderError(TracklistifyError):
    """Base exception for provider-specific errors."""

    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        cause: Optional[Exception] = None,
    ):
        self.provider = provider
        self.cause = cause
        super().__init__(message)


class ACRCloudError(ProviderError):
    """Raised when ACRCloud API operations fail."""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        cause: Optional[Exception] = None,
    ):
        self.error_code = error_code
        super().__init__(message, provider="ACRCloud", cause=cause)


class ShazamError(ProviderError):
    """Raised when Shazam API operations fail."""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        cause: Optional[Exception] = None,
    ):
        self.error_code = error_code
        super().__init__(message, provider="Shazam", cause=cause)


class SpotifyError(ProviderError):
    """Raised when Spotify API operations fail."""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        cause: Optional[Exception] = None,
    ):
        self.error_code = error_code
        super().__init__(message, provider="Spotify", cause=cause)


class AuthenticationError(TracklistifyError):
    """Raised when authentication fails."""

    def __init__(
        self,
        message: str,
        service: Optional[str] = None,
        cause: Optional[Exception] = None,
    ):
        self.service = service
        self.cause = cause
        super().__init__(message)


class RateLimitError(ProviderError):
    """Raised when provider rate limit is exceeded."""

    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        retry_after: Optional[float] = None,
    ):
        self.retry_after = retry_after
        super().__init__(message, provider=provider)


class IdentificationError(ProviderError):
    """Raised when track identification fails."""

    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(message, provider=provider, cause=cause)


class ExportError(TracklistifyError):
    """Raised when exporting data fails."""

    def __init__(
        self,
        message: str,
        format: Optional[str] = None,
        cause: Optional[Exception] = None,
    ):
        self.format = format
        self.cause = cause
        super().__init__(message)
