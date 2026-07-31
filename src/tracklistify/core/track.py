"""
Track identification and management module.
"""

import re
import unicodedata
from dataclasses import dataclass, field
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


def _tracks_match(t1: "Track", t2: "Track") -> bool:
    """Identity match: same normalized title AND overlapping artists.

    Title-match + artist-mismatch = different tracks (a DJ playing the same
    song by different artists is two tracks). Time-blind; ``get_unique_tracks``
    layers proximity on top.
    """
    return _normalize_token(t1.song_name) == _normalize_token(
        t2.song_name
    ) and _artists_match(t1.artist, t2.artist)


def _rep_key(track: "Track") -> Tuple[int, int, str, str]:
    """Deterministic representative-selection key for a dedup cluster.

    Minimize this tuple to pick the cluster representative. The 5-point
    confidence deadband quantizes Shazam's run-to-run confidence noise so the
    winner no longer flips between runs of identical audio; within a deadband
    bucket, earliest time wins (then lexicographic name/artist for total
    determinism).
    """
    return (
        -int(track.confidence / 5.0),  # higher confidence bucket first
        track.time_to_seconds(),  # then earliest time
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
        self.time_threshold = self._config.time_threshold
        # Wire the config knob: config.min_confidence is 0.0-1.0, Track
        # confidence is 0-100. Default config 0.0 -> keep all tracks (no
        # behavior change vs the prior hardcoded 0).
        self._min_confidence = self._config.min_confidence * 100
        self.max_duplicates = self._config.max_duplicates

    @property
    def min_confidence(self) -> float:
        """Get the minimum confidence threshold."""
        return self._min_confidence

    @min_confidence.setter
    def min_confidence(self, value: float):
        """Set the minimum confidence threshold with validation."""
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
        logger.debug(
            f"Added track to matcher: {track.song_name} "
            f"(Confidence: {track.confidence:.1f}%)"
        )

    def get_unique_tracks(self) -> List[Track]:
        """Get list of unique tracks, sorted by time in mix.

        Greedy clustering: a track joins the first cluster where it is both
        within the proximity window of some member AND matches that member by
        identity. The proximity window is derived from the segmentation step
        (``2 * (segment_length - overlap_duration)``), so adjacent-segment
        detections of the same audio merge while genuinely distinct plays
        (minutes apart) stay separate. One deterministic representative is
        picked per cluster via ``_rep_key`` (5-point confidence deadband +
        earliest-time tiebreak) so the chosen ``time_in_mix`` no longer flips
        between runs of the same audio.
        """
        if not self.tracks:
            return []

        step = self._config.segment_length - self._config.overlap_duration
        window = 2 * step

        sorted_tracks = sorted(self.tracks, key=lambda t: t.time_to_seconds())
        clusters: List[List[Track]] = []

        for track in sorted_tracks:
            placed = False
            # Clusters are time-ordered (we append as tracks arrive sorted by
            # time); scan recent clusters first. A track joins the first
            # cluster where it is within the window of AND identity-matches a
            # member.
            for cluster in reversed(clusters):
                if any(
                    abs(track.time_to_seconds() - m.time_to_seconds()) <= window
                    for m in cluster
                ) and any(_tracks_match(track, m) for m in cluster):
                    cluster.append(track)
                    placed = True
                    break
            if not placed:
                clusters.append([track])

        reps = [min(cluster, key=_rep_key) for cluster in clusters]
        return sorted(reps, key=lambda t: t.time_to_seconds())
