"""Tests for Step 2: the DownloadCache blob store.

A URL-keyed cache for downloaded audio + metadata sidecar, separate from
the existing BaseCache (which rejects non-JSON values). Keys on a per-
provider canonical ID + stream_copy flag, so the same URL yields one entry
per codec variant.
"""

import hashlib
import json

import pytest

from tracklistify.cache.download import DownloadCache
from tracklistify.downloaders.cache_key import canonicalize_url


def _sha(url: str, stream_copy: bool) -> str:
    key_material = f"{canonicalize_url(url)}|stream_copy={stream_copy}"
    return hashlib.sha256(key_material.encode()).hexdigest()


class TestDownloadCacheRoundTrip:
    @pytest.mark.asyncio
    async def test_miss_then_set_then_hit(self, tmp_path):
        cache = DownloadCache(cache_dir=tmp_path)
        url = "https://youtu.be/dQw4w9WgXcQ"

        # Initially absent.
        assert await cache.get(url, stream_copy=False) is None

        # Stage a fake audio file and store it.
        src = tmp_path / "src.mp3"
        src.write_bytes(b"audio-bytes")
        meta = {"title": "Test", "uploader": "Tester", "duration": 180.0, "ext": "mp3"}
        await cache.set(url, stream_copy=False, audio_path=src, metadata=meta)

        # Now it hits.
        entry = await cache.get(url, stream_copy=False)
        assert entry is not None
        assert entry.audio_path.is_file()
        assert entry.audio_path.read_bytes() == b"audio-bytes"
        assert entry.metadata["title"] == "Test"
        assert entry.metadata["uploader"] == "Tester"

    @pytest.mark.asyncio
    async def test_stream_copy_produces_distinct_entries(self, tmp_path):
        cache = DownloadCache(cache_dir=tmp_path)
        url = "https://youtu.be/dQw4w9WgXcQ"

        src_mp3 = tmp_path / "a.mp3"
        src_mp3.write_bytes(b"mp3-bytes")
        await cache.set(
            url,
            stream_copy=False,
            audio_path=src_mp3,
            metadata={"title": "T", "ext": "mp3"},
        )
        src_webm = tmp_path / "a.webm"
        src_webm.write_bytes(b"webm-bytes")
        await cache.set(
            url,
            stream_copy=True,
            audio_path=src_webm,
            metadata={"title": "T", "ext": "webm"},
        )

        mp3_entry = await cache.get(url, stream_copy=False)
        webm_entry = await cache.get(url, stream_copy=True)
        assert mp3_entry.audio_path.read_bytes() == b"mp3-bytes"
        assert webm_entry.audio_path.read_bytes() == b"webm-bytes"
        assert mp3_entry.audio_path != webm_entry.audio_path

    @pytest.mark.asyncio
    async def test_has(self, tmp_path):
        cache = DownloadCache(cache_dir=tmp_path)
        url = "https://youtu.be/dQw4w9WgXcQ"
        assert await cache.has(url, stream_copy=False) is False
        src = tmp_path / "x.mp3"
        src.write_bytes(b"x")
        await cache.set(url, stream_copy=False, audio_path=src, metadata={"ext": "mp3"})
        assert await cache.has(url, stream_copy=False) is True


class TestSidecarPersistence:
    @pytest.mark.asyncio
    async def test_sidecar_written_and_named_by_hash(self, tmp_path):
        cache = DownloadCache(cache_dir=tmp_path)
        url = "https://youtu.be/dQw4w9WgXcQ"
        src = tmp_path / "src.mp3"
        src.write_bytes(b"audio")
        meta = {"title": "T", "uploader": "U", "duration": 60.0, "ext": "mp3"}
        await cache.set(url, stream_copy=False, audio_path=src, metadata=meta)

        expected_hash = _sha(url, False)
        downloads_dir = tmp_path / "downloads"
        audio_file = downloads_dir / expected_hash
        sidecar = downloads_dir / f"{expected_hash}.meta.json"
        assert audio_file.is_file()
        assert sidecar.is_file()
        stored = json.loads(sidecar.read_text())
        assert stored["title"] == "T"
        assert stored["duration"] == 60.0

    @pytest.mark.asyncio
    async def test_corrupt_sidecar_degrades_to_miss(self, tmp_path):
        """If the sidecar is unreadable, treat as a miss (not a crash)."""
        cache = DownloadCache(cache_dir=tmp_path)
        url = "https://youtu.be/dQw4w9WgXcQ"
        src = tmp_path / "src.mp3"
        src.write_bytes(b"audio")
        await cache.set(url, stream_copy=False, audio_path=src, metadata={"ext": "mp3"})

        # Corrupt the sidecar.
        h = _sha(url, False)
        sidecar = tmp_path / "downloads" / f"{h}.meta.json"
        sidecar.write_text("{not valid json")

        entry = await cache.get(url, stream_copy=False)
        assert entry is None, "corrupt sidecar must degrade to miss, not raise"

    @pytest.mark.asyncio
    async def test_missing_audio_file_degrades_to_miss(self, tmp_path):
        """If the audio blob is gone (manual deletion), treat as a miss."""
        cache = DownloadCache(cache_dir=tmp_path)
        url = "https://youtu.be/dQw4w9WgXcQ"
        src = tmp_path / "src.mp3"
        src.write_bytes(b"audio")
        await cache.set(url, stream_copy=False, audio_path=src, metadata={"ext": "mp3"})

        h = _sha(url, False)
        (tmp_path / "downloads" / h).unlink()  # delete the blob

        entry = await cache.get(url, stream_copy=False)
        assert entry is None


class TestCacheKeyIncludesStreamCopy:
    """The hash must include stream_copy so codec variants don't collide."""

    def test_hash_differs_by_stream_copy(self):
        url = "https://youtu.be/dQw4w9WgXcQ"
        assert _sha(url, False) != _sha(url, True)
