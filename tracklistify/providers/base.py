"""Base interfaces and error types for track identification providers."""

from abc import ABC, abstractmethod
from typing import Dict, Optional


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
    """Base interface for track identification providers."""

    @abstractmethod
    async def identify_track(self, audio_data: bytes, start_time: float = 0) -> Dict:
        """Identify a track from audio data.
        
        Args:
            audio_data: Raw audio data bytes
            start_time: Start time in seconds for the audio segment
            
        Returns:
            Dict containing track information
            
        Raises:
            AuthenticationError: If authentication fails
            RateLimitError: If rate limit is exceeded
            IdentificationError: If identification fails
            ProviderError: For other provider-related errors
        """
        pass

    @abstractmethod
    async def enrich_metadata(self, track_info: Dict) -> Dict:
        """Enrich track metadata with additional information.
        
        Args:
            track_info: Basic track information
            
        Returns:
            Dict containing enriched track information
        """
        pass

    async def close(self) -> None:
        """Close the provider's resources."""
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
