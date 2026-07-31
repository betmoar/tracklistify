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
    async def test_cache_hit_suffix_matches_actual_codec_not_sidecar(
        self, monkeypatch, tmp_path
    ):
        """The cached blob is extensionless; the sidecar's ext is the
        *container* YouTube served, which may not match the actual audio
        codec inside (e.g. an mp3 stream labeled webm). split_audio must
        get a suffix matching the real codec (probed via ffprobe) so
        ffmpeg's stream-copy muxer accepts it — not the sidecar's label.

        Reproduces the regression where a webm-labeled mp3 stream produced
        zero segments ("Only Vorbis or Opus ... supported for WebM").
        """
        import shutil
        import subprocess

        if not shutil.which("ffmpeg"):
            pytest.skip("ffmpeg not installed")

        app = _make_app(monkeypatch, tmp_path)
        url = "https://youtu.be/dQw4w9WgXcQ"

        # Generate a real, tiny mp3 file (2s of silence) — this is the
        # actual codec the cache will hold.
        real_mp3 = tmp_path / "src.mp3"
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=8000:cl=mono",
                "-t",
                "2",
                "-c:a",
                "mp3",
                str(real_mp3),
            ],
            check=True,
        )
        await app.download_cache.set(
            url,
            stream_copy=True,
            audio_path=real_mp3,
            # Deliberately WRONG: the container label, not the codec inside.
            metadata={"title": "T", "uploader": "U", "duration": 2.0, "ext": "webm"},
        )

        downloader = MagicMock()
        downloader.download = AsyncMock(return_value="/nope")
        app.downloader_factory.create_downloader = MagicMock(return_value=downloader)

        # Capture the path split_audio receives (the real one, not a stub).
        captured_path = []
        original_split = app.split_audio

        def spy_split(file_path, duration_hint=None):
            captured_path.append(str(file_path))
            return original_split(file_path, duration_hint=duration_hint)

        app.split_audio = spy_split
        await app.process_input(url, stream_copy=True)

        assert captured_path, "split_audio was never called"
        # The suffix must be compatible with the real codec (mp3), NOT the
        # lying sidecar label (webm). ffmpeg stream-copy into .webm would
        # reject an mp3 stream.
        assert not captured_path[0].endswith(".webm"), (
            f"split_audio got {captured_path[0]!r} — suffix must match the "
            f"probed codec (mp3), not the sidecar label (webm)"
        )

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
