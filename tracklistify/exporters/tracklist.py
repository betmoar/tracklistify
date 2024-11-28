"""
Output formatting and file handling for Tracklistify.
"""

# Standard library imports
import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Local/package imports
from tracklistify.config import get_config
from tracklistify.core.exceptions import ExportError
from tracklistify.core.track import Track
from tracklistify.utils.logger import logger


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
        self.output_dir = Path(self._config.output_dir)
        self.output_dir.mkdir(exist_ok=True)

    def _format_filename(self, extension: str) -> str:
        """
        Generate filename in format: [YYYYMMDD] Artist - Description.extension

        Args:
            extension: File extension without dot

        Returns:
            Formatted filename
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
            # Replace invalid filename characters with spaces
            s = re.sub(r'[<>:"/\\|?*@]', " ", s)
            # Replace multiple spaces with single space
            s = re.sub(r"\s+", " ", s)
            # Strip leading/trailing spaces
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

        # Format filename
        return f"[{mix_date}] {artist} - {description}.{extension}"

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
        avg_confidence = 0
        min_confidence = 0
        max_confidence = 0

        if track_count > 0:
            confidences = [
                t.confidence for t in self.tracks if hasattr(t, "confidence")
            ]
            if confidences:
                avg_confidence = sum(confidences) / len(confidences)
                min_confidence = min(confidences)
                max_confidence = max(confidences)

        data = {
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
                }
                for track in self.tracks
            ],
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

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
        """Save tracks as M3U playlist."""
        output_file = self.output_dir / self._format_filename("m3u")

        with open(output_file, "w", encoding="utf-8") as f:
            f.write("#EXTM3U\n")

            for track in self.tracks:
                duration = getattr(track, "duration", -1)
                f.write(f"#EXTINF:{duration},{track.artist} - {track.song_name}\n")
                # Note: We don't have actual file paths, add comment with time in mix
                f.write(f"# Time in mix: {track.time_in_mix}\n")

        logger.info(f"Saved M3U playlist to: {output_file}")
        return output_file

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
