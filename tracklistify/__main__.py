"""
Main entry point for Tracklistify.
"""

import argparse
import os
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
        logger.debug(f"Using primary provider: {args.provider}")
    if args.no_fallback:
        config.fallback_enabled = False
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
    if is_youtube_url(input_path) or is_mixcloud_url(input_path):
        logger.info(f"Downloading {'YouTube' if is_youtube_url(input_path) else 'Mixcloud'} audio...")
        try:
            import yt_dlp  # Import here to catch import error
            downloader = DownloaderFactory(config).create_downloader(input_path)
            if not downloader:
                logger.error("Failed to create downloader")
                return 1
            
            audio_path = await downloader.download(input_path)
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
        # Get output format from environment or config
        config_format = os.environ.get('OUTPUT_FORMAT', config.output_format.lower())
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
