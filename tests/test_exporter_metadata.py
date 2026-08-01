"""JSON export of Track.metadata (PR #57 enrichment).

``Track.metadata`` existed as a dataclass field long before anything
serialized it, so provider extras were collected and then silently
dropped at the output boundary. ``_save_json`` is the exporter that
surfaces them; the md/m3u formats intentionally stay unchanged.
"""

import json

import pytest

from tracklistify.core.track import Track
from tracklistify.exporters.tracklist import TracklistOutput


@pytest.fixture
def mix_info(tmp_path, monkeypatch):
    monkeypatch.setenv("TRACKLISTIFY_OUTPUT_DIR", str(tmp_path))
    from tracklistify.config import get_config

    get_config(force_refresh=True)
    return {"title": "Test Mix", "artist": "Test DJ", "total_duration": 600}


def _load(out: TracklistOutput):
    return json.loads(out._save_json().read_text(encoding="utf-8"))


def test_metadata_is_serialized(mix_info):
    track = Track(
        song_name="Berghain",
        artist="Sara Landry",
        time_in_mix="00:01:00",
        confidence=90.0,
        metadata={"isrc": "USABC1234567", "album": "Hyperdrive"},
    )
    data = _load(TracklistOutput(mix_info, [track]))
    assert data["tracks"][0]["metadata"] == {
        "isrc": "USABC1234567",
        "album": "Hyperdrive",
    }


def test_empty_metadata_serializes_as_null_not_empty_dict(mix_info):
    """``Track.metadata`` defaults to ``{}`` (field(default_factory=dict)),
    so without the ``or None`` every track would carry a noisy empty object.
    """
    track = Track(
        song_name="Berghain",
        artist="Sara Landry",
        time_in_mix="00:01:00",
        confidence=90.0,
    )
    data = _load(TracklistOutput(mix_info, [track]))
    assert data["tracks"][0]["metadata"] is None


def test_metadata_survives_round_trip_with_unicode(mix_info):
    """ensure_ascii=False is already set; lock it for metadata values too."""
    track = Track(
        song_name="Berghain",
        artist="ROSALÍA",
        time_in_mix="00:01:00",
        confidence=90.0,
        metadata={"label": "HEKATE", "genres": ["Techno", "Hård Techno"]},
    )
    data = _load(TracklistOutput(mix_info, [track]))
    assert data["tracks"][0]["metadata"]["genres"] == ["Techno", "Hård Techno"]
