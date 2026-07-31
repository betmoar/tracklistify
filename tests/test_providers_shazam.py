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
