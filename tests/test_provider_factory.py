"""Tests for the provider factory, focusing on ACRCloud credential wiring.

ACRCloud credentials are read from the environment (``TRACKLISTIFY_ACR_*``),
not the config dataclass. The factory must pass them to the provider and fail
with a clear error when they are missing (rather than a cryptic ``TypeError``).
"""

import pytest

from tracklistify.core.exceptions import ProviderError
from tracklistify.providers.factory import ProviderFactory


@pytest.fixture(autouse=True)
def _clear_acr_env(monkeypatch):
    """Ensure ACRCloud env vars never bleed in from a local .env."""
    monkeypatch.delenv("TRACKLISTIFY_ACR_ACCESS_KEY", raising=False)
    monkeypatch.delenv("TRACKLISTIFY_ACR_ACCESS_SECRET", raising=False)
    monkeypatch.delenv("TRACKLISTIFY_ACR_HOST", raising=False)


class TestACRCloudFactory:
    def test_missing_credentials_raise_clear_error(self):
        factory = ProviderFactory()
        with pytest.raises(ProviderError, match="ACRCloud"):
            factory.get_identification_provider("acrcloud")

    def test_partial_credentials_raise_clear_error(self, monkeypatch):
        monkeypatch.setenv("TRACKLISTIFY_ACR_ACCESS_KEY", "key123")
        factory = ProviderFactory()
        with pytest.raises(ProviderError, match="ACRCloud"):
            factory.get_identification_provider("acrcloud")

    def test_constructs_with_env_credentials(self, monkeypatch):
        monkeypatch.setenv("TRACKLISTIFY_ACR_ACCESS_KEY", "key123")
        monkeypatch.setenv("TRACKLISTIFY_ACR_ACCESS_SECRET", "secret123")
        factory = ProviderFactory()
        provider = factory.get_identification_provider("acrcloud")
        assert provider.access_key == "key123"
        # The provider encodes the secret to bytes in __init__.
        assert provider.access_secret == b"secret123"

    def test_host_override(self, monkeypatch):
        monkeypatch.setenv("TRACKLISTIFY_ACR_ACCESS_KEY", "key123")
        monkeypatch.setenv("TRACKLISTIFY_ACR_ACCESS_SECRET", "secret123")
        monkeypatch.setenv("TRACKLISTIFY_ACR_HOST", "identify-us-west-2.acrcloud.com")
        factory = ProviderFactory()
        provider = factory.get_identification_provider("acrcloud")
        assert provider.host == "identify-us-west-2.acrcloud.com"

    def test_provider_is_cached(self, monkeypatch):
        monkeypatch.setenv("TRACKLISTIFY_ACR_ACCESS_KEY", "key123")
        monkeypatch.setenv("TRACKLISTIFY_ACR_ACCESS_SECRET", "secret123")
        factory = ProviderFactory()
        first = factory.get_identification_provider("acrcloud")
        second = factory.get_identification_provider("acrcloud")
        assert first is second

    def test_unknown_provider_raises(self):
        factory = ProviderFactory()
        with pytest.raises(ValueError, match="Unknown provider"):
            factory.get_identification_provider("does-not-exist")
