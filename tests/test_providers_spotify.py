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
