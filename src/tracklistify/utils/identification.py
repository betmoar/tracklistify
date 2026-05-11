"""
Track identification helper functions and utilities.
"""

# Standard library imports
import sys
import time
from typing import List, Optional

# Third-party imports
from mutagen._file import File, FileType

from tracklistify.config.factory import get_config

# Local/package imports
from tracklistify.core.track import Track, TrackMatcher
from tracklistify.providers.factory import create_provider_factory
from .logger import get_logger
from .time_formatter import format_seconds_to_hhmmss

logger = get_logger(__name__)


def get_audio_info(audio_path: str) -> Optional[FileType]:
    """Get audio file metadata."""
    return File(audio_path)


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
            bar = create_progress_bar(progress, width=30)

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

        Resets the display line and cursor position.

        Examples:
            >>> display = ProgressDisplay()
            >>> display.start(10)
            >>> display.update(5)
            >>> display.clear()
        """
        # Clear current line by overwriting with spaces
        sys.stdout.write("\r" + " " * 80 + "\r")
        sys.stdout.flush()
        self._last_line_length = 0


class IdentificationManager:
    """Manages track identification using configured providers."""

    def __init__(self, config=None, provider_factory=None):
        self.config = config or get_config()
        self.provider_factory = provider_factory or create_provider_factory()
        self.track_matcher = TrackMatcher()

    async def identify_tracks(self, audio_segments):
        provider_name = self.config.primary_provider
        provider = self.provider_factory.get_identification_provider(provider_name)
        identified_tracks = []

        for segment in audio_segments:
            try:
                track_info = await provider.identify_track(segment)
                if track_info is None:
                    logger.debug("Provider returned None for track identification")
                    continue

                # Extract track metadata with safe array access
                music_list = track_info.get("metadata", {}).get("music", [])
                if not music_list:
                    logger.error("No track metadata found in provider response")
                    continue
                metadata = music_list[0] if music_list else {}
                if not metadata:
                    logger.error("Empty track metadata in provider response")
                    continue

                # Format time in mix with proper zero-padding
                time_in_mix = format_seconds_to_hhmmss(int(segment.start_time))

                # Safely extract artist name with default
                artists_list = metadata.get("artists", [])
                artist_name = (
                    artists_list[0].get("name", "Unknown Artist")
                    if artists_list
                    else "Unknown Artist"
                )

                try:
                    track = Track(
                        song_name=metadata.get("title", "Unknown Title"),
                        artist=artist_name,
                        time_in_mix=time_in_mix,
                        confidence=float(
                            metadata.get("score", 100.0)
                        ),  # Default to 100% if not provided
                    )
                    self.track_matcher.add_track(track)
                    identified_tracks.append(track)
                except ValueError as e:
                    logger.error(f"Failed to create track: {e}")
                    continue
                except Exception as e:
                    logger.error(f"Unexpected error creating track: {e}")
                    continue

            except Exception as e:
                logger.error(f"Identification failed for segment: {e}")
                continue

        # Get unique tracks sorted by time in mix
        unique_tracks = self.track_matcher.get_unique_tracks()
        logger.info(
            (
                f"Identified {len(unique_tracks)} unique tracks from "
                f"{len(identified_tracks)} total matches"
            )
        )
        return unique_tracks

    async def close(self):
        """Cleanup resources."""
        if self.provider_factory:
            await self.provider_factory.close_all()


async def identify_tracks(audio_path: str) -> Optional[List[Track]]:
    """
    Identify tracks in an audio file.

    Args:
        audio_path: Path to audio file

    Returns:
        List[Track]: List of identified tracks, or None if identification failed
    """
    try:
        manager = IdentificationManager()
        return await manager.identify_tracks(audio_path)
    except Exception as e:
        logger.error(f"Track identification failed: {e}")
        return None
