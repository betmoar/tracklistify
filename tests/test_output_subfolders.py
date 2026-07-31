"""Tests for Step 1: per-set self-contained output subfolders.

Each run produces ``output/[date] Artist - Title/`` containing all formats.
Replaces the previous flat layout. The subfolder is named from the same
date/artist/title/venue logic that produced the old filename, minus the
extension. Inside the subfolder, files use fixed names (``tracklist.{ext}``)
— the folder is the identity.
"""

from pathlib import Path


from tracklistify.config.factory import get_config
from tracklistify.core.track import Track
from tracklistify.exporters.tracklist import TracklistOutput


def _make_track(time_in_mix="00:01:00") -> Track:
    return Track(
        song_name="Test Song",
        artist="Test Artist",
        time_in_mix=time_in_mix,
        confidence=90.0,
    )


def _config_with_output_dir(monkeypatch, output_dir: Path):
    """Point config.output_dir at output_dir; refresh the singleton."""
    monkeypatch.setenv("TRACKLISTIFY_OUTPUT_DIR", str(output_dir))
    return get_config(force_refresh=True)


class TestSubfolderCreation:
    def test_subfolder_created_from_mix_info(self, monkeypatch, tmp_path):
        """Output lands inside a subfolder named [date] Artist - Title."""
        _config_with_output_dir(monkeypatch, tmp_path)
        mix_info = {
            "artist": "Dimitri Vegas",
            "title": "Tomorrowland 2026",
            "date": "2026-07-31",
        }
        out = TracklistOutput(mix_info=mix_info, tracks=[_make_track()])
        # Expected subfolder name mirrors the old filename stem.
        expected = tmp_path / "[20260731] Dimitri Vegas - Tomorrowland 2026"
        assert out.output_dir == expected
        assert out.output_dir.is_dir()

    def test_no_files_in_output_root(self, monkeypatch, tmp_path):
        """Nothing is written directly under the root output dir."""
        _config_with_output_dir(monkeypatch, tmp_path)
        mix_info = {"artist": "A", "title": "B", "date": "2026-07-31"}
        out = TracklistOutput(mix_info=mix_info, tracks=[_make_track()])
        out.save_all()
        # Root should contain only the one subfolder.
        root_entries = list(tmp_path.iterdir())
        assert len(root_entries) == 1
        assert root_entries[0].is_dir()


class TestArtistFromMixInfo:
    def test_artist_used_in_subfolder_name(self, monkeypatch, tmp_path):
        """The 'Unknown Artist' fallback must not fire when artist is supplied."""
        _config_with_output_dir(monkeypatch, tmp_path)
        mix_info = {
            "artist": "Real Artist",
            "title": "Real Title",
            "date": "2026-07-31",
        }
        out = TracklistOutput(mix_info=mix_info, tracks=[_make_track()])
        assert "Real Artist" in out.output_dir.name
        assert "Unknown Artist" not in out.output_dir.name

    def test_unknown_artist_fallback_still_works(self, monkeypatch, tmp_path):
        """When no artist and no ' - ' in title, fall back to 'Unknown Artist'."""
        _config_with_output_dir(monkeypatch, tmp_path)
        mix_info = {"title": "TitleNoSeparator", "date": "2026-07-31"}
        out = TracklistOutput(mix_info=mix_info, tracks=[_make_track()])
        assert "Unknown Artist" in out.output_dir.name


class TestFormatsLandInsideSubfolder:
    def test_all_formats_inside_subfolder(self, monkeypatch, tmp_path):
        """json/md/m3u all land inside the subfolder, not in the root."""
        _config_with_output_dir(monkeypatch, tmp_path)
        mix_info = {"artist": "A", "title": "B", "date": "2026-07-31"}
        out = TracklistOutput(mix_info=mix_info, tracks=[_make_track()])
        out.save_all()
        files = {f.name for f in out.output_dir.iterdir()}
        assert "tracklist.json" in files
        assert "tracklist.md" in files
        assert "tracklist.m3u" in files

    def test_save_single_format_inside_subfolder(self, monkeypatch, tmp_path):
        _config_with_output_dir(monkeypatch, tmp_path)
        mix_info = {"artist": "A", "title": "B", "date": "2026-07-31"}
        out = TracklistOutput(mix_info=mix_info, tracks=[_make_track()])
        path = out.save("m3u")
        assert path == out.output_dir / "tracklist.m3u"
        assert path.is_file()
