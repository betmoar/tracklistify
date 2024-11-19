"""Main application module."""

import asyncio
import logging
from pathlib import Path
from typing import List, Optional

from .config import Config, load_config
from .identification import IdentificationManager
from .models import Track
from .audio import AudioProcessor

logger = logging.getLogger(__name__)

class Tracklistify:
    """Main application class."""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize application.
        
        Args:
            config_path: Optional path to configuration file
        """
        self.config = load_config(config_path) if config_path else Config()
        self._setup_logging()
        
        self.identification = IdentificationManager(self.config)
        self.audio_processor = AudioProcessor()

    def _setup_logging(self):
        """Setup logging configuration."""
        log_level = getattr(logging, self.config.log_level.upper(), logging.INFO)
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            filename=self.config.log_file if self.config.log_file else None
        )

    async def identify_file(self, file_path: str) -> List[Track]:
        """Identify tracks in an audio file.
        
        Args:
            file_path: Path to audio file
            
        Returns:
            List of identified tracks
            
        Raises:
            FileNotFoundError: If audio file not found
            ValueError: If audio file format not supported
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Audio file not found: {file_path}")

        logger.info("Processing audio file: %s", file_path)
        segments = await self.audio_processor.process_file(file_path)
        
        tracks = []
        for segment in segments:
            try:
                result = await self.identification.identify_segment(
                    segment.audio_data,
                    segment.start_time
                )
                if result:
                    track = await self.identification.create_track_from_provider_result(
                        result,
                        segment.start_time
                    )
                    tracks.append(track)
                    logger.info(
                        "Identified track: %s - %s at %s",
                        track.artist,
                        track.title,
                        track.start_time
                    )
            except Exception as e:
                logger.error("Failed to identify segment at %s: %s", segment.start_time, str(e))

        return tracks

    async def close(self):
        """Cleanup application resources."""
        await self.identification.close()
        await self.audio_processor.close()

async def identify_tracks(file_path: str, config_path: Optional[str] = None) -> List[Track]:
    """Convenience function to identify tracks in an audio file.
    
    Args:
        file_path: Path to audio file
        config_path: Optional path to configuration file
        
    Returns:
        List of identified tracks
    """
    app = Tracklistify(config_path)
    try:
        return await app.identify_file(file_path)
    finally:
        await app.close()
