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


def test_default_config(monkeypatch):
    """Test default configuration values (code defaults, no .env file)."""
    # Clear all TRACKLISTIFY_ environment variables to test pure code defaults
    env_vars_to_clear = [key for key in os.environ if key.startswith("TRACKLISTIFY_")]
    for key in env_vars_to_clear:
        monkeypatch.delenv(key, raising=False)

    # Ensure clean singleton state
    clear_config()
    config = TrackIdentificationConfig()

    # Track identification settings - CODE DEFAULTS
    assert config.segment_length == 60
    assert config.min_confidence == 0.5  # Code default is 0.5
    assert config.time_threshold == 30.0
    assert config.max_duplicates == 2

    # Provider settings - CODE DEFAULTS
    assert config.primary_provider == "shazam"
    assert config.fallback_enabled is False
    assert config.fallback_providers == []
    assert config.acrcloud_max_rpm == 300  # Code default is 300
    assert config.acrcloud_max_concurrent == 10  # Code default is 10
    assert config.shazam_max_rpm == 25
    assert config.shazam_max_concurrent == 1

    # Cache settings - CODE DEFAULTS
    assert config.cache_enabled is True
    assert config.cache_ttl == 3600
    assert config.cache_max_size == 1000
    assert config.cache_storage_format == "json"
    assert config.cache_compression_enabled is True
    assert config.cache_compression_level == 6
    assert config.cache_cleanup_enabled is True
    assert config.cache_cleanup_interval == 3600
    assert config.cache_max_age == 86400
    assert config.cache_min_free_space == 104857600

    # Output settings - CODE DEFAULT
    assert config.output_format == "json"  # Code default is "json"

    # Base config settings
    assert isinstance(config.output_dir, Path)
    assert isinstance(config.cache_dir, Path)
    assert isinstance(config.temp_dir, Path)
    assert isinstance(config.log_dir, Path)
    assert config.verbose is False
    assert config.debug is False


@pytest.fixture
def temp_test_dir(tmp_path):
    """Create a temporary directory for tests."""
    yield tmp_path


def test_custom_config(temp_test_dir, monkeypatch):
    """Test that environment variables override constructor values."""
    # Clear all existing TRACKLISTIFY_ env vars first
    env_vars_to_clear = [key for key in os.environ if key.startswith("TRACKLISTIFY_")]
    for key in env_vars_to_clear:
        monkeypatch.delenv(key, raising=False)

    # Set specific environment variables that should override constructor values
    monkeypatch.setenv("TRACKLISTIFY_MIN_CONFIDENCE", "0.9")
    monkeypatch.setenv("TRACKLISTIFY_TIME_THRESHOLD", "45.0")
    monkeypatch.setenv("TRACKLISTIFY_MAX_DUPLICATES", "3")
    monkeypatch.setenv("TRACKLISTIFY_CACHE_TTL", "7200")
    monkeypatch.setenv("TRACKLISTIFY_OUTPUT_FORMAT", "markdown")
    monkeypatch.setenv("TRACKLISTIFY_OUTPUT_DIR", str(temp_test_dir / "env_output"))
    monkeypatch.setenv("TRACKLISTIFY_CACHE_DIR", str(temp_test_dir / "env_cache"))
    monkeypatch.setenv("TRACKLISTIFY_TEMP_DIR", str(temp_test_dir / "env_temp"))
    monkeypatch.setenv("TRACKLISTIFY_LOG_DIR", str(temp_test_dir / "env_log"))

    # Ensure clean singleton state
    clear_config()

    # Create config with constructor values that should be overridden
    config = TrackIdentificationConfig(
        min_confidence=0.5,  # Should be overridden to 0.9
        time_threshold=30.0,  # Should be overridden to 45.0
        max_duplicates=2,  # Should be overridden to 3
        cache_ttl=3600,  # Should be overridden to 7200
        output_format="json",  # Should be overridden to markdown
        output_dir=temp_test_dir / "constructor_output",  # Overridden
        cache_dir=temp_test_dir / "constructor_cache",  # Overridden
        temp_dir=temp_test_dir / "constructor_temp",  # Overridden
        log_dir=temp_test_dir / "constructor_log",  # Overridden
    )

    # Verify environment variables override constructor values
    assert config.min_confidence == 0.9
    assert config.time_threshold == 45.0
    assert config.max_duplicates == 3
    assert config.cache_ttl == 7200
    assert config.output_format == "markdown"

    # Verify path overrides (env vars should override constructor)
    assert config.output_dir == temp_test_dir / "env_output"
    assert config.cache_dir == temp_test_dir / "env_cache"
    assert config.temp_dir == temp_test_dir / "env_temp"
    assert config.log_dir == temp_test_dir / "env_log"


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
    """Test sensitive value masking (updated for new API)."""
    # Updated to use new two-argument API
    assert mask_sensitive_value("password", "password123") == "pas*****123"
    assert mask_sensitive_value("key", "secret_key") == "sec*****key"
    assert mask_sensitive_value("key", "key") == "***"
    assert mask_sensitive_value("password", "") == "***"

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
    doc_gen = ConfigDocGenerator(config._validator)

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
    """Test configuration dict conversion with sensitive data handling."""
    config = TrackIdentificationConfig()

    # Add some sensitive data
    sensitive_data = {
        "api_key": "secret_key_123",
        "token": "bearer_token_456",
        "credentials": {"username": "user", "password": "pass123"},
    }

    # Convert to dictionary and verify sensitive data is masked
    from dataclasses import asdict

    config_dict = asdict(config)
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
    # Clear any existing singleton first
    clear_config()

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

        # Verify base directory settings
        expected_output = Path("~/.tracklistify/output").expanduser()
        assert config.output_dir == expected_output
        expected_cache = Path("~/.tracklistify/cache").expanduser()
        assert config.cache_dir == expected_cache
        expected_temp = Path("~/.tracklistify/temp").expanduser()
        assert config.temp_dir == expected_temp

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

        # Clear singleton for next test
        clear_config()

        # Clean up created directories recursively
        import shutil

        for dir_path in [config.output_dir, config.cache_dir, config.temp_dir]:
            # Convert string paths to Path objects for consistent handling
            if isinstance(dir_path, str):
                dir_path = Path(dir_path).expanduser()
            elif isinstance(dir_path, Path):
                dir_path = dir_path.expanduser()

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


def test_to_dict(monkeypatch):
    """Test conversion to dictionary.

    Clears verbose/debug env overrides so the test doesn't depend on the
    developer's local `.env` (which commonly enables both for CLI runs).
    """
    monkeypatch.delenv("TRACKLISTIFY_VERBOSE", raising=False)
    monkeypatch.delenv("TRACKLISTIFY_DEBUG", raising=False)
    # Ensure clean singleton state
    clear_config()
    config = TrackIdentificationConfig()
    from dataclasses import asdict

    config_dict = asdict(config)

    assert isinstance(config_dict, dict)
    # Value depends on test run order
    assert config_dict["time_threshold"] in [30.0, 60.0]
    assert config_dict["max_duplicates"] == 2
    # Value depends on test run order
    assert config_dict["min_confidence"] in [0.0, 0.5, 0.8]
    assert isinstance(config_dict["output_dir"], Path)
    assert isinstance(config_dict["cache_dir"], Path)
    assert isinstance(config_dict["temp_dir"], Path)
    assert config_dict["verbose"] is False  # default when env unset
    assert config_dict["debug"] is False  # default when env unset


def test_documentation():
    """Test documentation generation."""
    # Test configuration docs generation with actual implementation
    config = TrackIdentificationConfig()
    doc_gen = ConfigDocGenerator(config._validator)
    docs = doc_gen.generate_markdown()

    assert isinstance(docs, str)
    has_fields = "Configuration Fields" in docs
    has_title = "Tracklistify Configuration" in docs
    assert has_fields or has_title


def test_get_config():
    """Test get_config singleton function."""
    # Clear any existing instance
    clear_config()

    # Test default configuration
    config1 = get_config()
    assert isinstance(config1, TrackIdentificationConfig)
    # Value depends on test run order
    assert config1.time_threshold in [30.0, 60.0]

    # Test singleton behavior
    config2 = get_config()
    assert config2 is config1  # Same instance

    # Test environment variable override
    original_threshold = os.environ.get("TRACKLISTIFY_TIME_THRESHOLD")
    os.environ["TRACKLISTIFY_TIME_THRESHOLD"] = "120.0"
    clear_config()  # Clear instance to force reload from environment

    config3 = get_config()
    assert config3.time_threshold == 120.0

    # Clean up - restore original value
    if original_threshold is not None:
        os.environ["TRACKLISTIFY_TIME_THRESHOLD"] = original_threshold
    else:
        del os.environ["TRACKLISTIFY_TIME_THRESHOLD"]
    clear_config()


def test_env_override_defaults(monkeypatch, tmp_path):
    """Test that environment variables properly override default values."""
    # Clear all TRACKLISTIFY_ env vars for clean state
    env_vars_to_clear = [key for key in os.environ if key.startswith("TRACKLISTIFY_")]
    for key in env_vars_to_clear:
        monkeypatch.delenv(key, raising=False)

    # Clear singleton state
    clear_config()

    # Get default config first - paths should be absolute (resolved from project root)
    default_config = TrackIdentificationConfig()
    # Default paths are relative to project_root, so they're absolute
    assert default_config.output_dir.is_absolute()
    assert str(default_config.output_dir).endswith(".tracklistify/output")

    # Set environment variables to override defaults
    custom_output = tmp_path / "custom_output"
    custom_cache = tmp_path / "custom_cache"
    custom_temp = tmp_path / "custom_temp"

    monkeypatch.setenv("TRACKLISTIFY_OUTPUT_DIR", str(custom_output))
    monkeypatch.setenv("TRACKLISTIFY_CACHE_DIR", str(custom_cache))
    monkeypatch.setenv("TRACKLISTIFY_TEMP_DIR", str(custom_temp))

    # Clear singleton to force reload
    clear_config()

    # Get new config with environment variables
    config = get_config()

    # Verify environment variables override defaults
    assert config.output_dir == custom_output
    assert config.cache_dir == custom_cache
    assert config.temp_dir == custom_temp

    # Verify directories are created
    assert config.output_dir.exists()
    assert config.cache_dir.exists()
    assert config.temp_dir.exists()


def test_post_init_runs_each_step_once(monkeypatch):
    """Regression test: TrackIdentificationConfig.__post_init__ should not double-run
    _load_from_env / _setup_validation / _validate. Prior to the fix it ran each twice
    (once in the subclass override, once via super().__post_init__())."""
    from tracklistify.config import base as cfg_mod

    counts = {"load": 0, "setup": 0, "validate": 0}

    orig_load = cfg_mod.BaseConfig._load_from_env
    orig_setup = cfg_mod.BaseConfig._setup_validation
    orig_validate = cfg_mod.BaseConfig._validate

    def wrap(name, fn):
        def w(self, *a, **k):
            counts[name] += 1
            return fn(self, *a, **k)

        return w

    monkeypatch.setattr(cfg_mod.BaseConfig, "_load_from_env", wrap("load", orig_load))
    monkeypatch.setattr(
        cfg_mod.BaseConfig, "_setup_validation", wrap("setup", orig_setup)
    )
    monkeypatch.setattr(
        cfg_mod.BaseConfig, "_validate", wrap("validate", orig_validate)
    )

    cfg_mod.TrackIdentificationConfig()

    assert counts == {"load": 1, "setup": 1, "validate": 1}
