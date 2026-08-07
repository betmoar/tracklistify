"""Test Track.metadata field added in Phase 1.5."""

import pytest

from tracklistify.core.track import Track
from tracklistify.core.types import TrackLinks, TrackMetadata


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


# ---------------------------------------------------------------------------
# Q2 — Track.metadata schema lock (2026-08 code-quality review)
# ---------------------------------------------------------------------------


def test_track_metadata_schema_names_every_written_key():
    """Every metadata key a writer can put on a Track must be declared in
    the TrackMetadata TypedDict (flat keys) or TrackLinks (nested links).

    Before Q2, ``Track.metadata`` was ``Dict[str, Any]`` — a typo in a
    writer (``spotify_isrc`` vs ``spotify_id``) was invisible until someone
    read the JSON. This test pins the closed set of keys the writers use
    against the schema, so adding a new key without declaring it fails here,
    and a typo'd key (one not in the schema) is caught by mypy at the write
    site (the CI ratchet). The key set is enumerated from the actual writers
    (_extra_metadata + the three enrichment passes); update it WITH the
    schema when a new field is added.
    """
    declared_flat = set(TrackMetadata.__annotations__)
    declared_links = set(TrackLinks.__annotations__)

    # Flat keys written across _extra_metadata + spotify/musicbrainz/beatport
    # enrichment passes (grep track.metadata and the result["..."] loops).
    written_flat = {
        "isrc",
        "album",
        "label",
        "release_date",
        "genres",
        "shazam_id",
        "apple_music_id",
        "artwork_url",
        "spotify_id",
        "spotify_match",
        "beatport_id",
        "bpm",
        "key",
        "genre",
        "sub_genre",
        "remixers",
        "catalog_number",
        "beatport_match",
    }
    # Nested link keys written under metadata['links'].
    written_links = {
        "shazam",
        "spotify",
        "spotify_search",
        "deezer",
        "deezer_search",
        "tidal",
        "apple",
        "beatport",
    }

    undeclared_flat = written_flat - declared_flat
    assert not undeclared_flat, (
        f"metadata flat keys written by code but missing from TrackMetadata "
        f"schema: {sorted(undeclared_flat)} — declare them or fix the typo"
    )
    undeclared_links = written_links - declared_links
    assert not undeclared_links, (
        f"link keys written by code but missing from TrackLinks schema: "
        f"{sorted(undeclared_links)} — declare them or fix the typo"
    )


def test_typed_dict_key_typo_is_not_a_valid_write():
    """A misspelled key must NOT silently land on the dict as a new field.

    TrackMetadata is total=False, so all declared keys are optional — but a
    key NOT in the schema should not pass silently. This asserts the schema
    is closed over the declared annotations: a known-typo'd name is absent
    from the annotation set, which is exactly what mypy flags at write sites
    (the CI ratchet enforces it). This is the runtime mirror of that check.
    """
    declared = set(TrackMetadata.__annotations__)
    typo = "spotify_isrc"  # plausible typo of spotify_id / isrc
    assert typo not in declared, (
        f"{typo!r} is not a declared TrackMetadata key; the schema must not "
        "accept it (mypy flags such writes via the CI ratchet)"
    )
    # Sanity: the correctly-spelled sibling IS declared.
    assert "spotify_id" in declared and "isrc" in declared


def test_track_metadata_field_is_typed_as_schema():
    """Track.metadata must carry the TrackMetadata TypedDict annotation, not
    the old Dict[str, Any] — that's what makes the write-site checks live.
    """
    import dataclasses

    fields = {f.name: f for f in dataclasses.fields(Track)}
    # The annotation is stored as a string forward-ref or the type object;
    # normalize to its __name__ for a stable assertion.
    ann = fields["metadata"].type
    name = ann if isinstance(ann, str) else getattr(ann, "__name__", str(ann))
    assert name == "TrackMetadata", (
        f"Track.metadata must be annotated as TrackMetadata (was {name!r}); "
        "Dict[str, Any] disables write-site typo checking"
    )
