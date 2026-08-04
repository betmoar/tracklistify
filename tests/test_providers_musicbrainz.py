"""Tests for MusicBrainzProvider — covers lookup_isrc parsing + error posture.

Mocks the aiohttp session; never hits the network. Covers spec tests 1-6.
"""

import pytest

from tracklistify.providers.musicbrainz import MusicBrainzProvider


async def _noop_sleep(_s):
    pass


class _FakeResponse:
    def __init__(self, status, json_data=None, headers=None):
        self.status = status
        self._json = json_data
        self.headers = headers or {}
        # For ClientResponseError construction
        from types import SimpleNamespace

        self.request_info = SimpleNamespace()
        self.history = ()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None

    async def json(self):
        return self._json


class _FakeSession:
    """Captures the request URL/params and returns a canned (or sequenced) response."""

    def __init__(self, response):
        # ``response`` may be a single _FakeResponse or a list (one per call).
        self._responses = response if isinstance(response, list) else [response]
        self._idx = 0
        self.requested_url = None
        self.requested_params = None
        self.call_count = 0

    def get(self, url, params=None):
        self.requested_url = url
        self.requested_params = params
        self.call_count += 1
        # Sequence: return each response in turn; repeat the last if exhausted.
        idx = min(self._idx, len(self._responses) - 1)
        self._idx += 1
        return self._responses[idx]

    async def close(self):
        pass


def _mb_response(relations):
    """Build a MusicBrainz ISRC JSON body with the given url-relations."""
    return {
        "isrc": "USABC1234567",
        "recordings": [
            {"relations": [{"type": t, "url": {"resource": u}} for t, u in relations]}
        ],
    }


@pytest.fixture
def provider():
    return MusicBrainzProvider()


@pytest.mark.asyncio
async def test_lookup_isrc_parses_streaming_relations(provider, monkeypatch):
    """200 with streaming relations → {service: url} keyed by service."""
    session = _FakeSession(
        _FakeResponse(
            200,
            _mb_response(
                [
                    ("free streaming", "https://open.spotify.com/track/abc"),
                    ("free streaming", "https://www.deezer.com/track/123"),
                    ("streaming", "https://tidal.com/track/456"),
                ]
            ),
        )
    )
    provider._session = session

    links = await provider.lookup_isrc("USABC1234567")

    assert links == {
        "spotify": "https://open.spotify.com/track/abc",
        "deezer": "https://www.deezer.com/track/123",
        "tidal": "https://tidal.com/track/456",
    }
    # Correct endpoint + params.
    assert "isrc/USABC1234567" in session.requested_url
    assert session.requested_params == {"inc": "url-rels", "fmt": "json"}


@pytest.mark.asyncio
async def test_lookup_isrc_404_is_clean_miss(provider):
    """404 (ISRC not in MB) → empty dict, no raise."""
    provider._session = _FakeSession(_FakeResponse(404))
    assert await provider.lookup_isrc("NLB471400012") == {}


@pytest.mark.asyncio
async def test_lookup_isrc_400_is_clean_miss(provider):
    """400 (malformed ISRC) → empty dict, no raise."""
    provider._session = _FakeSession(_FakeResponse(400))
    assert await provider.lookup_isrc("NOSUCHISRC001") == {}


@pytest.mark.asyncio
async def test_lookup_isrc_merges_relations_across_recordings(provider):
    """Relations across multiple recordings are merged into one map."""
    body = {
        "isrc": "X",
        "recordings": [
            {
                "relations": [
                    {
                        "type": "free streaming",
                        "url": {"resource": "https://open.spotify.com/track/a"},
                    }
                ]
            },
            {
                "relations": [
                    {
                        "type": "free streaming",
                        "url": {"resource": "https://tidal.com/track/b"},
                    }
                ]
            },
        ],
    }
    provider._session = _FakeSession(_FakeResponse(200, body))

    links = await provider.lookup_isrc("X")

    assert links == {
        "spotify": "https://open.spotify.com/track/a",
        "tidal": "https://tidal.com/track/b",
    }


@pytest.mark.asyncio
async def test_lookup_isrc_skips_unknown_hosts(provider):
    """An unknown host in a relation is skipped — no invented key."""
    body = _mb_response(
        [
            ("free streaming", "https://open.spotify.com/track/abc"),
            ("some relation", "https://bandcamp.com/track/xyz"),
            ("download", "https://example.com/buy"),
        ]
    )
    provider._session = _FakeSession(_FakeResponse(200, body))

    links = await provider.lookup_isrc("USABC1234567")

    assert links == {"spotify": "https://open.spotify.com/track/abc"}


@pytest.mark.asyncio
async def test_lookup_isrc_no_relations_returns_empty(provider):
    """A 200 with no url-relations → empty dict."""
    provider._session = _FakeSession(
        _FakeResponse(200, {"isrc": "X", "recordings": [{"relations": []}]})
    )
    assert await provider.lookup_isrc("X") == {}


@pytest.mark.asyncio
async def test_lookup_isrc_503_retries_then_raises(provider, monkeypatch):
    """A persistent 503 is retried (bounded) then surfaces to the caller."""
    import aiohttp

    # Speed up the retry sleeps so the test is fast.
    monkeypatch.setattr("tracklistify.providers.musicbrainz.asyncio.sleep", _noop_sleep)
    provider._session = _FakeSession(_FakeResponse(503))
    with pytest.raises(aiohttp.ClientResponseError):
        await provider.lookup_isrc("USABC1234567")
    # 1 initial + _MAX_503_RETRIES retries.
    assert provider._session.call_count == MusicBrainzProvider._MAX_503_RETRIES + 1


@pytest.mark.asyncio
async def test_lookup_isrc_503_then_success(provider, monkeypatch):
    """A transient 503 followed by a 200 recovers the links (no miss)."""
    monkeypatch.setattr("tracklistify.providers.musicbrainz.asyncio.sleep", _noop_sleep)
    body = _mb_response([("free streaming", "https://open.spotify.com/track/abc")])
    provider._session = _FakeSession([_FakeResponse(503), _FakeResponse(200, body)])

    links = await provider.lookup_isrc("USABC1234567")

    assert links == {"spotify": "https://open.spotify.com/track/abc"}
    assert provider._session.call_count == 2


@pytest.mark.asyncio
async def test_lookup_isrc_non_503_5xx_does_not_retry(provider, monkeypatch):
    """A 500 (non-503) surfaces immediately — only 503 is retried."""
    import aiohttp

    monkeypatch.setattr("tracklistify.providers.musicbrainz.asyncio.sleep", _noop_sleep)
    provider._session = _FakeSession(_FakeResponse(500))
    with pytest.raises(aiohttp.ClientResponseError):
        await provider.lookup_isrc("USABC1234567")
    assert provider._session.call_count == 1


@pytest.mark.asyncio
async def test_close_is_reentrant(provider):
    """close() can be called twice (async with + close_all) without error."""
    await provider.close()  # _session is None — must not raise
    await provider.close()


@pytest.mark.asyncio
async def test_user_agent_uses_contact_env(monkeypatch):
    """TRACKLISTIFY_MUSICBRAINZ_CONTACT flows into the default User-Agent."""
    monkeypatch.setenv("TRACKLISTIFY_MUSICBRAINZ_CONTACT", "me@example.com")
    p = MusicBrainzProvider()
    assert "me@example.com" in p.user_agent
