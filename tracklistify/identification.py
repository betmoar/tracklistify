"""
Track identification helper functions and utilities.
"""

import hashlib
import logging
import os
from typing import Dict, Optional, List
from datetime import timedelta

from mutagen import File

from .config import Config, get_config
from .providers.factory import create_provider_factory, ProviderFactory
from .providers.base import TrackIdentificationProvider, ProviderError, IdentificationError, AuthenticationError, RateLimitError
from .track import Track, TrackMatcher
from .cache import Cache, get_cache
from .rate_limiter import RateLimiter, get_rate_limiter

logger = logging.getLogger(__name__)


class IdentificationManager:
    """Manages track identification using configured providers."""
    
    def __init__(self, config: Config = None, provider_factory: ProviderFactory = None):
        """Initialize identification manager."""
        self.config = config or get_config()
        self.provider_factory = provider_factory or create_provider_factory(self.config)
        self.cache = get_cache()
        self.rate_limiter = get_rate_limiter()
        self.track_matcher = TrackMatcher()

    async def identify_tracks(self, audio_path: str) -> List[Track]:
        """
        Identify tracks in an audio file using configured providers.
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            List[Track]: List of identified tracks
            
        Raises:
            IdentificationError: If track identification fails
        """
        try:
            # Get providers in priority order
            providers = self._get_providers_in_priority()
            if not providers:
                raise IdentificationError("No identification providers configured")
            
            # Get audio file metadata
            audio = File(audio_path)
            if audio is None:
                raise IdentificationError("Failed to read audio file metadata")
                
            total_length = audio.info.length
            segment_length = self.config.track.segment_length
            total_segments = int(total_length // segment_length)
            
            # Log identification start
            total_time_str = str(timedelta(seconds=int(total_length)))
            logger.info(f"Starting track identification...")
            logger.info(f"Total length: {total_time_str}")
            logger.info(f"Total segments to analyze: {total_segments}")
            logger.info(f"Segment length: {segment_length} seconds")
            
            identified_count = 0
            
            # Calculate audio file metrics
            audio_size = os.path.getsize(audio_path)
            bytes_per_second = audio_size / total_length
            
            # Process each segment
            for i in range(total_segments):
                start_time = i * segment_length
                # Format time as HH:MM:SS
                hours = int(start_time // 3600)
                minutes = int((start_time % 3600) // 60)
                seconds = int(start_time % 60)
                time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                logger.info(f"Analyzing segment {i+1}/{total_segments} at {time_str}...")
                
                # Get segment data
                start_bytes = int((start_time / total_length) * audio_size)
                end_bytes = int(((start_time + segment_length) / total_length) * audio_size)
                
                # Try each provider in priority order
                result = None
                last_error = None
                
                for provider in providers:
                    try:
                        result = await self._identify_segment(
                            audio_path=audio_path,
                            provider=provider,
                            start_time=start_time,
                            start_bytes=start_bytes,
                            end_bytes=end_bytes
                        )
                        if result and result.get('metadata', {}).get('music'):
                            logger.debug(f"Successfully identified segment with provider {provider.__class__.__name__}")
                            break
                    except (AuthenticationError, RateLimitError) as e:
                        # Critical errors - remove provider from list
                        logger.error(f"Provider {provider.__class__.__name__} error: {e}")
                        providers.remove(provider)
                        if not providers:
                            raise IdentificationError("All providers failed with critical errors")
                    except ProviderError as e:
                        # Non-critical error - try next provider
                        logger.warning(f"Provider {provider.__class__.__name__} error: {e}")
                        last_error = e
                
                if not result and last_error:
                    logger.error(f"All providers failed for segment {i+1}: {last_error}")
                    continue
                
                if result and result.get('metadata', {}).get('music'):
                    for music in result['metadata']['music']:
                        track = Track(
                            song_name=music['title'],
                            artist=music['artists'][0]['name'],
                            time_in_mix=time_str,
                            confidence=float(music['score'])
                        )
                        self.track_matcher.add_track(track)
                        identified_count += 1
                        logger.info(f"Found track: {track.song_name} by {track.artist} (Confidence: {track.confidence:.1f}%)")
                else:
                    logger.debug(f"No music detected in segment {i+1}")
            
            # Log identification completion
            logger.info(f"\nTrack identification completed:")
            logger.info(f"- Segments analyzed: {total_segments}")
            logger.info(f"- Raw tracks identified: {identified_count}")
            
            # Merge nearby tracks and return
            merged_tracks = self.track_matcher.merge_nearby_tracks()
            logger.info(f"- Final unique tracks after merging: {len(merged_tracks)}")
            
            return merged_tracks
            
        except Exception as e:
            raise IdentificationError(f"Track identification failed: {str(e)}")

    def _get_providers_in_priority(self) -> List[TrackIdentificationProvider]:
        """Get track identification providers in priority order."""
        providers = []
        
        # Add primary provider first
        primary_provider_name = self.config.providers.primary_provider
        primary = self.provider_factory.get_identification_provider(primary_provider_name)
        if primary:
            providers.append(primary)
            logger.info(f"Using {primary_provider_name} as primary provider")
        else:
            logger.error(f"Primary provider {primary_provider_name} not found")
            return []
        
        # Add fallback providers if enabled
        if self.config.providers.fallback_enabled:
            logger.info("Provider fallback is enabled")
            for provider_name in self.config.providers.fallback_providers:
                if provider_name != primary_provider_name:  # Skip if it's the primary provider
                    provider = self.provider_factory.get_identification_provider(provider_name)
                    if provider:
                        providers.append(provider)
                        logger.info(f"Added {provider_name} as fallback provider")
                    else:
                        logger.warning(f"Fallback provider {provider_name} not found")
        else:
            logger.info("Provider fallback is disabled")
        
        return providers

    async def _identify_segment(
        self,
        audio_path: str,
        provider: TrackIdentificationProvider,
        start_time: float,
        start_bytes: int,
        end_bytes: int
    ) -> Optional[Dict]:
        """
        Identify a single audio segment.
        
        Args:
            audio_path: Path to audio file
            provider: Track identification provider
            start_time: Start time in seconds
            start_bytes: Start position in bytes
            end_bytes: End position in bytes
            
        Returns:
            Optional[Dict]: Provider response if successful, None otherwise
        """
        # Generate cache key
        cache_key = hashlib.md5(
            f"{audio_path}:{start_time}:{provider.__class__.__name__}".encode()
        ).hexdigest()
        
        # Check cache first
        if self.config.cache.enabled:
            try:
                cached = self.cache.get(cache_key)
                if cached:
                    logger.debug(f"Cache hit for segment at {start_time}s using {provider.__class__.__name__}")
                    return cached
            except Exception as e:
                logger.warning(f"Cache error: {e}")
        
        # Rate limit check
        if self.config.app.rate_limit_enabled:
            if not self.rate_limiter.acquire(timeout=30):
                raise ProviderError("Rate limit exceeded")
        
        try:
            # Read segment data
            with open(audio_path, 'rb') as f:
                f.seek(start_bytes)
                segment_data = f.read(end_bytes - start_bytes)
            
            # Log provider being used
            logger.info(f"Identifying segment at {start_time}s using {provider.__class__.__name__}")
            
            # Identify segment
            result = await provider.identify_track(segment_data, start_time)
            
            # Cache result if successful
            if result and self.config.cache.enabled:
                try:
                    self.cache.set(cache_key, result)
                except Exception as e:
                    logger.warning(f"Failed to cache result: {e}")
            
            return result
            
        except Exception as e:
            raise ProviderError(f"Failed to identify segment with {provider.__class__.__name__}: {str(e)}")

    async def close(self) -> None:
        """Close all resources."""
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
