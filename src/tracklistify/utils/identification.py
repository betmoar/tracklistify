"""
Track identification helper functions and utilities.
"""

# Standard library imports
import asyncio
import contextlib
import hashlib
import sys
import time
from typing import Any, Dict, List, Optional

from tracklistify.cache.factory import get_cache
from tracklistify.config.factory import get_config

# Local/package imports
from tracklistify.core.track import Track, TrackMatcher
from tracklistify.providers.factory import create_provider_factory
from .constants import DEFAULT_PROGRESS_BAR_WIDTH, TERMINAL_LINE_WIDTH
from .logger import get_logger
from .rate_limiter import get_global_rate_limiter
from .time_formatter import format_seconds_to_hhmmss

logger = get_logger(__name__)


def format_duration(duration: float) -> str:
    """Format duration in seconds to HH:MM:SS.

    Args:
        duration: Time in seconds (can be float)

    Returns:
        Formatted string in HH:MM:SS format

    Examples:
        >>> format_duration(0)
        '00:00:00'
        >>> format_duration(3661.5)
        '01:01:01'
    """
    hours = int(duration // 3600)
    minutes = int((duration % 3600) // 60)
    seconds = int(duration % 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def create_progress_bar(progress: float, width: int = 30) -> str:
    """Create a progress bar string.

    Args:
        progress: Progress value between 0.0 and 1.0
        width: Width of the progress bar (default: 30)

    Returns:
        ASCII progress bar string like "[█████░░░░░]"

    Examples:
        >>> create_progress_bar(0.5, 10)
        '[█████░░░░░]'
        >>> create_progress_bar(1.0, 10)
        '[██████████]'
    """
    # Clamp progress to 0.0-1.0 range
    progress = max(0.0, min(1.0, progress))

    # Calculate filled and empty sections
    filled = int(progress * width)
    empty = width - filled

    # Build progress bar with filled (█) and empty (░) blocks
    bar = "[" + "█" * filled + "░" * empty + "]"
    return bar


def _extra_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Pull provider-supplied extras out of a music entry.

    ISRC, genre, album/label/release date, platform ids and artwork. No
    provider fills every key — ACRCloud has no Shazam id, Shazam has no
    ACRCloud fields — so empty values are dropped rather than stored as
    ``None``. That keeps ``Track.metadata`` free of null noise and lets
    ``_save_json`` emit ``null`` for a track with no extras at all.

    Reads defensively: provider payloads are third-party JSON, and a
    malformed shape here must not take down identification. Anything
    unparseable yields ``{}`` and the Track is still built.
    """
    if not isinstance(metadata, dict):
        return {}

    external_ids = metadata.get("external_ids")
    isrc = external_ids.get("isrc") if isinstance(external_ids, dict) else None

    genres_raw = metadata.get("genres")
    genres = (
        [g.get("name") for g in genres_raw if isinstance(g, dict) and g.get("name")]
        if isinstance(genres_raw, list)
        else []
    )

    extras = {
        "isrc": isrc,
        "album": metadata.get("album"),
        "label": metadata.get("label"),
        "release_date": metadata.get("release_date"),
        "genres": genres or None,
        "shazam_id": metadata.get("shazam_id"),
        "apple_music_id": metadata.get("apple_music_id"),
        "artwork_url": metadata.get("artwork_url"),
        "shazam_url": metadata.get("shazam_url"),
        # Platform search deeplinks Shazam ships with the match. Named
        # ``*_search_uri`` because they are searches, not canonical track
        # URLs — see the provider for why.
        "spotify_search_uri": metadata.get("spotify_search_uri"),
        "deezer_search_uri": metadata.get("deezer_search_uri"),
    }
    return {k: v for k, v in extras.items() if v}


class ProgressDisplay:
    """Handles the progress display for track identification.

    Provides a terminal-based progress display with elapsed time,
    progress bar, and percentage completion.

    Attributes:
        start_time: ``time.monotonic()`` value captured when ``start()``
            was called. Only meaningful as the base for elapsed-time
            calculations — NOT a wall-clock timestamp.
        current_segment: Current segment being processed
        total_segments: Total number of segments to process
    """

    def __init__(self):
        """Initialize progress display."""
        self.start_time: Optional[float] = None
        self.current_segment: int = 0
        self.total_segments: int = 0
        self._last_line_length: int = 0

    def start(self, total: int) -> None:
        """Start progress tracking.

        Args:
            total: Total number of segments to process

        Examples:
            >>> display = ProgressDisplay()
            >>> display.start(10)
            >>> display.total_segments
            10
        """
        self.start_time = time.monotonic()
        self.current_segment = 0
        self.total_segments = total
        logger.info(f"Starting identification of {total} segments")

    def update(self, current: int) -> None:
        """Update progress to current segment.

        Args:
            current: Current segment number (1-based indexing)

        Examples:
            >>> display = ProgressDisplay()
            >>> display.start(10)
            >>> display.update(5)
            >>> display.current_segment
            5
        """
        self.current_segment = current

        # Calculate progress
        if self.total_segments > 0:
            progress = current / self.total_segments
            elapsed = time.monotonic() - self.start_time if self.start_time else 0

            # Create progress bar
            bar = create_progress_bar(progress, width=DEFAULT_PROGRESS_BAR_WIDTH)

            # Display progress with carriage return to overwrite line
            percentage = int(progress * 100)
            elapsed_str = format_duration(elapsed)
            line = (
                f"\r{bar} {percentage}% ({current}/{self.total_segments}) "
                f"- Elapsed: {elapsed_str}"
            )
            self._last_line_length = len(line)
            sys.stdout.write(line)
            sys.stdout.flush()

    def complete(self) -> None:
        """Mark progress as complete.

        Displays final completion message with total elapsed time.

        Examples:
            >>> display = ProgressDisplay()
            >>> display.start(10)
            >>> display.update(10)
            >>> display.complete()
        """
        if self.start_time:
            elapsed = time.monotonic() - self.start_time
            elapsed_str = format_duration(elapsed)

            # Move to next line and show completion
            sys.stdout.write("\n")
            logger.info(
                f"Identification complete! Processed {self.total_segments} "
                f"segments in {elapsed_str}"
            )

    def clear(self) -> None:
        """Clear the progress display.

        Overwrites the actual rendered line length (tracked in
        ``_last_line_length``) so wide lines don't leave a trailing
        residue. Falls back to ``TERMINAL_LINE_WIDTH`` as a floor in case
        ``clear()`` is called before any ``update()``.

        Examples:
            >>> display = ProgressDisplay()
            >>> display.start(10)
            >>> display.update(5)
            >>> display.clear()
        """
        width = max(self._last_line_length, TERMINAL_LINE_WIDTH)
        sys.stdout.write("\r" + " " * width + "\r")
        sys.stdout.flush()
        self._last_line_length = 0


class IdentificationManager:
    """Manages track identification using configured providers."""

    def __init__(self, config=None, provider_factory=None, cache=None):
        # Memoize segment sha256 digests by file_path so _cache_key() doesn't
        # re-read+re-hash the same file once per provider in the chain.
        self._segment_digests: dict[str, str] = {}
        self.config = config or get_config()
        self.provider_factory = provider_factory or create_provider_factory()
        self.track_matcher = TrackMatcher(self.config)
        # Cache is optional: tests inject a double; production resolves the
        # global cache singleton. It's only consulted when
        # ``config.cache_enabled`` is set (checked per-call in identify_tracks).
        self._cache = cache if cache is not None else get_cache()

    def _provider_chain(self) -> List[str]:
        """Resolve the ordered provider chain: primary, then fallbacks.

        Fallback providers are only appended when ``fallback_enabled`` is
        set (config default, or ``--no-fallback`` CLI override). Duplicates
        of the primary are dropped so a segment is never retried on the
        same provider.
        """
        chain = [self.config.primary_provider]
        if getattr(self.config, "fallback_enabled", False):
            for name in getattr(self.config, "fallback_providers", None) or []:
                if name not in chain:
                    chain.append(name)
        return chain

    def _track_from_info(self, track_info, segment) -> Optional[Track]:
        """Build a ``Track`` from a provider response dict, or None.

        Providers return ``{"metadata": {"music": [{title, artists,
        score}]}}``; anything that doesn't parse into a valid Track (empty
        music list, blank title/artist, out-of-range score) yields None so
        the caller can fall back to the next provider.
        """
        if track_info is None:
            return None
        music_list = track_info.get("metadata", {}).get("music", [])
        if not music_list or not music_list[0]:
            logger.debug("No track metadata in provider response")
            return None
        metadata = music_list[0]

        time_in_mix = format_seconds_to_hhmmss(int(segment.start_time))
        artists_list = metadata.get("artists", [])
        artist_name = (
            artists_list[0].get("name", "Unknown Artist")
            if artists_list
            else "Unknown Artist"
        )
        try:
            return Track(
                song_name=metadata.get("title", "Unknown Title"),
                artist=artist_name,
                time_in_mix=time_in_mix,
                confidence=float(metadata.get("score", 100.0)),
                metadata=_extra_metadata(metadata),
            )
        except (ValueError, TypeError) as e:
            logger.error(f"Failed to create track from provider response: {e}")
            return None

    async def identify_tracks(self, audio_segments):
        provider_names = self._provider_chain()

        # Instantiate providers up front. A broken PRIMARY is fatal (raise,
        # with the factory's actionable message); a broken FALLBACK is
        # skipped with a warning so it can't take down the whole run.
        chain = []
        for name in provider_names:
            try:
                provider = self.provider_factory.get_identification_provider(name)
                chain.append((name, provider))
            except Exception as e:
                if name == self.config.primary_provider:
                    raise
                logger.warning(f"Skipping unusable fallback provider {name!r}: {e}")

        identified_tracks = []
        limiter = get_global_rate_limiter()

        # Enter every provider's async context so aiohttp/shazamio
        # resources are closed even if an exception escapes the loop.
        async with contextlib.AsyncExitStack() as stack:
            for _, provider in chain:
                await stack.enter_async_context(provider)

            for segment in audio_segments:
                track = None
                for provider_name, provider in chain:
                    # Cache lookup (best-effort, content-addressed by segment
                    # bytes + provider — temp paths are per-run). A hit
                    # short-circuits both the rate limiter and the network.
                    cache_key = self._cache_key(provider_name, segment)
                    if cache_key is not None:
                        try:
                            cached = await self._cache.get(cache_key)
                        except Exception as e:
                            logger.debug(f"Cache get failed: {e}")
                            cached = None
                        if cached is not None:
                            track = self._track_from_info(cached, segment)
                            if track is not None:
                                # Mark the hit: this path never touches the
                                # provider, so without a line here a cached
                                # segment is indistinguishable from one that
                                # was never processed. That reads as a gap
                                # in the segment sequence (e.g. 200s jumping
                                # to 350s) and looks like dropped work.
                                logger.debug(
                                    f"Cache hit for segment at "
                                    f"{segment.start_time}s ({provider_name})"
                                )
                                break

                    acquired = False
                    try:
                        acquired = await limiter.acquire(provider_name)
                        if not acquired:
                            logger.warning(
                                f"Rate limiter rejected request for "
                                f"{provider_name}; trying next provider"
                            )
                            continue
                        track_info = await provider.identify_track(segment)
                        limiter.record_result(provider_name, success=True)
                        track = self._track_from_info(track_info, segment)
                        if track is not None:
                            # Best-effort cache of the raw provider response.
                            # Failures degrade to live-only; never abort.
                            if cache_key is not None:
                                try:
                                    await self._cache.set(cache_key, track_info)
                                except Exception as e:
                                    logger.debug(f"Cache set failed: {e}")
                            break
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        limiter.record_result(provider_name, success=False)
                        logger.error(
                            f"{provider_name} identification failed for "
                            f"segment at {segment.start_time}s: {e}"
                        )
                        continue
                    finally:
                        if acquired:
                            limiter.release(provider_name)

                if track is not None:
                    self.track_matcher.add_track(track)
                    identified_tracks.append(track)

        # Get unique tracks sorted by time in mix
        unique_tracks = self.track_matcher.get_unique_tracks()
        logger.info(
            (
                f"Identified {len(unique_tracks)} unique tracks from "
                f"{len(identified_tracks)} total matches"
            )
        )
        return unique_tracks

    def _cache_key(self, provider_name: str, segment) -> Optional[str]:
        """Build a content-addressed cache key, or None to skip caching.

        The key is ``f"{provider_name}:{sha256(segment_bytes)}"`` — temp
        segment paths are per-run, so the path is unhashable; the bytes are
        stable for identical audio. Returns None when caching is disabled
        or the segment file can't be read, so the caller degrades to live
        identification.

        The digest is memoized per ``file_path`` so the segment is read +
        hashed once even when multiple providers in the chain consult the
        cache. Reads are chunked to avoid memory spikes on large segments.
        """
        if not getattr(self.config, "cache_enabled", False):
            return None
        digest = self._segment_digests.get(segment.file_path)
        if digest is None:
            try:
                h = hashlib.sha256()
                with open(segment.file_path, "rb") as f:
                    for chunk in iter(lambda: f.read(1 << 16), b""):
                        h.update(chunk)
            except OSError as e:
                logger.debug(
                    f"Cannot read segment for cache key ({segment.file_path}): {e}"
                )
                return None
            digest = h.hexdigest()
            self._segment_digests[segment.file_path] = digest
        return f"{provider_name}:{digest}"

    async def close(self):
        """Cleanup resources."""
        if self.provider_factory:
            await self.provider_factory.close_all()
