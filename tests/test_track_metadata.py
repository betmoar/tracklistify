"""Test Track.metadata field added in Phase 1.5."""

from tracklistify.core.track import Track


def test_track_has_metadata_field_default_empty():
    t = Track(song_name="x", artist="y", time_in_mix="00:00:00", confidence=1.0)
    assert t.metadata == {}


def test_track_metadata_is_per_instance():
    """default_factory must produce a fresh dict per instance, not share one."""
    t1 = Track(song_name="a", artist="b", time_in_mix="00:00:00", confidence=1.0)
    t2 = Track(song_name="c", artist="d", time_in_mix="00:00:01", confidence=1.0)
    t1.metadata["spotify_id"] = "abc"
    assert t2.metadata == {}


def test_track_metadata_writeable():
    t = Track(song_name="x", artist="y", time_in_mix="00:00:00", confidence=1.0)
    t.metadata["spotify_id"] = "abc"
    assert t.metadata["spotify_id"] == "abc"
