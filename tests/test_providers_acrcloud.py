"""Tests for ACRCloudProvider.identify_track response handling.

The provider only became reachable once the factory was fixed to pass
credentials, so these lock in the response-parsing and error-mapping behavior.
The HTTP session is mocked; no network is touched.
"""

import pytest

from tracklistify.providers.acrcloud import ACRCloudProvider
from tracklistify.providers.base import (
    AuthenticationError,
    ProviderError,
    RateLimitError,
)


class _FakeResponse:
    def __init__(self, status: int, text: str):
        self.status = status
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def text(self) -> str:
        return self._text


class _FakeSession:
    def __init__(self, response: _FakeResponse):
        self._response = response

    def post(self, *args, **kwargs):
        return self._response


@pytest.fixture
def provider():
    return ACRCloudProvider("access-key", "access-secret")


def _patch_session(provider, monkeypatch, response: _FakeResponse):
    async def _get_session():
        return _FakeSession(response)

    monkeypatch.setattr(provider, "_get_session", _get_session)


@pytest.mark.asyncio
async def test_successful_identification(provider, monkeypatch):
    body = (
        '{"status": {"code": 0, "msg": "Success"}, '
        '"metadata": {"music": [{"title": "Song", '
        '"artists": [{"name": "Artist"}], "score": 95}]}}'
    )
    _patch_session(provider, monkeypatch, _FakeResponse(200, body))

    result = await provider.identify_track(b"audio-bytes")

    assert result["status"]["code"] == 0
    music = result["metadata"]["music"]
    assert len(music) == 1
    assert music[0]["title"] == "Song"
    assert music[0]["score"] == 95.0


@pytest.mark.asyncio
async def test_no_result_code_maps_to_empty_music(provider, monkeypatch):
    body = '{"status": {"code": 1001, "msg": "No result"}}'
    _patch_session(provider, monkeypatch, _FakeResponse(200, body))

    result = await provider.identify_track(b"audio-bytes")

    assert result["metadata"]["music"] == []


@pytest.mark.asyncio
async def test_http_401_raises_authentication_error(provider, monkeypatch):
    _patch_session(provider, monkeypatch, _FakeResponse(401, ""))
    with pytest.raises(AuthenticationError):
        await provider.identify_track(b"audio-bytes")


@pytest.mark.asyncio
async def test_http_429_raises_rate_limit_error(provider, monkeypatch):
    _patch_session(provider, monkeypatch, _FakeResponse(429, ""))
    with pytest.raises(RateLimitError):
        await provider.identify_track(b"audio-bytes")


@pytest.mark.asyncio
async def test_invalid_json_raises_provider_error(provider, monkeypatch):
    _patch_session(provider, monkeypatch, _FakeResponse(200, "not-json"))
    with pytest.raises(ProviderError, match="parse"):
        await provider.identify_track(b"audio-bytes")


@pytest.mark.asyncio
async def test_accepts_audio_segment_reading_file(provider, monkeypatch, tmp_path):
    """identify_track must accept an AudioSegment (protocol used by the loop)."""
    from types import SimpleNamespace

    seg_file = tmp_path / "seg.wav"
    seg_file.write_bytes(b"RIFFfake-audio")
    segment = SimpleNamespace(file_path=str(seg_file), start_time=42)

    captured = {}

    def fake_prepare(audio_data, start_time):
        captured["audio_data"] = audio_data
        captured["start_time"] = start_time
        return {"data": {}}

    monkeypatch.setattr(provider, "_prepare_request_data", fake_prepare)
    body = '{"status": {"code": 1001, "msg": "No result"}}'
    _patch_session(provider, monkeypatch, _FakeResponse(200, body))

    result = await provider.identify_track(segment)

    assert captured["audio_data"] == b"RIFFfake-audio"
    assert captured["start_time"] == 42
    assert result["metadata"]["music"] == []
