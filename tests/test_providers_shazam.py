"""Tests for the Shazam identification provider."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tracklistify.config import clear_config, get_config
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
