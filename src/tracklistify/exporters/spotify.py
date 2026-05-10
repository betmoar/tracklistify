"""Spotify playlist exporter implementation."""

# Standard library imports
from datetime import datetime
from typing import List, Optional

# Local/package imports
from tracklistify.config import get_config
from tracklistify.core.exceptions import AuthenticationError, ExportError
from tracklistify.core.track import Track
from tracklistify.providers.spotify import SpotifyProvider


class SpotifyPlaylistExporter:
    """Exports identified tracks to Spotify playlists."""

    def __init__(self, spotify_provider: Optional[SpotifyProvider] = None):
        """
        Initialize Spotify playlist exporter.

        Args:
            spotify_provider: Optional SpotifyProvider instance. If not provided,
                            will attempt to create one using environment variables.
        """
        self.spotify = spotify_provider
        self._config = get_config()

    async def export_playlist(
        self, tracks: List[Track], playlist_name: Optional[str] = None
    ) -> str:
        """
        Export tracks to a Spotify playlist.

        Args:
            tracks: List of identified tracks to export
            playlist_name: Optional custom playlist name. If not provided,
                         will generate one based on current date

        Returns:
            str: URL of the created Spotify playlist

        Raises:
            ExportError: If playlist creation or track addition fails
            AuthenticationError: If Spotify authentication fails
        """
        if not self.spotify:
            raise AuthenticationError("Spotify provider not configured")

        # Generate playlist name if not provided
        if not playlist_name:
            date_str = datetime.now().strftime("%Y-%m-%d")
            playlist_name = f"Tracklistify Mix - {date_str}"

        try:
            playlist_id = await self.spotify.create_playlist(playlist_name)

            # Resolve Spotify track IDs (use cached metadata when present)
            track_ids = []
            for track in tracks:
                spotify_id = track.metadata.get("spotify_id")
                if spotify_id:
                    track_ids.append(spotify_id)
                    continue
                spotify_info = await self.spotify.search_track(
                    track.song_name, track.artist
                )
                if spotify_info:
                    track_ids.append(spotify_info["spotify_id"])

            if not track_ids:
                raise ExportError("No tracks found on Spotify")

            await self.spotify.add_tracks_to_playlist(playlist_id, track_ids)
            return f"https://open.spotify.com/playlist/{playlist_id}"

        except ExportError:
            raise
        except Exception as e:
            raise ExportError(f"Failed to export playlist: {e}") from e
