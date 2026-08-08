"""
Output formatting and file handling for Tracklistify.
"""

# Standard library imports
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Local/package imports
from tracklistify.config import get_config
from tracklistify.core.exceptions import ExportError
from tracklistify.core.track import Track
from tracklistify.utils.logger import get_logger

# Precompiled sanitization patterns for clean_string (called per track).
_INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\|?*@]')
_MULTISPACE_RE = re.compile(r"\s+")

logger = get_logger(__name__)


class TracklistOutput:
    """Handles tracklist output in various formats."""

    def __init__(self, mix_info: dict, tracks: List[Track]):
        """
        Initialize with mix information and tracks.

        Args:
            mix_info: Dictionary containing mix metadata
            tracks: List of identified tracks

        Raises:
            ExportError: If tracks is None or empty
        """
        if not tracks:
            raise ExportError("No tracks provided for output")

        self.mix_info = mix_info or {}
        self.tracks = tracks
        self._config = get_config()
        # Each run produces a self-contained subfolder under output_dir,
        # named from the mix metadata. The folder is the identity; files
        # inside use fixed names (tracklist.{ext}).
        self.output_dir = Path(self._config.output_dir) / self._format_subfolder_name()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _format_subfolder_name(self) -> str:
        """Build the per-set subfolder name from mix metadata.

        Format: ``[YYYYMMDD] Artist - Description`` (same stem as the old
        flat filename, minus the extension). Used as the self-contained
        output directory for a single run.
        """
        # Get date in YYYYMMDD format
        mix_date = self.mix_info.get("date", datetime.now().strftime("%Y-%m-%d"))
        if isinstance(mix_date, str):
            try:
                mix_date = datetime.strptime(mix_date, "%Y-%m-%d").strftime("%Y%m%d")
            except ValueError:
                mix_date = datetime.now().strftime("%Y%m%d")

        # Get artist and description
        artist = self.mix_info.get("artist", "")
        title = self.mix_info.get("title", "")
        venue = self.mix_info.get("venue", "")

        # Clean up special characters but preserve spaces and basic punctuation
        def clean_string(s: str) -> str:
            s = _INVALID_FILENAME_CHARS_RE.sub(" ", s)
            s = _MULTISPACE_RE.sub(" ", s)
            return s.strip()

        # Clean and format parts
        artist = clean_string(artist)
        title = clean_string(title)
        venue = clean_string(venue)

        # Use artist from title if no artist provided
        if not artist and " - " in title:
            artist, title = title.split(" - ", 1)
        elif not artist:
            artist = "Unknown Artist"

        # Format description with venue
        description = title
        if venue:
            description = f"{title} | {venue}"

        return f"[{mix_date}] {artist} - {description}"

    def _format_filename(self, extension: str) -> str:
        """Build a filename inside the subfolder.

        Files use fixed names (``tracklist.{ext}``) since the subfolder is
        the identity. Kept for backwards compatibility with callers/tests
        that build paths from the formatted name.
        """
        return f"tracklist.{extension}"

    def save(self, format_type: str) -> Optional[Path]:
        """
        Save tracks in specified format.

        Args:
            format_type: Output format ('json', 'markdown', or 'm3u')

        Returns:
            Path to saved file, or None if format is invalid
        """
        if format_type == "json":
            return self._save_json()
        elif format_type == "markdown":
            return self._save_markdown()
        elif format_type == "m3u":
            return self._save_m3u()
        else:
            logger.error(f"Invalid format type: {format_type}")
            return None

    def _save_json(self) -> Path:
        """Save tracks as JSON file."""
        output_file = self.output_dir / self._format_filename("json")

        # Ensure tracks is not None and is a list
        if not isinstance(self.tracks, list):
            logger.error("No valid tracks list available")
            raise ExportError("Cannot save JSON: tracks is not a valid list")

        # Calculate statistics safely with null checks
        track_count = len(self.tracks)
        avg_confidence: float = 0
        min_confidence: float = 0
        max_confidence: float = 0

        if track_count > 0:
            confidences = [
                t.confidence for t in self.tracks if hasattr(t, "confidence")
            ]
            if confidences:
                avg_confidence = sum(confidences) / len(confidences)
                min_confidence = min(confidences)
                max_confidence = max(confidences)

        data: Dict[str, Any] = {
            "mix_info": self.mix_info or {},
            "track_count": track_count,
            "analysis_info": {
                "timestamp": datetime.now().isoformat(),
                "track_count": track_count,
                "average_confidence": avg_confidence,
                "min_confidence": min_confidence,
                "max_confidence": max_confidence,
            },
            "tracks": [
                {
                    "song_name": track.song_name,
                    "artist": track.artist,
                    "time_in_mix": track.time_in_mix,
                    "confidence": track.confidence,
                    "duration": getattr(track, "duration", None),
                    "metadata": getattr(track, "metadata", None) or None,
                }
                for track in self.tracks
            ],
        }

        # Serialize fully in memory before touching the file. ``json.dump``
        # streams, so a TypeError partway through leaves a truncated file
        # that looks like a finished tracklist — and this runs AFTER the
        # whole expensive identification pass, so a corrupt write is the
        # most costly moment to fail.
        #
        # ``default=str`` is the safety net: ``Track.metadata`` is opaque
        # pass-through, currently only ever provider strings, but the
        # planned Spotify/MusicBrainz enrichment (BACKLOG P2/P3) will feed
        # it values like datetimes straight from a client library. Falling
        # back to str() degrades one field instead of losing the export.
        payload = json.dumps(data, indent=4, ensure_ascii=False, default=str)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(payload)

        logger.info("Analysis Summary:")
        logger.info(f"- Total tracks: {data['analysis_info']['track_count']}")
        logger.info(
            f"- Average confidence: {data['analysis_info']['average_confidence']:.1f}%"
        )
        logger.info(
            f"- Confidence range: {data['analysis_info']['min_confidence']:.1f}%"
            f" - {data['analysis_info']['max_confidence']:.1f}%"
        )
        logger.info(f"Saved JSON tracklist to: {output_file}")
        return output_file

    def _save_markdown(self) -> Path:
        """Save tracks as Markdown file."""
        output_file = self.output_dir / self._format_filename("md")

        with open(output_file, "w", encoding="utf-8") as f:
            # Write header
            f.write(f"# {self.mix_info.get('title', 'Unknown Mix')}\n\n")

            if self.mix_info.get("artist"):
                f.write(f"**Artist:** {self.mix_info['artist']}\n")
            if self.mix_info.get("date"):
                f.write(f"**Date:** {self.mix_info['date']}\n")
            f.write("\n## Tracklist\n\n")

            # Write tracks
            for i, track in enumerate(self.tracks, 1):
                f.write(
                    f"{i}. **{track.time_in_mix}** - {track.artist} - {track.song_name}"
                )
                if track.confidence < 80:
                    f.write(f" _(Confidence: {track.confidence:.0f}%)_")
                f.write("\n")

        logger.info(f"Saved Markdown tracklist to: {output_file}")
        return output_file

    def _save_m3u(self) -> Path:
        """Save a playable, self-contained M3U playlist.

        Each entry points at the single audio file in the subfolder and uses
        VLC's ``#EXTVLCOPT:start-time`` for per-track seeking (the standard
        way to seek within one file in M3U; works in VLC, the natural player
        for DJ mixes). EXTINF duration is the gap to the next track's start;
        the last track's duration is ``total_duration - last_start`` (or -1
        when total_duration is unknown, which VLC/players treat as live).
        """
        output_file = self.output_dir / self._format_filename("m3u")
        audio_filename = self.mix_info.get("audio_filename", "")
        total_duration = self.mix_info.get("total_duration", 0) or 0

        # Precompute start offsets; time_in_mix is "H+:MM:SS" (hours unbounded).
        starts = [self._time_in_mix_to_seconds(t.time_in_mix) for t in self.tracks]

        with open(output_file, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")

            for i, track in enumerate(self.tracks):
                start = starts[i]
                # Duration = gap to next track; last track uses the remainder.
                if i + 1 < len(starts):
                    duration = starts[i + 1] - start
                elif total_duration > 0:
                    duration = total_duration - start
                else:
                    duration = -1

                f.write(f"#EXTINF:{int(duration)},{track.artist} - {track.song_name}\n")
                if start > 0:
                    f.write(f"#EXTVLCOPT:start-time={int(start)}\n")
                if audio_filename:
                    f.write(f"{audio_filename}\n")

        logger.info(f"Saved M3U playlist to: {output_file}")
        return output_file

    @staticmethod
    def _time_in_mix_to_seconds(time_in_mix: str) -> float:
        """Parse an "H+:MM:SS" timestamp (hours unbounded) to seconds.

        Tolerant of missing hours (``MM:SS``). Returns 0 on any parse
        failure rather than raising — a malformed timestamp should not
        abort the whole playlist.
        """
        parts = str(time_in_mix).split(":")
        try:
            nums = [float(p) for p in parts]
        except ValueError:
            return 0.0
        if len(nums) == 3:
            return nums[0] * 3600 + nums[1] * 60 + nums[2]
        if len(nums) == 2:
            return nums[0] * 60 + nums[1]
        if len(nums) == 1:
            return nums[0]
        return 0.0

    def save_all(self) -> List[Path]:
        """
        Save tracks in all available formats.

        Returns:
            List of paths to saved files
        """
        formats = ["json", "markdown", "m3u"]
        saved_files = []

        try:
            for format_type in formats:
                try:
                    if path := self.save(format_type):
                        saved_files.append(path)
                    else:
                        logger.error(f"Failed to save {format_type} format")
                except Exception as e:
                    logger.error(f"Error saving {format_type} format: {e}")
                    continue

            if not saved_files:
                raise ExportError("Failed to save tracks in any format")

            logger.info(f"Successfully saved tracklist in {len(saved_files)} formats")
            return saved_files

        except Exception as e:
            logger.error(f"Error in save_all: {e}")
            return []
