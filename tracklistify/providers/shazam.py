"""Shazam track identification provider using shazamio."""

# Standard library imports
from typing import Any, Dict, Optional

# Third-party imports
from shazamio import Shazam

from tracklistify.providers.base import TrackIdentificationProvider

# Local/package imports
from tracklistify.utils.logger import get_logger

logger = get_logger(__name__)


class ShazamProvider(TrackIdentificationProvider):
    """Shazam track identification provider."""

    def __init__(self):
        self.shazam = Shazam()

    async def identify_track(self, audio_segment) -> Optional[Dict[str, Any]]:
        """Identify track from an audio segment."""
        try:
            logger.info(f"Identifying segment at {audio_segment.start_time}s")

            # Ensure the audio file path is valid
            if not hasattr(audio_segment, "file_path") or not audio_segment.file_path:
                logger.error("Audio segment is missing 'file_path' attribute.")
                return None

            # Perform track recognition using the updated method
            result = await self.shazam.recognize(audio_segment.file_path)
            logger.debug(f"Shazam response: {result}")

            if not result or "matches" not in result:
                logger.warning("No matches found in Shazam response.")
                return None

            # The track information is directly in the response
            if "track" not in result:
                logger.info("No track information found in Shazam response.")
                return None

            track_info = result["track"]

            # Calculate confidence score based on the best match
            best_score = 0.0
            for match in result.get("matches", []):
                freq_skew = abs(match.get("frequencyskew", 0))
                time_skew = abs(match.get("timeskew", 0))

                # Convert skews to a 0-100 score where lower skew = higher score
                freq_score = 100 * (1 - min(freq_skew, 0.1) / 0.1)  # Cap at 0.1
                time_score = 100 * (1 - min(time_skew, 0.1) / 0.1)  # Cap at 0.1

                # Combine scores with weights
                match_score = (
                    freq_score * 0.6 + time_score * 0.4
                )  # Weight frequency more
                best_score = max(best_score, match_score)

            return {
                "metadata": {
                    "music": [
                        {
                            "title": track_info.get("title", "Unknown Title"),
                            "artists": [
                                {"name": track_info.get("subtitle", "Unknown Artist")}
                            ],
                            "score": best_score,
                        }
                    ]
                }
            }

        except Exception as e:
            logger.error(f"Error during track identification: {e}")
            return None

    async def enrich_metadata(self, track_info: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich track metadata with additional information."""
        # Implement any additional metadata enrichment if necessary
        return track_info

    async def close(self):
        """Cleanup resources."""
        # Shazam object does not have a close method; nothing to clean up
        logger.debug("ShazamProvider cleanup called, no resources to close.")
        pass
