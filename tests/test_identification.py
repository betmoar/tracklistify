"""Test suite for track identification utilities."""

import pytest
from unittest.mock import Mock, AsyncMock
from tracklistify.identification import identify_segment, create_track_from_provider_result
from tracklistify.providers.base import TrackIdentificationProvider, ProviderError
from tracklistify.track import Track

@pytest.fixture
def mock_provider():
    provider = Mock(spec=TrackIdentificationProvider)
    provider.identify_track = AsyncMock()
    return provider

@pytest.fixture
def mock_cache():
    return Mock(get=Mock(), set=Mock())

@pytest.fixture
def mock_rate_limiter():
    return Mock(acquire=AsyncMock(return_value=True))

@pytest.fixture
def sample_provider_result():
    return {
        'metadata': {
            'music': [{
                'title': 'Test Song',
                'artists': [{'name': 'Test Artist'}],
                'score': 85.5
            }]
        }
    }

@pytest.mark.asyncio
async def test_identify_segment_success(mock_provider, mock_cache, sample_provider_result):
    """Test successful track identification."""
    mock_provider.identify_track.return_value = sample_provider_result
    
    result = await identify_segment(
        provider=mock_provider,
        segment=b'test_audio_data',
        start_time=0.0,
        cache=mock_cache
    )
    
    assert result == sample_provider_result
    mock_provider.identify_track.assert_called_once_with(b'test_audio_data', 0.0)

@pytest.mark.asyncio
async def test_identify_segment_with_cache(mock_provider, mock_cache, sample_provider_result):
    """Test track identification with cache hit."""
    mock_cache.get.return_value = sample_provider_result
    
    result = await identify_segment(
        provider=mock_provider,
        segment=b'test_audio_data',
        start_time=0.0,
        cache=mock_cache
    )
    
    assert result == sample_provider_result
    mock_provider.identify_track.assert_not_called()

@pytest.mark.asyncio
async def test_identify_segment_rate_limited(mock_provider, mock_rate_limiter):
    """Test track identification when rate limited."""
    mock_rate_limiter.acquire.return_value = False
    
    result = await identify_segment(
        provider=mock_provider,
        segment=b'test_audio_data',
        start_time=0.0,
        rate_limiter=mock_rate_limiter
    )
    
    assert result is None
    mock_provider.identify_track.assert_not_called()

@pytest.mark.asyncio
async def test_identify_segment_provider_error(mock_provider):
    """Test track identification with provider error."""
    mock_provider.identify_track.side_effect = ProviderError("Test error")
    
    result = await identify_segment(
        provider=mock_provider,
        segment=b'test_audio_data',
        start_time=0.0
    )
    
    assert result is None

def test_create_track_from_provider_result(sample_provider_result):
    """Test track creation from provider result."""
    track = create_track_from_provider_result(
        result=sample_provider_result,
        time_in_mix="00:00:00"
    )
    
    assert isinstance(track, Track)
    assert track.song_name == "Test Song"
    assert track.artist == "Test Artist"
    assert track.time_in_mix == "00:00:00"
    assert track.confidence == 85.5

def test_create_track_from_invalid_result():
    """Test track creation with invalid provider result."""
    invalid_result = {'metadata': {}}  # Missing music data
    
    track = create_track_from_provider_result(
        result=invalid_result,
        time_in_mix="00:00:00"
    )
    
    assert track is None
