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
    # Inject the config so the matcher doesn't re-resolve the global singleton.
    matcher = TrackMatcher(config)
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
        """Dedup with no tracks returns an empty list."""
        assert track_matcher.get_unique_tracks() == []

    def test_single_track(self, track_matcher):
        """A single track is returned unchanged."""
        track = create_track("Test Song", "Test Artist", "00:00:00")
        track_matcher.tracks = [track]
        unique = track_matcher.get_unique_tracks()
        assert len(unique) == 1
        assert unique[0] == track

    def test_identical_tracks_within_window(self, track_matcher):
        """Identical tracks within the dedup window collapse to one,
        keeping the higher-confidence detection."""
        track1 = create_track("Same Song", "Same Artist", "00:00:00", confidence=80.0)
        track2 = create_track("Same Song", "Same Artist", "00:00:10", confidence=90.0)
        track_matcher.tracks = [track1, track2]

        unique = track_matcher.get_unique_tracks()
        assert len(unique) == 1
        # Higher confidence wins (5-pt deadband separates 80 from 90).
        assert unique[0] == track2

    def test_different_tracks_within_window(self, track_matcher):
        """Different songs within the window stay as two tracks."""
        track1 = create_track("Song 1", "Artist 1", "00:00:00")
        track2 = create_track("Song 2", "Artist 2", "00:00:10")
        track_matcher.tracks = [track1, track2]

        unique = track_matcher.get_unique_tracks()
        assert len(unique) == 2
        assert track1 in unique
        assert track2 in unique

    def test_similar_tracks_outside_window(self, track_matcher):
        """The same track replayed outside the dedup window stays as two
        tracks (a DJ playing a track twice is two plays)."""
        track1 = create_track("Same Song", "Same Artist", "00:00:00", confidence=80.0)
        track2 = create_track(
            "Same Song", "Same Artist", "00:05:00", confidence=90.0
        )  # 300s apart — outside the 100s default window
        track_matcher.tracks = [track1, track2]

        unique = track_matcher.get_unique_tracks()
        # 300s > 2*(60-10)=100s window -> separate plays.
        assert len(unique) == 2

    def test_confidence_based_selection(self, track_matcher):
        """Among clustered duplicates, the highest-confidence detection
        represents the cluster."""
        track1 = create_track("Same Song", "Same Artist", "00:00:00", confidence=70.0)
        track2 = create_track("Same Song", "Same Artist", "00:00:10", confidence=90.0)
        track3 = create_track("Same Song", "Same Artist", "00:00:20", confidence=80.0)
        track_matcher.tracks = [track1, track2, track3]

        unique = track_matcher.get_unique_tracks()
        assert len(unique) == 1
        assert unique[0] == track2  # Highest confidence track

    def test_similar_song_different_artist(self, track_matcher):
        """Same title, non-overlapping artists -> two tracks (Jaccard 0)."""
        track1 = create_track("Same Song", "Artist 1", "00:00:00")
        track2 = create_track("Same Song", "Artist 2", "00:00:10")
        track_matcher.tracks = [track1, track2]

        unique = track_matcher.get_unique_tracks()
        assert len(unique) == 2
        assert track1 in unique
        assert track2 in unique

    def test_complex_sequence(self, track_matcher):
        """Mixed sequence: clustered duplicates collapse, a far-apart replay
        of the same song stays separate."""
        tracks = [
            # Group 1 - clustered duplicates
            create_track("Song 1", "Artist 1", "00:00:00", confidence=80.0),
            create_track("Song 1", "Artist 1", "00:00:10", confidence=90.0),
            # Group 2 - different song, clustered duplicates
            create_track("Song 2", "Artist 2", "00:00:30", confidence=85.0),
            create_track("Song 2", "Artist 2", "00:00:40", confidence=75.0),
            # Group 3 - separate track
            create_track("Song 3", "Artist 3", "00:02:00", confidence=95.0),
            # Same song as Group 1, but 5 minutes apart -> separate play.
            create_track("Song 1", "Artist 1", "00:05:00", confidence=70.0),
        ]
        track_matcher.tracks = tracks

        unique = track_matcher.get_unique_tracks()
        # Four groups: Song1@0s cluster, Song2@30s cluster, Song3, Song1@5min.
        assert len(unique) == 4

        # Helper to find track by song name and confidence
        def find_track(tracks, song_name, confidence=None):
            for t in tracks:
                if t.song_name == song_name:
                    if confidence is not None and t.confidence != confidence:
                        continue
                    return True
            return False

        # Highest-confidence representative from each cluster.
        assert find_track(unique, "Song 1", confidence=90.0)  # First group
        assert find_track(unique, "Song 2", confidence=85.0)  # Second group
        assert find_track(unique, "Song 3", confidence=95.0)  # Third
        assert find_track(unique, "Song 1", confidence=70.0)  # 5min-apart replay

    def test_min_confidence_filters_low_confidence(self, track_matcher):
        """Tracks below min_confidence are dropped by add_track."""
        track_matcher.min_confidence = 75.0
        low = create_track("Low", "Artist", "00:00:00", confidence=50.0)
        high = create_track("High", "Artist", "00:00:10", confidence=90.0)
        track_matcher.add_track(low)
        track_matcher.add_track(high)
        unique = track_matcher.get_unique_tracks()
        assert len(unique) == 1
        assert unique[0] == high

    def test_artist_variant_merge_berghain(self, track_matcher):
        """Regression for the observed Shazam bug: the same track returns
        different collaboration artist strings on adjacent segments. The
        Jaccard token-set match collapses them to one track."""
        t1 = create_track(
            "Berghain (Remix)",
            "Conrad Taylor & ROSALÍA & Björk & Yves Tumor",
            "00:31:40",  # 1900s
            confidence=85.0,
        )
        t2 = create_track(
            "Berghain (Remix)",
            "ROSALÍA, Björk & Yves Tumor",
            "00:32:30",  # 1950s — exactly one 50s segmentation step apart
            confidence=88.0,
        )
        track_matcher.tracks = [t1, t2]

        unique = track_matcher.get_unique_tracks()
        assert len(unique) == 1, (
            f"Expected the two Berghain variants to merge, got {len(unique)}"
        )

    def test_accent_fold_artist_merge(self, track_matcher):
        """Diacritic variants of the same artist merge (ROSALÍA == ROSALIA)."""
        t1 = create_track("Song", "ROSALÍA", "00:00:00")
        t2 = create_track("Song", "ROSALIA", "00:00:10")
        track_matcher.tracks = [t1, t2]

        unique = track_matcher.get_unique_tracks()
        assert len(unique) == 1, "Accent-folded artist variants should merge"

    def test_representative_is_deterministic_under_confidence_noise(
        self, track_matcher
    ):
        """The 5-point confidence deadband keeps the representative stable
        when Shazam's per-run confidence jitters by a few points: near-equal
        confidence falls in one bucket and earliest-time wins deterministically."""
        base = create_track("Song", "Artist", "00:00:00", confidence=85.0)
        # Jittered neighbor: within the deadband of 85, slightly higher.
        jittered_high = create_track("Song", "Artist", "00:00:50", confidence=87.0)
        track_matcher.tracks = [base, jittered_high]

        unique = track_matcher.get_unique_tracks()
        assert len(unique) == 1
        # 85 and 87 fall in the same 5-pt bucket (int(85/5)=17, int(87/5)=17);
        # earliest time wins the tiebreak -> the 00:00:00 track represents.
        assert unique[0] == base
