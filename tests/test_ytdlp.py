"""Tests for the yt-dlp downloader.

Focus: the SoundCloud ``/sets/`` single-entry playlist unwrap and the
``requested_downloads[0]["filepath"]`` preference. Both are mocked at the
``yt_dlp.YoutubeDL`` boundary — no network. The convention in this suite is
full mocking (see test_download_cache_wiring.py), never live fetches.
"""

from unittest.mock import MagicMock

import pytest

from tracklistify.downloaders import ytdlp
from tracklistify.downloaders.ytdlp import YtDlpDownloader


class _FakeYdl:
    """Minimal stand-in for the yt-dlp YoutubeDL context manager.

    ``extract_info`` returns the canned ``info`` dict; ``prepare_filename``
    mimics yt-dlp reconstructing a path from ``%(id)s.%(ext)s`` (so a
    playlist container yields a path from the *set* id, which is the bug
    the unwrap must bypass).
    """

    def __init__(self, info, temp_dir):
        self._info = info
        self._temp_dir = temp_dir

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=True):
        return self._info

    def prepare_filename(self, info):
        # Mirror the outtmpl ``%(id)s.%(ext)s`` in download().
        return f"{self._temp_dir}/{info.get('id', 'x')}.{info.get('ext', 'mp3')}"


@pytest.mark.asyncio
async def test_soundcloud_sets_unwraps_playlist_container(monkeypatch, tmp_path):
    """A ``/sets/`` URL returns a playlist container whose id/ext/duration
    describe the set, not the track. After download(), last_metadata and
    title/uploader/duration must reflect the unwrapped entry[0], and the
    output path must point at the actually-downloaded track file."""
    track_path = tmp_path / "track123.mp3"
    track_path.write_bytes(b"audio")

    set_info = {
        "_type": "playlist",
        "id": "the-set-id",
        "title": "My Set",
        "uploader": "Set Curator",
        "duration": 9999,
        "ext": "mp3",
        "entries": [
            {
                "id": "track123",
                "title": "Real Track Title",
                "uploader": "Track Artist",
                "duration": 200,
                "ext": "mp3",
                "requested_downloads": [{"filepath": str(track_path)}],
            }
        ],
    }

    monkeypatch.setattr(
        ytdlp, "yt_dlp", MagicMock(YoutubeDL=lambda opts: _FakeYdl(set_info, tmp_path))
    )

    dl = YtDlpDownloader(stream_copy=True, temp_dir=str(tmp_path))
    out = await dl.download("https://soundcloud.com/user/sets/my-set")

    # Metadata was unwrapped from the container to entries[0].
    meta = dl.get_last_metadata()
    assert meta["id"] == "track123"
    assert meta["title"] == "Real Track Title"
    assert dl.title == "Real Track Title"
    assert dl.uploader == "Track Artist"
    assert dl.duration == 200

    # The output path is the one yt-dlp actually wrote, not the set-id path.
    assert out == str(track_path)


@pytest.mark.asyncio
async def test_non_playlist_info_passes_through_unchanged(monkeypatch, tmp_path):
    """A plain (non-playlist) info dict is not unwrapped — no behavior change
    for YouTube/Mixcloud/direct SoundCloud track URLs."""
    audio = tmp_path / "vid9.mp3"
    audio.write_bytes(b"audio")

    info = {
        "id": "vid9",
        "title": "Direct Title",
        "uploader": "Direct Uploader",
        "duration": 120,
        "ext": "mp3",
        "requested_downloads": [{"filepath": str(audio)}],
    }

    monkeypatch.setattr(
        ytdlp, "yt_dlp", MagicMock(YoutubeDL=lambda opts: _FakeYdl(info, tmp_path))
    )

    dl = YtDlpDownloader(stream_copy=True, temp_dir=str(tmp_path))
    out = await dl.download("https://www.youtube.com/watch?v=vid9")

    meta = dl.get_last_metadata()
    assert meta["id"] == "vid9"  # unchanged — no _type == playlist
    assert dl.title == "Direct Title"
    assert out == str(audio)


@pytest.mark.asyncio
async def test_prepare_filename_fallback_when_no_requested_downloads(
    monkeypatch, tmp_path
):
    """When ``requested_downloads`` is absent, fall back to reconstructing the
    path via prepare_filename + the stream-copy glob (the pre-fix behavior)."""
    # Create the file at the prepare_filename-reconstructed path so the glob
    # resolves. Use the entry's id/ext after unwrap.
    reconstructed = tmp_path / "abc.m4a"
    reconstructed.write_bytes(b"audio")

    set_info = {
        "_type": "playlist",
        "id": "setid",
        "entries": [
            {"id": "abc", "title": "T", "uploader": "U", "duration": 10, "ext": "m4a"}
            # No requested_downloads -> forces the fallback path.
        ],
    }

    monkeypatch.setattr(
        ytdlp, "yt_dlp", MagicMock(YoutubeDL=lambda opts: _FakeYdl(set_info, tmp_path))
    )

    dl = YtDlpDownloader(stream_copy=True, temp_dir=str(tmp_path))
    out = await dl.download("https://soundcloud.com/u/sets/s")

    # Unwrap happened (entry id), and the fallback reconstructed path resolves.
    assert dl.get_last_metadata()["id"] == "abc"
    assert out == str(reconstructed)


@pytest.mark.asyncio
async def test_multi_entry_set_warns_about_truncation(monkeypatch, tmp_path, caplog):
    """F05: a multi-track set is truncated to entries[0] — that must be
    visible at default verbosity, not buried at debug level.

    A silently truncated set yields a tracklist for one track and caches it
    under the set's URL with no TTL, which is indistinguishable from a
    correct result.
    """
    import logging

    track_path = tmp_path / "first.mp3"
    track_path.write_bytes(b"audio")

    set_info = {
        "_type": "playlist",
        "id": "set-id",
        "entries": [
            {
                "id": "first",
                "title": "First Track",
                "uploader": "U",
                "duration": 100,
                "ext": "mp3",
                "requested_downloads": [{"filepath": str(track_path)}],
            },
            {"id": "second", "title": "Second Track", "ext": "mp3"},
            {"id": "third", "title": "Third Track", "ext": "mp3"},
        ],
    }

    monkeypatch.setattr(
        ytdlp, "yt_dlp", MagicMock(YoutubeDL=lambda opts: _FakeYdl(set_info, tmp_path))
    )

    dl = YtDlpDownloader(stream_copy=True, temp_dir=str(tmp_path))
    with caplog.at_level(logging.WARNING):
        await dl.download("https://soundcloud.com/user/sets/multi")

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, "truncating a multi-entry set must warn at WARNING level"
    assert "3-track set" in warnings[0].getMessage()
    # Still returns the first entry.
    assert dl.get_last_metadata()["id"] == "first"
