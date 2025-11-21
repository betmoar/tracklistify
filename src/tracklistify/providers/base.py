"""Base interfaces and error types for track identification providers."""

# Standard library imports
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

# Import exceptions from canonical location
from tracklistify.core.exceptions import (
    AuthenticationError,
    IdentificationError,
    ProviderError,
    RateLimitError,
)

# Re-export for backward compatibility
__all__ = [
    "AuthenticationError",
    "IdentificationError",
    "ProviderError",
    "RateLimitError",
    "TrackIdentificationProvider",
    "MetadataProvider",
]


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

    @abstractmethod
    async def close(self) -> None:
        """Close the provider's resources."""
        pass

    async def __aenter__(self) -> "MetadataProvider":
        """Enter async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context manager, ensuring cleanup."""
        await self.close()
