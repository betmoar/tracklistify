"""Spotify metadata provider implementation."""

# Standard library imports
import asyncio
import base64
from typing import Dict, List, Optional

# Third-party imports
import aiohttp

from tracklistify.providers.base import (
    AuthenticationError,
    MetadataProvider,
    ProviderError,
    RateLimitError,
)

# Local/package imports
from tracklistify.utils.logger import get_logger

logger = get_logger(__name__)


class SpotifyProvider(MetadataProvider):
    """Spotify metadata provider for track information enrichment."""

    AUTH_URL = "https://accounts.spotify.com/api/token"
    API_BASE = "https://api.spotify.com/v1"

    def __init__(self, client_id: str, client_secret: str):
        """
        Initialize Spotify provider.

        Args:
            client_id: Spotify API client ID
            client_secret: Spotify API client secret
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token = None
        self._token_expiry = 0
        self._session = None

    async def _ensure_session(self):
        """Ensure aiohttp session exists."""
        if self._session is None:
            self._session = aiohttp.ClientSession()

    async def _get_access_token(self) -> str:
        """Get or refresh Spotify access token."""
        if self._access_token and self._token_expiry > asyncio.get_event_loop().time():
            return self._access_token

        auth_string = f"{self.client_id}:{self.client_secret}"
        auth_b64 = base64.b64encode(auth_string.encode()).decode()

        await self._ensure_session()
        async with self._session.post(
            self.AUTH_URL,
            headers={"Authorization": f"Basic {auth_b64}"},
            data={"grant_type": "client_credentials"},
        ) as response:
            if response.status == 401:
                raise AuthenticationError("Invalid Spotify credentials")
            elif response.status == 429:
                raise RateLimitError("Spotify rate limit exceeded")
            elif response.status != 200:
                raise ProviderError(f"Spotify authentication failed: {response.status}")

            data = await response.json()
            self._access_token = data["access_token"]
            self._token_expiry = asyncio.get_event_loop().time() + data["expires_in"]
            return self._access_token

    async def enrich_metadata(self, track_info: Dict) -> Dict:
        """Enrich track metadata with additional information."""
        # If we already have Spotify metadata, return as is
        if "spotify_id" in track_info:
            return track_info

        # Search for the track using available metadata
        title = track_info.get("title")
        artist = track_info.get("artist")
        album = track_info.get("album")
        duration = track_info.get("duration")

        if not title:
            return track_info

        try:
            spotify_info = await self.search_track(title, artist, album, duration)
            if spotify_info:
                track_info.update(spotify_info)
        except (RateLimitError, AuthenticationError):
            # Must propagate so callers can honor Retry-After / refresh tokens.
            raise
        except Exception as e:
            logger.warning(f"Failed to enrich metadata: {str(e)}")

        return track_info

    async def close(self) -> None:
        """Close the provider's resources."""
        if self._session:
            await self._session.close()
            self._session = None

    async def _api_request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """Make authenticated request to Spotify API.

        Accepts any 2xx response. Spotify's playlist mutation endpoints return
        201 (Created) on success and some return 204 (No Content) with an
        empty body; both are treated as success here. Returns the decoded
        JSON body when present, otherwise an empty dict.
        """
        await self._ensure_session()
        token = await self._get_access_token()

        headers = {"Authorization": f"Bearer {token}", **kwargs.pop("headers", {})}

        url = f"{self.API_BASE}/{endpoint}"
        async with self._session.request(
            method, url, headers=headers, **kwargs
        ) as response:
            if response.status == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                raise RateLimitError(
                    f"Spotify rate limit exceeded. Retry after {retry_after}s"
                )
            if response.status == 401:
                self._access_token = None
                raise AuthenticationError("Spotify token expired")
            if not 200 <= response.status < 300:
                raise ProviderError(f"Spotify API error: {response.status}")

            # 204 No Content (and similar empty-body responses) have no JSON
            if response.status == 204 or response.headers.get("Content-Length") == "0":
                return {}
            try:
                return await response.json()
            except aiohttp.ContentTypeError:
                return {}

    async def search_track(
        self,
        title: str,
        artist: Optional[str] = None,
        album: Optional[str] = None,
        duration: Optional[float] = None,
    ) -> Dict:
        """Search Spotify for the best match for the supplied track metadata.

        Signature matches the ``MetadataProvider`` ABC. The ``duration`` argument
        is accepted for ABC compliance but Spotify search does not take it as a
        query parameter; if needed for ranking it can be applied client-side.

        Args:
            title: Track title (required).
            artist: Artist name (optional).
            album: Album name (optional).
            duration: Track duration in seconds (optional, currently unused).

        Returns:
            Dict: Top-match track info with keys
            ``spotify_id``, ``name``, ``artists``, ``album``, ``release_date``.
            Empty dict if no match is found.
        """
        del duration  # unused; reserved for future client-side ranking
        parts = [f'track:"{title}"']
        if artist:
            parts.append(f'artist:"{artist}"')
        if album:
            parts.append(f'album:"{album}"')
        query = " ".join(parts)

        try:
            response = await self._api_request(
                "GET", "search", params={"q": query, "type": "track", "limit": 5}
            )
        except (RateLimitError, AuthenticationError):
            raise
        except Exception as e:
            raise ProviderError(f"Error searching for track: {e}") from e

        items = response.get("tracks", {}).get("items", [])
        if not items:
            return {}

        top = items[0]
        return {
            "spotify_id": top["id"],
            "name": top["name"],
            "artists": [a["name"] for a in top["artists"]],
            "album": top["album"]["name"],
            "release_date": top["album"]["release_date"],
        }

    async def get_track_details(self, track_id: str) -> Dict:
        """
        Get detailed track information from Spotify.

        Args:
            track_id: Spotify track ID

        Returns:
            Dict containing detailed track information
        """
        try:
            track = await self._api_request("GET", f"tracks/{track_id}")
            audio_features = await self._api_request(
                "GET", f"audio-features/{track_id}"
            )

            return {
                "id": track["id"],
                "name": track["name"],
                "artists": [artist["name"] for artist in track["artists"]],
                "album": track["album"]["name"],
                "release_date": track["album"]["release_date"],
                "duration_ms": track["duration_ms"],
                "popularity": track["popularity"],
                "preview_url": track["preview_url"],
                "external_urls": track["external_urls"],
                "audio_features": {
                    "tempo": audio_features["tempo"],
                    "key": audio_features["key"],
                    "mode": audio_features["mode"],
                    "time_signature": audio_features["time_signature"],
                    "danceability": audio_features["danceability"],
                    "energy": audio_features["energy"],
                    "loudness": audio_features["loudness"],
                },
            }

        except Exception as e:
            logger.error(f"Spotify track details error: {e}")
            raise

    async def create_playlist(
        self,
        name: str,
        description: str = "Created by Tracklistify",
        public: bool = True,
    ) -> str:
        """Create a new Spotify playlist.

        Args:
            name: Playlist name
            description: Playlist description
            public: Whether the playlist should be public

        Returns:
            Playlist ID

        Raises:
            ProviderError: If playlist creation fails
        """
        data = {"name": name, "description": description, "public": public}

        try:
            response = await self._api_request("POST", "me/playlists", json=data)
            return response["id"]
        except (RateLimitError, AuthenticationError):
            raise
        except Exception as e:
            raise ProviderError(f"Failed to create playlist: {e}") from e

    async def add_tracks_to_playlist(
        self, playlist_id: str, track_ids: List[str]
    ) -> None:
        """Add tracks to a Spotify playlist.

        Args:
            playlist_id: Spotify playlist ID
            track_ids: List of Spotify track IDs to add

        Raises:
            ProviderError: If adding tracks fails
        """
        # Spotify API limits: max 100 tracks per request
        for i in range(0, len(track_ids), 100):
            batch = track_ids[i : i + 100]
            uris = [f"spotify:track:{track_id}" for track_id in batch]

            try:
                await self._api_request(
                    "POST", f"playlists/{playlist_id}/tracks", json={"uris": uris}
                )
            except (RateLimitError, AuthenticationError):
                raise
            except Exception as e:
                raise ProviderError(f"Failed to add tracks to playlist: {e}") from e
