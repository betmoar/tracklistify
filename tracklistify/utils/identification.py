"""
Track identification helper functions and utilities.
"""

# Standard library imports
from typing import List, Optional

# Third-party imports
from mutagen import File

from tracklistify.config.factory import get_config

# Local/package imports
from tracklistify.core.track import Track, TrackMatcher
from tracklistify.providers.factory import create_provider_factory
from tracklistify.utils.logger import logger
from tracklistify.utils.time_formatter import format_seconds_to_hhmmss


def get_audio_info(audio_path: str) -> File:
    """Get audio file metadata."""
    return File(audio_path)


def format_duration(duration: float) -> str:
    """Format duration in seconds to HH:MM:SS."""
    ...


def create_progress_bar(progress: float, width: int = 30) -> str:
    """Create a progress bar string."""
    ...


class ProgressDisplay:
    """Handles the progress display for track identification."""

    ...


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

                # Extract track metadata
                metadata = track_info.get("metadata", {}).get("music", [{}])[0]
                if not metadata:
                    logger.error("No track metadata found in provider response")
                    continue

                # Format time in mix with proper zero-padding
                time_in_mix = format_seconds_to_hhmmss(int(segment.start_time))

                try:
                    track = Track(
                        song_name=metadata.get("title", "Unknown Title"),
                        artist=metadata.get("artists", [{}])[0].get(
                            "name", "Unknown Artist"
                        ),
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
            f"Identified {len(unique_tracks)} unique tracks from {len(identified_tracks)} total matches"
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
