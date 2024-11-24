"""
Main entry point for Tracklistify.
"""

import argparse
import os
import asyncio
from datetime import timedelta
from typing import List, Optional

from .config import get_config
from .logger import logger
from .track import Track
from .downloaders import DownloaderFactory
from .output import TracklistOutput
from .validation import validate_and_clean_url, is_youtube_url, is_mixcloud_url, clean_url
from .identification import IdentificationManager
from .providers.factory import create_provider_factory

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Identify tracks in a mix.')
    parser.add_argument('input', help='Path to audio file or YouTube URL')
    parser.add_argument('-f', '--formats',
                      choices=['json', 'markdown', 'm3u', 'all'],
                      help='Output format(s). If not specified, uses format from config')
    parser.add_argument('-p', '--provider',
                      help='Primary track identification provider')
    parser.add_argument('--no-fallback', action='store_true',
                      help='Disable provider fallback')
    parser.add_argument('-v', '--verbose', action='store_true',
                      help='Enable verbose logging')
    return parser.parse_args()

def get_mix_info(input_path: str) -> dict:
    """
    Extract mix information from input.
    
    Args:
        input_path: Path to audio file or URL
        
    Returns:
        dict: Mix information with default values if extraction fails
    """
    try:
        # Clean URL if it's a URL
        if is_youtube_url(input_path) or is_mixcloud_url(input_path):
            input_path = clean_url(input_path)
            
        if is_youtube_url(input_path):
            import yt_dlp
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(input_path, download=False)
                return {
                    'title': info.get('title', 'Unknown Mix'),
                    'uploader': info.get('uploader', 'Unknown Artist'),
                    'duration': str(timedelta(seconds=info.get('duration', 0))),
                    'source': input_path
                }
                
        if is_mixcloud_url(input_path):
            import yt_dlp
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(input_path, download=False)
                return {
                    'title': info.get('title', 'Unknown Mix'),
                    'uploader': info.get('uploader', 'Unknown Artist'),
                    'duration': str(timedelta(seconds=info.get('duration', 0))),
                    'source': input_path
                }
                
        from mutagen import File
        audio = File(input_path)
        if audio is None:
            raise ValueError("Could not read audio file")
            
        return {
            'title': str(audio.get('title', ['Unknown Mix'])[0]),
            'artist': str(audio.get('artist', ['Unknown Artist'])[0]),
            'duration': str(timedelta(seconds=int(audio.info.length))),
            'source': input_path
        }
    except Exception as e:
        logger.warning(f"Failed to get mix info: {e}, using defaults")
        return {
            'title': 'Unknown Mix',
            'artist': 'Unknown Artist',
            'duration': '00:00:00',
            'source': input_path
        }

async def main() -> int:
    """Main entry point."""
    try:
        args = parse_args()
        
        # Set verbose logging if requested
        if args.verbose:
            logger.setLevel('DEBUG')
            logger.debug("Verbose logging enabled")
        
        # Get configuration
        config = get_config()
        
        # Override provider settings from command line
        if args.provider:
            config.primary_provider = args.provider
        if args.no_fallback:
            config.fallback_enabled = False
        
        # Create provider factory
        provider_factory = create_provider_factory(config)
        
        # Create identification manager
        manager = IdentificationManager(config, provider_factory)
        
        try:
            # Validate input URL or path
            input_path = validate_and_clean_url(args.input)
            
            # Download if URL
            if is_youtube_url(input_path) or is_mixcloud_url(input_path):
                downloader = DownloaderFactory.create_downloader(input_path, verbose=args.verbose)
                input_path = await downloader.download(input_path)
                if not input_path:
                    logger.error("Download failed")
                    return 1
            
            # Get mix info
            mix_info = get_mix_info(args.input)
            
            # Identify tracks
            tracks = await manager.identify_tracks(input_path)
            if not tracks:
                logger.error("No tracks identified")
                return 1
                
            logger.info(f"Found {len(tracks)} tracks")
            
            # Generate output
            output = TracklistOutput(mix_info, tracks)
            output.save_all()
            
            return 0
            
        except asyncio.CancelledError:
            # Handle task cancellation
            logger.info("\nOperation cancelled by user")
            return 0
            
        finally:
            # Clean up resources
            if manager:
                await manager.close()
            if provider_factory:
                await provider_factory.close_all()
                
    except KeyboardInterrupt:
        logger.info("\nOperation cancelled by user")
        return 0
        
    except Exception as e:
        logger.error(f"Error: {e}")
        if args.verbose:
            import traceback
            logger.debug(traceback.format_exc())
        return 1

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
