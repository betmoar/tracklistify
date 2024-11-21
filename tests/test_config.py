"""Tests for the Tracklistify configuration system."""

import os
from pathlib import Path
import pytest
from tracklistify.config import TracklistifyConfig, AppConfig, ProviderConfig, TrackConfig, CacheConfig, OutputConfig, DownloadConfig

def test_default_config():
    """Test default configuration values."""
    config = TracklistifyConfig()
    
    # Test app config defaults
    assert config.app.max_requests_per_minute == 60
    assert config.app.max_concurrent_requests == 5
    assert config.app.rate_limit_enabled is True
    assert config.app.rate_limit_window == 60
    assert config.app.max_retries == 3
    assert config.app.retry_delay == 1.0
    assert config.app.retry_backoff == 2.0
    assert config.app.retry_max_delay == 30.0

    # Test provider config defaults
    assert config.providers.primary_provider == "shazam"
    assert config.providers.fallback_enabled is False
    assert config.providers.fallback_order == "acrcloud"

    # Test track config defaults
    assert config.track.confidence_threshold == 0.8
    assert config.track.segment_length == 30
    assert config.track.overlap == 5
    assert config.track.time_threshold == 60
    assert config.track.max_duplicates == 2
    assert config.track.min_confidence == 0.8

    # Test cache config defaults
    assert config.cache.enabled is True
    assert config.cache.ttl == 3600
    assert config.cache.max_size == 1000

def test_environment_variable_override():
    """Test environment variable overrides."""
    # Set test environment variables
    os.environ["RATE_LIMIT_REQUESTS"] = "30"
    os.environ["MAX_CONCURRENT_REQUESTS"] = "3"
    os.environ["CONFIDENCE_THRESHOLD"] = "0.9"
    os.environ["SEGMENT_LENGTH"] = "45"
    os.environ["CACHE_ENABLED"] = "false"
    
    config = TracklistifyConfig()
    config.load()
    
    # Test overridden values
    assert config.app.max_requests_per_minute == 30
    assert config.app.max_concurrent_requests == 3
    assert config.track.confidence_threshold == 0.9
    assert config.track.segment_length == 45
    assert config.cache.enabled is False
    
    # Clean up environment
    del os.environ["RATE_LIMIT_REQUESTS"]
    del os.environ["MAX_CONCURRENT_REQUESTS"]
    del os.environ["CONFIDENCE_THRESHOLD"]
    del os.environ["SEGMENT_LENGTH"]
    del os.environ["CACHE_ENABLED"]

def test_config_dot_notation():
    """Test configuration access using dot notation."""
    config = TracklistifyConfig()
    
    # Test accessing values using dot notation
    assert config.get("app.max_requests_per_minute") == 60
    assert config.get("providers.primary_provider") == "shazam"
    assert config.get("track.confidence_threshold") == 0.8
    assert config.get("cache.enabled") is True
    
    # Test non-existent keys
    assert config.get("nonexistent.key") is None
    assert config.get("nonexistent.key", "default") == "default"

def test_sensitive_data_masking():
    """Test sensitive data is properly masked in string representation."""
    config = TracklistifyConfig()
    config.providers.acrcloud_access_key = "secret_key"
    config.providers.acrcloud_access_secret = "secret_secret"
    config.providers.spotify_client_id = "spotify_id"
    config.providers.spotify_client_secret = "spotify_secret"
    
    str_repr = str(config)
    
    # Check that sensitive data is masked
    assert "secret_key" not in str_repr
    assert "secret_secret" not in str_repr
    assert "spotify_id" not in str_repr
    assert "spotify_secret" not in str_repr
    assert "***" in str_repr

def test_directory_creation():
    """Test required directories are created."""
    config = TracklistifyConfig()
    config.load()
    
    # Check that directories are created
    assert config.cache.dir.exists()
    assert config.cache.temp_dir.exists()
    assert config.output.dir.exists()
    
    # Check directory permissions (Unix-like systems only)
    if os.name != "nt":  # Skip on Windows
        assert oct(config.cache.dir.stat().st_mode)[-3:] == "700"
        assert oct(config.cache.temp_dir.stat().st_mode)[-3:] == "700"
        assert oct(config.output.dir.stat().st_mode)[-3:] == "700"

def test_config_validation():
    """Test configuration validation."""
    config = TracklistifyConfig()
    
    # Test invalid confidence threshold
    with pytest.raises(ValueError):
        config.track.confidence_threshold = 1.5
        config._validate()
    
    # Test invalid segment length
    with pytest.raises(ValueError):
        config.track.segment_length = -1
        config._validate()
    
    # Test invalid cache TTL
    with pytest.raises(ValueError):
        config.cache.ttl = -3600
        config._validate()

def test_config_update():
    """Test configuration update functionality."""
    config = TracklistifyConfig()
    
    # Update values
    config.set("app.max_requests_per_minute", 30)
    config.set("track.confidence_threshold", 0.9)
    config.set("cache.enabled", False)
    
    # Verify updates
    assert config.app.max_requests_per_minute == 30
    assert config.track.confidence_threshold == 0.9
    assert config.cache.enabled is False
    
    # Test invalid updates
    with pytest.raises(ValueError):
        config.set("nonexistent.key", "value")

def test_track_config_new_fields():
    """Test new track configuration fields."""
    config = TracklistifyConfig()
    
    # Test default values
    assert config.track.time_threshold == 60
    assert config.track.max_duplicates == 2
    assert config.track.min_confidence == 0.8
    
    # Test environment variable override
    os.environ["RECOGNITION_TIME_THRESHOLD"] = "90"
    os.environ["RECOGNITION_MAX_DUPLICATES"] = "3"
    os.environ["RECOGNITION_MIN_CONFIDENCE"] = "0.85"
    
    config = TracklistifyConfig()
    config.load()
    
    assert config.track.time_threshold == 90
    assert config.track.max_duplicates == 3
    assert config.track.min_confidence == 0.85
    
    # Clean up
    del os.environ["RECOGNITION_TIME_THRESHOLD"]
    del os.environ["RECOGNITION_MAX_DUPLICATES"]
    del os.environ["RECOGNITION_MIN_CONFIDENCE"]

def test_config_file_loading():
    """Test loading configuration from file."""
    # Create a temporary config file
    config_data = {
        "track": {
            "confidence_threshold": 0.75,
            "segment_length": 40,
            "time_threshold": 80,
            "max_duplicates": 4
        },
        "cache": {
            "enabled": True,
            "ttl": 7200
        }
    }
    
    temp_config = Path("test_config.json")
    try:
        with open(temp_config, "w") as f:
            import json
            json.dump(config_data, f)
        
        config = TracklistifyConfig()
        config.load_from_file(temp_config)
        
        # Verify loaded values
        assert config.track.confidence_threshold == 0.75
        assert config.track.segment_length == 40
        assert config.track.time_threshold == 80
        assert config.track.max_duplicates == 4
        assert config.cache.enabled is True
        assert config.cache.ttl == 7200
        
    finally:
        # Clean up
        if temp_config.exists():
            temp_config.unlink()

def test_env_var_precedence():
    """Test environment variables take precedence over config file."""
    # Set up config file
    config_data = {
        "track": {
            "confidence_threshold": 0.75,
            "segment_length": 40
        }
    }
    
    temp_config = Path("test_config.json")
    try:
        with open(temp_config, "w") as f:
            import json
            json.dump(config_data, f)
        
        # Set environment variables
        os.environ["CONFIDENCE_THRESHOLD"] = "0.95"
        os.environ["SEGMENT_LENGTH"] = "50"
        
        config = TracklistifyConfig()
        config.load_from_file(temp_config)
        config.load()  # Load environment variables
        
        # Environment variables should override file values
        assert config.track.confidence_threshold == 0.95
        assert config.track.segment_length == 50
        
    finally:
        # Clean up
        if temp_config.exists():
            temp_config.unlink()
        del os.environ["CONFIDENCE_THRESHOLD"]
        del os.environ["SEGMENT_LENGTH"]

def test_secure_config_loading():
    """Test secure loading of sensitive configuration."""
    config = TracklistifyConfig()
    
    # Set sensitive data
    os.environ["SPOTIFY_CLIENT_ID"] = "test_client_id"
    os.environ["SPOTIFY_CLIENT_SECRET"] = "test_client_secret"
    os.environ["ACR_ACCESS_KEY"] = "test_access_key"
    os.environ["ACR_ACCESS_SECRET"] = "test_access_secret"
    
    config.load()
    
    # Test that sensitive data is loaded but masked in string representation
    assert config.providers.spotify_client_id == "test_client_id"
    assert "test_client_id" not in str(config)
    assert "***" in str(config)
    
    # Test secure storage
    config_dict = config.to_dict()
    assert config_dict["providers"]["spotify_client_id"] == "***"
    assert config_dict["providers"]["spotify_client_secret"] == "***"
    
    # Clean up
    del os.environ["SPOTIFY_CLIENT_ID"]
    del os.environ["SPOTIFY_CLIENT_SECRET"]
    del os.environ["ACR_ACCESS_KEY"]
    del os.environ["ACR_ACCESS_SECRET"]

def test_config_documentation():
    """Test auto-generated configuration documentation."""
    from tracklistify.config.docs import ConfigDocGenerator
    
    config = TracklistifyConfig()
    doc_gen = ConfigDocGenerator(config)
    docs = doc_gen.generate_markdown()
    
    # Verify documentation content
    assert "# Tracklistify Configuration" in docs
    assert "## Configuration Fields" in docs
    
    # Check field documentation
    assert "confidence_threshold" in docs
    assert "segment_length" in docs
    assert "time_threshold" in docs
    assert "max_duplicates" in docs
    
    # Check type information
    assert "**Type:**" in docs
    assert "**Properties:**" in docs
    assert "**Constraints:**" in docs
    
    # Check sensitive field masking
    assert "spotify_client_secret" in docs.lower()
    assert "your_spotify_client_secret" not in docs.lower()

def test_config_validation_comprehensive():
    """Test comprehensive configuration validation."""
    config = TracklistifyConfig()
    
    # Test track config validation
    config.track.time_threshold = -1  # Invalid value
    with pytest.raises(ValueError, match=r"time_threshold must be positive"):
        config.track.validate()

    # Test app config validation
    with pytest.raises(ValueError, match=r".*rate limit.*"):
        config.app.rate_limit_window = 0
        config._validate()

def test_track_config_validation():
    """Test track configuration validation."""
    # Valid configuration
    track_config = TrackConfig(
        time_threshold=60,
        max_duplicates=2,
        min_confidence=0.8
    )
    track_config.validate()  # Should not raise
    
    # Invalid time threshold
    with pytest.raises(ValueError, match="time_threshold must be positive"):
        TrackConfig(time_threshold=0).validate()
    
    # Invalid max duplicates
    with pytest.raises(ValueError, match="max_duplicates must be at least 1"):
        TrackConfig(max_duplicates=0).validate()
    
    # Invalid min confidence
    with pytest.raises(ValueError, match="min_confidence must be between 0 and 1"):
        TrackConfig(min_confidence=1.5).validate()
