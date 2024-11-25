"""Configuration management for tracklistify."""

import os
import ast
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, Any, Optional, List, get_origin, get_args
from dotenv import load_dotenv

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

# Load environment variables at module import time
_env_path = Path(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))) / '.env'
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path)

def _parse_env_value(value: str, expected_type: type) -> Any:
    """Parse environment variable value to expected type."""
    if expected_type == bool:
        return value.lower() in ('true', '1', 'yes', 'on')
    elif get_origin(expected_type) == list or expected_type == list:
        try:
            # Try to parse as Python literal first
            parsed = ast.literal_eval(value)
            if isinstance(parsed, list):
                return parsed
            elif isinstance(parsed, str):
                # If it's a single string, wrap it in a list
                return [parsed]
        except (ValueError, SyntaxError):
            # If not a Python literal, split by comma if it contains commas
            if ',' in value:
                return [v.strip() for v in value.split(',')]
            # Otherwise treat as a single value
            return [value]
    elif expected_type == int:
        return int(value)
    elif expected_type == float:
        return float(value)
    elif expected_type == Path:
        return Path(os.path.expanduser(value))
    return value

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
        self._load_from_env()
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

    def _load_from_env(self):
        """Load configuration from environment variables."""
        prefix = "TRACKLISTIFY_"
        for field_name, field_info in self.__class__.__dataclass_fields__.items():
            env_key = f"{prefix}{field_name.upper()}"
            if env_key in os.environ:
                env_value = os.environ[env_key]
                try:
                    parsed_value = _parse_env_value(env_value, field_info.type)
                    setattr(self, field_name, parsed_value)
                except (ValueError, SyntaxError) as e:
                    raise ValueError(f"Invalid value for {env_key}: {e}")

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
    
    # Rate limiting settings
    rate_limit_enabled: bool = field(default=True)
    max_requests_per_minute: int = field(default=60)
    max_concurrent_requests: int = field(default=10)
    
    # Circuit breaker settings
    circuit_breaker_enabled: bool = field(default=True)
    circuit_breaker_threshold: int = field(default=5)  # Consecutive failures before opening
    circuit_breaker_reset_timeout: float = field(default=60.0)  # Seconds to wait before half-open
    
    # Alert settings
    rate_limit_alert_enabled: bool = field(default=True)
    rate_limit_alert_threshold: float = field(default=5.0)  # Alert if wait time exceeds this
    rate_limit_alert_cooldown: float = field(default=300.0)  # Minimum time between alerts
    
    # Per-provider rate limits
    spotify_max_rpm: int = field(default=120)
    spotify_max_concurrent: int = field(default=20)
    shazam_max_rpm: int = field(default=60)
    shazam_max_concurrent: int = field(default=10)
    acrcloud_max_rpm: int = field(default=30)
    acrcloud_max_concurrent: int = field(default=5)
    
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
        self._validator.add_rule(TypeRule('max_concurrent_requests', int))
        self._validator.add_rule(RangeRule('max_concurrent_requests', 1, 100))
        
        # Circuit breaker validation
        self._validator.add_rule(TypeRule('circuit_breaker_enabled', bool))
        self._validator.add_rule(TypeRule('circuit_breaker_threshold', int))
        self._validator.add_rule(RangeRule('circuit_breaker_threshold', 1, 100))
        self._validator.add_rule(TypeRule('circuit_breaker_reset_timeout', float))
        self._validator.add_rule(RangeRule('circuit_breaker_reset_timeout', 1.0, 3600.0))
        
        # Alert validation
        self._validator.add_rule(TypeRule('rate_limit_alert_enabled', bool))
        self._validator.add_rule(TypeRule('rate_limit_alert_threshold', float))
        self._validator.add_rule(RangeRule('rate_limit_alert_threshold', 0.1, 60.0))
        self._validator.add_rule(TypeRule('rate_limit_alert_cooldown', float))
        self._validator.add_rule(RangeRule('rate_limit_alert_cooldown', 1.0, 3600.0))
        
        # Per-provider rate limit validation
        self._validator.add_rule(TypeRule('spotify_max_rpm', int))
        self._validator.add_rule(RangeRule('spotify_max_rpm', 1, 1000))
        self._validator.add_rule(TypeRule('spotify_max_concurrent', int))
        self._validator.add_rule(RangeRule('spotify_max_concurrent', 1, 100))
        
        self._validator.add_rule(TypeRule('shazam_max_rpm', int))
        self._validator.add_rule(RangeRule('shazam_max_rpm', 1, 1000))
        self._validator.add_rule(TypeRule('shazam_max_concurrent', int))
        self._validator.add_rule(RangeRule('shazam_max_concurrent', 1, 100))
        
        self._validator.add_rule(TypeRule('acrcloud_max_rpm', int))
        self._validator.add_rule(RangeRule('acrcloud_max_rpm', 1, 1000))
        self._validator.add_rule(TypeRule('acrcloud_max_concurrent', int))
        self._validator.add_rule(RangeRule('acrcloud_max_concurrent', 1, 100))

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
        _config_instance = TrackIdentificationConfig()

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
