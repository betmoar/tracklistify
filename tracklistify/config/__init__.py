"""Configuration management for tracklistify."""

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Any, Optional, List

from .validation import (
    ConfigValidator,
    TypeRule,
    RangeRule,
    ValidationRule,
    PathRule,
    PathRequirement
)

from .security import (
    mask_sensitive_data,
    SENSITIVE_FIELDS,
    SecureString
)

from .docs import (
    ConfigDocGenerator,
    generate_full_docs,
    generate_field_docs,
    generate_validation_docs,
    generate_example_docs
)

@dataclass
class BaseConfig:
    """Base configuration class."""
    output_dir: Path = field(default=Path('.tracklistify/output'))
    cache_dir: Path = field(default=Path('.tracklistify/cache'))
    temp_dir: Path = field(default=Path('.tracklistify/temp'))
    verbose: bool = field(default=False)
    debug: bool = field(default=False)

    def __post_init__(self):
        """Initialize configuration after creation."""
        self._validator = ConfigValidator()
        self._setup_validation()
        self._create_directories()
        self._validate()

    def _setup_validation(self):
        """Set up validation rules."""
        # Directory validation
        for dir_field in ['output_dir', 'cache_dir', 'temp_dir']:
            self._validator.add_rule(TypeRule(dir_field, Path, f"{dir_field} must be a Path"))
            self._validator.add_rule(PathRule(
                dir_field,
                {PathRequirement.IS_DIR},
                f"{dir_field} must be a directory",
                create_if_missing=True
            ))

        # Boolean validation
        for bool_field in ['verbose', 'debug']:
            self._validator.add_rule(TypeRule(bool_field, bool, f"{bool_field} must be a boolean"))

    def _validate(self):
        """Validate configuration."""
        config_dict = asdict(self)
        self._validator.validate(config_dict)

    def _create_directories(self):
        """Create necessary directories."""
        for dir_field in ['output_dir', 'cache_dir', 'temp_dir']:
            path = getattr(self, dir_field)
            # Expand home directory if path starts with ~
            if isinstance(path, Path):
                path = Path(os.path.expanduser(str(path)))
                setattr(self, dir_field, path)
            path.mkdir(parents=True, exist_ok=True)

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        config_dict = asdict(self)
        # Convert Path objects to strings
        for key, value in config_dict.items():
            if isinstance(value, Path):
                config_dict[key] = str(value)
        return mask_sensitive_data(config_dict)

    @property
    def rules(self):
        """Get validation rules."""
        return self._validator.rules

    def __str__(self) -> str:
        """String representation with masked sensitive data."""
        return str(self.to_dict())

    @classmethod
    def get_documentation(cls) -> str:
        """Get markdown documentation for configuration."""
        return generate_full_docs(cls)

@dataclass
class TrackIdentificationConfig(BaseConfig):
    """Track identification configuration."""
    # Track identification settings
    segment_length: int = field(default=60)
    min_confidence: float = field(default=0.0)
    time_threshold: float = field(default=60.0)
    max_duplicates: int = field(default=2)

    # Provider settings
    primary_provider: str = field(default="shazam")
    fallback_enabled: bool = field(default=False)
    fallback_providers: List[str] = field(default_factory=lambda: ["acrcloud"])
    
    # Provider endpoints and timeouts
    acrcloud_host: str = field(default="identify-eu-west-1.acrcloud.com")
    acrcloud_timeout: int = field(default=10)
    shazam_enabled: bool = field(default=True)
    shazam_timeout: int = field(default=10)
    spotify_timeout: int = field(default=10)
    
    # Extended provider settings
    retry_strategy: str = field(default="exponential")  # exponential, linear, constant
    retry_max_attempts: int = field(default=3)
    retry_base_delay: float = field(default=1.0)
    retry_max_delay: float = field(default=30.0)
    
    # Rate limiting
    rate_limit_enabled: bool = field(default=True)
    max_requests_per_minute: int = field(default=60)

    # Cache settings
    cache_enabled: bool = field(default=True)
    cache_ttl: int = field(default=3600)
    cache_max_size: int = field(default=1000)
    cache_storage_format: str = field(default="json")
    cache_compression_enabled: bool = field(default=True)
    cache_compression_level: int = field(default=6)
    cache_cleanup_enabled: bool = field(default=True)
    cache_cleanup_interval: int = field(default=3600)
    cache_max_age: int = field(default=86400)
    cache_min_free_space: int = field(default=1024 * 1024 * 100)

    # Output settings
    output_format: str = field(default="all")

    # Download settings
    download_quality: str = field(default="192")
    download_format: str = field(default="mp3")
    download_max_retries: int = field(default=3)

    def _setup_validation(self):
        """Set up validation rules."""
        super()._setup_validation()

        # Track identification validation
        self._validator.add_rule(TypeRule('segment_length', int))
        self._validator.add_rule(RangeRule('segment_length', 10, 300))
        self._validator.add_rule(TypeRule('min_confidence', float))
        self._validator.add_rule(RangeRule('min_confidence', 0.0, 1.0))
        self._validator.add_rule(TypeRule('time_threshold', float))
        self._validator.add_rule(RangeRule('time_threshold', 0.0, 300.0))
        self._validator.add_rule(TypeRule('max_duplicates', int))
        self._validator.add_rule(RangeRule('max_duplicates', 0, 10))

        # Provider validation
        self._validator.add_rule(TypeRule('primary_provider', str))
        self._validator.add_rule(TypeRule('fallback_enabled', bool))
        self._validator.add_rule(TypeRule('fallback_providers', list))
        self._validator.add_rule(TypeRule('acrcloud_host', str))
        self._validator.add_rule(TypeRule('acrcloud_timeout', int))
        self._validator.add_rule(RangeRule('acrcloud_timeout', 1, 60))
        self._validator.add_rule(TypeRule('shazam_enabled', bool))
        self._validator.add_rule(TypeRule('shazam_timeout', int))
        self._validator.add_rule(RangeRule('shazam_timeout', 1, 60))
        self._validator.add_rule(TypeRule('spotify_timeout', int))
        self._validator.add_rule(RangeRule('spotify_timeout', 1, 60))
        self._validator.add_rule(TypeRule('retry_strategy', str))
        self._validator.add_rule(TypeRule('retry_max_attempts', int))
        self._validator.add_rule(RangeRule('retry_max_attempts', 1, 10))
        self._validator.add_rule(TypeRule('retry_base_delay', float))
        self._validator.add_rule(RangeRule('retry_base_delay', 0.1, 10.0))
        self._validator.add_rule(TypeRule('retry_max_delay', float))
        self._validator.add_rule(RangeRule('retry_max_delay', 1.0, 300.0))

        # Rate limiting validation
        self._validator.add_rule(TypeRule('rate_limit_enabled', bool))
        self._validator.add_rule(TypeRule('max_requests_per_minute', int))
        self._validator.add_rule(RangeRule('max_requests_per_minute', 1, 1000))

        # Cache validation
        self._validator.add_rule(TypeRule('cache_enabled', bool))
        self._validator.add_rule(TypeRule('cache_ttl', int))
        self._validator.add_rule(RangeRule('cache_ttl', 1, 86400))
        self._validator.add_rule(TypeRule('cache_max_size', int))
        self._validator.add_rule(RangeRule('cache_max_size', 1, 1000000))
        self._validator.add_rule(TypeRule('cache_storage_format', str))
        self._validator.add_rule(TypeRule('cache_compression_enabled', bool))
        self._validator.add_rule(TypeRule('cache_compression_level', int))
        self._validator.add_rule(RangeRule('cache_compression_level', 1, 9))
        self._validator.add_rule(TypeRule('cache_cleanup_enabled', bool))
        self._validator.add_rule(TypeRule('cache_cleanup_interval', int))
        self._validator.add_rule(RangeRule('cache_cleanup_interval', 60, 86400))
        self._validator.add_rule(TypeRule('cache_max_age', int))
        self._validator.add_rule(RangeRule('cache_max_age', 3600, 2592000))
        self._validator.add_rule(TypeRule('cache_min_free_space', int))
        self._validator.add_rule(RangeRule('cache_min_free_space', 1024 * 1024, 1024 * 1024 * 1024))

        # Output validation
        self._validator.add_rule(TypeRule('output_format', str))

        # Download validation
        self._validator.add_rule(TypeRule('download_quality', str))
        self._validator.add_rule(TypeRule('download_format', str))
        self._validator.add_rule(TypeRule('download_max_retries', int))
        self._validator.add_rule(RangeRule('download_max_retries', 1, 10))

def get_config() -> TrackIdentificationConfig:
    """
    Get the global configuration instance.
    
    This function returns a singleton instance of the TrackIdentificationConfig class,
    which is created with environment variables if they exist, or default values otherwise.
    
    Returns:
        TrackIdentificationConfig: The global configuration instance
    """
    global _config_instance

    if _config_instance is None:
        # Create config dictionary from environment variables
        config_dict = {}
        
        # First, get all default values from the dataclass
        for field_name, field_info in TrackIdentificationConfig.__dataclass_fields__.items():
            if hasattr(field_info.default, 'default'):
                config_dict[field_name] = field_info.default.default
            elif hasattr(field_info.default_factory, '__call__'):
                config_dict[field_name] = field_info.default_factory()
            else:
                config_dict[field_name] = field_info.default
        
        # Then override with environment variables
        for key, value in os.environ.items():
            if key.startswith('TRACKLISTIFY_'):
                config_key = key[len('TRACKLISTIFY_'):].lower()
                # Handle type conversion based on default field type
                field = TrackIdentificationConfig.__dataclass_fields__.get(config_key)
                if field:
                    try:
                        if field.type == bool:
                            config_dict[config_key] = value.lower() in ('true', '1', 'yes')
                        elif field.type == int:
                            config_dict[config_key] = int(value)
                        elif field.type == float:
                            config_dict[config_key] = float(value)
                        elif field.type == Path:
                            config_dict[config_key] = Path(value)
                        else:
                            config_dict[config_key] = value
                    except (ValueError, TypeError) as e:
                        print(f"Warning: Failed to convert environment variable {key}: {e}")

        _config_instance = TrackIdentificationConfig(**config_dict)

    return _config_instance

def clear_config():
    """Clear the global configuration instance."""
    global _config_instance
    _config_instance = None

# Initialize global configuration instance
_config_instance: Optional[TrackIdentificationConfig] = None

__all__ = [
    'BaseConfig',
    'TrackIdentificationConfig',
    'get_config',
    'clear_config',
    'SENSITIVE_FIELDS',
    'generate_field_docs',
    'generate_validation_docs',
    'generate_example_docs',
    'ConfigDocGenerator'
]
