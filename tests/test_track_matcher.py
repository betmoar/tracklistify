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
    # time_threshold is a real dedup-window override (see
    # TrackMatcher._dedup_window). Leave it at 0 so these tests exercise the
    # derived default, 2 * (segment_length - overlap_duration) = 100s.
    # Setting it here would silently narrow the window for every test.
    config.time_threshold = 0
    config.segment_length = 60
    config.overlap_duration = 10
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
        """Identical tracks within the dedup window collapse to one.

        The representative is the EARLIEST detection, not the highest
        confidence: every cluster member is the same track by construction,
        and any confidence-derived choice reintroduces run-to-run
        instability (Shazam's confidence jitters per run). See _rep_key.
        """
        track1 = create_track("Same Song", "Same Artist", "00:00:00", confidence=80.0)
        track2 = create_track("Same Song", "Same Artist", "00:00:10", confidence=90.0)
        track_matcher.tracks = [track1, track2]

        unique = track_matcher.get_unique_tracks()
        assert len(unique) == 1
        assert unique[0] == track1  # earliest wins, deterministically

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

    def test_representative_selection_is_time_based_not_confidence_based(
        self, track_matcher
    ):
        """Clustered duplicates collapse to the earliest detection.

        Confidence deliberately does not influence selection — see _rep_key.
        Whichever detection Shazam scored highest varies per run; the
        earliest does not.
        """
        track1 = create_track("Same Song", "Same Artist", "00:00:00", confidence=70.0)
        track2 = create_track("Same Song", "Same Artist", "00:00:10", confidence=90.0)
        track3 = create_track("Same Song", "Same Artist", "00:00:20", confidence=80.0)
        track_matcher.tracks = [track1, track2, track3]

        unique = track_matcher.get_unique_tracks()
        assert len(unique) == 1
        assert unique[0] == track1  # earliest, regardless of confidence

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

        # Earliest detection represents each cluster (confidence is not a
        # selection input — see _rep_key).
        assert find_track(unique, "Song 1", confidence=80.0)  # first group @0s
        assert find_track(unique, "Song 2", confidence=85.0)  # second group @30s
        assert find_track(unique, "Song 3", confidence=95.0)  # third
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


def _t(name, artist, secs, conf=80.0):
    """Build a Track from an absolute second offset."""
    h, rem = divmod(secs, 3600)
    mi, s = divmod(rem, 60)
    return Track(
        song_name=name,
        artist=artist,
        time_in_mix=f"{h}:{mi:02d}:{s:02d}",
        confidence=float(conf),
    )


class TestDedupInvariants:
    """Guardrails for the implicit contracts the dedup rewrite depends on.

    Each test names the contract it locks (see docs/ARCHITECTURE.md and
    AUDIT_STATE.md). These exist because the audit found the code silently
    violating the guarantees its own docstrings advertised.
    """

    def test_c3_cluster_span_is_bounded_by_the_window(self, track_matcher):
        """C3: a cluster's total temporal span never exceeds the window.

        Regression for the chaining bug: proximity was tested against ANY
        cluster member, so each join extended the cluster's reach and a
        chain of near-neighbours could swallow an arbitrarily long stretch
        of the set — silently deleting genuinely distinct plays.
        """
        # 41 detections, each 90s from the last (inside the 100s window),
        # spanning 300s..3900s. Pairwise they chain; the span is 60 minutes.
        track_matcher.tracks = [
            _t("Epic", "Faithless", s) for s in range(300, 3901, 90)
        ]
        unique = track_matcher.get_unique_tracks()
        assert len(unique) > 1, (
            "chained detections collapsed into one cluster spanning an hour; "
            "cluster span must be bounded by the window, not chained"
        )

    def test_c3_adjacent_segment_detections_still_merge(self, track_matcher):
        """C3 (other side): bounding the span must NOT break the real fix.

        The Berghain pair is one segmentation step apart (50s < 100s window)
        and must still merge after the span bound is enforced.
        """
        track_matcher.tracks = [
            _t("Berghain (Remix)", "Conrad Taylor & ROSALÍA & Björk", 1900, 85.0),
            _t("Berghain (Remix)", "ROSALÍA, Björk", 1950, 88.0),
        ]
        assert len(track_matcher.get_unique_tracks()) == 1

    def test_c4_constructor_scales_config_min_confidence(self):
        """C4: config is 0.0-1.0, TrackMatcher is 0-100. The ctor scales."""
        cfg = get_config()
        cfg.min_confidence = 0.8
        matcher = TrackMatcher(cfg)
        assert matcher.min_confidence == 80.0, (
            "constructor must scale the 0-1 config value onto the 0-100 "
            "Track.confidence scale"
        )

    def test_c5_representative_stable_across_deadband_boundary(self, track_matcher):
        """C5: representative selection is order- and jitter-independent.

        Two detections of the same track straddling a confidence bucket
        boundary (84.9 / 85.0) must yield the same representative no matter
        which order they were added — otherwise Shazam's per-run jitter
        changes the reported time_in_mix, the exact bug _rep_key exists to
        prevent.
        """
        a = _t("Song", "Artist", 0, 84.9)
        b = _t("Song", "Artist", 50, 85.0)

        track_matcher.tracks = [a, b]
        first = track_matcher.get_unique_tracks()

        matcher2 = TrackMatcher(track_matcher._config)
        matcher2.tracks = [b, a]
        second = matcher2.get_unique_tracks()

        assert len(first) == 1 and len(second) == 1
        assert first[0].time_in_mix == second[0].time_in_mix, (
            "representative flipped when input order changed across a "
            "confidence-bucket boundary"
        )

    def test_f07_is_similar_to_agrees_with_dedup_predicate(self):
        """F07: the public predicate must not drift from the shipping rule."""
        merge_a = _t("Berghain (Remix)", "Conrad Taylor & ROSALÍA & Björk", 0)
        merge_b = _t("Berghain (Remix)", "ROSALÍA, Björk", 50)
        sep_a = _t("Same Song", "Artist 1", 0)
        sep_b = _t("Same Song", "Artist 2", 50)

        assert merge_a.is_similar_to(merge_b) is True
        assert sep_a.is_similar_to(sep_b) is False

    def test_f06_time_threshold_overrides_the_dedup_window(self, track_matcher):
        """F06: `time_threshold` is a live knob again, not dead config.

        It was assigned in __init__ and read nowhere, while .env.example and
        config/docs.py still advertised it as controlling merge behavior.
        """
        cfg = track_matcher._config
        # Default (no override): window is 2 * step = 2*(60-10) = 100s.
        cfg.time_threshold = 0
        cfg.segment_length, cfg.overlap_duration = 60, 10
        assert track_matcher._dedup_window() == 100.0

        # An override above the derived floor wins and widens the window.
        # (Values below 2*step are floored — see the clamp test below.)
        cfg.time_threshold = 400
        assert track_matcher._dedup_window() == 400.0

        track_matcher.tracks = [
            _t("Song", "Artist", 0),
            _t("Song", "Artist", 300),  # outside default 100s, inside 400s
        ]
        assert len(track_matcher.get_unique_tracks()) == 1, (
            "a widened time_threshold must actually widen the dedup window"
        )

    def test_f06_window_override_is_floored_at_one_segmentation_step(
        self, track_matcher, caplog
    ):
        """A window narrower than the step would disable dedup entirely.

        Regression: the shipped .env.example carried TIME_THRESHOLD=30.0
        while the step is 50s. When time_threshold became a live override,
        every existing .env silently switched dedup OFF — adjacent
        detections are one step (50s) apart, so a 30s window can never
        merge them. Caught only by running against a real mix (41 tracks
        emitted where 23 were correct).
        """
        import logging

        cfg = track_matcher._config
        cfg.segment_length, cfg.overlap_duration = 60, 10  # step = 50
        cfg.time_threshold = 30.0  # narrower than the step

        with caplog.at_level(logging.WARNING):
            window = track_matcher._dedup_window()

        assert window == 100.0, "override below 2*step must be floored there"
        assert any(
            "below the minimum useful dedup window" in r.getMessage()
            for r in caplog.records
        ), "clamping must warn so the user can fix their config"

        # And the practical consequence: adjacent detections still merge.
        track_matcher.tracks = [
            _t("Work On It", "ANNIE", 650),
            _t("Work On It", "ANNIE", 700),  # exactly one step later
        ]
        assert len(track_matcher.get_unique_tracks()) == 1

    def test_i2_nonpositive_step_falls_back_instead_of_disabling_dedup(
        self, track_matcher, caplog
    ):
        """A non-positive segmentation step must not yield a dead window.

        Config validation rejects overlap >= segment at construction, but
        plain attribute assignment afterwards is not re-validated (the same
        hole split_audio guards for invariant I2). Without this floor the
        window goes zero/negative and every track becomes its own cluster —
        dedup silently off, the exact failure the time_threshold clamp
        exists to prevent.
        """
        import logging

        cfg = track_matcher._config
        cfg.time_threshold = 0
        cfg.segment_length, cfg.overlap_duration = 30, 60  # step = -30

        with caplog.at_level(logging.WARNING):
            window = track_matcher._dedup_window()

        assert window > 0, "a non-positive step must not produce a dead window"
        assert any("must exceed" in r.getMessage() for r in caplog.records)

        # Dedup still functions on the fallback window.
        track_matcher.tracks = [
            _t("Song", "Artist", 0),
            _t("Song", "Artist", 50),
        ]
        assert len(track_matcher.get_unique_tracks()) == 1
