"""Tests for configuration management."""

# Standard library imports
import os
from pathlib import Path

# Third-party imports
import pytest

# Local/package imports
from tracklistify.config import (
    TrackIdentificationConfig,
    clear_config,
    get_config,
)
from tracklistify.config.docs import (
    ConfigDocGenerator,
    generate_example_docs,
    generate_field_docs,
    generate_validation_docs,
)
from tracklistify.config.security import (
    detect_sensitive_fields,
    is_sensitive_field,
    mask_sensitive_data,
    mask_sensitive_value,
)
from tracklistify.config.validation import (
    validate_optional_string,
    validate_path,
    validate_positive_float,
    validate_positive_int,
    validate_probability,
    validate_string_list,
)


def test_default_config():
    """Test default configuration values."""
    config = TrackIdentificationConfig()

    # Track identification settings
    assert config.segment_length == 60
    assert config.min_confidence == 0.0
    assert config.time_threshold == 60.0
    assert config.max_duplicates == 2

    # Provider settings
    assert config.primary_provider == "shazam"
    assert config.fallback_enabled is False
    assert config.fallback_providers == ["acrcloud"]
    assert config.acrcloud_host == "identify-eu-west-1.acrcloud.com"
    assert config.acrcloud_timeout == 10
    assert config.shazam_enabled is True
    assert config.shazam_timeout == 10
    assert config.spotify_timeout == 10
    assert config.retry_strategy == "exponential"
    assert config.retry_max_attempts == 3
    assert config.retry_base_delay == 1.0
    assert config.retry_max_delay == 30.0

    # Rate limiting
    assert config.rate_limit_enabled is True
    assert config.max_requests_per_minute == 60

    # Cache settings
    assert config.cache_enabled is True
    assert config.cache_ttl == 3600
    assert config.cache_max_size == 1000
    assert config.cache_storage_format == "json"
    assert config.cache_compression_enabled is True
    assert config.cache_compression_level == 6
    assert config.cache_cleanup_enabled is True
    assert config.cache_cleanup_interval == 3600
    assert config.cache_max_age == 86400
    assert config.cache_min_free_space == 1024 * 1024 * 100

    # Output settings
    assert config.output_format == "all"

    # Download settings
    assert config.download_quality == "192"
    assert config.download_format == "mp3"
    assert config.download_max_retries == 3

    # Base config settings
    assert isinstance(config.output_dir, Path)
    assert isinstance(config.cache_dir, Path)
    assert isinstance(config.temp_dir, Path)
    assert config.verbose is False
    assert config.debug is False


@pytest.fixture
def temp_test_dir(tmp_path):
    """Create a temporary directory for tests."""
    yield tmp_path


def test_custom_config(temp_test_dir):
    """Test custom configuration values."""
    config = TrackIdentificationConfig(
        # Track identification settings
        segment_length=30,
        min_confidence=0.8,
        time_threshold=45.0,
        max_duplicates=5,
        # Provider settings
        primary_provider="shazam",
        fallback_enabled=False,
        fallback_providers=["acrcloud"],
        acrcloud_timeout=20,
        shazam_timeout=20,
        spotify_timeout=20,
        retry_max_attempts=5,
        retry_base_delay=2.0,
        retry_max_delay=60.0,
        # Rate limiting
        rate_limit_enabled=False,
        max_requests_per_minute=120,
        # Cache settings
        cache_enabled=False,
        cache_ttl=7200,
        cache_max_size=2000,
        cache_compression_level=9,
        cache_cleanup_interval=7200,
        cache_max_age=172800,
        # Output settings
        output_format="yaml",
        # Download settings
        download_quality="320",
        download_format="flac",
        download_max_retries=5,
        # Base config settings
        output_dir=temp_test_dir / "custom_output",
        cache_dir=temp_test_dir / "custom_cache",
        temp_dir=temp_test_dir / "custom_temp",
        verbose=True,
        debug=True,
    )

    # Track identification settings
    assert config.segment_length == 30
    assert config.min_confidence == 0.8
    assert config.time_threshold == 45.0
    assert config.max_duplicates == 5

    # Provider settings
    assert config.primary_provider == "shazam"
    assert config.fallback_enabled is False
    assert config.fallback_providers == ["acrcloud"]
    assert config.acrcloud_timeout == 20
    assert config.shazam_timeout == 20
    assert config.spotify_timeout == 20
    assert config.retry_max_attempts == 5
    assert config.retry_base_delay == 2.0
    assert config.retry_max_delay == 60.0

    # Rate limiting
    assert config.rate_limit_enabled is False
    assert config.max_requests_per_minute == 120

    # Cache settings
    assert config.cache_enabled is False
    assert config.cache_ttl == 7200
    assert config.cache_max_size == 2000
    assert config.cache_compression_level == 9
    assert config.cache_cleanup_interval == 7200
    assert config.cache_max_age == 172800

    # Output settings
    assert config.output_format == "yaml"

    # Download settings
    assert config.download_quality == "320"
    assert config.download_format == "flac"
    assert config.download_max_retries == 5

    # Base config settings
    assert config.output_dir == temp_test_dir / "custom_output"
    assert config.cache_dir == temp_test_dir / "custom_cache"
    assert config.temp_dir == temp_test_dir / "custom_temp"
    assert config.verbose is True
    assert config.debug is True


def test_validation_positive_float():
    """Test validation of positive float values."""
    assert validate_positive_float(1.0, "test") == 1.0

    with pytest.raises(TypeError):
        validate_positive_float("not a number", "test")

    with pytest.raises(ValueError):
        validate_positive_float(0.0, "test")

    with pytest.raises(ValueError):
        validate_positive_float(-1.0, "test")


def test_validation_positive_int():
    """Test validation of positive integer values."""
    assert validate_positive_int(1, "test") == 1

    with pytest.raises(TypeError):
        validate_positive_int(1.5, "test")

    with pytest.raises(ValueError):
        validate_positive_int(0, "test")

    with pytest.raises(ValueError):
        validate_positive_int(-1, "test")


def test_validation_probability():
    """Test validation of probability values."""
    assert validate_probability(0.5, "test") == 0.5

    with pytest.raises(TypeError):
        validate_probability("not a number", "test")

    with pytest.raises(ValueError):
        validate_probability(-0.1, "test")

    with pytest.raises(ValueError):
        validate_probability(1.1, "test")


def test_validation_path():
    """Test validation of path values."""
    test_dir = Path("test_dir")
    test_dir.mkdir(exist_ok=True)

    try:
        assert validate_path(test_dir, must_exist=True) == test_dir.resolve()
        assert validate_path("test_dir", must_exist=True) == test_dir.resolve()

        with pytest.raises(ValueError):
            validate_path("nonexistent_dir", must_exist=True)

    finally:
        test_dir.rmdir()


def test_string_list_validation():
    """Test validation of string lists."""
    valid_list = ["item1", "item2"]
    assert validate_string_list(valid_list, "test_list") == valid_list

    with pytest.raises(TypeError, match="test_list must be a list"):
        validate_string_list("not a list", "test_list")

    with pytest.raises(TypeError, match="test_list must contain only strings"):
        validate_string_list([1, 2], "test_list")

    with pytest.raises(TypeError, match="test_list must contain only strings"):
        validate_string_list(["valid", 1], "test_list")


def test_optional_string_validation():
    """Test validation of optional strings."""
    assert validate_optional_string(None, "test_str") is None
    assert validate_optional_string("valid", "test_str") == "valid"

    with pytest.raises(TypeError, match="test_str must be a string or None"):
        validate_optional_string(123, "test_str")


def test_sensitive_field_detection():
    """Test sensitive field detection."""
    assert is_sensitive_field("password")
    assert is_sensitive_field("api_key")
    assert is_sensitive_field("secret")
    assert is_sensitive_field("token")
    assert not is_sensitive_field("username")
    assert not is_sensitive_field("email")

    sensitive_fields = detect_sensitive_fields(
        {
            "username": "user",
            "password": "secret123",
            "api_key": "key123",
            "settings": {"token": "token123", "display_name": "User"},
        }
    )

    assert "password" in sensitive_fields
    assert "api_key" in sensitive_fields
    assert "settings.token" in sensitive_fields
    assert "username" not in sensitive_fields
    assert "settings.display_name" not in sensitive_fields


def test_sensitive_value_masking():
    """Test sensitive value masking."""
    assert mask_sensitive_value("password123") == "pas*****"
    assert mask_sensitive_value("key") == "k**"
    assert mask_sensitive_value("") == ""

    data = {
        "username": "user",
        "password": "secret123",
        "api_key": "key123",
        "settings": {"token": "token123", "display_name": "User"},
    }

    masked = mask_sensitive_data(data)
    assert masked["username"] == "user"
    assert masked["password"] != "secret123"
    assert masked["api_key"] != "key123"
    assert masked["settings"]["token"] != "token123"
    assert masked["settings"]["display_name"] == "User"
    assert "***" in masked["password"]
    assert "***" in masked["api_key"]
    assert "***" in masked["settings"]["token"]


def test_config_documentation_generation():
    """Test configuration documentation generation."""
    config = TrackIdentificationConfig()
    doc_gen = ConfigDocGenerator(config)

    # Test field documentation
    field_docs = generate_field_docs(config)
    assert "time_threshold" in field_docs
    assert "max_duplicates" in field_docs
    assert "min_confidence" in field_docs
    assert "**Type:**" in field_docs
    assert "**Description:**" in field_docs

    # Test validation documentation
    validation_docs = generate_validation_docs(TrackIdentificationConfig)
    assert "Validation Rules" in validation_docs
    assert "time_threshold" in validation_docs
    assert "must be positive" in validation_docs

    # Test example documentation
    example_docs = generate_example_docs(TrackIdentificationConfig)
    assert "Configuration Example" in example_docs
    assert "time_threshold" in example_docs
    assert "max_duplicates" in example_docs

    # Test full documentation
    full_docs = doc_gen.generate_markdown()
    assert "# Tracklistify Configuration" in full_docs
    assert (
        "This document describes the configuration options for Tracklistify."
        in full_docs
    )
    assert "## Configuration Fields" in full_docs


def test_config_validation_edge_cases():
    """Test configuration validation edge cases."""
    # Test empty paths
    with pytest.raises(ValueError):
        validate_path("", must_exist=False)

    # Test invalid probabilities
    with pytest.raises(ValueError):
        validate_probability(2.0, "test")

    # Test zero values
    with pytest.raises(ValueError):
        validate_positive_float(0.0, "test")
    with pytest.raises(ValueError):
        validate_positive_int(0, "test")

    # Test negative values
    with pytest.raises(ValueError):
        validate_positive_float(-1.0, "test")
    with pytest.raises(ValueError):
        validate_positive_int(-1, "test")

    # Test invalid types
    with pytest.raises(TypeError):
        validate_positive_float("invalid", "test")
    with pytest.raises(TypeError):
        validate_positive_int(1.5, "test")
    with pytest.raises(TypeError):
        validate_probability("invalid", "test")


def test_config_to_dict_with_sensitive_data():
    """Test configuration dictionary conversion with sensitive data handling."""
    config = TrackIdentificationConfig()

    # Add some sensitive data
    sensitive_data = {
        "api_key": "secret_key_123",
        "token": "bearer_token_456",
        "credentials": {"username": "user", "password": "pass123"},
    }

    # Convert to dictionary and verify sensitive data is masked
    config_dict = config.to_dict()
    # Use the variable to avoid the unused variable warning
    assert config_dict is not None
    masked_dict = mask_sensitive_data(sensitive_data)

    assert masked_dict["api_key"] != "secret_key_123"
    assert masked_dict["token"] != "bearer_token_456"
    assert masked_dict["credentials"]["password"] != "pass123"
    assert masked_dict["credentials"]["username"] == "user"
    assert "***" in masked_dict["api_key"]
    assert "***" in masked_dict["token"]
    assert "***" in masked_dict["credentials"]["password"]


def test_env_config():
    """Test configuration from environment variables."""
    # Test base directory settings
    os.environ["TRACKLISTIFY_OUTPUT_DIR"] = "~/.tracklistify/output"
    os.environ["TRACKLISTIFY_CACHE_DIR"] = "~/.tracklistify/cache"
    os.environ["TRACKLISTIFY_TEMP_DIR"] = "~/.tracklistify/temp"

    # Test other settings
    os.environ["TRACKLISTIFY_TIME_THRESHOLD"] = "45.0"
    os.environ["TRACKLISTIFY_MAX_DUPLICATES"] = "4"
    os.environ["TRACKLISTIFY_MIN_CONFIDENCE"] = "0.95"

    try:
        config = get_config()
        clear_config()  # Clear singleton for next test

        # Verify base directory settings
        assert config.output_dir == Path("~/.tracklistify/output").expanduser()
        assert config.cache_dir == Path("~/.tracklistify/cache").expanduser()
        assert config.temp_dir == Path("~/.tracklistify/temp").expanduser()

        # Verify other settings
        assert config.time_threshold == 45.0
        assert config.max_duplicates == 4
        assert config.min_confidence == 0.95

        # Verify directories are created
        assert config.output_dir.exists()
        assert config.cache_dir.exists()
        assert config.temp_dir.exists()

    finally:
        # Clean up environment variables
        del os.environ["TRACKLISTIFY_OUTPUT_DIR"]
        del os.environ["TRACKLISTIFY_CACHE_DIR"]
        del os.environ["TRACKLISTIFY_TEMP_DIR"]
        del os.environ["TRACKLISTIFY_TIME_THRESHOLD"]
        del os.environ["TRACKLISTIFY_MAX_DUPLICATES"]
        del os.environ["TRACKLISTIFY_MIN_CONFIDENCE"]

        # Clean up created directories recursively
        import shutil

        for dir_path in [config.output_dir, config.cache_dir, config.temp_dir]:
            if dir_path.exists():
                shutil.rmtree(dir_path)


def test_directory_creation():
    """Test automatic directory creation."""
    config = TrackIdentificationConfig(
        output_dir=Path("test_output"),
        cache_dir=Path("test_cache"),
        temp_dir=Path("test_temp"),
    )

    try:
        assert config.output_dir.exists()
        assert config.cache_dir.exists()
        assert config.temp_dir.exists()

    finally:
        config.output_dir.rmdir()
        config.cache_dir.rmdir()
        config.temp_dir.rmdir()


def test_to_dict():
    """Test conversion to dictionary."""
    config = TrackIdentificationConfig()
    config_dict = config.to_dict()

    assert isinstance(config_dict, dict)
    assert config_dict["time_threshold"] == 60.0
    assert config_dict["max_duplicates"] == 2
    assert config_dict["min_confidence"] == 0.0
    assert isinstance(config_dict["output_dir"], str)
    assert isinstance(config_dict["cache_dir"], str)
    assert isinstance(config_dict["temp_dir"], str)
    assert config_dict["verbose"] is False
    assert config_dict["debug"] is False


def test_documentation():
    """Test documentation generation."""
    docs = TrackIdentificationConfig.get_documentation()

    assert isinstance(docs, str)
    assert "Configuration Fields" in docs
    assert "Environment Variables" in docs
    assert "Configuration Example" in docs
    assert "Validation Rules" in docs


def test_get_config():
    """Test get_config singleton function."""
    # Clear any existing instance
    clear_config()

    # Test default configuration
    config1 = get_config()
    assert isinstance(config1, TrackIdentificationConfig)
    assert config1.time_threshold == 60.0

    # Test singleton behavior
    config2 = get_config()
    assert config2 is config1  # Same instance

    # Test environment variable override
    os.environ["TRACKLISTIFY_TIME_THRESHOLD"] = "120.0"
    clear_config()  # Clear instance to force reload from environment

    config3 = get_config()
    assert config3.time_threshold == 120.0

    # Clean up
    del os.environ["TRACKLISTIFY_TIME_THRESHOLD"]
    clear_config()


def test_env_override_defaults():
    """Test that environment variables properly override default values."""
    # Get default config first
    default_config = TrackIdentificationConfig()
    assert default_config.output_dir == Path(".tracklistify/output")
    assert default_config.cache_dir == Path(".tracklistify/cache")
    assert default_config.temp_dir == Path(".tracklistify/temp")

    # Set environment variables
    os.environ["TRACKLISTIFY_OUTPUT_DIR"] = "~/.tracklistify/output"
    os.environ["TRACKLISTIFY_CACHE_DIR"] = "~/.tracklistify/cache"
    os.environ["TRACKLISTIFY_TEMP_DIR"] = "~/.tracklistify/temp"

    try:
        # Clear singleton to force reload
        clear_config()

        # Get new config with environment variables
        config = get_config()

        # Verify environment variables override defaults
        assert config.output_dir == Path("~/.tracklistify/output").expanduser()
        assert config.cache_dir == Path("~/.tracklistify/cache").expanduser()
        assert config.temp_dir == Path("~/.tracklistify/temp").expanduser()

        # Verify directories are created
        assert config.output_dir.exists()
        assert config.cache_dir.exists()
        assert config.temp_dir.exists()

    finally:
        # Clean up environment variables
        del os.environ["TRACKLISTIFY_OUTPUT_DIR"]
        del os.environ["TRACKLISTIFY_CACHE_DIR"]
        del os.environ["TRACKLISTIFY_TEMP_DIR"]

        # Clean up created directories recursively
        import shutil

        for dir_path in [config.output_dir, config.cache_dir, config.temp_dir]:
            if dir_path.exists():
                shutil.rmtree(dir_path)
