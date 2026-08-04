"""Tests for the MusicBrainz enrichment pass (spec unit C, MB doc).

Exercises ``_enrich_tracks`` / ``_enrich_musicbrainz`` / ``_enrich_one_mb``
with a fake MB provider and counting limiter. Covers spec tests 8-16.
"""

import pytest

from tracklistify.config import get_config
from tracklistify.core.track import Track
from tracklistify.utils.identification import IdentificationManager


def _track(song_name="Song", artist="Artist", metadata=None):
    return Track(
        song_name=song_name,
        artist=artist,
        time_in_mix="00:00:10",
        confidence=90.0,
        metadata=metadata or {},
    )


class _FakeMBProvider:
    """Minimal MB provider exposing lookup_isrc + async CM."""

    def __init__(self):
        self.calls = 0
        self.result = {}  # what lookup_isrc returns
        self.exc = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None

    async def lookup_isrc(self, isrc):
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.result

    async def close(self):
        pass


class _CountingLimiter:
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
        self.results.append((provider, success))


class _MBFactory:
    """Returns a fixed MB provider; no Spotify accessor → Spotify pass is no-op."""

    def __init__(self, mb_provider):
        self._mb = mb_provider

    def get_musicbrainz_provider(self):
        return self._mb


def _mgr(mb_provider, limiter, monkeypatch):
    monkeypatch.setattr(
        "tracklistify.utils.identification.get_global_rate_limiter", lambda: limiter
    )
    config = get_config(force_refresh=True)
    config.enrichment_enabled = True
    config.musicbrainz_enabled = True
    return IdentificationManager(
        config=config, provider_factory=_MBFactory(mb_provider)
    )


@pytest.mark.asyncio
async def test_mb_sets_spotify_link_when_spotify_source_absent(monkeypatch):
    """MB sets links.spotify + spotify_match='musicbrainz' when no prior link."""
    mb = _FakeMBProvider()
    mb.result = {
        "spotify": "https://open.spotify.com/track/mb1",
        "deezer": "https://deezer.com/track/1",
    }
    limiter = _CountingLimiter()
    mgr = _mgr(mb, limiter, monkeypatch)
    track = _track(metadata={"isrc": "USABC1234567"})

    await mgr._enrich_tracks([track])

    assert track.metadata["links"]["spotify"] == "https://open.spotify.com/track/mb1"
    assert track.metadata["links"]["deezer"] == "https://deezer.com/track/1"
    assert track.metadata["spotify_match"] == "musicbrainz"


@pytest.mark.asyncio
async def test_mb_does_not_overwrite_spotify_link(monkeypatch):
    """First-writer-wins: a pre-existing links.spotify is not overwritten."""
    mb = _FakeMBProvider()
    mb.result = {"spotify": "https://open.spotify.com/track/MB"}
    limiter = _CountingLimiter()
    mgr = _mgr(mb, limiter, monkeypatch)
    track = _track(
        metadata={
            "isrc": "USABC1234567",
            "links": {"spotify": "https://open.spotify.com/track/SPOTIFY"},
            "spotify_match": "isrc",
        }
    )

    await mgr._enrich_tracks([track])

    # Spotify source's canonical link survives.
    assert (
        track.metadata["links"]["spotify"] == "https://open.spotify.com/track/SPOTIFY"
    )
    assert track.metadata["spotify_match"] == "isrc"


@pytest.mark.asyncio
async def test_mb_adds_other_services_alongside_spotify(monkeypatch):
    """MB adds deezer/tidal when present, even alongside the spotify key."""
    mb = _FakeMBProvider()
    mb.result = {
        "spotify": "https://open.spotify.com/track/a",
        "deezer": "https://deezer.com/track/b",
        "tidal": "https://tidal.com/track/c",
    }
    limiter = _CountingLimiter()
    mgr = _mgr(mb, limiter, monkeypatch)
    track = _track(metadata={"isrc": "X"})

    await mgr._enrich_tracks([track])

    assert set(track.metadata["links"]) == {"spotify", "deezer", "tidal"}


@pytest.mark.asyncio
async def test_first_writer_wins_per_key(monkeypatch):
    """Each link key is set by the first source to provide it; MB fills gaps."""
    mb = _FakeMBProvider()
    mb.result = {
        "spotify": "https://open.spotify.com/track/MB",
        "tidal": "https://tidal.com/track/t",
    }
    limiter = _CountingLimiter()
    mgr = _mgr(mb, limiter, monkeypatch)
    # Track already has deezer from Shazam search URL (nested); MB must not touch it.
    track = _track(
        metadata={
            "isrc": "X",
            "links": {"deezer_search": "https://deezer.com/search/X"},
        }
    )

    await mgr._enrich_tracks([track])

    assert track.metadata["links"]["spotify"] == "https://open.spotify.com/track/MB"
    assert track.metadata["links"]["tidal"] == "https://tidal.com/track/t"
    # Pre-existing deezer_search untouched.
    assert "deezer_search" in track.metadata["links"]


@pytest.mark.asyncio
async def test_no_isrc_mb_not_called(monkeypatch):
    """A track with no ISRC is skipped — MB lookup never fires."""
    mb = _FakeMBProvider()
    limiter = _CountingLimiter()
    mgr = _mgr(mb, limiter, monkeypatch)
    track = _track()  # no isrc

    await mgr._enrich_tracks([track])

    assert mb.calls == 0
    assert limiter.acquires == 0


@pytest.mark.asyncio
async def test_musicbrainz_disabled_is_noop(monkeypatch):
    """musicbrainz_enabled=False → MB pass never runs."""
    mb = _FakeMBProvider()
    limiter = _CountingLimiter()
    config = get_config(force_refresh=True)
    config.enrichment_enabled = True
    config.musicbrainz_enabled = False
    mgr = IdentificationManager(config=config, provider_factory=_MBFactory(mb))
    monkeypatch.setattr(
        "tracklistify.utils.identification.get_global_rate_limiter", lambda: limiter
    )

    await mgr._enrich_tracks([_track(metadata={"isrc": "X"})])

    assert mb.calls == 0
    assert limiter.acquires == 0


@pytest.mark.asyncio
async def test_mb_limiter_released_on_every_path(monkeypatch):
    """R6: acquire/release counts match across normal + exception paths."""
    mb = _FakeMBProvider()
    mb.exc = RuntimeError("transient")
    limiter = _CountingLimiter()
    mgr = _mgr(mb, limiter, monkeypatch)

    await mgr._enrich_tracks(
        [_track(metadata={"isrc": "X"}), _track(metadata={"isrc": "Y"})]
    )

    assert limiter.acquires == 2
    assert limiter.releases == 2


@pytest.mark.asyncio
async def test_mb_transport_error_continues_and_keeps_tracks(monkeypatch):
    """R5: a transport error on one track continues; tracks intact."""
    mb = _FakeMBProvider()
    mb.exc = RuntimeError("network down")
    limiter = _CountingLimiter()
    mgr = _mgr(mb, limiter, monkeypatch)
    tracks = [_track(metadata={"isrc": "X"}), _track(metadata={"isrc": "Y"})]

    await mgr._enrich_tracks(tracks)

    # Both tracks attempted, neither gained a link, both survive.
    assert mb.calls == 2
    for t in tracks:
        assert t.metadata.get("links", {}).get("spotify") is None


@pytest.mark.asyncio
async def test_mb_no_hit_track_left_untouched(monkeypatch):
    """A track where MB returns no relations is untouched."""
    mb = _FakeMBProvider()
    mb.result = {}  # no relations
    limiter = _CountingLimiter()
    mgr = _mgr(mb, limiter, monkeypatch)
    track = _track(metadata={"isrc": "NONE"})

    await mgr._enrich_tracks([track])

    assert "links" not in track.metadata or not track.metadata.get("links")
    assert "spotify_match" not in track.metadata


@pytest.mark.asyncio
async def test_summary_log_reports_mb_resolved(monkeypatch, caplog):
    """R7: the run summary reports the MusicBrainz resolved count."""
    import logging

    mb = _FakeMBProvider()
    mb.result = {"spotify": "https://open.spotify.com/track/a"}
    limiter = _CountingLimiter()
    mgr = _mgr(mb, limiter, monkeypatch)

    with caplog.at_level(logging.INFO, logger="tracklistify.utils.identification"):
        await mgr._enrich_tracks([_track(metadata={"isrc": "X"})])

    summary = [r.message for r in caplog.records if "MusicBrainz" in r.message]
    assert any("1 tracks resolved" in m for m in summary)


@pytest.mark.asyncio
async def test_mb_pass_runs_without_spotify_creds(monkeypatch):
    """The MB pass runs even when the Spotify source is unavailable (no creds).

    The factory here has no get_spotify_provider → Spotify pass is a no-op,
    but MB still resolves links. This is the key property that makes MB
    useful without a Premium-backed Spotify app.
    """
    mb = _FakeMBProvider()
    mb.result = {"spotify": "https://open.spotify.com/track/solo"}
    limiter = _CountingLimiter()
    mgr = _mgr(mb, limiter, monkeypatch)
    track = _track(metadata={"isrc": "X"})

    await mgr._enrich_tracks([track])

    assert mb.calls == 1
    assert track.metadata["links"]["spotify"] == "https://open.spotify.com/track/solo"
