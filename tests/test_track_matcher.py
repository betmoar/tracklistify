import pytest

from tracklistify.config.base import TrackIdentificationConfig
from tracklistify.config.factory import ConfigFactory, get_config
from tracklistify.core.track import Track, TrackMatcher


@pytest.fixture(autouse=True)
def setup_teardown():
    """Setup and teardown for each test."""
    ConfigFactory.clear_cache()
    yield
    ConfigFactory.clear_cache()


@pytest.fixture
def config() -> TrackIdentificationConfig:
    config = get_config()
    # Set specific test values
    config.time_threshold = 30  # 30 seconds threshold for testing
    config.max_duplicates = 3
    return config


@pytest.fixture
def track_matcher(config):
    matcher = TrackMatcher()
    matcher.time_threshold = config.time_threshold
    matcher.max_duplicates = config.max_duplicates
    return matcher


def create_track(song_name, artist, time_in_mix, confidence=80.0):
    # Ensure time format is HH:MM:SS
    if len(time_in_mix) == 5:  # If format is MM:SS
        time_in_mix = f"00:{time_in_mix}"

    # Create track with required parameters
    track = Track(
        song_name=song_name.strip(),
        artist=artist.strip(),
        time_in_mix=time_in_mix,
        confidence=float(confidence),
    )
    return track


class TestTrackMatcher:
    def test_empty_tracks(self, track_matcher):
        """Test merging with no tracks."""
        assert track_matcher.merge_nearby_tracks() == []

    def test_single_track(self, track_matcher):
        """Test merging with a single track."""
        track = create_track("Test Song", "Test Artist", "00:00:00")
        track_matcher.tracks = [track]
        merged = track_matcher.merge_nearby_tracks()
        assert len(merged) == 1
        assert merged[0] == track

    def test_identical_tracks_within_threshold(self, track_matcher):
        """Test merging identical tracks within time threshold."""
        track1 = create_track("Same Song", "Same Artist", "00:00:00", confidence=80.0)
        track2 = create_track("Same Song", "Same Artist", "00:00:10", confidence=90.0)
        track_matcher.tracks = [track1, track2]

        merged = track_matcher.merge_nearby_tracks()
        assert len(merged) == 1
        # Should keep the higher confidence track
        assert merged[0] == track2

    def test_different_tracks_within_threshold(self, track_matcher):
        """Test handling different tracks within time threshold."""
        track1 = create_track("Song 1", "Artist 1", "00:00:00")
        track2 = create_track("Song 2", "Artist 2", "00:00:10")
        track_matcher.tracks = [track1, track2]

        merged = track_matcher.merge_nearby_tracks()
        assert len(merged) == 2
        assert track1 in merged
        assert track2 in merged

    def test_similar_tracks_outside_threshold(self, track_matcher):
        """Test handling similar tracks outside time threshold."""
        # Create tracks that are similar but far apart in time
        track1 = create_track("Same Song", "Same Artist", "00:00:00", confidence=80.0)
        track2 = create_track(
            "Same Song", "Same Artist", "00:05:00", confidence=90.0
        )  # Far apart
        track_matcher.tracks = [track1, track2]

        merged = track_matcher.merge_nearby_tracks()
        # Since tracks are similar, only keep the first one due to implementation
        assert len(merged) == 1
        assert merged[0].confidence == 80.0  # Keep the first track

    def test_max_duplicates_limit(self, track_matcher):
        """Test respecting max_duplicates limit."""
        # Create tracks with increasing confidence
        track1 = create_track("Same Song", "Same Artist", "00:00:00", confidence=80.0)
        track2 = create_track(
            "Same Song", "Same Artist", "00:00:02", confidence=84.0
        )  # Highest confidence
        track3 = create_track("Same Song", "Same Artist", "00:00:04", confidence=82.0)

        track_matcher.tracks = [track1, track2, track3]
        track_matcher.max_duplicates = 3

        merged = track_matcher.merge_nearby_tracks()
        assert len(merged) == 1
        # Should keep track2 which has the highest confidence (84.0)
        assert merged[0].confidence == 84.0
        assert merged[0].time_in_mix == "00:00:02"

    def test_confidence_based_selection(self, track_matcher):
        """Test selecting tracks based on confidence."""
        track1 = create_track("Same Song", "Same Artist", "00:00:00", confidence=70.0)
        track2 = create_track("Same Song", "Same Artist", "00:00:10", confidence=90.0)
        track3 = create_track("Same Song", "Same Artist", "00:00:20", confidence=80.0)
        track_matcher.tracks = [track1, track2, track3]

        merged = track_matcher.merge_nearby_tracks()
        assert len(merged) == 1
        assert merged[0] == track2  # Highest confidence track

    def test_similar_song_different_artist(self, track_matcher):
        """Test handling tracks with same song but different artists."""
        track1 = create_track("Same Song", "Artist 1", "00:00:00")
        track2 = create_track("Same Song", "Artist 2", "00:00:10")
        track_matcher.tracks = [track1, track2]

        merged = track_matcher.merge_nearby_tracks()
        assert len(merged) == 2
        assert track1 in merged
        assert track2 in merged

    def test_complex_sequence(self, track_matcher):
        """Test a complex sequence of tracks."""
        tracks = [
            # Group 1 - Similar songs within threshold
            create_track("Song 1", "Artist 1", "00:00:00", confidence=80.0),
            create_track("Song 1", "Artist 1", "00:00:10", confidence=90.0),
            # Group 2 - Different song
            create_track("Song 2", "Artist 2", "00:00:30", confidence=85.0),
            create_track("Song 2", "Artist 2", "00:00:40", confidence=75.0),
            # Group 3 - Separate track
            create_track("Song 3", "Artist 3", "00:02:00", confidence=95.0),
            # Similar to Group 1 but filtered out since it's similar to existing track
            create_track("Song 1", "Artist 1", "00:05:00", confidence=70.0),
        ]
        track_matcher.tracks = tracks

        merged = track_matcher.merge_nearby_tracks()
        assert len(merged) == 3  # Three groups after merging

        # Helper to find track by song name and confidence
        def find_track(tracks, song_name, confidence=None):
            for t in tracks:
                if t.song_name == song_name:
                    if confidence is not None and t.confidence != confidence:
                        continue
                    return True
            return False

        # Check if highest confidence tracks from each group are present
        assert find_track(merged, "Song 1", confidence=90.0)  # First group
        assert find_track(merged, "Song 2", confidence=85.0)  # Second group
        assert find_track(merged, "Song 3", confidence=95.0)  # Third group
