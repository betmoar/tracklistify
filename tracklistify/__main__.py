"""
Main entry point for Tracklistify.
"""

import argparse
import os
from datetime import timedelta
from pathlib import Path
from typing import List, Optional

from .config import get_config
from .logger import logger
from .track import Track
from .downloader import DownloaderFactory
from .output import TracklistOutput
from .validation import validate_and_clean_url, is_youtube_url
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

def get_mix_info(input_path: str) -> Optional[dict]:
    """
    Extract mix information from input.
    
    Args:
        input_path: Path to audio file or URL
        
    Returns:
        dict: Mix information, or None if extraction failed
    """
    try:
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
        else:
            from mutagen import File
            audio = File(input_path)
            if audio is None:
                return None
                
            return {
                'title': str(audio.get('title', ['Unknown Mix'])[0]),
                'artist': str(audio.get('artist', ['Unknown Artist'])[0]),
                'duration': str(timedelta(seconds=int(audio.info.length))),
                'source': input_path
            }
    except Exception as e:
        logger.error(f"Failed to get mix info: {e}")
        return None

async def main() -> int:
    """Main entry point."""
    args = parse_args()
    
    # Set verbose logging if requested
    if args.verbose:
        logger.setLevel('DEBUG')
        logger.debug("Verbose logging enabled")
    
    # Get configuration
    config = get_config()
    
    # Override provider settings from command line
    if args.provider:
        config.providers.primary_provider = args.provider
        logger.debug(f"Using primary provider: {args.provider}")
    if args.no_fallback:
        config.providers.fallback_enabled = False
        logger.debug("Provider fallback disabled")
    
    # Create provider factory
    provider_factory = create_provider_factory(config)
    if not provider_factory:
        logger.error("Failed to create provider factory")
        return 1
    
    # Validate and clean input URL/path
    input_path = args.input
    if '://' in input_path:  # Looks like a URL
        cleaned_url = validate_and_clean_url(input_path)
        if not cleaned_url:
            logger.error(f"Invalid URL: {input_path}")
            return 1
        input_path = cleaned_url
        logger.debug(f"Cleaned URL: {input_path}")
    
    # Download if URL
    if is_youtube_url(input_path):
        logger.info("Downloading YouTube video...")
        try:
            import yt_dlp  # Import here to catch import error
            downloader = DownloaderFactory.create_downloader(input_path)
            if not downloader:
                logger.error("Failed to create downloader")
                return 1
            
            audio_path = downloader.download(input_path)
            if not audio_path:
                logger.error("Failed to download audio")
                return 1
        except ImportError:
            logger.error("yt-dlp not installed. Please install it with: pip install yt-dlp")
            return 1
    else:
        audio_path = input_path
    
    # Get mix information
    mix_info = get_mix_info(input_path)
    if not mix_info:
        logger.error("Failed to get mix information")
        return 1
    
    # Create identification manager with provider factory
    manager = IdentificationManager(config=config, provider_factory=provider_factory)
    
    # Identify tracks
    try:
        tracks = await manager.identify_tracks(audio_path)
        if not tracks:
            logger.error("No tracks identified")
            return 1
    except Exception as e:
        logger.error(f"Track identification failed: {e}")
        return 1
    finally:
        await manager.close()  # Ensure providers are properly closed
    
    # Generate output
    output = TracklistOutput(tracks, mix_info)
    
    # Use format from command line if specified, otherwise use format from config
    if args.formats == 'all':
        formats = ['json', 'markdown', 'm3u']
    elif args.formats:
        formats = [args.formats]
    else:
        # Use format from config, defaulting to json if not set
        config_format = os.environ.get('OUTPUT_FORMAT', config.output.format.lower())
        if config_format == 'all':
            formats = ['json', 'markdown', 'm3u']
        elif config_format in ['json', 'markdown', 'm3u']:
            formats = [config_format]
        else:
            logger.warning(f"Invalid format in config: {config_format}, using json")
            formats = ['json']
    
    for fmt in formats:
        output.save(fmt)
    
    logger.info(f"Found {len(tracks)} tracks")
    return 0

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
