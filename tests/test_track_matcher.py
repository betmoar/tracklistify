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
    # Pin EVERY field the dedup path reads. get_config() returns a
    # process-wide singleton that other test modules mutate, so anything
    # left unpinned leaks in and silently changes clustering.
    #
    # time_threshold is a real dedup-window override (see
    # TrackMatcher._dedup_window). Leave it at 0 so these tests exercise the
    # derived default, 2 * (segment_length - overlap_duration) = 100s.
    config.time_threshold = 0
    config.segment_length = 60
    config.overlap_duration = 10
    config.min_confidence = 0.0
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

    def test_artist_jaccard_threshold_lower_bound(self, track_matcher):
        """Just BELOW 0.34 must not merge: 2 shared of 6 union = 0.333.

        Pins the threshold from underneath. Without this the constant can be
        loosened a long way (0.10 merges almost anything with one shared
        token) and every other test still passes — verified by mutation.
        """
        track_matcher.tracks = [
            create_track("Song", "Ann & Bob & Cid & Dee", "00:00:00"),
            create_track("Song", "Cid & Dee & Eve & Fay", "00:00:50"),
        ]
        assert len(track_matcher.get_unique_tracks()) == 2, (
            "Jaccard 0.333 is below the 0.34 threshold and must not merge"
        )

    def test_artist_jaccard_threshold_upper_bound(self, track_matcher):
        """Just ABOVE 0.34 must merge: 2 shared of 5 union = 0.40.

        Pins the threshold from above, so it cannot be tightened without a
        failing test. Together with the lower bound these bracket 0.34 to
        within 0.067.
        """
        track_matcher.tracks = [
            create_track("Song", "Ann & Bob & Cid", "00:00:00"),
            create_track("Song", "Ann & Bob & Dee & Eve", "00:00:50"),
        ]
        assert len(track_matcher.get_unique_tracks()) == 1, (
            "Jaccard 0.40 is above the 0.34 threshold and must merge"
        )

    def test_representative_is_deterministic_under_confidence_noise(
        self, track_matcher
    ):
        """Confidence never influences the representative — earliest wins.

        Shazam scores the same audio differently per run, so any
        confidence-derived term would flip the reported time_in_mix between
        runs. `_rep_key` excludes confidence outright; an earlier design
        quantized it into 5-point buckets to absorb the jitter, but two
        detections straddling a bucket edge still flipped. See `_rep_key`.
        """
        base = create_track("Song", "Artist", "00:00:00", confidence=85.0)
        # Jittered neighbour, scored higher — must still lose on time.
        jittered_high = create_track("Song", "Artist", "00:00:50", confidence=87.0)
        track_matcher.tracks = [base, jittered_high]

        unique = track_matcher.get_unique_tracks()
        assert len(unique) == 1
        # Earliest detection represents the cluster; 87 > 85 is irrelevant.
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
    docs/playbooks/changing-dedup.md). These exist because the audit found
    the code silently violating the guarantees its own docstrings
    advertised.
    """

    def test_c3_distinct_plays_separated_by_a_gap_stay_separate(self, track_matcher):
        """C3: a break in detection cadence splits the cluster.

        This is the discriminator between the two real cases. A DJ playing
        the same track twice leaves minutes of other tracks in between, so
        the gap far exceeds the window and the chain breaks. Contrast
        test_c3_long_track_chains_at_step_cadence: an unbroken one-step
        cadence must NOT split, however long it runs.

        Note the rule is gap-based, not span-based. Bounding the total span
        instead would split a genuinely long track (observed on a real mix:
        Hands Up ran 150s across four detections).
        """
        # Two plays: a short chain at ~5min, another at ~65min.
        first = [_t("Epic", "Faithless", s) for s in (300, 350, 400)]
        second = [_t("Epic", "Faithless", s) for s in (3900, 3950)]
        track_matcher.tracks = first + second

        unique = track_matcher.get_unique_tracks()
        assert len(unique) == 2, (
            "two plays separated by an hour of other music must not merge"
        )
        assert [t.time_in_mix for t in unique] == ["0:05:00", "1:05:00"]

    def test_c3_long_track_chains_at_step_cadence(self, track_matcher):
        """C3 (other side): an unbroken one-step cadence is ONE play.

        Real regression. ``Hands Up`` was detected at 18:20/19:10/20:00/
        20:50 — four detections, gaps of exactly one 50s segmentation step,
        total span 150s. An earlier span-bounded rule split it at the 100s
        window and emitted the track twice, while the very next track
        started at 21:40, proving it was one continuous ~3.3min play.
        """
        track_matcher.tracks = [
            _t("Hands Up", "Sara Landry & Alt8", s)
            for s in (1100, 1150, 1200, 1250)  # 18:20 .. 20:50, step 50s
        ]
        unique = track_matcher.get_unique_tracks()
        assert len(unique) == 1, (
            "a track spanning several segments at step cadence is one play, "
            "even when its span exceeds the window"
        )
        assert unique[0].time_in_mix == "0:18:20"

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

    def test_c3_collab_credit_does_not_bridge_distinct_artists(self, track_matcher):
        """C3 (identity axis): identity must not chain transitively.

        Artist Jaccard is not transitive: "Artist A" and "Artist B" share no
        tokens (0.0, correctly distinct), but a collaboration credit
        "Artist A, Artist B" matches BOTH at 0.5. If cluster membership is
        tested against *any* member, that credit bridges the two and the
        second play is deleted outright — the silent data loss the playbook
        rates as worse than the duplicate it removes. Identity is therefore
        anchored on cluster[0], exactly as proximity is anchored on
        cluster[-1].

        The credit itself is genuinely ambiguous — "Artist A" vs
        "Artist A, Artist B" is the same shape as the Berghain variant this
        dedup exists to merge, so absorbing it into the anchor's cluster is
        correct. What must never happen is the *third* row disappearing:
        "Artist B" shares no tokens with the anchor and is a distinct play.
        """
        track_matcher.tracks = [
            _t("Same Title", "Artist A", 0),
            _t("Same Title", "Artist A, Artist B", 30),
            _t("Same Title", "Artist B", 60),
        ]
        unique = track_matcher.get_unique_tracks()
        assert [t.artist for t in unique] == ["Artist A", "Artist B"], (
            "a collaboration credit must not bridge two distinct solo "
            "artists into one row"
        )

    def test_c3_collab_bridge_does_not_delete_a_later_play(self, track_matcher):
        """C3 (identity axis): the bridge must not swallow a whole play.

        Each transitive hop also refreshes cluster[-1], so the time guard
        never retires the cluster and the chain runs unbounded. Observed
        before the fix: six detections spanning two plays collapsed to a
        single row and the entire "Artist B" play vanished.
        """
        track_matcher.tracks = [
            _t("Same Title", "Artist A", 0),
            _t("Same Title", "Artist A", 50),
            _t("Same Title", "Artist A, Artist B", 100),
            _t("Same Title", "Artist B", 150),
            _t("Same Title", "Artist B", 200),
            _t("Same Title", "Artist B", 250),
        ]
        artists = [t.artist for t in track_matcher.get_unique_tracks()]
        assert "Artist B" in artists, (
            "the later solo play was deleted by transitive identity chaining"
        )

    def test_c4_constructor_scales_config_min_confidence(self):
        """C4: config is 0.0-1.0, TrackMatcher is 0-100. The ctor scales."""
        cfg = get_config()
        cfg.min_confidence = 0.8
        matcher = TrackMatcher(cfg)
        assert matcher.min_confidence == 80.0, (
            "constructor must scale the 0-1 config value onto the 0-100 "
            "Track.confidence scale"
        )

    def test_c5_representative_stable_regardless_of_confidence_order(
        self, track_matcher
    ):
        """C5: representative selection is order- and jitter-independent.

        Two detections of the same track with near-identical confidence
        (84.9 / 85.0) must yield the same representative no matter which
        order they were added — otherwise Shazam's per-run jitter changes
        the reported time_in_mix, the exact bug _rep_key exists to prevent.
        These two values are the pair that defeated an earlier bucketing
        design: they straddle a 5-point bucket edge, so bucketing sorted
        them into different buckets and the winner flipped. Selection is now
        purely time-based, which no confidence pair can perturb.
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
            "representative flipped when input order changed"
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

    # --- Title-variant stripping (spec 2026-08-02-dedup-title-variants) ---
    #
    # Pairs are exactly 50s apart so they fall inside the 100s derived window
    # — the title gate is the only thing under test. Both poles (merge and
    # separate) are mandatory for every case.

    def test_d1_feat_marker_spelling_variants_merge(self, track_matcher):
        """D5: `feat.`/`ft.`/`featuring` are spelling variants of the same
        credit marker. Canonicalizing the marker (keeping the credited name)
        collapses them. Two detections of `Track (ft. Carl Cox)` and
        `Track (feat. Carl Cox)` — same credit, same artist, 50 s apart —
        are one play.
        """
        track_matcher.tracks = [
            _t("Track (ft. Carl Cox)", "DJ Example", 500),
            _t("Track (feat. Carl Cox)", "DJ Example", 550),
        ]
        unique = track_matcher.get_unique_tracks()
        assert len(unique) == 1, (
            "feat./ft. spelling variants of the same credit must merge"
        )

    def test_d2_club_mix_merges_with_bare_title(self, track_matcher):
        """`(Club Mix)` is on the drop-list, so it merges with the bare title.
        Real backlog case at 57:30 / 58:20."""
        track_matcher.tracks = [
            _t("Outside World (Club Mix)", "DJ Example", 3450),
            _t("Outside World", "DJ Example", 3500),
        ]
        unique = track_matcher.get_unique_tracks()
        assert len(unique) == 1, (
            "a `(Club Mix)` variant and the bare title are the same recording"
        )

    def test_d3_square_brackets_live_at_drops(self, track_matcher):
        """The regex anchors on delimiters, not parens only.

        `[Live At ...]` is square-bracketed. A paren-only rewriter would leave
        it intact and the pair would stay separate. The delimiter-anchored
        regex catches both shapes; `live at ` is on the drop-prefix list.
        """
        track_matcher.tracks = [
            _t("Stereo Murder [Live At Tomorrowland]", "DJ Example", 1000),
            _t("Stereo Murder", "DJ Example", 1050),
        ]
        unique = track_matcher.get_unique_tracks()
        assert len(unique) == 1, (
            "square-bracketed `[Live At ...]` variants must also drop"
        )

    def test_d4_remix_suffix_kept_against_bare_title(self, track_matcher):
        """Must-separate pole for the keep-list.

        `(Remix)` names a different recording than the bare title, so it must
        NOT be touched. This pole does not exist elsewhere in the suite —
        every other `"Berghain (Remix)"` literal carries the suffix on both
        sides of the comparison and would merge with or without rewriting.
        """
        track_matcher.tracks = [
            _t("Berghain", "DJ Example", 2000),
            _t("Berghain (Remix)", "DJ Example", 2050),
        ]
        unique = track_matcher.get_unique_tracks()
        assert len(unique) == 2, (
            "a bare title and a `(Remix)` variant are different recordings"
        )

    def test_d5_named_remix_kept_against_club_mix(self, track_matcher):
        """Must-separate pole: the keep-list's main job.

        `(Adam Beyer Remix)` is a named remix (kept), `(Club Mix)` is on the
        drop-list (dropped). They must stay two rows — the named remix is a
        genuinely different recording from the original mix.
        """
        track_matcher.tracks = [
            _t("Outside World (Club Mix)", "DJ Example", 3000),
            _t("Outside World (Adam Beyer Remix)", "DJ Example", 3050),
        ]
        unique = track_matcher.get_unique_tracks()
        assert len(unique) == 2, "a named remix and a club mix are different recordings"

    def test_d6_rewriter_anchors_on_delimiters(self, track_matcher):
        """The drop-list is matched only inside brackets, never as a
        substring of the raw title.

        A track genuinely titled `Club Mix` (no brackets) must NOT be dropped
        to empty and merged with `Mixed` — that would require substring-
        matching the drop-list against the raw string. The regex anchors on
        delimiters, so there is no group to match and the title passes through
        unchanged.
        """
        track_matcher.tracks = [
            _t("Club Mix", "DJ Example", 4000),
            _t("Mixed", "DJ Example", 4050),
        ]
        unique = track_matcher.get_unique_tracks()
        assert len(unique) == 2, (
            "the drop-list must not substring-match raw titles with no brackets"
        )

    def test_d7_empty_rewrite_falls_back_to_original(self, track_matcher):
        """D4: if rewriting leaves only whitespace, return the original.

        Both `(Mixed)` and `(Club Mix)` would reduce to the empty string
        without this fallback, silently merging two distinct recordings
        (every detection of either would be `""`). The fallback keeps the raw
        title so the normal title comparison separates them.
        """
        track_matcher.tracks = [
            _t("(Mixed)", "DJ Example", 5000),
            _t("(Club Mix)", "DJ Example", 5050),
        ]
        unique = track_matcher.get_unique_tracks()
        assert len(unique) == 2, (
            "D4 fallback must keep distinct all-bracket titles separate"
        )

    def test_d8_different_featured_artists_separate(self, track_matcher):
        """D5 must-separate pole: the credit is kept, so distinct featured
        artists stay apart. `(ft. Snoop Dogg)` and `(feat. Pharrell)` are
        different recordings — the canonicalize-don't-drop rule's main job.
        """
        track_matcher.tracks = [
            _t("Hit (ft. Snoop Dogg)", "DJ Example", 5500),
            _t("Hit (feat. Pharrell)", "DJ Example", 5550),
        ]
        unique = track_matcher.get_unique_tracks()
        assert len(unique) == 2, (
            "different featured artists are different recordings — the credit "
            "is kept, not dropped"
        )

    def test_d9_ft_place_name_separates_from_bare_title(self, track_matcher):
        """D5: `Ft.` as a US place abbreviation (`Ft. Lauderdale`) must NOT
        collapse with a bare title. Canonicalizing (not dropping) fixes the
        over-merge that the earlier feat-drop draft shipped — the place
        qualifier is retained, so the keys differ.
        """
        track_matcher.tracks = [
            _t("Sunrise (Ft. Lauderdale Session)", "DJ Example", 6000),
            _t("Sunrise", "DJ Example", 6050),
        ]
        unique = track_matcher.get_unique_tracks()
        assert len(unique) == 2, (
            "Ft. <Place> must not over-merge with the bare title — the place "
            "qualifier is kept"
        )

    def test_d10_feat_credit_separates_from_mixed_tag(self, track_matcher):
        """Accepted trade-off (D5): a `feat. X` credit and a `(Mixed)` tag of
        the SAME audio now separate, because the credited artist is
        distinguishing. This was the original spec's must-merge case 1; it is
        revised to separate. A visible duplicate is the recoverable direction.
        """
        track_matcher.tracks = [
            _t(
                "Meet Her At The Love Parade (feat. Kiki Solvej)",
                "DJ Example",
                6500,
            ),
            _t("Meet Her At The Love Parade (Mixed)", "DJ Example", 6550),
        ]
        unique = track_matcher.get_unique_tracks()
        assert len(unique) == 2, (
            "a feat credit and a Mixed tag of the same audio now separate — "
            "the credit is distinguishing (accepted trade-off)"
        )

    def test_d11_representative_keeps_raw_song_name(self, track_matcher):
        """D3: rewriting is comparison-only. The emitted `song_name` is the
        raw provider spelling, never a canonicalized form.

        For the d1 pair the earlier detection wins by `_rep_key` (earliest
        time), and its raw `song_name` is the `(ft. ...)` form — exactly what
        Shazam returned. The displayed/output name never reflects the rewrite.
        """
        track_matcher.tracks = [
            _t("Track (ft. Carl Cox)", "DJ Example", 500),
            _t("Track (feat. Carl Cox)", "DJ Example", 550),
        ]
        unique = track_matcher.get_unique_tracks()
        assert len(unique) == 1
        assert unique[0].song_name == "Track (ft. Carl Cox)", (
            "the representative keeps its raw title (comparison-only rewrite)"
        )

    def test_d12_is_similar_to_agrees_with_tracks_match(self):
        """F07 (carried): the public predicate must not drift from the
        shipping rule. `(ft. X)` vs `(feat. X)` agree; same title + distinct
        artists disagree.
        """
        merge_a = _t("Track (ft. Carl Cox)", "DJ Example", 0)
        merge_b = _t("Track (feat. Carl Cox)", "DJ Example", 50)
        sep_a = _t("Same Song", "Artist 1", 0)
        sep_b = _t("Same Song", "Artist 2", 50)

        assert merge_a.is_similar_to(merge_b) is True
        assert sep_a.is_similar_to(sep_b) is False

    # --- Over-merge guards (max-review findings #1, #2, #4, #3) ------------
    # Each pins a silent-data-loss path the d1-d12 suite missed. Silent
    # over-merge = wrong direction for dedup; these must stay 2 rows.

    def test_d13_bare_name_bracket_distinct_from_feat_credit(self, track_matcher):
        """D5 over-merge guard: a bare parenthetical name `(Carl Cox)` is NOT
        the same as a feat credit `(feat. Carl Cox)`. Canonicalizing keeps the
        `feat` marker word, so the keys differ. The earlier draft deleted the
        marker and the two collided — a silent over-merge.
        """
        track_matcher.tracks = [
            _t("Song (Carl Cox)", "DJ Example", 7000),
            _t("Song (feat. Carl Cox)", "DJ Example", 7050),
        ]
        assert len(track_matcher.get_unique_tracks()) == 2, (
            "a bare-name bracket and a feat-credit of the same name are "
            "distinct (the feat marker word is kept)"
        )

    def test_d14_leading_bracket_not_treated_as_suffix(self, track_matcher):
        """D6 over-merge guard: a LEADING bracket `(Original) Sin` is not the
        version-credit placement the drop rules are built for, so it is kept
        verbatim and does not collapse with a bare `Sin`. Without the
        trailing-suffix position anchor both would drop to `sin`.
        """
        track_matcher.tracks = [
            _t("(Original) Sin", "DJ Example", 7500),
            _t("Sin", "DJ Example", 7550),
        ]
        assert len(track_matcher.get_unique_tracks()) == 2, (
            "a leading bracket is not a suffix and must not collapse with "
            "the bare title"
        )

    def test_d15_nested_same_type_brackets_do_not_defeat_d4(self, track_matcher):
        """D4 over-merge guard: `((Club Mix))` (nested same-type) must not
        match the inner span and leave a malformed dangling `()` that
        collapses to empty. The trailing regex's `[^()]*` cannot cross a
        nested paren, so the group falls through to keep — distinct tags stay
        distinct instead of both reducing to empty.
        """
        track_matcher.tracks = [
            _t("Anthem ((Club Mix))", "DJ Example", 8000),
            _t("Anthem ((Mixed))", "DJ Example", 8050),
        ]
        assert len(track_matcher.get_unique_tracks()) == 2, (
            "nested same-type brackets must not defeat the D4 empty-collapse "
            "guard and silently merge distinct version tags"
        )

    def test_d16_keep_markers_use_word_boundaries(self, track_matcher):
        """Under-merge guard: a credited name CONTAINING a keep-marker
        substring (`Vipul` contains `vip`) must not be shadowed into
        keep-verbatim, which would split spelling variants of the same credit.
        Word-boundary matching lets the feat-canonicalize rule still fire.
        """
        track_matcher.tracks = [
            _t("Track (ft. Vipul)", "DJ Example", 8500),
            _t("Track (feat. Vipul)", "DJ Example", 8550),
        ]
        assert len(track_matcher.get_unique_tracks()) == 1, (
            "a name containing a keep-marker substring (Vipul ~ vip) must "
            "still canonicalize across feat/ft spelling variants"
        )

    # --- Coverage gaps surfaced by the PR-review test-analyzer --------------

    def test_d17_keep_list_beats_drop_list(self, track_matcher):
        """Keep-list precedence: `(Extended Remix)` carries a keep-marker
        (`remix`) AND a drop-exact token (`extended`). The keep-list is
        checked first, so the group stays — a bare title and the remix stay
        two rows. Without this, a future widening of `_SUFFIX_DROP_EXACT`
        would silently swallow any named remix containing a drop token.
        """
        track_matcher.tracks = [
            _t("Foo (Extended Remix)", "DJ Example", 9000),
            _t("Foo", "DJ Example", 9050),
        ]
        assert len(track_matcher.get_unique_tracks()) == 2, (
            "a keep-marker (remix) must survive even when the group also "
            "contains a drop-exact token (extended)"
        )

    def test_d18_featuring_spelling_canonicalizes_on_title_side(self, track_matcher):
        """The third feat-marker spelling — `(Featuring X)` — must collapse
        with `(feat. X)`. Every prior test pair used only ft./feat.; this
        pins the `featuring` arm of `_FEAT_MARKER_RE` so it can't be silently
        dropped from the alternation.
        """
        track_matcher.tracks = [
            _t("Track (Featuring Carl Cox)", "DJ Example", 9500),
            _t("Track (feat. Carl Cox)", "DJ Example", 9550),
        ]
        assert len(track_matcher.get_unique_tracks()) == 1, (
            "(Featuring X) must canonicalize to the same key as (feat. X)"
        )

    def test_d19_multi_group_peel_merges_with_bare(self, track_matcher):
        """The peel loop processes two trailing groups of different delimiter
        types in one call: `Outside World (Club Mix) [Radio Edit]` peels BOTH
        version tags, leaving the bare title, which merges with a bare
        detection. Pins the multi-group cascade + the drop-then-drop
        termination. (A feat+version composition does NOT merge with the bare
        title — the feat credit is kept by D5; that pole is d19b.)
        """
        track_matcher.tracks = [
            _t("Outside World (Club Mix) [Radio Edit]", "DJ Example", 10000),
            _t("Outside World", "DJ Example", 10050),
        ]
        assert len(track_matcher.get_unique_tracks()) == 1, (
            "two trailing version tags must both peel and merge with the bare title"
        )

    def test_d19b_multi_group_distinct_credits_separate(self, track_matcher):
        """Other pole of the multi-group peel: the feat credit is kept, so
        two compositions with different featured artists stay two rows even
        when their version tag matches.
        """
        track_matcher.tracks = [
            _t("Song Title (feat. Snoop Dogg) [Extended Mix]", "DJ Example", 10500),
            _t("Song Title (feat. Pharrell) [Extended Mix]", "DJ Example", 10550),
        ]
        assert len(track_matcher.get_unique_tracks()) == 2, (
            "different featured artists stay separate even with matching version tags"
        )

    def test_d20_empty_credit_canonicalizes_across_spellings(self, track_matcher):
        """A feat marker with no credited name (`(feat.)`, `(ft.)`) is
        canonicalized to `(feat)` so the spellings merge — not dropped to
        empty (which would merge with the bare title). Pins the
        `else 'feat'` arm of the rewrite path.
        """
        track_matcher.tracks = [
            _t("(feat.)", "DJ Example", 11000),
            _t("(ft.)", "DJ Example", 11050),
        ]
        assert len(track_matcher.get_unique_tracks()) == 1, (
            "empty-credit feat markers (feat.)/(ft.) must canonicalize and merge"
        )

    def test_d21_cross_type_nested_brackets_do_not_defeat_d4(self, track_matcher):
        """D4 over-merge guard (cross-type nesting). d15 pins same-type
        `((..))`; this pins the cross-type case `([..])` / `[(..)]`. The
        trailing regex's inner classes exclude BOTH bracket types, so a
        nested group of any kind falls through to keep — distinct tags stay
        distinct instead of the inner brackets normalizing to spaces and
        collapsing to the drop-list.
        """
        track_matcher.tracks = [
            _t("Anthem ([Club Mix])", "DJ Example", 11500),
            _t("Anthem ([Mixed])", "DJ Example", 11550),
        ]
        assert len(track_matcher.get_unique_tracks()) == 2, (
            "cross-type nested brackets ([..]) must not defeat the D4 guard "
            "and silently merge distinct version tags"
        )


def test_identified_track_is_logged_at_info(track_matcher, caplog):
    """The per-track success line must stay at INFO.

    This is the only per-track success signal an operator sees during a
    run. It regressed to debug once (the dedup rewrite), which left the
    default log showing provider *failures* only — a healthy run scrolled
    past 45 "No track information found" lines with nothing to balance
    them, reading as if nothing had matched at all.
    """
    import logging

    track = create_track("Bassline Kick", "Revoxx", "00:04:10", confidence=99.9)
    with caplog.at_level(logging.INFO, logger="tracklistify.core.track"):
        track_matcher.add_track(track)

    info = [r for r in caplog.records if r.levelno == logging.INFO]
    assert info, "an identified track must be visible at INFO"
    msg = info[0].getMessage()
    assert "Bassline Kick" in msg and "Revoxx" in msg
    assert "00:04:10" in msg, "the timestamp is what makes the line actionable"


def test_low_confidence_skip_stays_below_info(track_matcher, caplog):
    """Gated tracks are not events the operator needs at default verbosity."""
    import logging

    track_matcher.min_confidence = 75.0
    low = create_track("Noise", "Nobody", "00:00:10", confidence=10.0)
    with caplog.at_level(logging.DEBUG, logger="tracklistify.core.track"):
        track_matcher.add_track(low)

    assert not [r for r in caplog.records if r.levelno >= logging.INFO]
    assert any(r.levelno == logging.DEBUG for r in caplog.records)


class TestExtractMixInfo:
    """Unit tests for _extract_mix_info — the U15 remixer-name gate helper."""

    def test_extract_mix_info_named_remixer(self):
        from tracklistify.core.track import _extract_mix_info

        result = _extract_mix_info("Track Name (Artist X Remix)")
        # _normalize_token lowercases and accent-folds; the extracted name
        # is the normalized form after the remix keyword is stripped.
        assert result["remixers"] == ["artist x"]
        assert result["mix_type"] is None

    def test_extract_mix_info_generic_mix(self):
        from tracklistify.core.track import _extract_mix_info

        result = _extract_mix_info("Track Name (Club Mix)")
        assert result["remixers"] == []
        assert result["mix_type"] == "club mix"

    def test_extract_mix_info_no_brackets(self):
        from tracklistify.core.track import _extract_mix_info

        result = _extract_mix_info("Track Name")
        assert result["remixers"] == []
        assert result["mix_type"] is None

    def test_extract_mix_info_multiple_remixers(self):
        from tracklistify.core.track import _extract_mix_info

        # "Artist X & Y" → _normalize_token → "artist x y" (punctuation→space)
        result = _extract_mix_info("Track Name (Artist X & Y Remix)")
        assert result["remixers"] == ["artist x y"]
        assert result["mix_type"] is None

    def test_extract_mix_info_remix_and_mix_type(self):
        from tracklistify.core.track import _extract_mix_info

        result = _extract_mix_info("Track Name (Artist X Remix) (Club Mix)")
        assert result["remixers"] == ["artist x"]
        assert result["mix_type"] == "club mix"

    def test_extract_mix_info_bootleg(self):
        from tracklistify.core.track import _extract_mix_info

        result = _extract_mix_info("Track Name (DJ Someone Bootleg)")
        assert result["remixers"] == ["dj someone"]
        assert result["mix_type"] is None

    def test_extract_mix_info_edit_by(self):
        from tracklistify.core.track import _extract_mix_info

        result = _extract_mix_info("Track Name (Edit By Producer)")
        assert result["remixers"] == ["producer"]
        assert result["mix_type"] is None

    def test_extract_mix_info_vip(self):
        from tracklistify.core.track import _extract_mix_info

        result = _extract_mix_info("Track Name (VIP)")
        # "VIP" alone is a keep-marker with no name after it — the kernel
        # word IS the identifier. Keep the whole thing as a remixer name.
        # After stripping the keyword "vip", nothing remains → treat it as
        # a generic mix type (it's a version label, not a remixer).
        assert result["remixers"] == []
        assert result["mix_type"] is None

    def test_extract_mix_info_original_mix_ignored(self):
        from tracklistify.core.track import _extract_mix_info

        result = _extract_mix_info("Track Name (Original Mix)")
        assert result["remixers"] == []
        assert result["mix_type"] == "original mix"

    def test_extract_mix_info_extended_mix(self):
        from tracklistify.core.track import _extract_mix_info

        result = _extract_mix_info("Track Name (Extended Mix)")
        assert result["remixers"] == []
        assert result["mix_type"] == "extended mix"

    def test_extract_mix_info_radio_edit(self):
        from tracklistify.core.track import _extract_mix_info

        result = _extract_mix_info("Track Name (Radio Edit)")
        assert result["remixers"] == []
        assert result["mix_type"] == "radio edit"

    def test_extract_mix_info_live_at_ignored(self):
        from tracklistify.core.track import _extract_mix_info

        result = _extract_mix_info("Track Name (Live at Tomorrowland)")
        assert result["remixers"] == []
        assert result["mix_type"] is None

    def test_extract_mix_info_feat_ignored(self):
        from tracklistify.core.track import _extract_mix_info

        # feat groups are canonicalized by _decide_title_group, not mix info.
        result = _extract_mix_info("Track Name (feat. Vocalist)")
        assert result["remixers"] == []
        assert result["mix_type"] is None

    def test_extract_mix_info_square_brackets(self):
        from tracklistify.core.track import _extract_mix_info

        result = _extract_mix_info("Track Name [DJ X Remix]")
        # _normalize_token("DJ X Remix") → "dj x remix", strip "remix" → "dj x"
        assert result["remixers"] == ["dj x"]
        assert result["mix_type"] is None

    def test_extract_mix_info_remix_keyword_only(self):
        from tracklistify.core.track import _extract_mix_info

        # "(Remix)" — a remix keyword with no name after it.
        result = _extract_mix_info("Track Name (Remix)")
        assert result["remixers"] == []
        assert result["mix_type"] is None


class TestRemixerMatching:
    """Unit tests for _any_remixer_in and _mix_type_matches (U15 gate helpers)."""

    def test_any_remixer_in_exact_match(self):
        from tracklistify.core.track import _any_remixer_in

        assert _any_remixer_in(["Artist X"], ["Artist X"], None) is True

    def test_any_remixer_in_case_insensitive(self):
        from tracklistify.core.track import _any_remixer_in

        assert _any_remixer_in(["artist x"], ["Artist X"], None) is True

    def test_any_remixer_in_mismatch(self):
        from tracklistify.core.track import _any_remixer_in

        assert _any_remixer_in(["Artist X"], ["Artist Y"], None) is False

    def test_any_remixer_in_substring_match(self):
        from tracklistify.core.track import _any_remixer_in

        # "John" is a substring of "Johnson" — the word-boundary check
        # must reject this.
        assert _any_remixer_in(["John"], ["Johnson"], None) is False

    def test_any_remixer_in_word_boundary_match(self):
        from tracklistify.core.track import _any_remixer_in

        # "John" should match "John Doe" (word boundary after John).
        assert _any_remixer_in(["John"], ["John Doe"], None) is True

    def test_any_remixer_in_mix_name_fallback(self):
        from tracklistify.core.track import _any_remixer_in

        # Remixer embedded in mix_name string rather than remixers list.
        assert _any_remixer_in(["Artist X"], None, "Artist X Remix") is True

    def test_any_remixer_in_no_remixers_no_mix_name(self):
        from tracklistify.core.track import _any_remixer_in

        assert _any_remixer_in(["Artist X"], None, None) is False

    def test_any_remixer_in_empty_lists(self):
        from tracklistify.core.track import _any_remixer_in

        assert _any_remixer_in([], [], None) is False

    def test_mix_type_matches_exact(self):
        from tracklistify.core.track import _mix_type_matches

        assert _mix_type_matches("Club Mix", "Club Mix") is True

    def test_mix_type_matches_case_insensitive(self):
        from tracklistify.core.track import _mix_type_matches

        assert _mix_type_matches("club mix", "Club Mix") is True

    def test_mix_type_matches_mismatch(self):
        from tracklistify.core.track import _mix_type_matches

        assert _mix_type_matches("Club Mix", "Extended Mix") is False

    def test_mix_type_matches_bp_none(self):
        from tracklistify.core.track import _mix_type_matches

        assert _mix_type_matches("Club Mix", None) is False


class TestEnrichmentTitleMatchHybrid:
    """Integration tests for the hybrid U15 gate in _enrichment_title_match."""

    def test_strict_equality_still_fast_path(self):
        from tracklistify.core.track import _enrichment_title_match

        # Titles that match via _comparison_title → True, no remixer needed.
        assert _enrichment_title_match("Track Name", "Track Name") is True

    def test_remixer_name_match_passes(self):
        from tracklistify.core.track import _enrichment_title_match

        # Shazam "Track (Artist X Remix)" + Beatport remixers=["Artist X"]
        assert (
            _enrichment_title_match(
                "Track Name (Artist X Remix)",
                "Track Name",
                remixers=["Artist X"],
            )
            is True
        )

    def test_remixer_name_mismatch_fails(self):
        from tracklistify.core.track import _enrichment_title_match

        # Shazam "Track (Artist X Remix)" + Beatport remixers=["Artist Y"]
        assert (
            _enrichment_title_match(
                "Track Name (Artist X Remix)",
                "Track Name",
                remixers=["Artist Y"],
            )
            is False
        )

    def test_remixer_in_mix_name_passes(self):
        from tracklistify.core.track import _enrichment_title_match

        # Remixer embedded in mix_name rather than remixers list.
        assert (
            _enrichment_title_match(
                "Track Name (Artist X Remix)",
                "Track Name",
                mix_name="Artist X Remix",
            )
            is True
        )

    def test_generic_mix_type_match_passes(self):
        from tracklistify.core.track import _enrichment_title_match

        assert (
            _enrichment_title_match(
                "Track Name (Club Mix)",
                "Track Name (Club Mix)",
                mix_name="Club Mix",
            )
            is True
        )

    def test_generic_mix_type_mismatch_fails(self):
        from tracklistify.core.track import _enrichment_title_match

        assert (
            _enrichment_title_match(
                "Track Name (Club Mix)",
                "Track Name (Extended Mix)",
                mix_name="Extended Mix",
            )
            is False
        )

    def test_no_mix_info_falls_back_to_stem(self):
        from tracklistify.core.track import _enrichment_title_match

        # Shazam "Track" (no brackets) + Beatport "Track (Original Mix)"
        # → stem match: both strip to "track".
        assert (
            _enrichment_title_match(
                "Track Name",
                "Track Name (Original Mix)",
            )
            is True
        )

    def test_stem_fallback_still_works_for_non_beatport_callers(self):
        from tracklistify.core.track import _enrichment_title_match

        # No remixers/mix_name kwargs → stem fallback (Spotify path).
        assert (
            _enrichment_title_match(
                "Track Name (Tritonia 404)",
                "Track Name (Original Mix)",
            )
            is True
        )

    def test_remixer_gate_blocks_wrong_remix_with_same_stem(self):
        from tracklistify.core.track import _enrichment_title_match

        # Both stem to "track name" — the remixer gate must catch this.
        assert (
            _enrichment_title_match(
                "Track Name (Artist X Remix)",
                "Track Name (Artist Y Remix)",
                remixers=["Artist Y"],
            )
            is False
        )
