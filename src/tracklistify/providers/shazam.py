"""Shazam track identification provider using shazamio."""

# Standard library imports
import asyncio
from typing import Any, Dict, Optional

# Third-party imports
from shazamio import Shazam

from tracklistify.core.exceptions import ShazamError
from tracklistify.providers.base import TrackIdentificationProvider

# Local/package imports
from tracklistify.utils.constants import SHAZAM_SKEW_CAP
from tracklistify.utils.logger import get_logger
from tracklistify.config.factory import get_config

logger = get_logger(__name__)


class ShazamProvider(TrackIdentificationProvider):
    """Shazam track identification provider."""

    def __init__(self):
        self.shazam = Shazam()
        self._config = get_config()

    async def identify_track(self, audio_segment) -> Optional[Dict[str, Any]]:
        """Identify track from an audio segment."""
        try:
            # Brief cooldown to avoid hammering upstream between calls
            try:
                cooldown = float(getattr(self._config, "shazam_cooldown_seconds", 2.25))
            except (ValueError, AttributeError, TypeError) as e:
                logger.debug(f"Failed to get cooldown config, using default: {e}")
                cooldown = 2.25
            if cooldown and cooldown > 0:
                await asyncio.sleep(cooldown)
            # Debug: one line per segment with no outcome attached is pure
            # noise at default verbosity (74 segments -> 74 lines saying
            # nothing). Progress is reported by ProgressDisplay; outcomes by
            # add_track.
            logger.debug(f"Identifying segment at {audio_segment.start_time}s")

            # Ensure the audio file path is valid
            if not hasattr(audio_segment, "file_path") or not audio_segment.file_path:
                logger.error("Audio segment is missing 'file_path' attribute.")
                return None

            # Perform track recognition using the updated method
            proxy = getattr(self._config, "shazam_proxy", "") or None
            result = await self.shazam.recognize(audio_segment.file_path, proxy=proxy)
            logger.debug(f"Shazam response: {result}")

            # An unmatched segment is the NORMAL case, not a fault: a DJ mix
            # is full of unreleased IDs, mashups and long transitions that
            # Shazam legitimately cannot place. Logging it above debug
            # drowns the run in noise and inverts the signal — the operator
            # sees a wall of failures while the successes (logged at INFO by
            # TrackMatcher.add_track) scroll past unnoticed. Genuine faults
            # here raise ShazamError; these two are just "no match".
            if not result or "matches" not in result:
                logger.debug("No matches found in Shazam response.")
                return None

            # The track information is directly in the response
            if "track" not in result:
                logger.debug("No track information found in Shazam response.")
                return None

            track_info = result["track"]

            # Calculate confidence score based on the best match
            best_score = 0.0
            for match in result.get("matches", []):
                freq_skew = abs(match.get("frequencyskew", 0))
                time_skew = abs(match.get("timeskew", 0))

                # Convert skews to a 0-100 score where lower skew = higher score
                freq_score = 100 * (
                    1 - min(freq_skew, SHAZAM_SKEW_CAP) / SHAZAM_SKEW_CAP
                )
                time_score = 100 * (
                    1 - min(time_skew, SHAZAM_SKEW_CAP) / SHAZAM_SKEW_CAP
                )

                # Combine scores with weights
                match_score = (
                    freq_score * 0.6 + time_score * 0.4
                )  # Weight frequency more
                best_score = max(best_score, match_score)

            # shazamio's raw track payload carries far more than title/subtitle
            # (isrc, genre, album/label/year, Apple Music id, artwork) -- surface
            # it here in the same shape the ACRCloud provider already uses, so
            # utils.identification can thread it into Track.metadata generically.
            #
            # Every lookup below is `or {}` / `or []` rather than a .get()
            # default: these keys are frequently present with an explicit
            # JSON null, and `.get("k", {})` returns the default only when
            # the key is ABSENT — a null yields None and the next .get()
            # raises AttributeError. That would turn a cosmetic metadata
            # gap into a failed identification for the whole segment.
            section_metadata = {}
            for section in track_info.get("sections") or []:
                for item in section.get("metadata") or []:
                    label = item.get("title")
                    if label:
                        section_metadata[label] = item.get("text")

            hub = track_info.get("hub") or {}

            apple_music_id = None
            for action in hub.get("actions") or []:
                if action.get("type") == "applemusicplay":
                    apple_music_id = action.get("id")
                    break

            # ``hub.providers`` carries per-platform deeplinks Shazam ships
            # with the match — free, no extra API call. Keyed off each
            # provider's ``type`` rather than a positional index: shazamio's
            # own factory hardcodes providers[0].actions[0], which silently
            # returns the wrong platform's link the moment Shazam reorders
            # the array.
            #
            # These are SEARCH deeplinks (``spotify:search:<artist> <title>``),
            # not canonical track URLs — Shazam does not resolve a Spotify
            # track id. Exposed under ``*_search_uri`` so the name cannot be
            # mistaken for a direct link; resolving to a real track id needs
            # the Spotify API (see BACKLOG P2).
            provider_uris = {}
            for prov in hub.get("providers") or []:
                prov_type = (prov.get("type") or "").strip().lower()
                if not prov_type:
                    continue
                for action in prov.get("actions") or []:
                    uri = action.get("uri")
                    if uri:
                        provider_uris.setdefault(prov_type, uri)
                        break

            images = track_info.get("images") or {}
            primary_genre = (track_info.get("genres") or {}).get("primary")

            return {
                "metadata": {
                    "music": [
                        {
                            "title": track_info.get("title", "Unknown Title"),
                            "artists": [
                                {"name": track_info.get("subtitle", "Unknown Artist")}
                            ],
                            "score": best_score,
                            "external_ids": {"isrc": track_info.get("isrc")},
                            "genres": [{"name": primary_genre}]
                            if primary_genre
                            else [],
                            "album": section_metadata.get("Album"),
                            "label": section_metadata.get("Label"),
                            "release_date": section_metadata.get("Released"),
                            "shazam_id": track_info.get("key"),
                            "apple_music_id": apple_music_id,
                            "artwork_url": images.get("coverarthq")
                            or images.get("coverart"),
                            "shazam_url": track_info.get("url"),
                            "spotify_search_uri": provider_uris.get("spotify"),
                            "deezer_search_uri": provider_uris.get("deezer"),
                        }
                    ]
                }
            }

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Shazam identification failed: {e}")
            raise ShazamError(f"Shazam identification failed: {e}", cause=e) from e

    async def enrich_metadata(self, track_info: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich track metadata with additional information."""
        # Implement any additional metadata enrichment if necessary
        return track_info

    async def close(self) -> None:
        """Cleanup resources."""
        # Shazam object does not have a close method; nothing to clean up
        logger.debug("ShazamProvider cleanup called, no resources to close.")
