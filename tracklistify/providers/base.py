"""Base interfaces and error types for track identification providers."""

# Standard library imports
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class ProviderError(Exception):
    """Base class for provider-related errors."""

    pass


class AuthenticationError(ProviderError):
    """Raised when provider authentication fails."""

    pass


class RateLimitError(ProviderError):
    """Raised when provider rate limit is exceeded."""

    pass


class IdentificationError(ProviderError):
    """Raised when track identification fails."""

    pass


class TrackIdentificationProvider(ABC):
    """Abstract base class for track identification providers."""

    @abstractmethod
    async def identify_track(self, audio_segment) -> Optional[Dict[str, Any]]:
        """Identify a track from an audio segment."""
        pass

    @abstractmethod
    async def enrich_metadata(self, track_info: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich track metadata with additional information."""
        pass

    @abstractmethod
    async def close(self):
        """Cleanup resources."""
        pass


class MetadataProvider(ABC):
    """Base interface for metadata providers."""

    @abstractmethod
    async def enrich_metadata(self, track_info: Dict) -> Dict:
        """Enrich track metadata with additional information.

        Args:
            track_info: Basic track information

        Returns:
            Dict containing enriched track information

        Raises:
            AuthenticationError: If authentication fails
            RateLimitError: If rate limit is exceeded
            ProviderError: For other provider-related errors
        """
        pass

    @abstractmethod
    async def search_track(
        self,
        title: str,
        artist: Optional[str] = None,
        album: Optional[str] = None,
        duration: Optional[float] = None,
    ) -> Dict:
        """Search for a track using available metadata.

        Args:
            title: Track title
            artist: Artist name
            album: Album name
            duration: Track duration in seconds

        Returns:
            Dict containing track information

        Raises:
            AuthenticationError: If authentication fails
            RateLimitError: If rate limit is exceeded
            ProviderError: For other provider-related errors
        """
        pass

    async def close(self) -> None:
        """Close the provider's resources."""
        pass
