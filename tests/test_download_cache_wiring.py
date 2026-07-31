"""Tests for Step 2 wiring: DownloadCache integrated into AsyncApp.process_input.

The download cache sits between URL validation and the downloader. A hit
skips ``downloader.download()`` and reads metadata from the sidecar; a miss
downloads and populates the cache. Failures degrade to a live download.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from tracklistify.config.factory import get_config
from tracklistify.core.base import AsyncApp
from tracklistify.core.track import Track
from tracklistify.core.types import AudioSegment


def _make_track():
    return Track(song_name="S", artist="A", time_in_mix="00:00:30", confidence=90.0)


def _make_app(monkeypatch, tmp_path, download_cache_enabled=True):
    """Build an AsyncApp pointed at tmp_path, with the heavy I/O stubbed."""
    monkeypatch.setenv("TRACKLISTIFY_TEMP_DIR", str(tmp_path / "temp"))
    monkeypatch.setenv("TRACKLISTIFY_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("TRACKLISTIFY_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv(
        "TRACKLISTIFY_DOWNLOAD_CACHE_ENABLED",
        "true" if download_cache_enabled else "false",
    )
    config = get_config(force_refresh=True)
    app = AsyncApp(config)
    # Stub split_audio + identification so process_input is isolated to the
    # download path. Both must return non-empty lists, or process_input
    # raises before reaching the cache-relevant assertions.
    seg = AudioSegment(file_path=str(tmp_path / "seg.wav"), start_time=0, duration=60)
    app.split_audio = MagicMock(return_value=[seg])
    app.identification_manager = MagicMock()
    app.identification_manager.identify_tracks = AsyncMock(return_value=[_make_track()])
    app.save_output = AsyncMock()
    return app


class TestDownloadCacheWiring:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_download(self, monkeypatch, tmp_path):
        app = _make_app(monkeypatch, tmp_path)
        url = "https://youtu.be/dQw4w9WgXcQ"

        # Stage a cached entry.
        audio = tmp_path / "cached.mp3"
        audio.write_bytes(b"audio")
        await app.download_cache.set(
            url,
            stream_copy=False,
            audio_path=audio,
            metadata={"title": "Cached", "uploader": "Cacher", "duration": 100.0},
        )

        # The real downloader must never be called.
        downloader = MagicMock()
        downloader.download = AsyncMock(return_value="/should/not/be/used")
        app.downloader_factory.create_downloader = MagicMock(return_value=downloader)

        await app.process_input(url)

        downloader.download.assert_not_awaited()
        # Metadata came from the sidecar, not the downloader.
        assert app.original_title == "Cached"
        assert app.uploader == "Cacher"
        assert app.duration == 100.0

    @pytest.mark.asyncio
    async def test_cache_miss_downloads_and_populates(self, monkeypatch, tmp_path):
        app = _make_app(monkeypatch, tmp_path)
        url = "https://youtu.be/dQw4w9WgXcQ"

        downloaded = tmp_path / "fresh.mp3"
        downloaded.write_bytes(b"fresh-audio")
        downloader = MagicMock()
        downloader.download = AsyncMock(return_value=str(downloaded))
        downloader.get_last_metadata = MagicMock(
            return_value={"title": "Fresh", "uploader": "Artist", "duration": 50.0}
        )
        app.downloader_factory.create_downloader = MagicMock(return_value=downloader)

        await app.process_input(url)

        downloader.download.assert_awaited_once()
        # Cache now has an entry for this URL.
        assert await app.download_cache.has(url, stream_copy=False)
        assert app.original_title == "Fresh"

    @pytest.mark.asyncio
    async def test_disabled_cache_always_downloads(self, monkeypatch, tmp_path):
        app = _make_app(monkeypatch, tmp_path, download_cache_enabled=False)
        url = "https://youtu.be/dQw4w9WgXcQ"

        # Stage a cached entry that must be ignored.
        audio = tmp_path / "cached.mp3"
        audio.write_bytes(b"cached")
        await app.download_cache.set(
            url,
            stream_copy=False,
            audio_path=audio,
            metadata={"title": "Ignored"},
        )

        downloaded = tmp_path / "fresh.mp3"
        downloaded.write_bytes(b"fresh")
        downloader = MagicMock()
        downloader.download = AsyncMock(return_value=str(downloaded))
        downloader.get_last_metadata = MagicMock(
            return_value={"title": "Live", "uploader": "X", "duration": 1.0}
        )
        app.downloader_factory.create_downloader = MagicMock(return_value=downloader)

        await app.process_input(url)

        downloader.download.assert_awaited_once()
        assert app.original_title == "Live", "disabled cache must not supply metadata"
