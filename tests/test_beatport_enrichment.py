"""Tests for the Beatport enrichment pass.

Exercises ``_enrich_tracks`` / ``_enrich_beatport`` / ``_enrich_one_beatport``
with a fake Beatport provider and a counting limiter. No network.
"""

import pytest

from tracklistify.core.track import Track
from tracklistify.providers.base import AuthenticationError, RateLimitError
from tracklistify.utils.identification import IdentificationManager


def _track(song_name="Hard Dance", artist="DJ One", metadata=None):
    return Track(
        song_name=song_name,
        artist=artist,
        time_in_mix="00:00:10",
        confidence=90.0,
        metadata=metadata or {},
    )


def _candidate(**overrides):
    data = {
        "beatport_id": "12345",
        "title": "Hard Dance",
        "mix_name": "Original Mix",
        "artists": ["DJ One"],
        "url": "https://www.beatport.com/track/hard-dance/12345",
        "bpm": 150,
        "key": "A Minor",
        "label": "Hard Label",
        "genre": "Techno",
        "sub_genre": "Peak Time",
        "remixers": ["Remixer X"],
        "catalog_number": "CAT001",
        "release_date": "2024-03-01",
        "isrc": "GBABC1234567",
    }
    data.update(overrides)
    return data


class _FakeBeatportProvider:
    def __init__(self, isrc_result=None, search_results=None):
        self.isrc_result = isrc_result or {}
        self.search_results = search_results or []
        self.isrc_calls = 0
        self.search_calls = 0
        self.exc = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None

    async def lookup_isrc(self, isrc):
        self.isrc_calls += 1
        if self.exc:
            raise self.exc
        return self.isrc_result

    async def search_tracks(self, title, artist=None):
        self.search_calls += 1
        if self.exc:
            raise self.exc
        return self.search_results

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


class _BPFactory:
    """Beatport-only factory: no Spotify/MB accessors, so those passes no-op."""

    def __init__(self, provider):
        self._bp = provider

    def get_beatport_provider(self):
        return self._bp


def _mgr(provider, limiter, monkeypatch, enabled=True):
    from types import SimpleNamespace

    monkeypatch.setattr(
        "tracklistify.utils.identification.get_global_rate_limiter", lambda: limiter
    )
    monkeypatch.setattr(
        "tracklistify.utils.identification._BEATPORT_REQUEST_INTERVAL", 0
    )
    config = SimpleNamespace(
        enrichment_enabled=True,
        musicbrainz_enabled=False,
        beatport_enabled=enabled,
        min_confidence=0.0,
        time_threshold=0.0,
        segment_length=60,
        overlap_duration=10,
    )
    return IdentificationManager(
        config=config, provider_factory=_BPFactory(provider), cache=object()
    )


@pytest.mark.asyncio
async def test_disabled_makes_no_calls(monkeypatch):
    provider = _FakeBeatportProvider(search_results=[_candidate()])
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch, enabled=False)

    await mgr._enrich_tracks([_track()])

    assert provider.isrc_calls == 0 and provider.search_calls == 0
    assert limiter.acquires == 0


@pytest.mark.asyncio
async def test_no_provider_is_a_silent_noop(monkeypatch):
    limiter = _CountingLimiter()
    mgr = _mgr(None, limiter, monkeypatch)
    track = _track()

    await mgr._enrich_tracks([track])

    assert track.metadata == {}
    assert limiter.acquires == 0


@pytest.mark.asyncio
async def test_isrc_path_writes_links_and_dj_metadata(monkeypatch):
    provider = _FakeBeatportProvider(isrc_result=_candidate())
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)
    track = _track(metadata={"isrc": "GBABC1234567"})

    await mgr._enrich_tracks([track])

    md = track.metadata
    assert md["links"]["beatport"] == "https://www.beatport.com/track/hard-dance/12345"
    assert md["beatport_id"] == "12345"
    assert md["bpm"] == 150
    assert md["key"] == "A Minor"
    assert md["genre"] == "Techno"
    assert md["sub_genre"] == "Peak Time"
    assert md["remixers"] == ["Remixer X"]
    assert md["catalog_number"] == "CAT001"
    assert md["label"] == "Hard Label"
    assert md["beatport_match"] == "isrc"
    assert provider.search_calls == 0  # ISRC hit short-circuits search


@pytest.mark.asyncio
async def test_search_path_accepts_a_matching_candidate(monkeypatch):
    provider = _FakeBeatportProvider(search_results=[_candidate()])
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)
    track = _track()

    await mgr._enrich_tracks([track])

    assert track.metadata["beatport_match"] == "search"
    assert track.metadata["bpm"] == 150


@pytest.mark.asyncio
async def test_gate_rejects_a_wrong_title(monkeypatch):
    """A search hit that isn't the same track must leave it untouched — a
    wrong BPM/key/label presented as fact is worse than no data."""
    provider = _FakeBeatportProvider(
        search_results=[_candidate(title="Completely Different Song")]
    )
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)
    track = _track()

    await mgr._enrich_tracks([track])

    assert track.metadata == {}


@pytest.mark.asyncio
async def test_gate_rejects_a_wrong_artist(monkeypatch):
    provider = _FakeBeatportProvider(
        search_results=[_candidate(artists=["Someone Else"])]
    )
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)
    track = _track()

    await mgr._enrich_tracks([track])

    assert track.metadata == {}


@pytest.mark.asyncio
async def test_gate_takes_the_first_accepted_candidate_in_rank_order(monkeypatch):
    provider = _FakeBeatportProvider(
        search_results=[
            _candidate(beatport_id="999", title="Wrong Song"),
            _candidate(beatport_id="12345"),
        ]
    )
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)
    track = _track()

    await mgr._enrich_tracks([track])

    assert track.metadata["beatport_id"] == "12345"


@pytest.mark.asyncio
async def test_mix_name_variant_still_matches(monkeypatch):
    """Beatport splits name/mix_name; '(Original Mix)' is a non-distinguishing
    suffix that _comparison_title already folds away."""
    provider = _FakeBeatportProvider(
        search_results=[_candidate(title="Hard Dance", mix_name="Club Mix")]
    )
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)
    track = _track(song_name="Hard Dance (Club Mix)")

    await mgr._enrich_tracks([track])

    assert track.metadata["beatport_match"] == "search"


@pytest.mark.asyncio
async def test_existing_beatport_link_is_not_overwritten(monkeypatch):
    """First-writer-wins per link key: a MusicBrainz-resolved URL survives,
    but the DJ metadata is still written (no other source supplies it)."""
    provider = _FakeBeatportProvider(search_results=[_candidate()])
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)
    track = _track(metadata={"links": {"beatport": "https://beatport.com/mb-set"}})

    await mgr._enrich_tracks([track])

    assert track.metadata["links"]["beatport"] == "https://beatport.com/mb-set"
    assert track.metadata["bpm"] == 150


@pytest.mark.asyncio
async def test_existing_label_is_not_overwritten(monkeypatch):
    provider = _FakeBeatportProvider(search_results=[_candidate()])
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)
    track = _track(metadata={"label": "Shazam Label"})

    await mgr._enrich_tracks([track])

    assert track.metadata["label"] == "Shazam Label"


@pytest.mark.asyncio
async def test_limiter_is_paired_and_outcomes_recorded(monkeypatch):
    provider = _FakeBeatportProvider(search_results=[_candidate()])
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)

    await mgr._enrich_tracks([_track(), _track(song_name="Other Song")])

    assert limiter.acquires == limiter.releases == 2
    assert all(p == "beatport" for p, _ in limiter.results)
    assert len(limiter.results) == 2


@pytest.mark.asyncio
async def test_rate_limiter_rejection_does_not_call_the_provider(monkeypatch):
    provider = _FakeBeatportProvider(search_results=[_candidate()])
    limiter = _CountingLimiter(acquire_ok=False)
    mgr = _mgr(provider, limiter, monkeypatch)

    await mgr._enrich_tracks([_track()])

    assert provider.search_calls == 0
    assert limiter.releases == 0  # nothing was acquired


@pytest.mark.asyncio
async def test_authentication_error_disables_the_pass_for_the_run(monkeypatch):
    provider = _FakeBeatportProvider(search_results=[_candidate()])
    provider.exc = AuthenticationError("bad token")
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)

    await mgr._enrich_tracks([_track(), _track(song_name="B"), _track(song_name="C")])

    assert provider.search_calls == 1  # stopped after the first failure
    assert limiter.acquires == limiter.releases == 1


@pytest.mark.asyncio
async def test_rate_limit_error_stops_but_keeps_earlier_work(monkeypatch):
    provider = _FakeBeatportProvider(search_results=[_candidate()])
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)
    first, second = _track(), _track(song_name="B")

    await mgr._enrich_beatport([first])
    provider.exc = RateLimitError("429")
    await mgr._enrich_beatport([second])

    assert first.metadata["bpm"] == 150
    assert second.metadata == {}


@pytest.mark.asyncio
async def test_a_raising_provider_never_fails_the_run(monkeypatch):
    provider = _FakeBeatportProvider(search_results=[_candidate()])
    provider.exc = RuntimeError("boom")
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)
    track = _track()

    await mgr._enrich_tracks([track])  # must not raise

    assert track.metadata == {}
    assert limiter.results == [("beatport", False)]


@pytest.mark.asyncio
async def test_isrc_miss_paces_before_the_search_fallback(monkeypatch):
    """Two requests for one track (ISRC miss -> search) must still be spaced.

    Without this the fallback path fires both calls back-to-back and the
    pass runs at double the intended request rate — the pacing constant is
    the real rate control here, not the token bucket (which seeds full).
    """
    sleeps = []

    async def _record_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(
        "tracklistify.utils.identification.asyncio.sleep", _record_sleep
    )
    provider = _FakeBeatportProvider(isrc_result={}, search_results=[_candidate()])
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)
    monkeypatch.setattr(
        "tracklistify.utils.identification._BEATPORT_REQUEST_INTERVAL", 0.5
    )
    track = _track(metadata={"isrc": "GBABC1234567"})

    await mgr._enrich_tracks([track])

    assert provider.isrc_calls == 1 and provider.search_calls == 1
    # One inter-request sleep between the two calls, one after the track.
    assert sleeps == [0.5, 0.5]


@pytest.mark.asyncio
async def test_a_fully_broken_pass_logs_at_info_without_debug(monkeypatch, caplog):
    """A misconfigured account (AuthenticationError on every track) must still
    surface an INFO line, not vanish below DEBUG. Without the unconditional
    zero-match log, a broken pass is indistinguishable from 'found nothing'
    unless the user runs --debug."""
    import logging

    provider = _FakeBeatportProvider(search_results=[_candidate()])
    provider.exc = AuthenticationError("bad client_id")
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)

    with caplog.at_level(logging.INFO):
        await mgr._enrich_tracks(
            [_track(), _track(song_name="B"), _track(song_name="C")]
        )

    # The per-track failure warns (disable), and the summary still logs at INFO.
    assert any(
        "Beatport enrichment" in rec.message and rec.levelno == logging.INFO
        for rec in caplog.records
    )
    assert provider.search_calls == 1  # disabled after the first track


@pytest.mark.asyncio
async def test_a_metadata_write_failure_does_not_break_the_run(monkeypatch):
    """_apply_beatport_metadata runs after the lookup try/except, so an
    exception there would escape the per-track boundary and abort enrichment
    for every remaining track. The write is guarded: a failure degrades to a
    miss for that track — never a run-ending error."""
    provider = _FakeBeatportProvider(isrc_result=_candidate())
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)

    def _boom(track, result, match_kind):
        raise RuntimeError("write failed")

    monkeypatch.setattr(mgr, "_apply_beatport_metadata", _boom)
    first, second = (
        _track(metadata={"isrc": "GBABC1234567"}),
        _track(song_name="B", metadata={"isrc": "GBABC1234568"}),
    )

    await mgr._enrich_tracks([first, second])  # must not raise

    # Both tracks were attempted (the first's write failure didn't abort the loop).
    assert provider.isrc_calls == 2
    assert first.metadata == {"isrc": "GBABC1234567"}  # write never landed
    assert limiter.results == [("beatport", True), ("beatport", True)]
