"""
Track identification helper functions and utilities.
"""

import hashlib
import logging
import os
import math
from typing import Dict, Optional, List
from datetime import timedelta
import sys

from mutagen import File

from .config import TrackIdentificationConfig, get_config
from .providers.factory import create_provider_factory, ProviderFactory
from .providers.base import TrackIdentificationProvider, ProviderError, IdentificationError, AuthenticationError, RateLimitError
from .track import Track, TrackMatcher
from .cache import Cache, get_cache
from .rate_limiter import RateLimiter, get_rate_limiter

logger = logging.getLogger(__name__)

def get_audio_info(audio_path: str) -> File:
    """Get audio file metadata."""
    return File(audio_path)

def format_duration(duration: float) -> str:
    """Format duration in seconds to HH:MM:SS."""
    hours = int(duration // 3600)
    minutes = int((duration % 3600) // 60)
    seconds = int(duration % 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def create_progress_bar(progress: float, width: int = 30) -> str:
    """Create a progress bar string."""
    filled_length = int(width * progress / 100)
    bar = '█' * filled_length + '░' * (width - filled_length)
    return bar

class ProgressDisplay:
    """Handles the progress display for track identification."""
    
    def __init__(self):
        self.last_lines = 0
        self.last_status = ""
        self.last_progress = 0
        self.GREEN = '\033[92m'
        self.RESET = '\033[0m'
    
    def clear_previous(self):
        """Clear all previous output lines."""
        if self.last_lines > 0:
            # Move up to the start of previous output and clear each line
            for _ in range(self.last_lines):
                print('\033[1A\033[K', end='', flush=True)
    
    def update(self, current: int, total: int, start_time: float, end_time: float, 
              segment_size: float, status: str = ""):
        """Update the progress display."""
        # Calculate progress
        progress = (current) / total * 100
        
        # Skip update if nothing has changed
        if status == self.last_status and progress == self.last_progress:
            return
            
        self.last_status = status
        self.last_progress = progress
        
        # Clear previous output
        self.clear_previous()
        
        # Format progress bar
        bar_width = 30
        filled_length = int(bar_width * progress // 100)
        bar = '█' * filled_length + '░' * (bar_width - filled_length)
        
        # Format segment information
        segment_info = f"Segment {current}/{total}"
        
        # Prepare output lines
        lines = [
            f"\r{self.GREEN}INFO{self.RESET} Progress: [{current}/{total}] {bar} {progress:.1f}%",
            f"{self.GREEN}INFO{self.RESET} Time: {format_duration(start_time)} - {format_duration(end_time)}",
            f"{self.GREEN}INFO{self.RESET} Size: {segment_size:.1f} MB",
            f"{self.GREEN}INFO{self.RESET} Status: {segment_info} - {status}"
        ]
        
        # Print all lines
        print('\n'.join(lines), end='', flush=True)
        
        # Store number of lines printed
        self.last_lines = len(lines)

class IdentificationManager:
    """Manages track identification using configured providers."""
    
    def __init__(self, config: TrackIdentificationConfig = None, provider_factory: ProviderFactory = None):
        """Initialize identification manager."""
        logger.info("Initializing track identification system...")
        
        logger.info("├─ Loading configuration...")
        self.config = config or get_config()
        
        logger.info("├─ Setting up provider factory...")
        self.provider_factory = provider_factory or create_provider_factory(self.config)
        
        logger.info("├─ Initializing cache system...")
        self.cache = get_cache()
        
        logger.info("├─ Setting up rate limiter...")
        self.rate_limiter = get_rate_limiter()
        
        logger.info("└─ Creating track matcher...")
        self.track_matcher = TrackMatcher()
        
        logger.info("Track identification system ready.")

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
            # Get audio duration and calculate segments
            audio_info = get_audio_info(audio_path)
            duration = audio_info.info.length
            segment_length = self.config.segment_length
            total_segments = math.ceil(duration / segment_length)
            file_size = os.path.getsize(audio_path) / (1024 * 1024)  # Convert to MB

            # Log initial setup
            logger.info("Starting audio analysis:")
            logger.info(f"├─ Duration: {format_duration(duration)}")
            logger.info(f"├─ Segment length: {segment_length} seconds")
            logger.info(f"├─ Total segments: {total_segments}")
            logger.info(f"└─ File size: {file_size:.1f} MB")
            logger.info("")

            identified_tracks = []
            providers = self._get_providers_in_priority()
            progress = ProgressDisplay()
            
            for i in range(total_segments):
                start_time = i * segment_length
                end_time = min((i + 1) * segment_length, duration)
                
                # Calculate segment size
                start_bytes = int(start_time / duration * os.path.getsize(audio_path))
                end_bytes = int(end_time / duration * os.path.getsize(audio_path))
                segment_size = (end_bytes - start_bytes) / (1024 * 1024)  # Convert to MB
                
                # Try each provider in priority order
                result = None
                last_error = None
                
                for provider in providers:
                    try:
                        # Update progress with current status
                        progress.update(i + 1, total_segments, start_time, end_time, segment_size,
                                     f"Using {provider.__class__.__name__}")
                        
                        result = await self._identify_segment(
                            audio_path, provider, start_time, start_bytes, end_bytes
                        )
                        if result:
                            break
                    except Exception as e:
                        last_error = e
                        continue
                
                if last_error and not result:
                    progress.update(i + 1, total_segments, start_time, end_time, segment_size,
                                 f"No match found")
                    continue

                # Process identification result
                if result and result.get('metadata', {}).get('music'):
                    for music in result['metadata']['music']:
                        track = Track(
                            song_name=music['title'],
                            artist=music['artists'][0]['name'],
                            time_in_mix=format_duration(start_time),
                            confidence=float(music['score'])
                        )
                        self.track_matcher.add_track(track)
                        identified_tracks.append(track)
                        
                        # Update progress with found track
                        progress.update(i + 1, total_segments, start_time, end_time, segment_size,
                                     f"Found: {track.song_name} by {track.artist}")
                        
                        # Log the found track
                        logger.info(f"Found track: {track.song_name} by {track.artist}")

            # Add newline after progress display
            print("\n")

            # Log identification completion
            logger.info("Identification complete:")
            logger.info(f"- Segments analyzed: {total_segments}")
            logger.info(f"- Raw tracks identified: {len(identified_tracks)}")
            
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
        primary_provider_name = self.config.primary_provider
        primary = self.provider_factory.get_identification_provider(primary_provider_name)
        if primary:
            providers.append(primary)
            logger.info(f"Using {primary_provider_name} as primary provider")
        else:
            logger.error(f"Primary provider {primary_provider_name} not found")
            return []
        
        # Add fallback providers if enabled
        if self.config.fallback_enabled:
            logger.info("Provider fallback is enabled")
            for provider_name in self.config.fallback_providers:
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
        # Generate cache key using both time and byte positions for better granularity
        cache_key = hashlib.md5(
            f"{audio_path}:{start_time}:{start_bytes}:{end_bytes}:{provider.__class__.__name__}".encode()
        ).hexdigest()
        
        # Check cache first
        if self.config.cache_enabled:
            try:
                cached = self.cache.get(cache_key)
                if cached:
                    logger.debug(f"Cache hit for segment at {start_time}s using {provider.__class__.__name__}")
                    return cached
            except Exception as e:
                logger.warning(f"Cache error: {e}")
        
        # Rate limit check
        if self.config.rate_limit_enabled:
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
            if result and self.config.cache_enabled:
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
