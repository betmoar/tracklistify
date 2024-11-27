"""Provider factory for creating track identification providers."""

# Standard library imports
from typing import Dict, Optional, Type

# Local imports
from .base import TrackIdentificationProvider
from .shazam import ShazamProvider
from .spotify import SpotifyProvider

_provider_factory = None


def create_provider_factory() -> "ProviderFactory":
    """Create and return a provider factory instance."""
    global _provider_factory
    if _provider_factory is None:
        _provider_factory = ProviderFactory()
    return _provider_factory


class ProviderFactory:
    """Factory class to manage identification providers."""

    def __init__(self):
        """Initialize the provider factory."""
        self.providers = {}

    def get_identification_provider(self, provider_name):
        """Retrieve or create an identification provider by name."""
        if provider_name in self.providers:
            return self.providers[provider_name]
        else:
            # Create a new provider instance based on the name
            if provider_name == "shazam":
                from tracklistify.providers.shazam import ShazamProvider

                provider = ShazamProvider()
            elif provider_name == "acrcloud":
                from tracklistify.providers.acrcloud import ACRCloudProvider

                provider = ACRCloudProvider()
            else:
                raise ValueError(f"Unknown provider: {provider_name}")
            self.providers[provider_name] = provider
            return provider

    async def close_all(self):
        """Close all providers."""
        for provider in self.providers.values():
            await provider.close()  # Make sure to await the coroutine
