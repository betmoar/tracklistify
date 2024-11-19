"""Audio processing functionality."""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np
from pydub import AudioSegment

@dataclass
class AudioSegment:
    """Represents a segment of audio data."""
    audio_data: bytes
    start_time: float
    duration: float

class AudioProcessor:
    """Handles audio file processing and segmentation."""

    def __init__(self, segment_duration: float = 10.0):
        """Initialize audio processor.
        
        Args:
            segment_duration: Duration of each segment in seconds
        """
        self.segment_duration = segment_duration

    async def process_file(self, file_path: Path) -> List[AudioSegment]:
        """Process an audio file and split it into segments.
        
        Args:
            file_path: Path to audio file
            
        Returns:
            List of audio segments
            
        Raises:
            ValueError: If audio file format not supported
        """
        # Load audio file using pydub
        audio = AudioSegment.from_file(str(file_path))
        
        # Convert to mono and set sample rate
        audio = audio.set_channels(1).set_frame_rate(44100)
        
        # Split into segments
        segments = []
        for start_ms in range(0, len(audio), int(self.segment_duration * 1000)):
            end_ms = min(start_ms + int(self.segment_duration * 1000), len(audio))
            segment = audio[start_ms:end_ms]
            
            # Convert to bytes in required format
            segment_data = segment.raw_data
            
            segments.append(AudioSegment(
                audio_data=segment_data,
                start_time=start_ms / 1000.0,
                duration=(end_ms - start_ms) / 1000.0
            ))
        
        return segments

    async def close(self):
        """Cleanup resources."""
        # Currently no cleanup needed
        pass
