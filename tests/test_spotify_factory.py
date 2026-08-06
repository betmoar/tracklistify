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


# --- Unit B: get_musicbrainz_provider (keyless enrichment accessor) ---


def test_get_musicbrainz_provider_returns_instance(factory):
    """Keyless — always returns a provider (no creds gate)."""
    from tracklistify.providers.musicbrainz import MusicBrainzProvider

    provider = factory.get_musicbrainz_provider()
    assert isinstance(provider, MusicBrainzProvider)


def test_get_musicbrainz_provider_is_cached(factory):
    """Memoized — second call returns the same object."""
    first = factory.get_musicbrainz_provider()
    second = factory.get_musicbrainz_provider()
    assert first is second


def test_musicbrainz_not_in_known_providers():
    """MusicBrainz is NOT an identification provider."""
    assert "musicbrainz" not in KNOWN_PROVIDERS


def test_musicbrainz_cache_key_does_not_collide(factory):
    """The enrichment provider sits under a non-colliding key."""
    factory.get_musicbrainz_provider()
    for key in factory.providers:
        assert key not in KNOWN_PROVIDERS


# --- get_beatport_provider (opt-in, user-supplied credentials) ---


def _clear_beatport_env(monkeypatch):
    for key in (
        "TRACKLISTIFY_BEATPORT_CLIENT_ID",
        "TRACKLISTIFY_BEATPORT_USERNAME",
        "TRACKLISTIFY_BEATPORT_PASSWORD",
        "TRACKLISTIFY_BEATPORT_TOKEN",
        "TRACKLISTIFY_BEATPORT_SESSION_TOKEN",
        "TRACKLISTIFY_BEATPORT_CF_CLEARANCE",
    ):
        monkeypatch.delenv(key, raising=False)


def test_get_beatport_provider_returns_none_without_client_id(monkeypatch, factory):
    """Absent credentials are a skip, not an error (unlike ACRCloud, where
    identification cannot proceed without them)."""
    _clear_beatport_env(monkeypatch)

    assert factory.get_beatport_provider() is None


def test_get_beatport_provider_returns_none_without_any_auth_path(monkeypatch, factory):
    """A client ID alone cannot obtain a token — no username/password and no
    pasted token means there is nothing to do."""
    _clear_beatport_env(monkeypatch)
    monkeypatch.setenv("TRACKLISTIFY_BEATPORT_CLIENT_ID", "cid")

    assert factory.get_beatport_provider() is None


def test_get_beatport_provider_builds_and_caches(monkeypatch, factory):
    from tracklistify.providers.beatport import BeatportProvider

    _clear_beatport_env(monkeypatch)
    monkeypatch.setenv("TRACKLISTIFY_BEATPORT_CLIENT_ID", "cid")
    monkeypatch.setenv("TRACKLISTIFY_BEATPORT_USERNAME", "dj")
    monkeypatch.setenv("TRACKLISTIFY_BEATPORT_PASSWORD", "pw")

    provider = factory.get_beatport_provider()
    assert isinstance(provider, BeatportProvider)
    assert provider.client_id == "cid"
    # Memoized, and cached under a key that cannot collide with an
    # identification provider, so close_all() closes its session.
    assert factory.get_beatport_provider() is provider
    assert "_beatport_enrichment" in factory.providers


def test_get_beatport_provider_accepts_a_pasted_token(monkeypatch, factory):
    _clear_beatport_env(monkeypatch)
    monkeypatch.setenv("TRACKLISTIFY_BEATPORT_CLIENT_ID", "cid")
    monkeypatch.setenv("TRACKLISTIFY_BEATPORT_TOKEN", "PASTED")

    provider = factory.get_beatport_provider()
    assert provider is not None
    assert provider._pasted_token == "PASTED"


def test_get_beatport_provider_accepts_a_browser_session(monkeypatch, factory):
    """The session cookie (+ cf_clearance) is a valid auth path on its own —
    the unattended route that mints a fresh token per run."""
    _clear_beatport_env(monkeypatch)
    monkeypatch.setenv("TRACKLISTIFY_BEATPORT_CLIENT_ID", "cid")
    monkeypatch.setenv("TRACKLISTIFY_BEATPORT_SESSION_TOKEN", "sess")
    monkeypatch.setenv("TRACKLISTIFY_BEATPORT_CF_CLEARANCE", "cf")

    provider = factory.get_beatport_provider()
    assert provider is not None
    assert provider._session_token == "sess"
    assert provider._cf_clearance == "cf"


def test_get_beatport_provider_session_without_cf_clearance_is_none(
    monkeypatch, factory
):
    """A session cookie alone is not enough — Cloudflare needs cf_clearance too,
    so without both the session path is treated as unconfigured."""
    _clear_beatport_env(monkeypatch)
    monkeypatch.setenv("TRACKLISTIFY_BEATPORT_CLIENT_ID", "cid")
    monkeypatch.setenv("TRACKLISTIFY_BEATPORT_SESSION_TOKEN", "sess")

    assert factory.get_beatport_provider() is None


def test_get_beatport_provider_sets_a_token_cache_path(monkeypatch, factory):
    """The token is cached next to the run cache so a normal run skips the
    whole login dance."""
    from tracklistify.providers.beatport import TOKEN_FILENAME

    _clear_beatport_env(monkeypatch)
    monkeypatch.setenv("TRACKLISTIFY_BEATPORT_CLIENT_ID", "cid")
    monkeypatch.setenv("TRACKLISTIFY_BEATPORT_TOKEN", "PASTED")

    provider = factory.get_beatport_provider()
    assert provider._token_path is not None
    assert provider._token_path.name == TOKEN_FILENAME


def test_beatport_not_in_known_providers():
    """Beatport is NOT an identification provider — it has no fingerprint."""
    assert "beatport" not in KNOWN_PROVIDERS


def test_beatport_cache_key_does_not_collide(monkeypatch, factory):
    _clear_beatport_env(monkeypatch)
    monkeypatch.setenv("TRACKLISTIFY_BEATPORT_CLIENT_ID", "cid")
    monkeypatch.setenv("TRACKLISTIFY_BEATPORT_TOKEN", "PASTED")

    factory.get_beatport_provider()
    for key in factory.providers:
        assert key not in KNOWN_PROVIDERS
