"""
Track identification and management module.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Optional, Set, Tuple

from tracklistify.config import TrackIdentificationConfig
from tracklistify.utils.logger import get_logger


logger = get_logger(__name__)


# Allow ``HH+`` (one or more digits) so elapsed offsets like ``25:00:00`` or
# ``100:30:00`` from long mixes are accepted. ``MM`` and ``SS`` must still be
# exactly two digits — the field is an *elapsed* time, not a wall-clock time,
# so ``datetime.strptime("%H:%M:%S")`` (which caps hours at 23) can't be used.
_TIME_IN_MIX_RE = re.compile(r"^(\d+):(\d{2}):(\d{2})$")


# --- Track-comparison helpers (single dedup authority) ---------------------
#
# Two tracks are "the same" iff their titles match exactly after normalization
# AND their artist token-sets overlap sufficiently (Jaccard >= _ARTIST_THRESHOLD).
# This collapses Shazam's run-to-run artist-string noise for collaborations:
#   "Conrad Taylor & ROSALÍA & Björk & Yves Tumor"  vs
#   "ROSALÍA, Björk & Yves Tumor"
# tokenize to {conrad taylor, rosalia, bjork, yves tumor} vs
# {rosalia, bjork, yves tumor} -> Jaccard 3/4 = 0.75 (>= threshold -> merge),
# while "Artist 1" vs "Artist 2" -> 0.0 (no overlap -> separate).
#
# Empirically (see docs/BACKLOG.md P2): all merge cases score >= 0.50, all
# separate cases score 0.00; 0.34 sits centered in the gap.

_ARTIST_THRESHOLD = 0.34

# Used only when the segmentation step is non-positive (a config that
# validation should have rejected, but attribute assignment can produce
# after the fact). Equals the default 2 * (60 - 10) so behavior matches a
# stock config rather than silently disabling dedup.
_FALLBACK_DEDUP_WINDOW = 100.0

# Split on collaboration separators BEFORE normalization (so they survive to
# drive the split). Word-boundary alternations (\band\b, \bfeat\b, ...) ensure
# "Commander" is not split on its interior "and".
_ARTIST_SEP = re.compile(
    r"\s*(?:&|,|/|\\|\band\b|\bfeat\.?\b|\bft\.?\b|\bvs\.?\b|\bx\b|\+|\||;)\s*",
    re.IGNORECASE,
)


def _normalize_token(s: str) -> str:
    """Normalize a string for track comparison.

    lowercase -> NFKC -> NFD strip combining marks (accent fold, so
    "ROSALÍA" == "ROSALIA") -> punctuation-to-space -> collapse whitespace.
    """
    s = unicodedata.normalize("NFKC", s.lower())
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# --- Title-variant canonicalization (spec 2026-08-02-dedup-title-variants) --
#
# Two detections of the same recording often arrive with bracketed suffixes
# that carry no identifying information — `(Mixed)`, `(Club Mix)`,
# `[Live At ...]` — so the normalized titles differ and dedup emits two rows
# for one play. This helper rewrites those groups BEFORE normalization, for the
# title comparison only.
#
# D1: rewrite on the RAW title before normalizing. `_normalize_token` maps
# punctuation to spaces, so after it runs there are no delimiters left to
# anchor on — a post-normalize rewriter would have to substring-match, which
# eats a track genuinely titled `Club Mix`. The regex anchors on `(...)`
# and `[...]` on the raw string.
#
# D2: default is KEEP. Only allowlisted suffixes are dropped; anything
# unrecognized is retained verbatim. An incomplete allowlist yields a *visible
# duplicate*, never a silent deletion.
#
# D3: comparison only. The displayed `song_name` stays raw — `_rep_key`
# and every output path read `track.song_name` directly, untouched.
#
# D4: if rewriting leaves only whitespace, return the ORIGINAL title so two
# distinct all-bracket titles (`(Mixed)` vs `(Club Mix)`) don't both collapse
# to empty and merge.
#
# D5: feat/ft/featuring credits are CANONICALIZED to `feat`, not dropped.
# The credited artist identifies a specific recording, so the marker word AND
# the name are kept: `(ft. Carl Cox)` -> `(feat carl cox)`, which is DISTINCT
# from a bare `(Carl Cox)` -> `(carl cox)`. Two earlier drafts are rejected:
# dropping the WHOLE GROUP merges different featured artists (`(feat. Snoop
# Dogg)` == `(feat. Pharrell)`, both -> bare title) AND swallows `Ft. <Place>`
# US abbreviations; deleting only the MARKER WORD but keeping the name collides
# the feat-credit namespace with the bare-name bracket (`Song (Carl Cox)` ==
# `Song (feat. Carl Cox)`, both -> `(carl cox)`). Keeping both marker and name
# avoids both.
#
# D6: only TRAILING-SUFFIX groups are rewritten. A bracket that is not the last
# non-space content of the title (e.g. a leading `(Original) Sin`) is kept
# verbatim — leading/middle brackets are not the version-credit placement the
# drop/canonicalize rules are built for, and rewriting them silently merges
# `(Original) Sin` with `Sin`.
#
# The keep-list is checked with WORD BOUNDARIES and FIRST, so a credited name
# containing a marker substring (`Vipul`, `Vipingo`) is not shadowed, and
# widening the drop-lists later can never quietly swallow a named remix.

# A trailing-suffix group: a `(...)` or `[...]` that ends the title (optional
# trailing whitespace). Each inner class excludes BOTH bracket types
# (`[^()\[\]]*`), so a NESTED group of ANY kind — same-type `((Club Mix))` or
# cross-type `([Club Mix])` / `[(Club Mix)]` — does NOT match here and falls
# through to keep (the safe default). Otherwise the cross-type case would
# match the outer span and `_normalize_token` would collapse the inner
# brackets to spaces, dropping a `([Club Mix])` to `club mix` and silently
# merging distinct tags (defeating the D4 empty-collapse guard).
_TRAILING_GROUP_RE = re.compile(r"(\(([^()\[\]]*)\)|\[([^()\[\]]*)\])\s*$")

# Keep-markers as whole words only (so "Vipul" does not match "vip").
_SUFFIX_KEEP_RE = re.compile(r"\b(?:remix|bootleg|edit by|vip)\b")

_SUFFIX_DROP_EXACT = frozenset(
    {
        "mixed",
        "club mix",
        "extended mix",
        "original mix",
        "radio edit",
        "radio mix",
        "extended",
        "original",
    }
)

_SUFFIX_DROP_PREFIXES = ("live at ",)

# A feat-credit marker at the start of a (normalized, lowercased) bracket
# group. Covers feat/ft/featuring and every casing variant.
_FEAT_MARKER_RE = re.compile(r"^(feat|ft|featuring)\b\s*")

# Cap on trailing-group peels per title. `drop` loops (there may be another
# suffix to peel); `keep` and `rewrite` break (a kept/rewritten group is
# retained in place, so nothing before it is a trailing suffix). Real titles
# peel <=2-3 groups; the cap is a backstop against pathological input.
_MAX_GROUP_PEELS = 8


def _decide_title_group(inner_raw: str) -> object:
    """Decide one trailing group's fate from its RAW inner text.

    Returns one of:
      ``("keep",)``       — keep the group verbatim (distinguishing / empty / nested)
      ``("drop",)``       — remove the group entirely (non-distinguishing)
      ``("rewrite", s)``  — replace the group's inner with ``s`` (canonicalized feat)
    """
    inner = _normalize_token(inner_raw)
    if not inner:
        return ("keep",)  # empty group is harmless noise; keep verbatim
    if _SUFFIX_KEEP_RE.search(inner):
        return ("keep",)  # title-distinguishing marker present
    # Canonicalize the feat-marker to `feat`, KEEPING marker word + credit (D5).
    if _FEAT_MARKER_RE.match(inner):
        credit = _FEAT_MARKER_RE.sub("", inner).strip()
        return ("rewrite", f"feat {credit}".strip() if credit else "feat")
    if inner in _SUFFIX_DROP_EXACT or inner.startswith(_SUFFIX_DROP_PREFIXES):
        return ("drop",)  # non-distinguishing version/live tag
    return ("keep",)  # unrecognized: keep verbatim (default is keep)


def _strip_title_variant(title: str) -> str:
    """Rewrite trailing bracketed suffixes into a canonical comparison form.

    Peels trailing `(...)` / `[...]` groups from the end of the title (D6:
    leading/middle brackets are left untouched) and applies the rule set to
    each: keep verbatim if it carries a keep-marker; canonicalize a
    `feat`/`ft`/`featuring` marker to `feat` while keeping the credit (D5);
    drop non-distinguishing version/live tags; otherwise keep. Stops at the
    first group that is kept. D4: a result that is only whitespace falls back
    to the original title.
    """
    result = title
    for _ in range(_MAX_GROUP_PEELS):
        match = _TRAILING_GROUP_RE.search(result)
        if not match:
            break
        group, g1, g2 = match.group(1), match.group(2), match.group(3)
        inner_raw = g1 if g1 is not None else g2
        action = _decide_title_group(inner_raw)
        if action[0] == "keep":
            break  # this trailing group stays; nothing before it is a suffix
        if action[0] == "drop":
            result = (result[: match.start()] + " " + result[match.end() :]).strip()
        else:  # rewrite — preserve the group's delimiter type
            new_inner = action[1]
            open_d, close_d = group[0], group[-1]
            result = (
                result[: match.start()].rstrip()
                + f" {open_d}{new_inner}{close_d}"
                + result[match.end() :]
            ).strip()
            break  # rewritten group is retained in place (like keep); nothing
            # before it is a trailing suffix, so peeling stops here
    return result if result.strip() else title


def _artist_tokens(artist: str) -> Set[str]:
    """Tokenize an artist string into a normalized token set."""
    return {
        _normalize_token(part)
        for part in _ARTIST_SEP.split(artist.strip())
        if part.strip()
    }


def _artists_match(a: str, b: str) -> bool:
    """True iff the artist token sets overlap with Jaccard >= threshold."""
    tokens_a = _artist_tokens(a)
    tokens_b = _artist_tokens(b)
    if not tokens_a or not tokens_b:
        return False
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b) >= _ARTIST_THRESHOLD


@lru_cache(maxsize=2048)
def _comparison_title(title: str) -> str:
    """The canonical comparison key for a raw title.

    ``_normalize_token(_strip_title_variant(...))`` folded into one memoized
    callable. ``get_unique_tracks`` compares each candidate against the
    cluster anchor's title, and the anchor's key is invariant across every
    comparison against that cluster — so caching it on the raw title removes
    the redundant strip+normalize pipeline (measured ~5996 calls collapsing
    to ~2 distinct results at n=2000). Bounded so a pathological title stream
    cannot grow it without limit.
    """
    return _normalize_token(_strip_title_variant(title))


def _tracks_match(t1: "Track", t2: "Track") -> bool:
    """Identity match: same normalized title AND overlapping artists.

    Titles are compared after rewriting trailing bracketed suffixes via
    ``_strip_title_variant`` — see the spec — so two detections of the same
    recording under different Shazam spellings collapse (a `feat.`/`ft.`
    credit is canonicalized, a `(Mixed)`/`(Club Mix)` tag is dropped).
    ``_rep_key`` and the output paths still read the raw ``song_name``; the
    rewrite is comparison-only (D3).

    Title-match + artist-mismatch = different tracks (a DJ playing the same
    song by different artists is two tracks). Time-blind; ``get_unique_tracks``
    layers proximity on top.
    """
    return _comparison_title(t1.song_name) == _comparison_title(
        t2.song_name
    ) and _artists_match(t1.artist, t2.artist)


def _rep_key(track: "Track") -> Tuple[int, str, str]:
    """Deterministic representative-selection key for a dedup cluster.

    Minimize this tuple to pick the cluster representative: earliest time
    wins, then lexicographic name/artist as a total-order tiebreak.

    Confidence is deliberately NOT part of this key. Every member of a
    cluster is the same track by construction (they passed ``_tracks_match``
    and the proximity bound), so preferring a "better" detection buys
    nothing — while any confidence-derived term reintroduces the exact
    instability this function exists to prevent: Shazam returns slightly
    different confidences per run, so the winner (and therefore the
    reported ``time_in_mix``) flips between runs of identical audio. An
    earlier version quantized confidence into 5-point buckets to absorb
    that jitter, but two detections straddling a bucket edge (84.9 vs
    85.0) still landed in different buckets and still flipped. Earliest
    time is jitter-proof.
    """
    return (
        track.time_to_seconds(),  # earliest detection wins
        track.song_name.lower(),  # then lex name
        track.artist.lower(),  # then lex artist
    )


def _parse_elapsed_hhmmss(value: str) -> Tuple[int, int, int]:
    """Parse an elapsed ``HH:MM:SS`` (HH unbounded) into ``(h, m, s)``.

    Raises ``ValueError`` for any malformed input or out-of-range MM/SS.
    """
    match = _TIME_IN_MIX_RE.match(value)
    if not match:
        raise ValueError(f"time_in_mix must be in elapsed HH:MM:SS form, got {value!r}")
    h, m, s = (int(part) for part in match.groups())
    if not (0 <= m < 60):
        raise ValueError(f"time_in_mix minutes out of range (0-59): {value!r}")
    if not (0 <= s < 60):
        raise ValueError(f"time_in_mix seconds out of range (0-59): {value!r}")
    return h, m, s


@dataclass
class Track:
    """Represents an identified track."""

    song_name: str
    artist: str
    time_in_mix: str
    confidence: float
    config: Optional["TrackIdentificationConfig"] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return (
            f"{self.time_in_mix} - {self.artist} - "
            f"{self.song_name} ({self.confidence:.0f}%)"
        )

    def is_similar_to(self, other: "Track") -> bool:
        """Check if two tracks are the same track (time-blind identity).

        Delegates to the module-level ``_tracks_match`` so there is one
        definition of "the same string for matching purposes". Time proximity
        is layered on separately by ``TrackMatcher.get_unique_tracks``.
        """
        return _tracks_match(self, other)

    def __post_init__(self):
        """Validate fields populated by the dataclass-generated __init__.

        The dataclass init does the assignment; this hook adds the field-level
        validation that used to live in a hand-written ``__init__`` overriding
        the dataclass init. Validation runs once, here.
        """
        if not isinstance(self.song_name, str) or not self.song_name.strip():
            raise ValueError("song_name must be a non-empty string")
        if not isinstance(self.artist, str) or not self.artist.strip():
            raise ValueError("artist must be a non-empty string")
        if not isinstance(self.time_in_mix, str):
            raise ValueError("time_in_mix must be in format HH:MM:SS")
        # Elapsed-time semantics: hours unbounded, MM/SS strictly 0-59.
        # Parsing here also acts as validation; ``time_to_seconds`` reuses it
        # so it stays infallible.
        _parse_elapsed_hhmmss(self.time_in_mix)
        if (
            not isinstance(self.confidence, (int, float))
            or self.confidence < 0
            or self.confidence > 100
        ):
            raise ValueError("confidence must be a number between 0 and 100")

        # Normalise inputs (the prior __init__ stripped strings + cast confidence)
        self.song_name = self.song_name.strip()
        self.artist = self.artist.strip()
        self.confidence = float(self.confidence)

        # Lazy-load config when the caller didn't supply one (preserves the
        # behaviour the manual __init__ used to provide unconditionally).
        if self.config is None:
            from tracklistify.config.factory import get_config

            self.config = get_config()

    @property
    def markdown_line(self) -> str:
        """Format track for markdown output."""
        return (
            f"- [{self.time_in_mix}] **{self.artist}** - "
            f"{self.song_name} ({self.confidence:.0f}%)"
        )

    @property
    def m3u_line(self) -> str:
        """Format track for M3U playlist."""
        return f"#EXTINF:-1,{self.artist} - {self.song_name}"

    def time_to_seconds(self) -> int:
        """Convert ``time_in_mix`` to seconds.

        Infallible — ``__post_init__`` rejects malformed input at construction
        so this method can rely on the string parsing cleanly. Handles hour
        values > 23 (elapsed time, not clock time).
        """
        h, m, s = _parse_elapsed_hhmmss(self.time_in_mix)
        return h * 3600 + m * 60 + s


class TrackMatcher:
    """Handles track matching and merging.

    Dedup authority is ``get_unique_tracks``: it clusters tracks that match by
    identity (token-set artist Jaccard + normalized title) within a proximity
    window, then picks one deterministic representative per cluster.
    """

    def __init__(self, config: Optional[TrackIdentificationConfig] = None):
        # Import locally to avoid circular import
        from tracklistify.config.factory import get_config

        self.tracks: List[Track] = []
        self._config = config or get_config()
        # Wire the config knob: config.min_confidence is 0.0-1.0, Track
        # confidence is 0-100. Default config 0.0 -> keep all tracks (no
        # behavior change vs the prior hardcoded 0).
        self._min_confidence = self._config.min_confidence * 100

    def _dedup_window(self) -> float:
        """Seconds within which two matching detections are the same play.

        Defaults to twice the segmentation step
        (``segment_length - overlap_duration``), because adjacent segments
        are exactly one step apart and the same track routinely lands in
        both. ``config.time_threshold`` overrides it when set to a positive
        value, which is what that knob has always claimed to mean ("time
        threshold for merging similar tracks").

        **The override is floored at the derived window (2 x step).** A
        track normally spans several segments, so its detections arrive one
        step apart and a cluster must reach across at least two of them.
        Anything narrower does not merely tighten dedup — it breaks it: at
        exactly one step a 3-segment track still emits two rows, and below
        one step nothing merges at all. This is not theoretical: the
        previous ``.env.example`` shipped ``TIME_THRESHOLD=30.0`` against a
        50s step, so every existing ``.env`` carries a value that would
        switch dedup off the moment this knob became live (observed: 41
        rows emitted where 23 were correct). Clamping keeps those configs
        working; only widening the window is reachable.

        Read per call rather than cached at construction: config attributes
        are mutable after load (CLI overrides mutate them), so a value
        captured in ``__init__`` can be stale by the time dedup runs. For
        the same reason the step is re-checked here rather than trusted:
        config validation rejects ``overlap_duration >= segment_length`` at
        construction, but plain attribute assignment afterwards is not
        re-validated, and a non-positive step would yield a zero/negative
        window that silently disables dedup. ``split_audio`` guards the
        identical arithmetic for the identical reason (invariant I2).
        """
        step = self._config.segment_length - self._config.overlap_duration
        if step <= 0:
            logger.warning(
                f"segment_length ({self._config.segment_length}) must exceed "
                f"overlap_duration ({self._config.overlap_duration}); the "
                f"derived dedup window would be {2 * step}s. Falling back to "
                f"{_FALLBACK_DEDUP_WINDOW}s so dedup still runs."
            )
            return _FALLBACK_DEDUP_WINDOW
        derived = 2.0 * step
        override = getattr(self._config, "time_threshold", 0) or 0
        if override > 0:
            if override < derived:
                logger.warning(
                    f"time_threshold={override}s is below the minimum "
                    f"useful dedup window ({derived:.0f}s = 2 x the {step}s "
                    f"segmentation step); detections of one track would not "
                    f"merge. Using {derived:.0f}s. Set "
                    f"TRACKLISTIFY_TIME_THRESHOLD=0 to derive it "
                    f"automatically, or a larger value to widen it."
                )
                return derived
            return float(override)
        return derived

    @property
    def min_confidence(self) -> float:
        """Minimum confidence threshold, on the **0-100** scale.

        This is ``Track.confidence``'s scale, NOT ``config.min_confidence``'s
        0.0-1.0 scale. The constructor converts; see ``__init__``.
        """
        return self._min_confidence

    @min_confidence.setter
    def min_confidence(self, value: float):
        """Set the threshold on the **0-100** scale (clamped).

        Assigning ``config.min_confidence`` directly here is a bug — it is
        0.0-1.0, so a value meant as "80%" silently becomes 0.8%, disabling
        the filter. Scale it (`* 100`) or let ``__init__`` do it for you.
        """
        # Clamp value between 0 and 100
        self._min_confidence = max(0, min(float(value), 100))

    def add_track(self, track: Track) -> None:
        """Add a track to the collection if it meets the confidence threshold.

        Dedup happens later in ``get_unique_tracks`` (the sole dedup
        authority); here we only confidence-gate and append.
        """
        # Skip tracks below confidence threshold
        if track.confidence < self.min_confidence:
            logger.debug(
                f"Skipping low confidence track: {track.song_name} "
                f"(Confidence: {track.confidence:.1f}%)"
            )
            return

        self.tracks.append(track)
        # INFO, not debug: this is the only per-track success signal the
        # operator sees during a run. Demoting it (as the dedup rewrite
        # briefly did) leaves the default log showing provider *failures*
        # only, so a healthy run reads as if nothing matched.
        logger.info(
            f"Identified: {track.song_name} — {track.artist} "
            f"at {track.time_in_mix} ({track.confidence:.1f}%)"
        )

    def get_unique_tracks(self) -> List[Track]:
        """Get list of unique tracks, sorted by time in mix.

        Greedy clustering: a track joins the first cluster that it matches by
        identity AND whose **most recent** member it is within the proximity
        window of. The window comes from ``_dedup_window()`` — twice the
        segmentation step by default, or ``config.time_threshold`` when set.

        The join tests the *gap to the last member*, not the span from the
        first, because gap continuity is what actually distinguishes the two
        cases:

        - One long track spans several segments, so its detections arrive at
          a steady one-step cadence (observed on a real mix: ``Hands Up`` at
          18:20/19:10/20:00/20:50, gaps of exactly 50s, total span 150s).
          Bounding the *span* to the window would split that at 100s and
          emit the same track twice.
        - Two genuinely distinct plays are separated by minutes of other
          tracks — a gap far larger than the window — so the chain breaks
          there and they stay separate.

        A pure any-member test would be transitively unbounded (a run of
        near-neighbours swallowing an arbitrary stretch and silently
        collapsing distinct plays into one row, which is worse than the
        duplicate it removes: a duplicate is visible, a deleted track is
        not). Testing the last member keeps the chain anchored to an
        unbroken cadence — it can only extend while detections keep
        arriving within one window of each other.

        One deterministic representative is picked per cluster via
        ``_rep_key`` (earliest time), so the reported ``time_in_mix`` is
        stable across runs of identical audio.
        """
        if not self.tracks:
            return []

        window = self._dedup_window()

        sorted_tracks = sorted(self.tracks, key=lambda t: t.time_to_seconds())
        # ``active`` holds clusters that a future track could still join;
        # ``finished`` holds those already out of reach. Because the input is
        # time-sorted, once a cluster's last member is more than one window
        # behind the current track it can never be joined again (every later
        # track is further still), so retiring it is safe and keeps the scan
        # amortized linear. A simple `break` over all clusters would be
        # WRONG here: clusters are created in anchor order but joined in
        # last-member order, so the two interleave and an out-of-reach
        # cluster can sit in front of a reachable one.
        active: List[List[Track]] = []
        finished: List[List[Track]] = []

        for track in sorted_tracks:
            t_secs = track.time_to_seconds()

            still_active = []
            for cluster in active:
                if t_secs - cluster[-1].time_to_seconds() > window:
                    finished.append(cluster)
                else:
                    still_active.append(cluster)
            active = still_active

            placed = False
            # Prefer the most recently extended cluster, so an unbroken
            # cadence keeps chaining rather than splitting.
            #
            # Identity is tested against ``cluster[0]`` — the anchor — not
            # against every member. Artist Jaccard is NOT transitive, so an
            # any-member test chains identity the same way an any-member
            # *time* test chains proximity: "Artist A" and "Artist B" share
            # no tokens (0.0, correctly distinct), but a collaboration
            # credit "Artist A, Artist B" matches both at 0.5 and bridges
            # them. Each hop also refreshes ``cluster[-1]``, so the time
            # guard above never retires the cluster and the chain runs
            # unbounded — observed deleting an entire second play (six
            # detections across two plays collapsed to one row). A visible
            # duplicate is recoverable; a silently deleted track is not.
            #
            # Note the two axes anchor on opposite ends, each for its own
            # reason: proximity on ``cluster[-1]`` so an unbroken cadence
            # can extend past the window, identity on ``cluster[0]`` so
            # membership cannot drift away from what the cluster *is*.
            # Anchoring also makes placement O(1) per cluster instead of
            # O(len(cluster)).
            for cluster in reversed(active):
                if _tracks_match(track, cluster[0]):
                    cluster.append(track)
                    placed = True
                    break
            if not placed:
                active.append([track])

        clusters = finished + active

        reps = [min(cluster, key=_rep_key) for cluster in clusters]
        return sorted(reps, key=lambda t: t.time_to_seconds())
