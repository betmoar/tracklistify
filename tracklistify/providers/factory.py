"""Provider factory for managing track identification and metadata providers."""

import logging
import os
from typing import Dict, List, Optional, Type, Union
from .base import TrackIdentificationProvider, MetadataProvider, ProviderError
from .spotify import SpotifyProvider
from .shazam import ShazamProvider
from .acrcloud import ACRCloudProvider
from ..config import Config

logger = logging.getLogger(__name__)

class ProviderFactory:
    """Factory for creating and managing providers."""

    def __init__(self):
        self._identification_providers: Dict[str, TrackIdentificationProvider] = {}
        self._metadata_providers: Dict[str, MetadataProvider] = {}

    def register_identification_provider(
        self, name: str, provider: TrackIdentificationProvider
    ) -> None:
        """Register a track identification provider."""
        if not isinstance(provider, TrackIdentificationProvider):
            raise ValueError(f"Provider {name} must implement TrackIdentificationProvider")
        self._identification_providers[name] = provider

    def register_metadata_provider(
        self, name: str, provider: MetadataProvider
    ) -> None:
        """Register a metadata provider."""
        if not isinstance(provider, MetadataProvider):
            raise ValueError(f"Provider {name} must implement MetadataProvider")
        self._metadata_providers[name] = provider

    def get_identification_provider(self, name: str) -> Optional[TrackIdentificationProvider]:
        """Get a track identification provider by name."""
        provider = self._identification_providers.get(name)
        if not provider:
            logger.warning(f"Identification provider {name} not found")
        return provider

    def get_metadata_provider(self, name: str) -> Optional[MetadataProvider]:
        """Get a metadata provider by name."""
        provider = self._metadata_providers.get(name)
        if not provider:
            logger.warning(f"Metadata provider {name} not found")
        return provider

    def get_all_identification_providers(self) -> List[TrackIdentificationProvider]:
        """Get all registered track identification providers."""
        return list(self._identification_providers.values())

    def get_all_metadata_providers(self) -> List[MetadataProvider]:
        """Get all registered metadata providers."""
        return list(self._metadata_providers.values())

    async def close_all(self) -> None:
        """Close all provider connections."""
        for provider in self._identification_providers.values():
            await provider.close()
        for provider in self._metadata_providers.values():
            await provider.close()

def create_provider_factory(config: Config) -> ProviderFactory:
    """Create and configure a provider factory based on configuration.

    Args:
        config: Configuration object containing provider settings

    Returns:
        Configured ProviderFactory instance
        
    Raises:
        ProviderError: If provider configuration is invalid
    """
    factory = ProviderFactory()
    
    try:
        # Get credentials from environment
        acr_access_key = os.getenv('ACR_ACCESS_KEY')
        acr_access_secret = os.getenv('ACR_ACCESS_SECRET')
        spotify_client_id = os.getenv('SPOTIFY_CLIENT_ID')
        spotify_client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')

        # Configure ACRCloud provider
        if acr_access_key and acr_access_secret:
            acr_provider = ACRCloudProvider(
                access_key=acr_access_key,
                access_secret=acr_access_secret,
                host=config.providers.acrcloud_host,
                timeout=config.providers.acrcloud_timeout,
            )
            factory.register_identification_provider("acrcloud", acr_provider)
            logger.info("Registered ACRCloud provider")

        # Configure Shazam provider
        if config.providers.shazam_enabled:
            shazam_provider = ShazamProvider()
            factory.register_identification_provider("shazam", shazam_provider)
            logger.info("Registered Shazam provider")

        # Configure Spotify provider
        if spotify_client_id and spotify_client_secret:
            spotify_provider = SpotifyProvider(
                client_id=spotify_client_id,
                client_secret=spotify_client_secret,
            )
            factory.register_metadata_provider("spotify", spotify_provider)
            logger.info("Registered Spotify provider")

        # Validate at least one identification provider is registered
        if not factory.get_all_identification_providers():
            raise ProviderError("No identification providers configured. Please check your configuration.")

        return factory
        
    except Exception as e:
        raise ProviderError(f"Failed to create provider factory: {str(e)}")
