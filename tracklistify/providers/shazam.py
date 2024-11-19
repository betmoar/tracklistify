"""Shazam track identification provider using shazamio."""

import logging
import io
import asyncio
import random
from typing import Dict, Optional, Any
import aiohttp
from aiohttp import ClientTimeout
from shazamio import Shazam
from pydub import AudioSegment
from .base import TrackIdentificationProvider, IdentificationError, AuthenticationError, RateLimitError, ProviderError

logger = logging.getLogger(__name__)

class ShazamProvider(TrackIdentificationProvider):
    """Shazam track identification provider."""
    
    def __init__(self, timeout: int = 10, max_retries: int = 3):
        """Initialize Shazam provider.
        
        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for failed requests
        """
        self.timeout = ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None
        self.shazam = None
        self._lock = asyncio.Lock()
        self._last_request_time = 0
        self._min_request_interval = 1.0  # Minimum time between requests in seconds
        self.max_retries = max_retries
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
            self.shazam = Shazam()
        return self._session

    async def close(self) -> None:
        """Close the provider's resources."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            self.shazam = None
    
    async def _retry_with_backoff(self, func: Any, *args, **kwargs) -> Any:
        """Execute a function with exponential backoff retry logic.
        
        Args:
            func: Async function to execute
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function
            
        Returns:
            Result from the function
            
        Raises:
            The last error encountered after all retries are exhausted
        """
        last_error = None
        for attempt in range(self.max_retries):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if "URL is invalid" not in str(e):
                    raise
                
                # Exponential backoff with jitter
                await self.close()  # Force new session
                delay = (2 ** attempt) + random.random()
                logger.warning(f"Retry attempt {attempt + 1}/{self.max_retries} after {delay:.2f}s delay")
                await asyncio.sleep(delay)
                continue
                
        raise last_error
    
    def _prepare_audio_data(self, audio_data: bytes, start_time: float = 0) -> bytes:
        """Prepare audio data for Shazam recognition."""
        try:
            audio = AudioSegment.from_file(io.BytesIO(audio_data))
            wav_data = io.BytesIO()
            audio = audio.set_channels(2)  # Convert to stereo
            audio = audio.set_frame_rate(44100)  # Set sample rate to 44.1kHz
            audio.export(wav_data, format='wav', parameters=["-ac", "2", "-ar", "44100"])
            return wav_data.getvalue()
        except Exception as e:
            logger.error(f"Failed to prepare audio data: {e}")
            raise ProviderError(f"Failed to prepare audio data: {e}")
    
    async def _rate_limit(self):
        """Enforce rate limiting between requests."""
        now = asyncio.get_event_loop().time()
        if self._last_request_time > 0:
            time_since_last = now - self._last_request_time
            if time_since_last < self._min_request_interval:
                await asyncio.sleep(self._min_request_interval - time_since_last)
        self._last_request_time = asyncio.get_event_loop().time()
            
    async def identify_track(self, audio_data: bytes, start_time: float = 0) -> Dict:
        """Identify a track using Shazam."""
        async with self._lock:  # Ensure only one request at a time
            try:
                await self._rate_limit()
                session = await self._get_session()
                
                # Prepare audio data for Shazam
                processed_audio = self._prepare_audio_data(audio_data, start_time)
                
                # Use retry logic for recognition
                result = await self._retry_with_backoff(
                    self.shazam.recognize_song,
                    processed_audio
                )
                
                if not result:
                    raise IdentificationError("No response from Shazam")
                    
                if not result.get('track'):
                    return {
                        'status': {'code': 1, 'msg': 'No music detected'},
                        'metadata': {'music': []}
                    }
                
                track_info = result['track']
                
                # Calculate confidence based on metadata completeness
                metadata_completeness = sum([
                    bool(track_info.get('title')),
                    bool(track_info.get('subtitle')),
                    bool(track_info.get('sections', [{}])[0].get('metadata')),
                    bool(track_info.get('genres')),
                ]) / 4.0
                
                # Extract artists and album info
                artists = []
                album = ''
                release_date = ''
                genres = []
                
                for section in track_info.get('sections', []):
                    if section.get('type') == 'ARTIST':
                        artists.append({'name': section.get('name', 'Unknown')})
                    elif section.get('type') == 'ALBUM':
                        album = section.get('name', '')
                    elif section.get('type') == 'RELEASE':
                        release_date = section.get('name', '')
                    elif section.get('type') == 'GENRE':
                        genres = [{'name': g} for g in section.get('name', '').split(',')]
                
                # If no artists found, use subtitle as artist
                if not artists and track_info.get('subtitle'):
                    artists = [{'name': track_info['subtitle']}]
                
                track = {
                    'title': track_info.get('title', ''),
                    'artists': artists or [{'name': 'Unknown'}],
                    'album': album,
                    'release_date': release_date,
                    'score': metadata_completeness * 100,  # Convert to percentage
                    'genres': genres,
                    'external_ids': {
                        'shazam': track_info.get('key', ''),
                        'isrc': track_info.get('isrc', '')
                    }
                }
                
                return {
                    'status': {'code': 0, 'msg': 'Success'},
                    'metadata': {'music': [track]}
                }
                
            except aiohttp.ClientError as e:
                if "429" in str(e):
                    raise RateLimitError("Shazam rate limit exceeded")
                raise ProviderError(f"Shazam network error: {str(e)}")
            except Exception as e:
                if "unauthorized" in str(e).lower():
                    raise AuthenticationError("Shazam authentication failed")
                if "rate" in str(e).lower():
                    raise RateLimitError("Shazam rate limit exceeded")
                raise ProviderError(f"Shazam provider error: {str(e)}")

    async def enrich_metadata(self, track_info: Dict) -> Dict:
        """Enrich track metadata with additional Shazam information."""
        if not track_info.get('external_ids', {}).get('shazam'):
            return track_info
            
        async with self._lock:  # Ensure only one request at a time
            try:
                await self._rate_limit()
                session = await self._get_session()
                
                # Use retry logic for track details
                details = await self._retry_with_backoff(
                    self.shazam.track_about,
                    track_info['external_ids']['shazam']
                )
                
                # Extract additional audio features if available
                audio_features = {
                    'bpm': details.get('hub', {}).get('bpm', ''),
                    'key': details.get('hub', {}).get('key', ''),
                    'time_signature': details.get('hub', {}).get('timeSignature', ''),
                    'mode': details.get('hub', {}).get('mode', ''),
                    'danceability': details.get('hub', {}).get('danceability', ''),
                    'energy': details.get('hub', {}).get('energy', ''),
                }
                
                # Enrich with additional metadata
                track_info.update({
                    'album_art': details.get('images', {}).get('coverart', ''),
                    'isrc': details.get('hub', {}).get('isrc', ''),
                    'label': details.get('hub', {}).get('label', ''),
                    'audio_features': {**track_info.get('audio_features', {}), **audio_features},
                })
                
                return track_info
                
            except Exception as e:
                logger.warning(f"Failed to enrich metadata from Shazam: {str(e)}")
                return track_info
