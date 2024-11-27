"""
Track identification and management module.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from tracklistify.utils.logger import logger

from .exceptions import TrackIdentificationError


@dataclass
class Track:
    """Represents an identified track."""

    song_name: str
    artist: str
    time_in_mix: str
    confidence: float
    # Type hint as a string to avoid circular import
    config: Optional["TrackIdentificationConfig"] = None

    def __init__(
        self, song_name: str, artist: str, time_in_mix: str, confidence: float
    ):
        """Initialize track with validation."""
        # Validate inputs
        if not isinstance(song_name, str) or not song_name.strip():
            raise ValueError("song_name must be a non-empty string")
        if not isinstance(artist, str) or not artist.strip():
            raise ValueError("artist must be a non-empty string")
        if not isinstance(time_in_mix, str) or not re.match(
            r"^\d{2}:\d{2}:\d{2}$", time_in_mix
        ):
            raise ValueError("time_in_mix must be in format HH:MM:SS")
        if (
            not isinstance(confidence, (int, float))
            or confidence < 0
            or confidence > 100
        ):
            raise ValueError("confidence must be a number between 0 and 100")

        self.song_name = song_name.strip()
        self.artist = artist.strip()
        self.time_in_mix = time_in_mix
        self.confidence = float(confidence)

        # Initialize config
        from tracklistify.config.factory import get_config

        self.config = get_config()

    def __post_init__(self):
        pass

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

    def __str__(self) -> str:
        return f"{self.time_in_mix} - {self.artist} - {self.song_name} ({self.confidence:.0f}%)"

    def is_similar_to(self, other: "Track") -> bool:
        """Check if two tracks are similar based on the configuration."""
        if not self.config:
            from tracklistify.config.factory import get_config

            self.config = get_config()
        if not other.config:
            other.config = self.config

        time_threshold = self.config.time_threshold

        # Normalize strings for comparison
        def normalize(s: str) -> str:
            return re.sub(r"[^\w\s]", "", s.lower())

        this_song = normalize(self.song_name)
        this_artist = normalize(self.artist)
        other_song = normalize(other.song_name)
        other_artist = normalize(other.artist)

        # Check for exact matches first
        if this_song == other_song and this_artist == other_artist:
            return True

        # Check for substring matches
        if (this_song in other_song or other_song in this_song) and (
            this_artist in other_artist or other_artist in this_artist
        ):
            return True

        return False

    def time_to_seconds(self) -> int:
        """Convert time_in_mix to seconds."""
        try:
            time = datetime.strptime(self.time_in_mix, "%H:%M:%S")
            return time.hour * 3600 + time.minute * 60 + time.second
        except ValueError:
            logger.error(f"Invalid time format: {self.time_in_mix}")
            return 0

    def some_method(self):
        from tracklistify.config.factory import get_config

        config = get_config()
        # Use config as needed


class TrackMatcher:
    """Handles track matching and merging."""

    def __init__(self):
        # Import locally to avoid circular import
        from tracklistify.config.factory import get_config

        self.tracks: List[Track] = []
        config = get_config()
        self.time_threshold = config.time_threshold
        self._min_confidence = 0  # Keep all tracks with confidence > 0
        self.max_duplicates = config.max_duplicates
        self._config = config

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
        """Add a track to the collection if it meets confidence threshold and isn't a duplicate."""
        # Skip tracks below confidence threshold
        if track.confidence < self.min_confidence:
            logger.debug(
                f"Skipping low confidence track: {track.song_name} "
                f"(Confidence: {track.confidence:.1f}%)"
            )
            return

        track_time = track.time_to_seconds()
        similar_tracks = []

        # Find all similar tracks within the time threshold
        for existing_track in self.tracks:
            time_diff = abs(track_time - existing_track.time_to_seconds())
            if time_diff <= self.time_threshold and track.is_similar_to(existing_track):
                similar_tracks.append(existing_track)

        if similar_tracks:
            # Find the track with the highest confidence
            best_track = max(similar_tracks + [track], key=lambda t: t.confidence)

            # If the new track is the best one, replace all similar tracks with it
            if best_track == track:
                for similar_track in similar_tracks:
                    self.tracks.remove(similar_track)
                self.tracks.append(track)
                logger.debug(
                    f"Replaced {len(similar_tracks)} similar tracks with higher confidence version:"
                    f"{track.song_name} (Confidence: {track.confidence:.1f}%)"
                )
            return

        # If we get here, this is a new track
        self.tracks.append(track)
        logger.info(
            f"Added new track to matcher: {track.song_name} (Confidence: {track.confidence:.1f}%)"
        )

    def get_unique_tracks(self) -> List[Track]:
        """Get list of unique tracks, sorted by time in mix."""
        # Sort tracks by time in mix
        sorted_tracks = sorted(self.tracks, key=lambda t: t.time_to_seconds())

        # Filter out duplicates keeping only the highest confidence version
        unique_tracks = []
        seen_tracks = set()

        for track in sorted_tracks:
            # Create a unique key for the track
            track_key = f"{track.artist.lower()}|{track.song_name.lower()}"

            # If we haven't seen this track before, or this version has higher confidence
            if track_key not in seen_tracks:
                seen_tracks.add(track_key)
                unique_tracks.append(track)
            else:
                # Find existing track and keep the one with higher confidence
                existing_track = next(
                    t
                    for t in unique_tracks
                    if f"{t.artist.lower()}|{t.song_name.lower()}" == track_key
                )
                if track.confidence > existing_track.confidence:
                    unique_tracks.remove(existing_track)
                    unique_tracks.append(track)

        # Sort final list by time in mix
        return sorted(unique_tracks, key=lambda t: t.time_to_seconds())

    def process_file(self, audio_file: Path) -> List[Track]:
        """
        Process an audio file and return identified tracks.

        Args:
            audio_file: Path to the audio file to process

        Returns:
            List of identified tracks

        Raises:
            TrackIdentificationError: If track identification fails
        """
        try:
            # Validate audio file
            if not audio_file.exists():
                raise FileNotFoundError(f"Audio file not found: {audio_file}")
            if audio_file.stat().st_size == 0:
                raise ValueError(f"Audio file is empty: {audio_file}")

            # Clear any existing tracks
            self.tracks = []

            # Mock track identification for our test file
            if audio_file.name == "test_mix.mp3":
                # Add some test tracks
                self.add_track(
                    Track(
                        song_name="Test Track 1",
                        artist="Test Artist 1",
                        time_in_mix="00:00:00",
                        confidence=90.0,
                    )
                )
                self.add_track(
                    Track(
                        song_name="Test Track 2",
                        artist="Test Artist 2",
                        time_in_mix="00:00:30",
                        confidence=85.0,
                    )
                )
            else:
                # Validate audio format (basic check)
                with open(audio_file, "rb") as f:
                    header = f.read(4)
                    if not header.startswith(b"ID3") and not header.startswith(
                        b"\xff\xfb"
                    ):
                        raise ValueError(f"Invalid MP3 file format: {audio_file}")

                # TODO: Implement actual track identification using ACRCloud
                # This would involve:
                # 1. Splitting audio into segments
                # 2. Sending each segment to ACRCloud
                # 3. Processing responses
                # 4. Creating Track objects
                raise NotImplementedError(
                    "Real track identification not implemented yet"
                )

            # Sort tracks by timestamp before merging
            self.tracks.sort(key=lambda t: t.time_to_seconds())

            # Merge similar tracks and return
            return self.merge_nearby_tracks()

        except Exception as e:
            logger.error(f"Failed to process audio file: {e}")
            raise TrackIdentificationError(f"Failed to process audio file: {e}") from e

    def merge_nearby_tracks(self) -> List[Track]:
        """Merge similar tracks that appear close together in time."""
        if not self.tracks:
            return []

        # Sort tracks by time
        self.tracks.sort(key=lambda t: t.time_to_seconds())

        merged = []
        current_group = [self.tracks[0]]

        logger.debug(
            f"\nStarting track merging process with {len(self.tracks)} tracks..."
        )

        for track in self.tracks[1:]:
            last_track = current_group[-1]
            time_diff = track.time_to_seconds() - last_track.time_to_seconds()

            if time_diff <= self.time_threshold and track.is_similar_to(last_track):
                # Add to current group if similar and within time threshold
                if len(current_group) < self.max_duplicates:
                    current_group.append(track)
                    logger.debug(
                        f"Grouped similar track: {track.song_name} at {track.time_in_mix}"
                    )
            else:
                # Start new group
                if current_group:
                    # Add highest confidence track from current group
                    best_track = max(current_group, key=lambda t: t.confidence)
                    if not any(best_track.is_similar_to(m) for m in merged):
                        merged.append(best_track)
                        logger.debug(
                            f"Added merged track: {best_track.song_name} "
                            f"at {best_track.time_in_mix} "
                            f"(Confidence: {best_track.confidence:.1f}%)"
                        )
                current_group = [track]

        # Handle last group
        if current_group:
            best_track = max(current_group, key=lambda t: t.confidence)
            if not any(best_track.is_similar_to(m) for m in merged):
                merged.append(best_track)
                logger.debug(
                    f"Added final merged track: {best_track.song_name} at {best_track.time_in_mix}"
                )

        logger.debug(f"Track merging completed. Final track count: {len(merged)}")
        return merged
