"""Tests for ProviderFactory.get_spotify_provider (enrichment accessor)."""

import pytest

from tracklistify.providers.factory import KNOWN_PROVIDERS, ProviderFactory


@pytest.fixture
def factory():
    return ProviderFactory()


def test_get_spotify_provider_none_without_creds(monkeypatch, factory):
    """No creds → None, never raises (enrichment is optional)."""
    monkeypatch.delenv("TRACKLISTIFY_SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("TRACKLISTIFY_SPOTIFY_CLIENT_SECRET", raising=False)

    assert factory.get_spotify_provider() is None


def test_get_spotify_provider_none_with_one_cred(monkeypatch, factory):
    """Only one of the two creds set → still None."""
    monkeypatch.setenv("TRACKLISTIFY_SPOTIFY_CLIENT_ID", "cid")
    monkeypatch.delenv("TRACKLISTIFY_SPOTIFY_CLIENT_SECRET", raising=False)

    assert factory.get_spotify_provider() is None


def test_get_spotify_provider_returns_instance_with_both_creds(monkeypatch, factory):
    """Both creds set → a SpotifyProvider."""
    from tracklistify.providers.spotify import SpotifyProvider

    monkeypatch.setenv("TRACKLISTIFY_SPOTIFY_CLIENT_ID", "cid")
    monkeypatch.setenv("TRACKLISTIFY_SPOTIFY_CLIENT_SECRET", "csec")

    provider = factory.get_spotify_provider()
    assert isinstance(provider, SpotifyProvider)
    assert provider.client_id == "cid"
    assert provider.client_secret == "csec"


def test_get_spotify_provider_is_cached(monkeypatch, factory):
    """The instance is memoized — a second call returns the same object."""
    monkeypatch.setenv("TRACKLISTIFY_SPOTIFY_CLIENT_ID", "cid")
    monkeypatch.setenv("TRACKLISTIFY_SPOTIFY_CLIENT_SECRET", "csec")

    first = factory.get_spotify_provider()
    second = factory.get_spotify_provider()
    assert first is second


def test_spotify_not_in_known_providers():
    """Spotify is NOT an identification provider — it has no identify_track."""
    assert "spotify" not in KNOWN_PROVIDERS


def test_spotify_cache_key_does_not_collide_with_identification(monkeypatch, factory):
    """The enrichment provider sits under a non-colliding key, so it never
    shadows an identification provider lookup."""
    monkeypatch.setenv("TRACKLISTIFY_SPOTIFY_CLIENT_ID", "cid")
    monkeypatch.setenv("TRACKLISTIFY_SPOTIFY_CLIENT_SECRET", "csec")

    factory.get_spotify_provider()
    # The enrichment key is not a valid identification provider name.
    for key in factory.providers:
        assert key not in KNOWN_PROVIDERS
