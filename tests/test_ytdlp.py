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


@pytest.mark.asyncio
async def test_download_is_bounded_to_a_single_playlist_entry(monkeypatch, tmp_path):
    """yt-dlp must be told to fetch only the first entry.

    ``extract_info(url, download=True)`` on a playlist URL downloads EVERY
    entry before returning, so unwrapping the returned info dict does not
    prevent the fetch. Against a real 15-track SoundCloud /sets/ URL this
    pulled 606MB across 6 tracks before being killed. The mocked tests
    above cannot see this — they stub extract_info entirely — so assert the
    option that bounds it.
    """
    captured = {}

    class _CapturingYdl(_FakeYdl):
        pass

    def _factory(opts):
        captured.update(opts)
        return _CapturingYdl(
            {
                "id": "x",
                "title": "T",
                "uploader": "U",
                "duration": 1,
                "ext": "mp3",
                "requested_downloads": [{"filepath": str(audio)}],
            },
            tmp_path,
        )

    audio = tmp_path / "x.mp3"
    audio.write_bytes(b"a")

    monkeypatch.setattr(ytdlp, "yt_dlp", MagicMock(YoutubeDL=_factory))

    dl = YtDlpDownloader(stream_copy=True, temp_dir=str(tmp_path))
    await dl.download("https://soundcloud.com/user/sets/whatever")

    assert captured.get("playlist_items") == "1", (
        "ydl_opts must set playlist_items='1' or a /sets/ URL downloads "
        "every track in the set"
    )


@pytest.mark.asyncio
async def test_empty_playlist_container_raises(monkeypatch, tmp_path):
    """A playlist container with zero entries must fail loudly.

    Reachable for a private, deleted, or region-locked ``/sets/`` URL:
    yt-dlp returns ``_type == "playlist"`` with an empty tracks list.
    Falling through would leave the *set's* metadata in last_metadata —
    silently reinstating the bug the unwrap exists to fix — and build an
    output path from the set id that no file was ever written to.
    """
    set_info = {
        "_type": "playlist",
        "id": "empty-set",
        "title": "Private Set",
        "entries": [],
    }
    monkeypatch.setattr(
        ytdlp, "yt_dlp", MagicMock(YoutubeDL=lambda opts: _FakeYdl(set_info, tmp_path))
    )

    dl = YtDlpDownloader(stream_copy=True, temp_dir=str(tmp_path))
    with pytest.raises(ValueError, match="No downloadable entries"):
        await dl.download("https://soundcloud.com/user/sets/private-set")


@pytest.mark.asyncio
async def test_missing_output_file_raises_instead_of_returning_dead_path(
    monkeypatch, tmp_path
):
    """No requested_downloads, no reconstructed file, no glob match -> raise.

    Returning the reconstructed path would report success for a file that
    does not exist; the failure would first surface in split_audio as
    "Could not read audio file", several frames from the cause.
    """
    info = {
        "id": "ghost",
        "title": "Ghost Track",
        "uploader": "Nobody",
        "duration": 100,
        "ext": "mp3",
        # No requested_downloads, and no file on disk at ghost.mp3.
    }
    monkeypatch.setattr(
        ytdlp, "yt_dlp", MagicMock(YoutubeDL=lambda opts: _FakeYdl(info, tmp_path))
    )

    dl = YtDlpDownloader(stream_copy=True, temp_dir=str(tmp_path))
    with pytest.raises(ValueError, match="Downloaded file not found"):
        await dl.download("https://soundcloud.com/user/ghost")


@pytest.mark.asyncio
async def test_requested_downloads_without_filepath_falls_back(
    monkeypatch, tmp_path, caplog
):
    """requested_downloads present but carrying no filepath: fall back to
    reconstruction, and say so — this is distinct from the documented
    "no requested_downloads at all" case."""
    audio = tmp_path / "partial.mp3"
    audio.write_bytes(b"audio")
    info = {
        "id": "partial",
        "title": "Partial",
        "uploader": "Someone",
        "duration": 50,
        "ext": "mp3",
        "requested_downloads": [{"filepath": None}],
    }
    monkeypatch.setattr(
        ytdlp, "yt_dlp", MagicMock(YoutubeDL=lambda opts: _FakeYdl(info, tmp_path))
    )

    dl = YtDlpDownloader(stream_copy=True, temp_dir=str(tmp_path))
    with caplog.at_level("DEBUG"):
        out = await dl.download("https://soundcloud.com/user/partial")

    assert out == str(audio)
    assert any("carries no filepath" in r.message for r in caplog.records), (
        "the degraded-path fallback must be logged, not silent"
    )


@pytest.mark.asyncio
async def test_download_max_retries_is_wired_into_ydl_opts(monkeypatch, tmp_path):
    """``config.download_max_retries`` must reach yt-dlp's native ``retries``
    option. yt-dlp's own retry layer handles transient HTTP 403s (YouTube
    bot-detection throttling — the case that succeeds on a manual second
    run ~3s later) with backoff and format/client rotation, which a
    Python-level loop re-running ``extract_info`` can't match.

    Without this wiring the knob is dead config (advertised in
    ``.env.example``, never read), so a transient 403 aborts the whole run.
    """
    from tracklistify.config.factory import ConfigFactory, get_config

    ConfigFactory.clear_cache()
    monkeypatch.setenv("TRACKLISTIFY_DOWNLOAD_MAX_RETRIES", "5")
    get_config(force_refresh=True)

    captured = {}

    def _factory(opts):
        captured.update(opts)
        return _FakeYdl(
            {
                "id": "x",
                "title": "T",
                "uploader": "U",
                "duration": 1,
                "ext": "mp3",
                "requested_downloads": [{"filepath": str(tmp_path / "x.mp3")}],
            },
            tmp_path,
        )

    monkeypatch.setattr(ytdlp, "yt_dlp", MagicMock(YoutubeDL=_factory))

    dl = YtDlpDownloader(stream_copy=True, temp_dir=str(tmp_path))
    await dl.download("https://www.youtube.com/watch?v=x")

    assert captured.get("retries") == 5, (
        "config.download_max_retries (5) must be wired into ydl_opts['retries'] "
        "or a transient 403 aborts the run instead of being retried"
    )
    ConfigFactory.clear_cache()


@pytest.mark.asyncio
async def test_ydl_opts_verbose_is_false(monkeypatch, tmp_path):
    """``ydl_opts['verbose']`` must be False. yt-dlp routes real errors through
    our ``YTDLPLogger.error`` hook regardless of ``verbose``; ``verbose=True``
    only dumps debug-level frames (the traceback flood) to stderr. The inline
    comment said "Always set to False" while the value was True — a one-line
    contradiction that flooded the log on every download failure.
    """
    captured = {}

    def _factory(opts):
        captured.update(opts)
        return _FakeYdl(
            {
                "id": "x",
                "title": "T",
                "uploader": "U",
                "duration": 1,
                "ext": "mp3",
                "requested_downloads": [{"filepath": str(tmp_path / "x.mp3")}],
            },
            tmp_path,
        )

    monkeypatch.setattr(ytdlp, "yt_dlp", MagicMock(YoutubeDL=_factory))

    dl = YtDlpDownloader(stream_copy=True, temp_dir=str(tmp_path))
    await dl.download("https://www.youtube.com/watch?v=x")

    assert captured.get("verbose") is False, (
        "ydl_opts['verbose'] must be False or yt-dlp dumps its traceback to "
        "stderr on every failure, on top of our own logged error"
    )


@pytest.mark.asyncio
async def test_youtube_playlist_params_stripped_before_download(monkeypatch, tmp_path):
    """A YouTube URL with ``&list=`` (an auto-mix / radio playlist) must have
    the playlist params stripped before reaching yt-dlp. YouTube returns 403
    on programmatic resolution of ``RD`` (server-generated mix) lists; yt-dlp
    descends into the playlist before ``playlist_items='1'`` bounds the
    *download*, so the 403 fires during resolution and is not retryable.

    We only ever process one video, so the playlist context is never wanted.
    ``?v=<id>`` is the only load-bearing param for a download. Verified
    against a real ``&list=RD...`` URL: the bare video succeeds, the playlist
    URL 403s.
    """
    captured_url = {}

    class _UrlCapturingYdl(_FakeYdl):
        def extract_info(self, url, download=True):
            captured_url["url"] = url
            return self._info

    info = {
        "id": "JH0tXHFmkS8",
        "title": "T",
        "uploader": "U",
        "duration": 1,
        "ext": "mp3",
        "requested_downloads": [{"filepath": str(tmp_path / "JH0tXHFmkS8.mp3")}],
    }

    def _factory(opts):
        return _UrlCapturingYdl(info, tmp_path)

    monkeypatch.setattr(ytdlp, "yt_dlp", MagicMock(YoutubeDL=_factory))

    dl = YtDlpDownloader(stream_copy=True, temp_dir=str(tmp_path))
    await dl.download("https://www.youtube.com/watch?v=JH0tXHFmkS8&list=RDJH0tXHFmkS8")

    passed = captured_url.get("url", "")
    assert "list=" not in passed, (
        f"the &list= playlist param must be stripped before yt-dlp sees the "
        f"URL (it triggers a non-retryable 403 on RD auto-mixes); got {passed!r}"
    )
    assert "v=JH0tXHFmkS8" in passed, "the video id must be preserved"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        # v= first (the common case the original test covered).
        "https://www.youtube.com/watch?v=JH0tXHFmkS8&list=RDJH0tXHFmkS8",
        # list= first — YouTube emits playlist URLs with the list param in
        # either order; the video id must still be extracted and the list
        # stripped, or the non-retryable 403 survives.
        "https://www.youtube.com/watch?list=RDJH0tXHFmkS8&v=JH0tXHFmkS8",
        # v= in the middle (feature/shared params before it).
        "https://www.youtube.com/watch?feature=shared&v=JH0tXHFmkS8&list=RDx",
        # music.youtube.com with list first.
        "https://music.youtube.com/watch?list=RDx&v=JH0tXHFmkS8",
    ],
)
async def test_youtube_playlist_params_stripped_v_in_any_position(
    monkeypatch, tmp_path, url
):
    """The video id must be extracted regardless of where ``v=`` sits in the
    query string. YouTube emits playlist URLs with params in either order; a
    regex that only matches ``watch?v=`` (v first) misses ``watch?list=...&v=``
    and leaves the playlist param — so the non-retryable 403 survives. The
    extractor needs a ``[?&]v=<id>`` fallback (mirroring
    ``downloaders/cache_key._YT_PATTERNS``)."""
    captured_url = {}

    class _UrlCapturingYdl(_FakeYdl):
        def extract_info(self, url, download=True):
            captured_url["url"] = url
            return self._info

    info = {
        "id": "JH0tXHFmkS8",
        "title": "T",
        "uploader": "U",
        "duration": 1,
        "ext": "mp3",
        "requested_downloads": [{"filepath": str(tmp_path / "JH0tXHFmkS8.mp3")}],
    }

    monkeypatch.setattr(
        ytdlp,
        "yt_dlp",
        MagicMock(YoutubeDL=lambda opts: _UrlCapturingYdl(info, tmp_path)),
    )

    dl = YtDlpDownloader(stream_copy=True, temp_dir=str(tmp_path))
    await dl.download(url)

    passed = captured_url.get("url", "")
    assert "list=" not in passed, (
        f"playlist param not stripped for {url!r} -> {passed!r}"
    )
    assert "v=JH0tXHFmkS8" in passed, f"video id lost for {url!r} -> {passed!r}"
