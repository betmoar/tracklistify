"""Tests for audio processing functionality."""

import os
import tempfile
from pathlib import Path

import pytest
from pydub import AudioSegment
from pydub.generators import Sine

from tracklistify.audio import AudioProcessor, AudioSegment as AudioSegmentData

@pytest.fixture
def test_audio_file():
    """Create a test audio file."""
    # Create a 30-second test audio file
    duration_ms = 30000  # 30 seconds
    sample_rate = 44100
    
    # Generate a sine wave
    sine = Sine(440)  # 440 Hz
    audio = sine.to_audio_segment(duration=duration_ms)
    
    # Save to temporary file
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
        audio.export(temp_file.name, format='wav')
        yield Path(temp_file.name)
    
    # Cleanup
    os.unlink(temp_file.name)

class TestAudioProcessor:
    """Test audio processing functionality."""

    @pytest.mark.asyncio
    async def test_process_file(self, test_audio_file):
        """Test processing an audio file into segments."""
        processor = AudioProcessor(segment_duration=10.0)
        segments = await processor.process_file(test_audio_file)
        
        # Should have 3 segments (30 seconds / 10 seconds per segment)
        assert len(segments) == 3
        
        # Check segment properties
        for i, segment in enumerate(segments):
            assert isinstance(segment, AudioSegmentData)
            assert segment.start_time == i * 10.0
            assert segment.duration == 10.0
            assert len(segment.audio_data) > 0

    @pytest.mark.asyncio
    async def test_process_file_invalid(self):
        """Test processing an invalid audio file."""
        processor = AudioProcessor()
        with pytest.raises(Exception):
            await processor.process_file(Path('nonexistent.wav'))

    @pytest.mark.asyncio
    async def test_custom_segment_duration(self, test_audio_file):
        """Test processing with custom segment duration."""
        processor = AudioProcessor(segment_duration=5.0)
        segments = await processor.process_file(test_audio_file)
        
        # Should have 6 segments (30 seconds / 5 seconds per segment)
        assert len(segments) == 6
        
        # Check segment properties
        for i, segment in enumerate(segments):
            assert segment.start_time == i * 5.0
            assert segment.duration == 5.0

    @pytest.mark.asyncio
    async def test_cleanup(self):
        """Test cleanup of audio processor."""
        processor = AudioProcessor()
        await processor.close()  # Should not raise any errors
