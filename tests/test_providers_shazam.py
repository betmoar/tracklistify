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
                    "actions": [
                        {
                            "name": "hub:deezer:deeplink",
                            "uri": "deezer-query://www.deezer.com/play?query=%7Btrack%3A%27Berghain%27%20artist%3A%27Sara+Landry%27%7D",
                        }
                    ],
                },
                {
                    "type": "SPOTIFY",
                    "actions": [
                        {
                            "name": "hub:spotify:searchdeeplink",
                            "uri": "spotify:search:Berghain%20Sara%20Landry",
                        }
                    ],
                },
            ],
        },
        # Deliberately NOT in Album/Label/Released order, with an unrelated
        # entry first: extraction is keyed on each item's "title", and a
        # positional rewrite must fail this fixture.
        "sections": [
            {
                "metadata": [
                    {"title": "Written By", "text": "Someone Else"},
                    {"title": "Released", "text": "2024"},
                    {"title": "Album", "text": "Hyperdrive"},
                    {"title": "Label", "text": "HEKATE"},
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

        assert (
            entry["spotify_search_url"]
            == "https://open.spotify.com/search/Berghain%20Sara%20Landry"
        )
        assert (
            entry["deezer_search_url"]
            == "https://www.deezer.com/search/Berghain%20Sara%20Landry"
        )
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

        assert entry["spotify_search_url"] is None
        assert entry["deezer_search_url"] is None
    finally:
        clear_config()


@pytest.mark.parametrize(
    "platform,uri,expected",
    [
        # Real payloads observed on a Tomorrowland set, 2026-08-01.
        (
            "spotify",
            "spotify:search:Kickdrum%20Junkie%20Revoxx",
            "https://open.spotify.com/search/Kickdrum%20Junkie%20Revoxx",
        ),
        (
            "deezer",
            "deezer-query://www.deezer.com/play?query="
            "%7Btrack%3A%27Kickdrum+Junkie%27%20artist%3A%27Revoxx%27%7D",
            "https://www.deezer.com/search/Kickdrum%20Junkie%20Revoxx",
        ),
        # Apostrophes inside the value. Deezer does not escape them, so a
        # naive [^']* match truncated "Don't Stop" to "Don" and produced a
        # search for the wrong track.
        (
            "deezer",
            "deezer-query://www.deezer.com/play?query="
            "%7Btrack%3A%27Don%27t%20Stop%27%20artist%3A%27Rock%27n%27Roll%27%7D",
            "https://www.deezer.com/search/Don%27t%20Stop%20Rock%27n%27Roll",
        ),
        # A slash must not survive as a path delimiter — "AC/DC" would
        # otherwise route to /search/AC with a stray /DC segment.
        (
            "spotify",
            "spotify:search:AC%2FDC%20Thunderstruck",
            "https://open.spotify.com/search/AC%2FDC%20Thunderstruck",
        ),
        (
            "deezer",
            "deezer-query://www.deezer.com/play?query="
            "%7Btrack%3A%27Thunderstruck%27%20artist%3A%27AC%2FDC%27%7D",
            "https://www.deezer.com/search/Thunderstruck%20AC%2FDC",
        ),
        # Non-ASCII must round-trip as UTF-8 percent-encoding.
        (
            "spotify",
            "spotify:search:Caf%C3%A9%20Tacvba",
            "https://open.spotify.com/search/Caf%C3%A9%20Tacvba",
        ),
        # Malformed / missing input must yield None, never raise: a bad
        # deeplink is not worth failing an identification over.
        ("spotify", None, None),
        ("spotify", "", None),
        ("spotify", "spotify:search:", None),
        ("spotify", "https://open.spotify.com/track/x", None),
        ("deezer", "deezer-query://x/play?query=not-the-expected-shape", None),
        ("tidal", "whatever", None),
    ],
)
def test_web_search_url_conversion(platform, uri, expected):
    """App-scheme deeplinks become clickable https universal links."""
    from tracklistify.providers.shazam import _web_search_url

    assert _web_search_url(platform, uri) == expected


def test_web_search_url_does_not_double_encode():
    """Shazam pre-encodes the terms; re-quoting without decoding first
    would emit %2520 for a space and break the search."""
    from tracklistify.providers.shazam import _web_search_url

    url = _web_search_url("spotify", "spotify:search:A%20B%20%26%20C")
    assert "%2520" not in url
    assert url == "https://open.spotify.com/search/A%20B%20%26%20C"


@pytest.mark.asyncio
async def test_malformed_provider_entry_does_not_lose_the_match(monkeypatch):
    """A junk hub.providers entry must not cost the whole identification.

    ``(123 or "").strip()`` raises AttributeError, and this loop sits in
    identify_track's outer try — so one numeric ``type`` in one deeplink
    entry would escalate to ShazamError and discard a match whose title,
    artist and ISRC were all perfectly valid. A cosmetic sub-field must
    never outrank the identification.
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
                    hub={
                        "actions": [],
                        "providers": [
                            {"type": 123, "actions": [{"uri": "x://y"}]},
                            "not-a-dict",
                            {"type": "", "actions": [{"uri": "x://blank"}]},
                            {"actions": [{"uri": "x://missing-type"}]},
                            {
                                "type": "  SPOTIFY  ",
                                "actions": ["junk", {"uri": "spotify:search:Real"}],
                            },
                        ],
                    }
                )
            ),
        )

        entry = (
            await provider.identify_track(
                SimpleNamespace(file_path="segment.mp3", start_time=0)
            )
        )["metadata"]["music"][0]

        # The match survived intact...
        assert entry["title"] == "Berghain"
        assert entry["external_ids"]["isrc"] == "USABC1234567"
        # ...and the one well-formed entry still resolved, whitespace and
        # casing normalized, junk entries skipped.
        assert entry["spotify_search_url"] == ("https://open.spotify.com/search/Real")
        assert entry["deezer_search_url"] is None
    finally:
        clear_config()
