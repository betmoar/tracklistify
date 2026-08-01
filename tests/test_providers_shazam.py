"""Tests for the Shazam identification provider."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tracklistify.config import clear_config, get_config
from tracklistify.core.exceptions import ShazamError
from tracklistify.providers.shazam import ShazamProvider


@pytest.mark.asyncio
async def test_shazam_proxy_env_is_forwarded_to_recognize(monkeypatch):
    proxy = "http://proxy.example:8080"
    monkeypatch.setenv("TRACKLISTIFY_SHAZAM_PROXY", proxy)
    monkeypatch.setenv("TRACKLISTIFY_SHAZAM_COOLDOWN_SECONDS", "0")
    clear_config()

    try:
        get_config(force_refresh=True)
        provider = ShazamProvider()
        recognize = AsyncMock(return_value={"matches": []})
        monkeypatch.setattr(provider.shazam, "recognize", recognize)

        await provider.identify_track(
            SimpleNamespace(file_path="segment.mp3", start_time=0)
        )

        recognize.assert_awaited_once_with("segment.mp3", proxy=proxy)
    finally:
        clear_config()


@pytest.mark.asyncio
async def test_shazam_no_proxy_env_forwards_none(monkeypatch):
    """When TRACKLISTIFY_SHAZAM_PROXY is unset, recognize gets proxy=None.

    This locks the empty-string-to-None coercion — if a future edit drops
    the ``or None``, recognize would receive proxy="" instead of None,
    which is the wrong no-proxy sentinel.
    """
    monkeypatch.delenv("TRACKLISTIFY_SHAZAM_PROXY", raising=False)
    monkeypatch.setenv("TRACKLISTIFY_SHAZAM_COOLDOWN_SECONDS", "0")
    clear_config()

    try:
        get_config(force_refresh=True)
        provider = ShazamProvider()
        recognize = AsyncMock(return_value={"matches": []})
        monkeypatch.setattr(provider.shazam, "recognize", recognize)

        await provider.identify_track(
            SimpleNamespace(file_path="segment.mp3", start_time=0)
        )

        recognize.assert_awaited_once_with("segment.mp3", proxy=None)
    finally:
        clear_config()


@pytest.mark.asyncio
async def test_shazam_raises_on_recognize_error(monkeypatch):
    """Errors from recognize() must raise ShazamError, not return None.

    identification.py records success=False only when identify_track
    raises — swallowing into None defeated the circuit breaker.
    """
    monkeypatch.setenv("TRACKLISTIFY_SHAZAM_COOLDOWN_SECONDS", "0")
    clear_config()

    try:
        get_config(force_refresh=True)
        provider = ShazamProvider()
        recognize = AsyncMock(side_effect=RuntimeError("connection refused"))
        monkeypatch.setattr(provider.shazam, "recognize", recognize)

        with pytest.raises(ShazamError, match="connection refused"):
            await provider.identify_track(
                SimpleNamespace(file_path="segment.mp3", start_time=0)
            )
    finally:
        clear_config()


def _shazam_payload(**track_overrides):
    """A shazamio-shaped response with the metadata fields we surface."""
    track = {
        "title": "Berghain",
        "subtitle": "Sara Landry",
        "key": "shazam-key-1",
        "isrc": "USABC1234567",
        "url": "https://www.shazam.com/track/1",
        "genres": {"primary": "Techno"},
        "images": {
            "coverart": "https://img/low.jpg",
            "coverarthq": "https://img/hq.jpg",
        },
        "hub": {
            "actions": [
                {"type": "uri", "id": "ignored"},
                {"type": "applemusicplay", "id": "am-999"},
            ],
            "providers": [
                {
                    "type": "DEEZER",
                    "actions": [{"name": "hub:deezer:deeplink", "uri": "dzr://x"}],
                },
                {
                    "type": "SPOTIFY",
                    "actions": [
                        {
                            "name": "hub:spotify:searchdeeplink",
                            "uri": "spotify:search:Sara Landry Berghain",
                        }
                    ],
                },
            ],
        },
        "sections": [
            {
                "metadata": [
                    {"title": "Album", "text": "Hyperdrive"},
                    {"title": "Label", "text": "HEKATE"},
                    {"title": "Released", "text": "2024"},
                ]
            }
        ],
    }
    track.update(track_overrides)
    return {"matches": [{"frequencyskew": 0.0, "timeskew": 0.0}], "track": track}


@pytest.mark.asyncio
async def test_shazam_surfaces_rich_metadata(monkeypatch):
    """ISRC, genre, album/label/release, platform ids and artwork are
    pulled out of the raw shazamio payload into the shared music-entry
    shape that utils.identification threads into Track.metadata."""
    monkeypatch.setenv("TRACKLISTIFY_SHAZAM_COOLDOWN_SECONDS", "0")
    clear_config()
    try:
        get_config(force_refresh=True)
        provider = ShazamProvider()
        monkeypatch.setattr(
            provider.shazam,
            "recognize",
            AsyncMock(return_value=_shazam_payload()),
        )

        result = await provider.identify_track(
            SimpleNamespace(file_path="segment.mp3", start_time=0)
        )

        entry = result["metadata"]["music"][0]
        assert entry["external_ids"]["isrc"] == "USABC1234567"
        assert entry["genres"] == [{"name": "Techno"}]
        assert entry["album"] == "Hyperdrive"
        assert entry["label"] == "HEKATE"
        assert entry["release_date"] == "2024"
        assert entry["shazam_id"] == "shazam-key-1"
        assert entry["apple_music_id"] == "am-999"
        # High-quality artwork wins over the low-res variant.
        assert entry["artwork_url"] == "https://img/hq.jpg"
        assert entry["shazam_url"] == "https://www.shazam.com/track/1"
    finally:
        clear_config()


@pytest.mark.asyncio
async def test_shazam_metadata_survives_explicit_nulls(monkeypatch):
    """Explicit JSON nulls must not break identification.

    ``.get("genres", {})`` returns the default only when the key is
    ABSENT — a present-but-null value yields None and the chained
    ``.get("primary")`` raises AttributeError, turning a cosmetic
    metadata gap into a failed identification for the whole segment.
    shazamio payloads carry these nulls in practice.
    """
    monkeypatch.setenv("TRACKLISTIFY_SHAZAM_COOLDOWN_SECONDS", "0")
    clear_config()
    try:
        get_config(force_refresh=True)
        provider = ShazamProvider()
        monkeypatch.setattr(
            provider.shazam,
            "recognize",
            AsyncMock(
                return_value=_shazam_payload(
                    genres=None, hub=None, sections=None, images=None, isrc=None
                )
            ),
        )

        result = await provider.identify_track(
            SimpleNamespace(file_path="segment.mp3", start_time=0)
        )

        # Identification still succeeds; the extras are simply absent.
        entry = result["metadata"]["music"][0]
        assert entry["title"] == "Berghain"
        assert entry["genres"] == []
        assert entry["album"] is None
        assert entry["apple_music_id"] is None
        assert entry["artwork_url"] is None
    finally:
        clear_config()


@pytest.mark.asyncio
async def test_shazam_surfaces_platform_search_deeplinks(monkeypatch):
    """hub.providers carries per-platform deeplinks Shazam ships with the
    match — free, no extra API call.

    Matched on each provider's ``type``, NOT a positional index. shazamio's
    own factory hardcodes providers[0].actions[0], which returns the wrong
    platform's link the moment Shazam reorders the array — the fixture puts
    DEEZER first precisely to catch that.
    """
    monkeypatch.setenv("TRACKLISTIFY_SHAZAM_COOLDOWN_SECONDS", "0")
    clear_config()
    try:
        get_config(force_refresh=True)
        provider = ShazamProvider()
        monkeypatch.setattr(
            provider.shazam,
            "recognize",
            AsyncMock(return_value=_shazam_payload()),
        )

        entry = (
            await provider.identify_track(
                SimpleNamespace(file_path="segment.mp3", start_time=0)
            )
        )["metadata"]["music"][0]

        assert entry["spotify_search_uri"] == "spotify:search:Sara Landry Berghain"
        assert entry["deezer_search_uri"] == "dzr://x"
    finally:
        clear_config()


@pytest.mark.asyncio
async def test_shazam_missing_providers_yields_none_not_crash(monkeypatch):
    """No hub.providers at all — the common case for obscure tracks."""
    monkeypatch.setenv("TRACKLISTIFY_SHAZAM_COOLDOWN_SECONDS", "0")
    clear_config()
    try:
        get_config(force_refresh=True)
        provider = ShazamProvider()
        monkeypatch.setattr(
            provider.shazam,
            "recognize",
            AsyncMock(
                return_value=_shazam_payload(hub={"actions": [], "providers": None})
            ),
        )

        entry = (
            await provider.identify_track(
                SimpleNamespace(file_path="segment.mp3", start_time=0)
            )
        )["metadata"]["music"][0]

        assert entry["spotify_search_uri"] is None
        assert entry["deezer_search_uri"] is None
    finally:
        clear_config()
