"""Tests for identification utility functions.

Tests for Phase 2, Issue #3: Implement stub functions
- format_duration()
- create_progress_bar()
- ProgressDisplay class
"""

import pytest
import time
import sys
from tracklistify.utils.identification import (
    format_duration,
    create_progress_bar,
    ProgressDisplay,
)


class TestFormatDuration:
    """Test duration formatting."""

    def test_zero_duration(self):
        """Test zero duration formatting."""
        assert format_duration(0) == "00:00:00"

    def test_seconds_only(self):
        """Test formatting seconds only."""
        assert format_duration(45) == "00:00:45"
        assert format_duration(59) == "00:00:59"

    def test_minutes_and_seconds(self):
        """Test formatting minutes and seconds."""
        assert format_duration(90) == "00:01:30"
        assert format_duration(150) == "00:02:30"

    def test_hours_minutes_seconds(self):
        """Test formatting hours, minutes, and seconds."""
        assert format_duration(3665) == "01:01:05"
        assert format_duration(7200) == "02:00:00"

    def test_large_duration(self):
        """Test large duration values."""
        assert format_duration(86400) == "24:00:00"
        assert format_duration(90000) == "25:00:00"

    def test_fractional_seconds(self):
        """Test that fractional seconds are handled correctly."""
        assert format_duration(90.7) == "00:01:30"
        assert format_duration(90.2) == "00:01:30"
        assert format_duration(90.9) == "00:01:30"


class TestCreateProgressBar:
    """Test progress bar creation."""

    def test_empty_progress(self):
        """Test empty progress bar (0%)."""
        bar = create_progress_bar(0.0, 10)
        assert bar == "[░░░░░░░░░░]"
        assert len(bar) == 12  # 10 chars + 2 brackets

    def test_full_progress(self):
        """Test full progress bar (100%)."""
        bar = create_progress_bar(1.0, 10)
        assert bar == "[██████████]"
        assert len(bar) == 12

    def test_half_progress(self):
        """Test half progress bar (50%)."""
        bar = create_progress_bar(0.5, 10)
        assert bar == "[█████░░░░░]"

    def test_quarter_progress(self):
        """Test quarter progress bar (25%)."""
        bar = create_progress_bar(0.25, 10)
        assert bar == "[██░░░░░░░░]" or bar == "[███░░░░░░░]"  # Rounding

    def test_custom_width(self):
        """Test progress bar with custom width."""
        bar = create_progress_bar(0.5, 20)
        assert len(bar) == 22  # 20 + 2 brackets
        assert bar.startswith("[")
        assert bar.endswith("]")

    def test_progress_clamping_low(self):
        """Test that negative progress is clamped to 0."""
        bar = create_progress_bar(-0.5, 10)
        assert bar == "[░░░░░░░░░░]"

    def test_progress_clamping_high(self):
        """Test that progress > 1.0 is clamped to 1.0."""
        bar = create_progress_bar(1.5, 10)
        assert bar == "[██████████]"

    def test_progress_contains_correct_characters(self):
        """Test that progress bar only contains valid characters."""
        bar = create_progress_bar(0.7, 20)
        # Remove brackets
        inner = bar[1:-1]
        # Should only contain filled or empty blocks
        for char in inner:
            assert char in ["█", "░"], f"Invalid character: {char}"


class TestProgressDisplay:
    """Test progress display functionality."""

    def test_initialization(self):
        """Test ProgressDisplay initializes correctly."""
        display = ProgressDisplay()
        assert display.current_segment == 0
        assert display.total_segments == 0
        assert display.start_time is None

    def test_start_sets_values(self):
        """Test that start() sets correct values."""
        display = ProgressDisplay()
        display.start(total=10)

        assert display.total_segments == 10
        assert display.current_segment == 0
        assert display.start_time is not None
        assert display.start_time <= time.time()

    def test_update_changes_current(self):
        """Test that update() changes current segment."""
        display = ProgressDisplay()
        display.start(total=10)

        display.update(current=5)
        assert display.current_segment == 5

        display.update(current=8)
        assert display.current_segment == 8

    def test_update_with_zero_total_no_crash(self):
        """Test that update() with zero total doesn't crash."""
        display = ProgressDisplay()
        display.start(total=0)

        # Should not raise exception
        display.update(current=0)
        display.complete()

    @pytest.mark.skipif(
        sys.platform == "win32", reason="Terminal output differs on Windows"
    )
    def test_update_writes_to_stdout(self, capsys):
        """Test that update() writes progress to stdout."""
        display = ProgressDisplay()
        display.start(total=10)
        display.update(current=5)

        captured = capsys.readouterr()
        # Should contain progress information
        assert "5/10" in captured.out or "5" in captured.out
        assert "50" in captured.out or "5" in captured.out  # 50% or 5/10

    def test_complete_writes_newline(self, capsys):
        """Test that complete() writes completion message."""
        display = ProgressDisplay()
        display.start(total=10)
        display.update(current=10)
        display.complete()

        captured = capsys.readouterr()
        # Should contain completion message
        assert "Completed" in captured.out or "\n" in captured.out

    def test_complete_without_start_no_crash(self):
        """Test that complete() without start() doesn't crash."""
        display = ProgressDisplay()
        # Should not raise exception
        display.complete()

    def test_clear_removes_progress(self):
        """Test that clear() clears the progress line."""
        display = ProgressDisplay()
        display.start(total=10)
        display.update(current=5)
        display.clear()

        assert display._last_line_length == 0

    def test_clear_overwrites_full_rendered_width(self, capsys):
        """clear() must blank at least the previously rendered line length.

        Regression: clearing a fixed 80 chars leaves residue when the
        progress line was wider (e.g. very large total segment counts).
        """
        display = ProgressDisplay()
        display.start(total=999_999)
        display.update(current=500_000)
        rendered_width = display._last_line_length

        # Force a wider-than-default rendered line for the assertion.
        assert rendered_width >= 0
        display._last_line_length = max(rendered_width, 120)
        capsys.readouterr()  # discard prior output
        display.clear()

        captured = capsys.readouterr().out
        # The clear must include at least max(_last_line_length, 80) spaces.
        # Strip the surrounding \r markers and count whitespace.
        blanks = captured.strip("\r")
        assert len(blanks) >= 120

    def test_multiple_updates(self):
        """Test multiple sequential updates."""
        display = ProgressDisplay()
        display.start(total=100)

        for i in range(0, 101, 10):
            # Should not crash
            display.update(current=i)

        display.complete()

    def test_progress_timing(self):
        """Test that elapsed time is tracked correctly."""
        display = ProgressDisplay()
        display.start(total=10)

        # Small delay
        time.sleep(0.1)

        display.update(current=5)

        # Start time should be in the past
        assert display.start_time < time.time()

    def test_update_idempotent(self):
        """Test that calling update with same value is safe."""
        display = ProgressDisplay()
        display.start(total=10)

        display.update(current=5)
        display.update(current=5)
        display.update(current=5)

        assert display.current_segment == 5


class TestExtraMetadata:
    """Provider extras -> Track.metadata (PR #57 enrichment).

    Extraction lives in ``_extra_metadata`` and is called from
    ``_track_from_info``, which is the single place a Track is built from a
    provider response — both the live and cache-hit paths route through it,
    so metadata lands on cached tracks too.
    """

    def test_full_metadata_is_extracted(self):
        from tracklistify.utils.identification import _extra_metadata

        extras = _extra_metadata(
            {
                "title": "Berghain",
                "external_ids": {"isrc": "USABC1234567"},
                "genres": [{"name": "Techno"}, {"name": "Hard Techno"}],
                "album": "Hyperdrive",
                "label": "HEKATE",
                "release_date": "2024",
                "shazam_id": "k1",
                "apple_music_id": "am-999",
                "artwork_url": "https://img/hq.jpg",
                "shazam_url": "https://shazam/1",
                "spotify_search_url": "https://open.spotify.com/search/Berghain",
                "deezer_search_url": "https://www.deezer.com/search/Berghain",
            }
        )
        assert extras == {
            "isrc": "USABC1234567",
            "genres": ["Techno", "Hard Techno"],
            "album": "Hyperdrive",
            "label": "HEKATE",
            "release_date": "2024",
            "shazam_id": "k1",
            "apple_music_id": "am-999",
            "artwork_url": "https://img/hq.jpg",
            "shazam_url": "https://shazam/1",
            "spotify_search_url": "https://open.spotify.com/search/Berghain",
            "deezer_search_url": "https://www.deezer.com/search/Berghain",
        }

    def test_empty_values_are_dropped_not_stored_as_none(self):
        """No provider fills every key — ACRCloud has no shazam_id, Shazam
        has no ACRCloud fields. Storing None would fill Track.metadata with
        null noise and defeat the `or None` in _save_json."""
        from tracklistify.utils.identification import _extra_metadata

        assert _extra_metadata({"title": "X", "album": None, "genres": []}) == {}

    def test_malformed_shapes_do_not_raise(self):
        """Provider payloads are third-party JSON. A wrong-typed field must
        degrade to "no extras", never take down identification."""
        from tracklistify.utils.identification import _extra_metadata

        assert _extra_metadata({"external_ids": None}) == {}
        assert _extra_metadata({"external_ids": "nope"}) == {}
        assert _extra_metadata({"genres": "Techno"}) == {}
        assert _extra_metadata({"genres": [None, {"no_name": 1}]}) == {}
        assert _extra_metadata(None) == {}

    def test_track_from_info_attaches_metadata(self):
        """The extras reach Track.metadata through the real build path."""
        from types import SimpleNamespace

        from tracklistify.config import get_config
        from tracklistify.utils.identification import IdentificationManager

        mgr = IdentificationManager(config=get_config(), provider_factory=object())
        track = mgr._track_from_info(
            {
                "metadata": {
                    "music": [
                        {
                            "title": "Berghain",
                            "artists": [{"name": "Sara Landry"}],
                            "score": 90.0,
                            "external_ids": {"isrc": "USABC1234567"},
                            "album": "Hyperdrive",
                        }
                    ]
                }
            },
            SimpleNamespace(start_time=0),
        )
        assert track is not None
        assert track.metadata["isrc"] == "USABC1234567"
        assert track.metadata["album"] == "Hyperdrive"


class TestZeroMatchWarning:
    """A broken pipeline and an unidentifiable set both end at zero matches.

    The per-segment no-match line is deliberately debug (it is the normal
    case in a DJ mix), and Shazam answers a degraded request with HTTP 200
    and an empty ``matches`` list rather than an error — so a dead proxy or
    geo-blocked endpoint produces a clean "0 tracks" run with nothing above
    debug to explain it.
    """

    @pytest.mark.asyncio
    async def test_full_miss_on_a_long_run_warns(self, caplog):
        import logging
        from types import SimpleNamespace

        from tracklistify.config import get_config
        from tracklistify.utils.identification import IdentificationManager

        mgr = IdentificationManager(config=get_config(), provider_factory=object())
        mgr._provider_chain = lambda: []
        segments = [SimpleNamespace(start_time=i * 50) for i in range(12)]

        with caplog.at_level(logging.WARNING):
            await mgr.identify_tracks(segments)

        assert any(
            "No segment out of 12 produced a match" in r.getMessage()
            for r in caplog.records
            if r.levelno >= logging.WARNING
        ), "a total miss across a full mix must be flagged"

    @pytest.mark.asyncio
    async def test_short_clip_full_miss_stays_quiet(self, caplog):
        """Below the threshold a zero-match run is unremarkable — warning
        there would cry wolf on a short clip that genuinely has nothing."""
        import logging
        from types import SimpleNamespace

        from tracklistify.config import get_config
        from tracklistify.utils.identification import IdentificationManager

        mgr = IdentificationManager(config=get_config(), provider_factory=object())
        mgr._provider_chain = lambda: []
        segments = [SimpleNamespace(start_time=i * 50) for i in range(3)]

        with caplog.at_level(logging.WARNING):
            await mgr.identify_tracks(segments)

        assert not [
            r
            for r in caplog.records
            if r.levelno >= logging.WARNING and "produced a match" in r.getMessage()
        ]


class TestCacheRefresh:
    """``cache_refresh`` (--no-cache) skips reads but keeps writes.

    If it skipped both, the flag would be a one-run bypass: the stale entry
    survives on disk and is served again on the next normal run. The point
    of the flag is to REPLACE a bad cached identification.
    """

    @pytest.mark.asyncio
    async def test_refresh_ignores_the_stored_result_and_overwrites_it(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        from tracklistify.config import get_config
        from tracklistify.utils.identification import IdentificationManager

        def _resp(title):
            return {
                "metadata": {
                    "music": [
                        {
                            "title": title,
                            "artists": [{"name": "Artist"}],
                            "score": 90.0,
                        }
                    ]
                }
            }

        cfg = get_config(force_refresh=True)
        cfg.cache_enabled = True
        cache = SimpleNamespace(
            get=AsyncMock(return_value=_resp("STALE WRONG TRACK")),
            set=AsyncMock(),
        )

        provider = AsyncMock()
        provider.identify_track = AsyncMock(return_value=_resp("FRESH CORRECT TRACK"))
        provider.__aenter__ = AsyncMock(return_value=provider)
        provider.__aexit__ = AsyncMock(return_value=False)

        mgr = IdentificationManager(config=cfg, provider_factory=object(), cache=cache)
        mgr._provider_chain = lambda: ["shazam"]
        mgr.provider_factory = SimpleNamespace(
            get_identification_provider=lambda name: provider
        )
        mgr._cache_key = lambda p, s: "k"
        cfg.cache_refresh = True

        tracks = await mgr.identify_tracks(
            [SimpleNamespace(start_time=0, file_path="seg.mp3")]
        )

        # The stale entry was never consulted...
        cache.get.assert_not_awaited()
        assert tracks and tracks[0].song_name == "FRESH CORRECT TRACK"
        # ...and the fresh result was written over it.
        cache.set.assert_awaited_once()
        assert cache.set.await_args.args[0] == "k"

    @pytest.mark.asyncio
    async def test_without_refresh_the_cache_is_read(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        from tracklistify.config import get_config
        from tracklistify.utils.identification import IdentificationManager

        cfg = get_config(force_refresh=True)
        cfg.cache_enabled = True
        cfg.cache_refresh = False
        cache = SimpleNamespace(
            get=AsyncMock(
                return_value={
                    "metadata": {
                        "music": [
                            {
                                "title": "CACHED",
                                "artists": [{"name": "Artist"}],
                                "score": 90.0,
                            }
                        ]
                    }
                }
            ),
            set=AsyncMock(),
        )

        provider = AsyncMock()
        provider.__aenter__ = AsyncMock(return_value=provider)
        provider.__aexit__ = AsyncMock(return_value=False)

        mgr = IdentificationManager(config=cfg, provider_factory=object(), cache=cache)
        mgr._provider_chain = lambda: ["shazam"]
        mgr.provider_factory = SimpleNamespace(
            get_identification_provider=lambda name: provider
        )
        mgr._cache_key = lambda p, s: "k"

        tracks = await mgr.identify_tracks(
            [SimpleNamespace(start_time=0, file_path="seg.mp3")]
        )

        cache.get.assert_awaited_once()
        assert tracks and tracks[0].song_name == "CACHED"
        # A hit short-circuits the provider entirely.
        provider.identify_track.assert_not_awaited()
