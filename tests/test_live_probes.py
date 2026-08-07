"""Live-network probes — opt-in via ``--live``, never run in CI (Q8).

These hit real external services with real credentials. They exist so a
developer can locally verify the pacing/regression shapes the cassette-locked
tests approximate, and to validate identification quality against a known set.
Run with::

    TRACKLISTIFY_MUSICBRAINZ_CONTACT=you@example.com \\
        uv run python -m pytest tests/test_live_probes.py --live -v

Without ``--live`` every test here is skipped (see conftest.py). CI never
passes ``--live``.
"""

import pytest

pytestmark = pytest.mark.live


@pytest.mark.asyncio
async def test_musicbrainz_live_resolves_a_known_isrc(monkeypatch):
    """MusicBrainz resolves a known-good ISRC to at least one streaming URL.

    This is the live counterpart to the cassette-locked 503-retry test: it
    confirms the provider resolves against the real API today. A failure here
    is either a real outage or a regression the cassette couldn't catch (a
    response-shape change). Not a gate — a manual signal.
    """
    import os

    if not os.getenv("TRACKLISTIFY_MUSICBRAINZ_CONTACT"):
        pytest.skip("TRACKLISTIFY_MUSICBRAINZ_CONTACT not set")

    from tracklistify.providers.musicbrainz import MusicBrainzProvider

    provider = MusicBrainzProvider()
    try:
        # Despacito — universally resolvable.
        links = await provider.lookup_isrc("USUM71703861")
        assert links, "MusicBrainz returned no links for a known-good ISRC"
    finally:
        await provider.close()
