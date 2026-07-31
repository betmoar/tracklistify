"""Tests for Step 3: playable self-contained M3U.

The M3U points at a single audio file inside the output subfolder and uses
VLC's ``#EXTVLCOPT:start-time`` for per-track seeking. EXTINF duration is
the gap to the next track. Previously the M3U emitted only comments with no
playable URI lines and EXTINF was always -1.
"""

from tracklistify.config.factory import get_config
from tracklistify.core.track import Track
from tracklistify.exporters.tracklist import TracklistOutput


def _config_output_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("TRACKLISTIFY_OUTPUT_DIR", str(tmp_path))
    return get_config(force_refresh=True)


def _tracks():
    # times: 00:00:30, 00:02:00, 00:04:30  (30s, 120s, 270s)
    return [
        Track(song_name="A", artist="X", time_in_mix="00:00:30", confidence=90.0),
        Track(song_name="B", artist="Y", time_in_mix="00:02:00", confidence=90.0),
        Track(song_name="C", artist="Z", time_in_mix="00:04:30", confidence=90.0),
    ]


def _read_m3u(out):
    path = out.save("m3u")
    return path.read_text(encoding="utf-8")


class TestPlayableM3U:
    def test_has_extm3u_header(self, monkeypatch, tmp_path):
        _config_output_dir(monkeypatch, tmp_path)
        out = TracklistOutput(
            mix_info={"title": "T", "artist": "A", "date": "2026-07-31"},
            tracks=_tracks(),
        )
        lines = _read_m3u(out).splitlines()
        assert lines[0] == "#EXTM3U"

    def test_each_track_has_playable_uri(self, monkeypatch, tmp_path):
        """Every track entry references the audio file (not just comments)."""
        _config_output_dir(monkeypatch, tmp_path)
        out = TracklistOutput(
            mix_info={
                "title": "T",
                "artist": "A",
                "date": "2026-07-31",
                "audio_filename": "mix.mp3",
            },
            tracks=_tracks(),
        )
        lines = _read_m3u(out).splitlines()
        # Drop the header; group remaining lines into per-track blocks.
        body = lines[1:]
        uri_lines = [ln for ln in body if not ln.startswith("#")]
        assert len(uri_lines) == 3, f"expected 3 URI lines, got: {uri_lines}"
        for ln in uri_lines:
            assert ln == "mix.mp3", f"URI line must be the audio filename: {ln}"

    def test_start_time_offset_matches_time_in_mix(self, monkeypatch, tmp_path):
        """#EXTVLCOPT:start-time is the track's offset in seconds."""
        _config_output_dir(monkeypatch, tmp_path)
        out = TracklistOutput(
            mix_info={
                "title": "T",
                "artist": "A",
                "date": "2026-07-31",
                "audio_filename": "mix.mp3",
            },
            tracks=_tracks(),
        )
        lines = _read_m3u(out).splitlines()
        start_opts = [ln for ln in lines if ln.startswith("#EXTVLCOPT:start-time=")]
        assert len(start_opts) == 3
        assert start_opts[0] == "#EXTVLCOPT:start-time=30"  # 00:00:30
        assert start_opts[1] == "#EXTVLCOPT:start-time=120"  # 00:02:00
        assert start_opts[2] == "#EXTVLCOPT:start-time=270"  # 00:04:30

    def test_extinf_duration_is_gap_to_next(self, monkeypatch, tmp_path):
        """EXTINF duration = next track start - this track start."""
        _config_output_dir(monkeypatch, tmp_path)
        out = TracklistOutput(
            mix_info={
                "title": "T",
                "artist": "A",
                "date": "2026-07-31",
                "audio_filename": "mix.mp3",
            },
            tracks=_tracks(),
        )
        lines = _read_m3u(out).splitlines()
        extinf = [ln for ln in lines if ln.startswith("#EXTINF:")]
        # 30->120 = 90s; 120->270 = 150s; last falls back to -1 (no
        # total_duration in this mix_info — covered by the dedicated test).
        assert extinf[0].startswith("#EXTINF:90,")
        assert extinf[1].startswith("#EXTINF:150,")
        assert extinf[2].startswith("#EXTINF:-1,")

    def test_last_track_uses_total_duration(self, monkeypatch, tmp_path):
        """Last track EXTINF = total_duration - last start."""
        _config_output_dir(monkeypatch, tmp_path)
        out = TracklistOutput(
            mix_info={
                "title": "T",
                "artist": "A",
                "date": "2026-07-31",
                "audio_filename": "mix.mp3",
                "total_duration": 300.0,
            },
            tracks=_tracks(),
        )
        lines = _read_m3u(out).splitlines()
        extinf = [ln for ln in lines if ln.startswith("#EXTINF:")]
        # last start 270s; total 300s -> 30s
        assert extinf[-1].startswith("#EXTINF:30,")

    def test_extinf_minus_one_when_no_total_duration(self, monkeypatch, tmp_path):
        """Without total_duration, last track EXTINF falls back to -1."""
        _config_output_dir(monkeypatch, tmp_path)
        out = TracklistOutput(
            mix_info={
                "title": "T",
                "artist": "A",
                "date": "2026-07-31",
                "audio_filename": "mix.mp3",
            },
            tracks=_tracks(),
        )
        lines = _read_m3u(out).splitlines()
        extinf = [ln for ln in lines if ln.startswith("#EXTINF:")]
        assert extinf[-1].startswith("#EXTINF:-1,")

    def test_artist_and_title_in_extinf(self, monkeypatch, tmp_path):
        _config_output_dir(monkeypatch, tmp_path)
        out = TracklistOutput(
            mix_info={
                "title": "T",
                "artist": "A",
                "date": "2026-07-31",
                "audio_filename": "mix.mp3",
            },
            tracks=_tracks(),
        )
        lines = _read_m3u(out).splitlines()
        extinf = [ln for ln in lines if ln.startswith("#EXTINF:")]
        assert "X - A" in extinf[0]
        assert "Y - B" in extinf[1]
