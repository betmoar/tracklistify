"""Tests for SpotifyProvider — covers ABC-compliant search_track signature."""

import pytest

from tracklistify.providers.spotify import SpotifyProvider


@pytest.fixture
def provider():
    return SpotifyProvider(client_id="x", client_secret="y")


@pytest.mark.asyncio
async def test_search_track_accepts_abc_signature(provider, monkeypatch):
    """search_track must accept the ABC signature: title + 3 optional kwargs."""
    captured = {}

    async def fake_api_request(self, method, endpoint, **kwargs):
        captured["params"] = kwargs.get("params", {})
        return {"tracks": {"items": []}}

    monkeypatch.setattr(SpotifyProvider, "_api_request", fake_api_request)

    result = await provider.search_track("Title", "Artist", "Album", 240.0)

    assert isinstance(result, dict)
    assert "Title" in captured["params"]["q"]
    assert "Artist" in captured["params"]["q"]
    assert "Album" in captured["params"]["q"]


@pytest.mark.asyncio
async def test_search_track_returns_first_match(provider, monkeypatch):
    """When Spotify returns matches, search_track returns the top hit as a flat dict."""

    async def fake_api_request(self, method, endpoint, **kwargs):
        return {
            "tracks": {
                "items": [
                    {
                        "id": "abc123",
                        "name": "Song A",
                        "artists": [{"name": "Artist X"}],
                        "album": {"name": "Album Z", "release_date": "2024-01-01"},
                    },
                    {
                        "id": "def456",
                        "name": "Song B",
                        "artists": [{"name": "Other"}],
                        "album": {"name": "Other Album", "release_date": "2023-01-01"},
                    },
                ]
            }
        }

    monkeypatch.setattr(SpotifyProvider, "_api_request", fake_api_request)

    result = await provider.search_track("Song A", "Artist X")

    assert result["spotify_id"] == "abc123"
    assert result["name"] == "Song A"
    assert result["artists"] == ["Artist X"]


@pytest.mark.asyncio
async def test_search_track_returns_empty_on_no_match(provider, monkeypatch):
    async def fake_api_request(self, method, endpoint, **kwargs):
        return {"tracks": {"items": []}}

    monkeypatch.setattr(SpotifyProvider, "_api_request", fake_api_request)

    result = await provider.search_track("nonexistent")

    assert result == {}


@pytest.mark.asyncio
async def test_search_track_title_only(provider, monkeypatch):
    """artist/album/duration are optional; title alone must work."""
    captured = {}

    async def fake_api_request(self, method, endpoint, **kwargs):
        captured["params"] = kwargs.get("params", {})
        return {"tracks": {"items": []}}

    monkeypatch.setattr(SpotifyProvider, "_api_request", fake_api_request)

    await provider.search_track("Just A Title")
    assert "Just A Title" in captured["params"]["q"]


@pytest.mark.asyncio
async def test_api_request_accepts_201(provider, monkeypatch):
    """Spotify mutation endpoints return 201 on success."""

    class FakeResponse:
        status = 201
        headers = {}

        async def json(self):
            return {"id": "new_playlist_id"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

    class FakeSession:
        def request(self, method, url, **kwargs):
            return FakeResponse()

    async def fake_ensure_session(self):
        self._session = FakeSession()

    async def fake_get_token(self):
        return "fake-token"

    monkeypatch.setattr(SpotifyProvider, "_ensure_session", fake_ensure_session)
    monkeypatch.setattr(SpotifyProvider, "_get_access_token", fake_get_token)

    result = await provider._api_request("POST", "me/playlists", json={"name": "X"})
    assert result == {"id": "new_playlist_id"}


@pytest.mark.asyncio
async def test_api_request_accepts_204_empty_body(provider, monkeypatch):
    """Spotify mutation endpoints return 204 with empty body for some ops."""
    import aiohttp

    class FakeResponse:
        status = 204
        headers = {"Content-Length": "0"}

        async def json(self):
            raise aiohttp.ContentTypeError(None, None)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

    class FakeSession:
        def request(self, method, url, **kwargs):
            return FakeResponse()

    async def fake_ensure_session(self):
        self._session = FakeSession()

    async def fake_get_token(self):
        return "fake-token"

    monkeypatch.setattr(SpotifyProvider, "_ensure_session", fake_ensure_session)
    monkeypatch.setattr(SpotifyProvider, "_get_access_token", fake_get_token)

    result = await provider._api_request("DELETE", "playlists/abc/tracks")
    assert result == {}


@pytest.mark.asyncio
async def test_api_request_rejects_non_2xx(provider, monkeypatch):
    """Non-2xx (excluding 401/429) still raises ProviderError."""
    from tracklistify.core.exceptions import ProviderError

    class FakeResponse:
        status = 500
        headers = {}

        async def json(self):
            return {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

    class FakeSession:
        def request(self, method, url, **kwargs):
            return FakeResponse()

    async def fake_ensure_session(self):
        self._session = FakeSession()

    async def fake_get_token(self):
        return "fake-token"

    monkeypatch.setattr(SpotifyProvider, "_ensure_session", fake_ensure_session)
    monkeypatch.setattr(SpotifyProvider, "_get_access_token", fake_get_token)

    with pytest.raises(ProviderError, match="500"):
        await provider._api_request("GET", "me")


@pytest.mark.asyncio
async def test_search_track_propagates_rate_limit(provider, monkeypatch):
    """RateLimitError from _api_request must not be wrapped as ProviderError."""
    from tracklistify.providers.base import RateLimitError

    async def fake_api_request(self, method, endpoint, **kwargs):
        raise RateLimitError("Spotify rate limit exceeded. Retry after 30s")

    monkeypatch.setattr(SpotifyProvider, "_api_request", fake_api_request)

    with pytest.raises(RateLimitError, match="Retry after 30s"):
        await provider.search_track("Title")


@pytest.mark.asyncio
async def test_create_playlist_propagates_auth_error(provider, monkeypatch):
    """AuthenticationError must not be wrapped as ProviderError."""
    from tracklistify.providers.base import AuthenticationError

    async def fake_api_request(self, method, endpoint, **kwargs):
        raise AuthenticationError("Spotify token expired")

    monkeypatch.setattr(SpotifyProvider, "_api_request", fake_api_request)

    with pytest.raises(AuthenticationError, match="token expired"):
        await provider.create_playlist("New Playlist")


@pytest.mark.asyncio
async def test_add_tracks_propagates_rate_limit(provider, monkeypatch):
    """add_tracks_to_playlist must propagate RateLimitError unchanged."""
    from tracklistify.providers.base import RateLimitError

    async def fake_api_request(self, method, endpoint, **kwargs):
        raise RateLimitError("Spotify rate limit exceeded")

    monkeypatch.setattr(SpotifyProvider, "_api_request", fake_api_request)

    with pytest.raises(RateLimitError):
        await provider.add_tracks_to_playlist("pid", ["tid1", "tid2"])
