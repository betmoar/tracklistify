"""Tests for the post-dedup Spotify enrichment hook (spec unit D).

The hook lives on ``IdentificationManager._enrich_tracks`` and is exercised
directly here — mocking the Spotify provider and the rate limiter, never the
network. Covers spec tests 7-15.
"""

import pytest

from tracklistify.config import get_config
from tracklistify.core.track import Track
from tracklistify.providers.base import AuthenticationError, RateLimitError
from tracklistify.utils.identification import IdentificationManager


def _track(song_name="Song", artist="Artist", metadata=None):
    return Track(
        song_name=song_name,
        artist=artist,
        time_in_mix="00:00:10",
        confidence=90.0,
        metadata=metadata or {},
    )


class _FakeSpotifyProvider:
    """Minimal provider exposing the two search methods + async CM."""

    def __init__(self):
        self.isrc_calls = 0
        self.search_calls = 0
        # What the next search_by_isrc / search_track call returns.
        self.isrc_result = {}
        self.search_result = {}
        self.isrc_exc = None
        self.search_exc = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None

    async def search_by_isrc(self, isrc):
        self.isrc_calls += 1
        if self.isrc_exc:
            raise self.isrc_exc
        return self.isrc_result

    async def search_track(self, title, artist=None, album=None, duration=None):
        self.search_calls += 1
        if self.search_exc:
            raise self.search_exc
        return self.search_result

    async def close(self):
        pass


class _CountingLimiter:
    """Records acquire/release/record_result so tests assert pairing."""

    def __init__(self, acquire_ok=True):
        self.acquire_ok = acquire_ok
        self.acquires = 0
        self.releases = 0
        self.results = []

    async def acquire(self, provider):
        self.acquires += 1
        return self.acquire_ok

    def release(self, provider):
        self.releases += 1

    def record_result(self, provider, success):
        self.results.append(success)


class _EnrichFactory:
    """Factory stub that returns a fixed Spotify provider (or None)."""

    def __init__(self, provider):
        self._spotify = provider

    def get_spotify_provider(self):
        return self._spotify


def _mgr(provider, limiter, monkeypatch):
    monkeypatch.setattr(
        "tracklistify.utils.identification.get_global_rate_limiter", lambda: limiter
    )
    config = get_config(force_refresh=True)
    config.enrichment_enabled = True
    return IdentificationManager(
        config=config, provider_factory=_EnrichFactory(provider)
    )


@pytest.mark.asyncio
async def test_isrc_path_preferred_when_isrc_present(monkeypatch):
    """metadata['isrc'] present → search_by_isrc called, search_track not."""
    provider = _FakeSpotifyProvider()
    provider.isrc_result = {
        "spotify_id": "abc",
        "external_urls": {"spotify": "https://open.spotify.com/track/abc"},
        "isrc": "USABC1234567",
    }
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)
    track = _track(metadata={"isrc": "USABC1234567"})

    await mgr._enrich_tracks([track])

    assert provider.isrc_calls == 1
    assert provider.search_calls == 0
    assert track.metadata["spotify_match"] == "isrc"


@pytest.mark.asyncio
async def test_search_fallback_when_no_isrc(monkeypatch):
    """No ISRC → search_track used with raw song_name + artist."""
    provider = _FakeSpotifyProvider()
    provider.search_result = {"spotify_id": "def", "external_urls": {}}
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)
    track = _track(song_name="Raw Title", artist="Raw Artist")

    await mgr._enrich_tracks([track])

    assert provider.isrc_calls == 0
    assert provider.search_calls == 1
    assert track.metadata["spotify_match"] == "search"


@pytest.mark.asyncio
async def test_external_urls_wins_over_constructed_url(monkeypatch):
    """external_urls['spotify'] preferred over the constructed track URL."""
    provider = _FakeSpotifyProvider()
    provider.search_result = {
        "spotify_id": "abc",
        "external_urls": {"spotify": "https://open.spotify.com/track/abc"},
    }
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)
    track = _track()

    await mgr._enrich_tracks([track])

    assert track.metadata["links"]["spotify"] == ("https://open.spotify.com/track/abc")


@pytest.mark.asyncio
async def test_constructed_url_when_no_external_urls(monkeypatch):
    """No external_urls → URL constructed from spotify_id."""
    provider = _FakeSpotifyProvider()
    provider.search_result = {"spotify_id": "xyz", "external_urls": {}}
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)
    track = _track()

    await mgr._enrich_tracks([track])

    assert track.metadata["links"]["spotify"] == ("https://open.spotify.com/track/xyz")
    assert track.metadata["spotify_id"] == "xyz"


@pytest.mark.asyncio
async def test_track_with_existing_spotify_link_skipped(monkeypatch):
    """A track already carrying links['spotify'] is left untouched."""
    provider = _FakeSpotifyProvider()
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)
    track = _track(
        metadata={"links": {"spotify": "https://open.spotify.com/track/old"}}
    )

    await mgr._enrich_tracks([track])

    assert provider.isrc_calls == 0
    assert provider.search_calls == 0
    # Limiter never touched for a skipped track.
    assert limiter.acquires == 0


@pytest.mark.asyncio
async def test_no_credentials_is_noop_and_never_touches_limiter(monkeypatch):
    """provider is None → no-op; rate limiter never acquired."""
    limiter = _CountingLimiter()
    config = get_config(force_refresh=True)
    config.enrichment_enabled = True
    mgr = IdentificationManager(config=config, provider_factory=_EnrichFactory(None))
    monkeypatch.setattr(
        "tracklistify.utils.identification.get_global_rate_limiter", lambda: limiter
    )
    track = _track()

    await mgr._enrich_tracks([track])

    assert limiter.acquires == 0
    assert "spotify_match" not in track.metadata


@pytest.mark.asyncio
async def test_enrichment_disabled_is_noop(monkeypatch):
    """enrichment_enabled = false → no-op."""
    provider = _FakeSpotifyProvider()
    limiter = _CountingLimiter()
    config = get_config(force_refresh=True)
    config.enrichment_enabled = False
    mgr = IdentificationManager(
        config=config, provider_factory=_EnrichFactory(provider)
    )
    monkeypatch.setattr(
        "tracklistify.utils.identification.get_global_rate_limiter", lambda: limiter
    )

    await mgr._enrich_tracks([_track()])

    assert limiter.acquires == 0
    assert provider.isrc_calls == 0


@pytest.mark.asyncio
async def test_authentication_error_disables_for_run_and_keeps_tracks(monkeypatch):
    """R5: AuthenticationError → warn, disable for run, tracks intact."""
    provider = _FakeSpotifyProvider()
    provider.search_exc = AuthenticationError("bad creds")
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)
    tracks = [_track(), _track(), _track()]

    await mgr._enrich_tracks(tracks)

    # Only the first track triggers the provider call; the rest are skipped.
    assert provider.search_calls == 1
    # No track gained a spotify link, all three survive unchanged.
    for t in tracks:
        assert "spotify_match" not in t.metadata
        assert t.metadata.get("links", {}).get("spotify") is None


@pytest.mark.asyncio
async def test_rate_limit_stops_enriching_and_keeps_so_far(monkeypatch):
    """R5: RateLimitError → stop, return tracks enriched so far."""
    provider = _FakeSpotifyProvider()
    provider.search_exc = RateLimitError("slow down")
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)

    await mgr._enrich_tracks([_track(), _track()])

    assert provider.search_calls == 1


@pytest.mark.asyncio
async def test_generic_exception_continues_to_next_track(monkeypatch):
    """R5: a generic Exception on one track continues to the next."""
    provider = _FakeSpotifyProvider()
    provider.search_exc = RuntimeError("transient")
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)

    await mgr._enrich_tracks([_track(), _track()])

    # Both tracks attempted (error does not halt the loop).
    assert provider.search_calls == 2


@pytest.mark.asyncio
async def test_limiter_released_on_every_path(monkeypatch):
    """R6: acquire/release counts match across normal + exception paths."""
    provider = _FakeSpotifyProvider()
    provider.search_exc = RuntimeError("transient")
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)

    await mgr._enrich_tracks([_track(), _track(), _track()])

    assert limiter.acquires == 3
    assert limiter.releases == 3


@pytest.mark.asyncio
async def test_limiter_released_on_no_hit_path(monkeypatch):
    """R6: a no-hit track still releases the limiter."""
    provider = _FakeSpotifyProvider()  # empty results → no hit
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)

    await mgr._enrich_tracks([_track(), _track()])

    assert limiter.acquires == 2
    assert limiter.releases == 2


@pytest.mark.asyncio
async def test_summary_counts_mixed_run(monkeypatch, caplog):
    """R7: the run summary reports isrc/search/none counts at INFO."""
    import logging

    provider = _FakeSpotifyProvider()
    provider.isrc_result = {"spotify_id": "a", "external_urls": {}}
    provider.search_result = {"spotify_id": "b", "external_urls": {}}
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)
    tracks = [
        _track(metadata={"isrc": "X1"}),  # isrc hit
        _track(),  # search hit
    ]

    with caplog.at_level(logging.INFO, logger="tracklistify.utils.identification"):
        await mgr._enrich_tracks(tracks)

    summary = [r.message for r in caplog.records if "enrichment" in r.message]
    assert any("isrc=1" in m and "search=1" in m and "none=0" in m for m in summary)


@pytest.mark.asyncio
async def test_no_hit_track_left_untouched(monkeypatch):
    """A track with no Spotify hit is untouched and counted as none."""
    provider = _FakeSpotifyProvider()  # empty results
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)
    track = _track(metadata={"isrc": "NONE"})

    await mgr._enrich_tracks([track])

    assert "spotify_match" not in track.metadata
    assert "links" not in track.metadata or "spotify" not in track.metadata.get(
        "links", {}
    )
