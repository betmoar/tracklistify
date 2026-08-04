"""Provider factory for creating track identification providers."""

# Standard library imports
import os
import threading
from typing import TYPE_CHECKING, Optional

# Local imports
from tracklistify.core.exceptions import ConfigError

if TYPE_CHECKING:
    from tracklistify.providers.spotify import SpotifyProvider

_provider_factory = None
_provider_lock = threading.Lock()

# Provider names this factory knows how to build. Keep in sync with the
# branches in ProviderFactory.get_identification_provider — the invariant
# test in tests/test_handoff_invariants.py checks each name constructs
# (or fails with a clear ConfigError, never a TypeError).
KNOWN_PROVIDERS = ("shazam", "acrcloud")


def create_provider_factory() -> "ProviderFactory":
    """Create and return a provider factory instance.

    This function is thread-safe using double-checked locking pattern.
    Multiple threads can safely call this function concurrently.

    Returns:
        ProviderFactory: The global provider factory instance.
    """
    global _provider_factory

    # Fast path: instance already exists
    if _provider_factory is not None:
        return _provider_factory

    # Slow path: need to create instance (thread-safe)
    with _provider_lock:
        # Double-check inside lock
        if _provider_factory is None:
            _provider_factory = ProviderFactory()

    return _provider_factory


def clear_provider_cache() -> None:
    """Clear the cached providers to force recreation with updated implementations.

    This function is thread-safe.
    """
    global _provider_factory
    with _provider_lock:
        if _provider_factory is not None:
            _provider_factory.clear_cache()
            _provider_factory = None


class ProviderFactory:
    """Factory class to manage identification providers."""

    def __init__(self) -> None:
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

                # Credentials are read from the environment (documented in
                # .env.example), NOT from the config dataclass — keeping
                # secrets off the dataclass avoids leaking them via repr()
                # or error messages.
                access_key = os.getenv("TRACKLISTIFY_ACR_ACCESS_KEY")
                access_secret = os.getenv("TRACKLISTIFY_ACR_ACCESS_SECRET")
                if not access_key or not access_secret:
                    raise ConfigError(
                        "ACRCloud provider requires TRACKLISTIFY_ACR_ACCESS_KEY "
                        "and TRACKLISTIFY_ACR_ACCESS_SECRET in the environment "
                        "or .env file. Get credentials at "
                        "https://console.acrcloud.com/ or use "
                        "`--provider shazam` (no credentials needed)."
                    )
                host = os.getenv(
                    "TRACKLISTIFY_ACR_HOST", "identify-eu-west-1.acrcloud.com"
                )
                provider = ACRCloudProvider(
                    access_key=access_key,
                    access_secret=access_secret,
                    host=host,
                )
            else:
                raise ValueError(
                    f"Unknown provider: {provider_name!r}. "
                    f"Known providers: {', '.join(KNOWN_PROVIDERS)}"
                )
            self.providers[provider_name] = provider
            return provider

    # Cache key for the enrichment-only Spotify provider. Distinct from any
    # identification provider name (KNOWN_PROVIDERS) so it cannot collide, and
    # leading underscore keeps it out of the identification name space.
    _SPOTIFY_ENRICHMENT_KEY = "_spotify_enrichment"

    def get_spotify_provider(self) -> "Optional[SpotifyProvider]":
        """Return a configured Spotify enrichment provider, or None.

        Reads ``TRACKLISTIFY_SPOTIFY_CLIENT_ID`` and
        ``TRACKLISTIFY_SPOTIFY_CLIENT_SECRET`` from the environment, following
        the ACRCloud env-only pattern — secrets are deliberately NOT on the
        config dataclass (they would leak through ``repr()`` and validation
        error messages).

        Unlike ``get_identification_provider`` for ACRCloud, missing
        credentials return ``None`` rather than raising ``ConfigError``:
        identification *requires* its provider, enrichment does not. Absent
        creds are a skip, not an error. The instance is cached under a
        non-colliding key so ``close_all()`` closes its aiohttp session; no
        new lifecycle code.
        """
        cached = self.providers.get(self._SPOTIFY_ENRICHMENT_KEY)
        if cached is not None:
            return cached

        client_id = os.getenv("TRACKLISTIFY_SPOTIFY_CLIENT_ID")
        client_secret = os.getenv("TRACKLISTIFY_SPOTIFY_CLIENT_SECRET")
        if not client_id or not client_secret:
            return None

        from tracklistify.providers.spotify import SpotifyProvider

        provider = SpotifyProvider(client_id=client_id, client_secret=client_secret)
        self.providers[self._SPOTIFY_ENRICHMENT_KEY] = provider
        return provider

    async def close_all(self) -> None:
        """Close all providers."""
        for provider in self.providers.values():
            await provider.close()  # Make sure to await the coroutine

    def clear_cache(self) -> None:
        """Clear the provider cache to force recreation of providers."""
        self.providers.clear()
