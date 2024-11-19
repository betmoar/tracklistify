"""Test suite for track identification and metadata providers."""

import pytest
import asyncio
from unittest.mock import Mock, patch
from tracklistify.providers.base import (
    TrackIdentificationProvider,
    MetadataProvider,
    ProviderError,
    AuthenticationError,
    RateLimitError
)
from tracklistify.providers.spotify import SpotifyProvider
from tracklistify.providers.factory import ProviderFactory, create_provider_factory
from tracklistify.providers.acrcloud import ACRCloudProvider


@pytest.fixture
def spotify_config():
    """Spotify configuration fixture."""
    return {
        "SPOTIFY_CLIENT_ID": "test_client_id",
        "SPOTIFY_CLIENT_SECRET": "test_client_secret"
    }

@pytest.fixture
def mock_spotify_response():
    """Mock Spotify API response fixture."""
    return {
        "tracks": {
            "items": [
                {
                    "id": "test_id",
                    "name": "Test Track",
                    "artists": [{"name": "Test Artist"}],
                    "album": {
                        "name": "Test Album",
                        "release_date": "2024-01-01"
                    },
                    "duration_ms": 180000,
                    "popularity": 80,
                    "preview_url": "https://example.com/preview",
                    "external_urls": {"spotify": "https://example.com/track"}
                }
            ]
        }
    }

@pytest.fixture
def mock_spotify_track():
    """Mock Spotify track details fixture."""
    return {
        "id": "test_id",
        "name": "Test Track",
        "artists": [{"name": "Test Artist"}],
        "album": {
            "name": "Test Album",
            "release_date": "2024-01-01"
        },
        "duration_ms": 180000,
        "popularity": 80,
        "preview_url": "https://example.com/preview",
        "external_urls": {"spotify": "https://example.com/track"}
    }

@pytest.fixture
def mock_audio_features():
    """Mock Spotify audio features fixture."""
    return {
        "tempo": 120.5,
        "key": 1,
        "mode": 1,
        "time_signature": 4,
        "danceability": 0.8,
        "energy": 0.9,
        "loudness": -5.5
    }

@pytest.fixture
def mock_acrcloud_response():
    """Mock ACRCloud API response."""
    return {
        "status": {"code": 0, "msg": "Success"},
        "metadata": {
            "music": [
                {
                    "title": "Test Track",
                    "artists": [{"name": "Test Artist"}],
                    "album": {"name": "Test Album"},
                    "release_date": "2023",
                    "duration_ms": 180000,
                    "score": 90,
                    "acrid": "test-acrid",
                    "external_ids": {"isrc": "test-isrc"},
                }
            ]
        },
    }

@pytest.fixture
def mock_acrcloud_provider(mock_acrcloud_response):
    """Create a mock ACRCloud provider."""
    with patch("aiohttp.ClientSession") as mock_session:
        mock_response = Mock()
        mock_response.status = 200
        mock_response.json.return_value = mock_acrcloud_response
        mock_session.return_value.post.return_value.__aenter__.return_value = mock_response
        
        provider = ACRCloudProvider(
            access_key="test_key",
            access_secret="test_secret",
        )
        yield provider


class TestSpotifyProvider:
    """Test cases for SpotifyProvider."""
    
    @pytest.mark.asyncio
    async def test_authentication(self, spotify_config):
        """Test Spotify authentication."""
        provider = SpotifyProvider(
            client_id=spotify_config["SPOTIFY_CLIENT_ID"],
            client_secret=spotify_config["SPOTIFY_CLIENT_SECRET"]
        )
        
        with patch("aiohttp.ClientSession.post") as mock_post:
            mock_post.return_value.__aenter__.return_value.status = 200
            mock_post.return_value.__aenter__.return_value.json = \
                asyncio.coroutine(lambda: {"access_token": "test_token", "expires_in": 3600})
            
            token = await provider._get_access_token()
            assert token == "test_token"
    
    @pytest.mark.asyncio
    async def test_search_track(self, spotify_config, mock_spotify_response):
        """Test track search functionality."""
        provider = SpotifyProvider(
            client_id=spotify_config["SPOTIFY_CLIENT_ID"],
            client_secret=spotify_config["SPOTIFY_CLIENT_SECRET"]
        )
        
        with patch("aiohttp.ClientSession.request") as mock_request:
            mock_request.return_value.__aenter__.return_value.status = 200
            mock_request.return_value.__aenter__.return_value.json = \
                asyncio.coroutine(lambda: mock_spotify_response)
            
            tracks = await provider.search_track("test query")
            assert len(tracks) == 1
            assert tracks[0]["name"] == "Test Track"
            assert tracks[0]["artists"] == ["Test Artist"]
    
    @pytest.mark.asyncio
    async def test_get_track_details(self, spotify_config, mock_spotify_track, mock_audio_features):
        """Test track details retrieval."""
        provider = SpotifyProvider(
            client_id=spotify_config["SPOTIFY_CLIENT_ID"],
            client_secret=spotify_config["SPOTIFY_CLIENT_SECRET"]
        )
        
        with patch("aiohttp.ClientSession.request") as mock_request:
            mock_request.return_value.__aenter__.return_value.status = 200
            mock_request.return_value.__aenter__.return_value.json = \
                asyncio.coroutine(lambda: mock_spotify_track)
            
            details = await provider.get_track_details("test_id")
            assert details["name"] == "Test Track"
            assert details["artists"] == ["Test Artist"]
    
    @pytest.mark.asyncio
    async def test_rate_limit_handling(self, spotify_config):
        """Test rate limit error handling."""
        provider = SpotifyProvider(
            client_id=spotify_config["SPOTIFY_CLIENT_ID"],
            client_secret=spotify_config["SPOTIFY_CLIENT_SECRET"]
        )
        
        with patch("aiohttp.ClientSession.request") as mock_request:
            mock_request.return_value.__aenter__.return_value.status = 429
            mock_request.return_value.__aenter__.return_value.headers = {"Retry-After": "60"}
            
            with pytest.raises(RateLimitError):
                await provider.search_track("test query")

class TestProviderFactory:
    """Test provider factory functionality."""

    def test_create_factory_empty_config(self):
        """Test creating factory with empty config raises error."""
        with pytest.raises(ProviderError):
            create_provider_factory({})

    def test_create_factory_valid_config(self):
        """Test creating factory with valid config."""
        config = {
            "ACR_ACCESS_KEY": "test_key",
            "ACR_ACCESS_SECRET": "test_secret",
            "SPOTIFY_CLIENT_ID": "test_id",
            "SPOTIFY_CLIENT_SECRET": "test_secret",
        }
        factory = create_provider_factory(config)
        assert factory.get_identification_provider("acrcloud") is not None
        assert factory.get_metadata_provider("spotify") is not None

    def test_register_invalid_provider(self):
        """Test registering invalid provider raises error."""
        factory = ProviderFactory()
        with pytest.raises(ValueError):
            factory.register_identification_provider("test", Mock())

    def test_get_nonexistent_provider(self):
        """Test getting nonexistent provider returns None."""
        factory = ProviderFactory()
        assert factory.get_identification_provider("nonexistent") is None
        assert factory.get_metadata_provider("nonexistent") is None

    def test_create_factory(self, spotify_config):
        """Test factory creation with configuration."""
        factory = create_provider_factory(spotify_config)
        assert factory.get_metadata_provider("spotify") is not None
    
    def test_register_providers(self):
        """Test provider registration."""
        factory = ProviderFactory()
        mock_provider = Mock(spec=MetadataProvider)
        
        factory.register_metadata_provider("test", mock_provider)
        assert factory.get_metadata_provider("test") == mock_provider
    
    @pytest.mark.asyncio
    async def test_close_all(self):
        """Test closing all provider connections."""
        factory = ProviderFactory()
        mock_provider = Mock(spec=MetadataProvider)
        mock_provider.close = asyncio.coroutine(lambda: None)
        
        factory.register_metadata_provider("test", mock_provider)
        await factory.close_all()
        
        mock_provider.close.assert_called_once()

class TestACRCloudProvider:
    """Test ACRCloud provider functionality."""

    @pytest.mark.asyncio
    async def test_identify_track_success(self, mock_acrcloud_provider):
        """Test successful track identification."""
        result = await mock_acrcloud_provider.identify_track(b"test_audio")
        assert result["title"] == "Test Track"
        assert result["artist"] == "Test Artist"
        assert result["album"] == "Test Album"
        assert result["year"] == "2023"
        assert result["duration"] == 180.0
        assert result["confidence"] == 90
        assert result["provider"] == "acrcloud"
        assert result["external_ids"]["acrcloud"] == "test-acrid"
        assert result["external_ids"]["isrc"] == "test-isrc"

    @pytest.mark.asyncio
    async def test_identify_track_auth_error(self, mock_acrcloud_provider):
        """Test authentication error handling."""
        with patch("aiohttp.ClientSession") as mock_session:
            mock_response = Mock()
            mock_response.status = 401
            mock_session.return_value.post.return_value.__aenter__.return_value = mock_response
            
            with pytest.raises(AuthenticationError):
                await mock_acrcloud_provider.identify_track(b"test_audio")

    @pytest.mark.asyncio
    async def test_identify_track_rate_limit(self, mock_acrcloud_provider):
        """Test rate limit error handling."""
        with patch("aiohttp.ClientSession") as mock_session:
            mock_response = Mock()
            mock_response.status = 429
            mock_session.return_value.post.return_value.__aenter__.return_value = mock_response
            
            with pytest.raises(RateLimitError):
                await mock_acrcloud_provider.identify_track(b"test_audio")

    @pytest.mark.asyncio
    async def test_identify_track_api_error(self, mock_acrcloud_provider):
        """Test API error handling."""
        with patch("aiohttp.ClientSession") as mock_session:
            mock_response = Mock()
            mock_response.status = 500
            mock_session.return_value.post.return_value.__aenter__.return_value = mock_response
            
            with pytest.raises(ProviderError):
                await mock_acrcloud_provider.identify_track(b"test_audio")

    @pytest.mark.asyncio
    async def test_close_provider(self, mock_acrcloud_provider):
        """Test provider cleanup."""
        await mock_acrcloud_provider.close()
        # Verify session is closed
        assert mock_acrcloud_provider._session is None
