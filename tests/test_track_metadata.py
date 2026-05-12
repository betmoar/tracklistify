"""Test Track.metadata field added in Phase 1.5."""

import pytest

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


def test_track_rejects_malformed_time_in_mix_shape():
    """Non HH:MM:SS strings raise at construction so callers can't smuggle
    them past ``time_to_seconds``."""
    with pytest.raises(ValueError, match="HH:MM:SS"):
        Track(song_name="x", artist="y", time_in_mix="garbage", confidence=1.0)


def test_track_rejects_semantically_invalid_time_in_mix():
    """Out-of-range MM/SS components are rejected at construction."""
    with pytest.raises(ValueError, match="out of range"):
        Track(song_name="x", artist="y", time_in_mix="99:99:99", confidence=1.0)


def test_track_time_to_seconds_is_now_infallible():
    """All constructed Tracks parse cleanly; no silent zero fallthrough."""
    t = Track(song_name="x", artist="y", time_in_mix="01:02:03", confidence=1.0)
    assert t.time_to_seconds() == 3723


def test_track_accepts_elapsed_hours_over_23():
    """time_in_mix is *elapsed* time, not wall-clock: a 25h offset must work
    for long mixes. Previously rejected by strptime("%H:%M:%S")."""
    t = Track(song_name="x", artist="y", time_in_mix="25:00:00", confidence=1.0)
    assert t.time_to_seconds() == 25 * 3600


def test_track_accepts_three_digit_hours():
    """Same rationale, longer offsets — regex must not cap HH at two digits."""
    t = Track(song_name="x", artist="y", time_in_mix="100:30:45", confidence=1.0)
    assert t.time_to_seconds() == 100 * 3600 + 30 * 60 + 45


def test_track_rejects_minutes_at_60():
    with pytest.raises(ValueError, match="minutes out of range"):
        Track(song_name="x", artist="y", time_in_mix="00:60:00", confidence=1.0)


def test_track_rejects_seconds_at_60():
    with pytest.raises(ValueError, match="seconds out of range"):
        Track(song_name="x", artist="y", time_in_mix="00:00:60", confidence=1.0)
