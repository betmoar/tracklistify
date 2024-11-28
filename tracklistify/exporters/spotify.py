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
            # Create playlist
            playlist_id = await self._create_playlist(playlist_name)

            # Get Spotify track IDs
            track_ids = []
            for track in tracks:
                if not track.metadata.get("spotify_id"):
                    # Try to find track on Spotify
                    spotify_info = await self.spotify.search_track(
                        track.song_name, track.artist, None, None  # album  # duration
                    )
                    if spotify_info:
                        track_ids.append(spotify_info["spotify_id"])
                else:
                    track_ids.append(track.metadata["spotify_id"])

            if not track_ids:
                raise ExportError("No tracks found on Spotify")

            # Add tracks to playlist
            await self._add_tracks_to_playlist(playlist_id, track_ids)

            # Return playlist URL
            return f"https://open.spotify.com/playlist/{playlist_id}"

        except Exception as e:
            raise ExportError(f"Failed to export playlist: {str(e)}")

    async def _create_playlist(self, name: str) -> str:
        """Create a new Spotify playlist."""
        endpoint = f"{self.spotify.API_BASE}/me/playlists"

        data = {"name": name, "description": "Created by Tracklistify", "public": True}

        async with self.spotify._session.post(
            endpoint, headers=await self.spotify._get_auth_headers(), json=data
        ) as response:
            if response.status == 201:
                playlist = await response.json()
                return playlist["id"]
            else:
                raise ExportError(f"Failed to create playlist: {response.status}")

    async def _add_tracks_to_playlist(self, playlist_id: str, track_ids: List[str]):
        """Add tracks to a Spotify playlist."""
        endpoint = f"{self.spotify.API_BASE}/playlists/{playlist_id}/tracks"

        # Spotify API limits: max 100 tracks per request
        for i in range(0, len(track_ids), 100):
            batch = track_ids[i : i + 100]
            uris = [f"spotify:track:{track_id}" for track_id in batch]

            async with self.spotify._session.post(
                endpoint,
                headers=await self.spotify._get_auth_headers(),
                json={"uris": uris},
            ) as response:
                if response.status != 201:
                    raise ExportError(
                        f"Failed to add tracks to playlist: {response.status}"
                    )
