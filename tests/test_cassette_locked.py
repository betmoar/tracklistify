"""Cassette-locked tests for the pacing/regression class (Q8, 2026-08 review).

These tests replay recorded HTTP interactions (vcrpy cassettes under
``tests/cassettes/``) so the behaviors that mocked tests structurally cannot
catch — the pacing, retry, and rate-limit-handling shapes — are locked without
needing live credentials or network in CI.

The canonical case is the MusicBrainz 503-retry: a mocked test that returns
``{}`` on every call passes regardless of whether the provider retries a
transient 503. An 8× yield regression (3% -> 25% link rate) once shipped
through exactly such a mock. The cassette here records a real 503-then-200
sequence and asserts the provider retries and resolves the link.
"""

import asyncio

import pytest

from tracklistify.providers.musicbrainz import MusicBrainzProvider

# A known-good ISRC (Despacito) that MusicBrainz resolves to a Spotify URL.
_ISRC = "USUM71703861"


@pytest.mark.asyncio
@pytest.mark.vcr
async def test_musicbrainz_retries_503_then_resolves(monkeypatch):
    """A transient 503 must be retried, not treated as a clean miss.

    The cassette records: first request -> 503 (Retry-After: 1), second
    request -> 200 with a Spotify url-rel. Without the retry logic this
    returns ``{}`` (the regression) instead of the resolved link. The
    ``asyncio.sleep`` on the 503 Retry-After is patched out so the test is
    instant, but the *decision* to retry is what this locks.
    """

    # Zero the retry sleep so the cassette replay is instant — the pacing
    # interval itself is not under test here, only the retry decision.
    async def _no_sleep(*a, **kw):
        return None

    monkeypatch.setattr(asyncio, "sleep", _no_sleep)

    monkeypatch.setenv("TRACKLISTIFY_MUSICBRAINZ_CONTACT", "test@example.com")
    provider = MusicBrainzProvider()
    try:
        links = await provider.lookup_isrc(_ISRC)
        assert "spotify" in links, (
            "provider treated the 503 as a clean miss instead of retrying; "
            "the pacing-regression class (Q8) would pass a mock that never 503s"
        )
        assert links["spotify"].startswith("https://open.spotify.com/track/")
    finally:
        await provider.close()
