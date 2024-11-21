"""
Tracklistify configuration management.

This module provides secure configuration loading and validation
for the Tracklistify application.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional, List
from dataclasses import dataclass, field, asdict
from dotenv import load_dotenv
import json

from .security import (
    SecureConfigLoader,
    SecureString,
    mask_sensitive_data,
    SENSITIVE_FIELDS
)
from .validation import (
    ConfigValidator,
    ValidationError,
    PathRequirement
)

@dataclass
class ProviderConfig:
    """Provider configuration."""
    primary_provider: str = field(default="shazam")
    fallback_enabled: bool = field(default=False)
    fallback_order: str = field(default="acrcloud")
    
    # ACRCloud settings
    acrcloud_access_key: str = field(default="")
    acrcloud_access_secret: str = field(default="")
    acrcloud_host: str = field(default="identify-eu-west-1.acrcloud.com")
    acrcloud_timeout: int = field(default=10)
    
    # Shazam settings
    shazam_enabled: bool = field(default=True)
    shazam_timeout: int = field(default=10)
    
    # Spotify settings
    spotify_client_id: str = field(default="")
    spotify_client_secret: str = field(default="")
    spotify_timeout: int = field(default=10)
    
    # Retry settings
    retry_strategy: str = field(default="exponential")
    max_retries: int = field(default=3)
    retry_delay: float = field(default=1.0)
    max_retry_delay: float = field(default=30.0)

@dataclass
class TrackConfig:
    """Track identification configuration."""
    confidence_threshold: float = field(default=0.8)
    segment_length: int = field(default=30)
    overlap: int = field(default=5)
    min_duration: float = field(default=5.0)
    max_duration: float = field(default=300.0)
    min_segment_confidence: float = field(default=0.5)
    max_segments: int = field(default=50)
    silence_threshold: float = field(default=-50.0)
    noise_reduction: bool = field(default=True)
    time_threshold: int = 60  # Time threshold for track merging in seconds
    max_duplicates: int = 2   # Maximum number of duplicate tracks to keep
    min_confidence: float = 0.8  # Minimum confidence threshold
    
    def validate(self) -> None:
        """Validate track configuration."""
        if not isinstance(self.time_threshold, (int, float)) or self.time_threshold <= 0:
            raise ValueError("time_threshold must be positive")
            
        if not isinstance(self.max_duplicates, int) or self.max_duplicates < 1:
            raise ValueError("max_duplicates must be at least 1")
            
        if not isinstance(self.min_confidence, float) or not 0 <= self.min_confidence <= 1:
            raise ValueError("min_confidence must be between 0 and 1")

@dataclass
class CacheConfig:
    """Cache configuration."""
    enabled: bool = field(default=True)
    ttl: int = field(default=3600)
    max_size: int = field(default=1000)
    dir: Path = field(default_factory=lambda: Path.home() / ".tracklistify" / "cache")
    base_dir: Path = field(default_factory=lambda: Path.home() / ".tracklistify" / "cache")
    temp_dir: Path = field(default_factory=lambda: Path.home() / ".tracklistify" / "cache" / "temp")
    storage_format: str = field(default="json")
    compression_enabled: bool = field(default=True)
    compression_level: int = field(default=6)
    cleanup_interval: int = field(default=3600)
    max_age: int = field(default=86400)
    min_free_space: int = field(default=104857600)  # 100MB in bytes

@dataclass
class OutputConfig:
    """Output configuration."""
    dir: Path = field(default_factory=lambda: Path.home() / ".tracklistify" / "output")
    directory: str = field(default="output")
    format: str = field(default="json")

@dataclass
class DownloadConfig:
    """Download configuration."""
    quality: str = field(default="192")

@dataclass
class AppConfig:
    """Application configuration."""
    max_requests_per_minute: int = field(default=60)
    max_concurrent_requests: int = field(default=5)
    rate_limit_enabled: bool = field(default=True)
    rate_limit_window: int = field(default=60)
    rate_limit_requests: int = field(default=60)
    max_retries: int = field(default=3)
    retry_delay: float = field(default=1.0)
    retry_backoff: float = field(default=2.0)
    retry_max_delay: float = field(default=30.0)

class TracklistifyConfig:
    """
    Configuration manager for Tracklistify.
    
    Provides secure configuration loading and validation with support for:
    - Type validation
    - Range validation
    - Path validation
    - Dependency validation
    - Secure secret handling
    - Configuration masking
    """
    
    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or Path.home() / ".tracklistify"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self._secure_loader = SecureConfigLoader()
        self._validator = self._create_validator()
        
        # Initialize configuration objects
        self.providers = ProviderConfig()
        self.track = TrackConfig()
        self.cache = CacheConfig()
        self.output = OutputConfig()
        self.download = DownloadConfig()
        self.app = AppConfig()
    
    def load(self) -> None:
        """
        Load and validate configuration.
        
        Raises:
            ValidationError: If configuration is invalid
        """
        # Create required directories
        self.cache.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.cache.temp_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.output.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        
        # Load provider configuration
        self.providers = ProviderConfig(
            primary_provider=os.getenv("PRIMARY_PROVIDER", "shazam"),
            fallback_enabled=os.getenv("PROVIDER_FALLBACK_ENABLED", "false").lower() == "true",
            fallback_order=os.getenv("PROVIDER_FALLBACK_ORDER", "acrcloud"),
            
            # ACRCloud settings
            acrcloud_access_key=os.getenv("ACR_ACCESS_KEY", ""),
            acrcloud_access_secret=os.getenv("ACR_ACCESS_SECRET", ""),
            acrcloud_host=os.getenv("ACR_HOST", "identify-eu-west-1.acrcloud.com"),
            acrcloud_timeout=int(os.getenv("ACR_TIMEOUT", "10")),
            
            # Shazam settings
            shazam_enabled=os.getenv("SHAZAM_ENABLED", "true").lower() == "true",
            shazam_timeout=int(os.getenv("SHAZAM_TIMEOUT", "10")),
            
            # Spotify settings
            spotify_client_id=os.getenv("SPOTIFY_CLIENT_ID", ""),
            spotify_client_secret=os.getenv("SPOTIFY_CLIENT_SECRET", ""),
            spotify_timeout=int(os.getenv("SPOTIFY_TIMEOUT", "10")),
            
            # Retry settings
            retry_strategy=os.getenv("PROVIDER_RETRY_STRATEGY", "exponential"),
            max_retries=int(os.getenv("PROVIDER_MAX_RETRIES", "3")),
            retry_delay=float(os.getenv("PROVIDER_RETRY_DELAY", "1.0")),
            max_retry_delay=float(os.getenv("PROVIDER_MAX_RETRY_DELAY", "30.0"))
        )
        
        # Load track configuration
        self.track = TrackConfig(
            confidence_threshold=float(os.getenv("CONFIDENCE_THRESHOLD", "0.8")),
            segment_length=int(os.getenv("SEGMENT_LENGTH", "30")),
            overlap=int(os.getenv("OVERLAP", "5")),
            min_duration=float(os.getenv("RECOGNITION_MIN_DURATION", "5.0")),
            max_duration=float(os.getenv("RECOGNITION_MAX_DURATION", "300.0")),
            min_segment_confidence=float(os.getenv("RECOGNITION_MIN_SEGMENT_CONFIDENCE", "0.5")),
            max_segments=int(os.getenv("RECOGNITION_MAX_SEGMENTS", "50")),
            silence_threshold=float(os.getenv("RECOGNITION_SILENCE_THRESHOLD", "-50.0")),
            noise_reduction=os.getenv("RECOGNITION_NOISE_REDUCTION", "true").lower() == "true",
            time_threshold=int(os.getenv("RECOGNITION_TIME_THRESHOLD", "60")),
            max_duplicates=int(os.getenv("RECOGNITION_MAX_DUPLICATES", "2")),
            min_confidence=float(os.getenv("RECOGNITION_MIN_CONFIDENCE", "0.8"))
        )
        
        # Load cache configuration
        self.cache = CacheConfig(
            enabled=os.getenv("CACHE_ENABLED", "true").lower() == "true",
            ttl=int(os.getenv("CACHE_TTL", "3600")),
            max_size=int(os.getenv("CACHE_MAX_SIZE", "1000")),
            dir=Path(os.getenv("CACHE_DIR", str(self.config_dir / "cache"))),
            base_dir=Path(os.getenv("CACHE_BASE_DIR", str(self.config_dir / "cache"))),
            temp_dir=Path(os.getenv("CACHE_TEMP_DIR", str(self.config_dir / "cache" / "temp"))),
            storage_format=os.getenv("CACHE_STORAGE_FORMAT", "json"),
            compression_enabled=os.getenv("CACHE_COMPRESSION_ENABLED", "true").lower() == "true",
            compression_level=int(os.getenv("CACHE_COMPRESSION_LEVEL", "6")),
            cleanup_interval=int(os.getenv("CACHE_CLEANUP_INTERVAL", "3600")),
            max_age=int(os.getenv("CACHE_MAX_AGE", "86400")),
            min_free_space=int(os.getenv("CACHE_MIN_FREE_SPACE", "104857600"))
        )
        
        # Load output configuration
        self.output = OutputConfig(
            dir=Path(os.getenv("OUTPUT_DIR", str(self.config_dir / "output"))),
            directory=os.getenv("OUTPUT_DIRECTORY", "output"),
            format=os.getenv("OUTPUT_FORMAT", "json")
        )
        
        # Load download configuration
        self.download = DownloadConfig(
            quality=os.getenv("DOWNLOAD_QUALITY", "192")
        )

        # Load app configuration
        self.app = AppConfig(
            max_requests_per_minute=int(os.getenv("RATE_LIMIT_REQUESTS", "60")),
            max_concurrent_requests=int(os.getenv("MAX_CONCURRENT_REQUESTS", "5")),
            rate_limit_enabled=os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true",
            rate_limit_window=int(os.getenv("RATE_LIMIT_WINDOW", "60")),
            rate_limit_requests=int(os.getenv("RATE_LIMIT_REQUESTS", "60")),
            max_retries=int(os.getenv("MAX_RETRIES", "3")),
            retry_delay=float(os.getenv("RETRY_DELAY", "1.0")),
            retry_backoff=float(os.getenv("RETRY_BACKOFF", "2.0")),
            retry_max_delay=float(os.getenv("MAX_RETRY_DELAY", "30.0"))
        )

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        parts = key.split(".")
        value = self
        
        try:
            for part in parts:
                value = getattr(value, part)
            return value
        except AttributeError:
            return default
    
    def set(self, key: str, value: Any) -> None:
        """
        Set a configuration value.
        
        Args:
            key: Configuration key (dot notation for nested values)
            value: Configuration value
            
        Raises:
            ValueError: If the key path is invalid or value is invalid
        """
        parts = key.split(".")
        target = self
        
        try:
            # Navigate to the parent object
            for part in parts[:-1]:
                target = getattr(target, part)
                
            # Set the value
            setattr(target, parts[-1], value)
            
            # Validate the new configuration
            self._validate()
        except AttributeError:
            raise ValueError(f"Invalid configuration key: {key}")

    def _validate(self) -> None:
        """
        Validate configuration values.
        
        Raises:
            ValueError: If any configuration value is invalid
        """
        # Track config validation
        if not 0 <= self.track.confidence_threshold <= 1:
            raise ValueError("Confidence threshold must be between 0 and 1")
        if self.track.segment_length <= 0:
            raise ValueError("Segment length must be positive")
        if self.track.overlap < 0:
            raise ValueError("Overlap must be non-negative")
            
        # Cache config validation
        if self.cache.ttl <= 0:
            raise ValueError("Cache TTL must be positive")
        if self.cache.max_size <= 0:
            raise ValueError("Cache max size must be positive")
            
        # App config validation
        if self.app.max_requests_per_minute <= 0:
            raise ValueError("Max requests per minute must be positive")
        if self.app.max_concurrent_requests <= 0:
            raise ValueError("Max concurrent requests must be positive")
        if self.app.rate_limit_window <= 0:
            raise ValueError("rate limit window must be positive")
        if self.app.max_retries < 0:
            raise ValueError("Max retries must be non-negative")
        if self.app.retry_delay <= 0:
            raise ValueError("Retry delay must be positive")
        if self.app.retry_backoff <= 1:
            raise ValueError("Retry backoff must be greater than 1")
        if self.app.retry_max_delay <= self.app.retry_delay:
            raise ValueError("Max retry delay must be greater than retry delay")

    def __str__(self) -> str:
        """Return string representation of config."""
        config_dict = self.to_dict()
        return json.dumps(config_dict, indent=2)

    def __repr__(self) -> str:
        """Return string representation with masked sensitive data."""
        return f"TracklistifyConfig({self.__str__()})"

    def load_from_file(self, file_path: Path) -> None:
        """
        Load configuration from a JSON file.
        
        Args:
            file_path: Path to configuration file
            
        Raises:
            ValueError: If file is invalid
            OSError: If file cannot be read
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")
            
        try:
            with open(file_path) as f:
                config_data = json.load(f)
                
            # Update configuration from file
            if "track" in config_data:
                for key, value in config_data["track"].items():
                    setattr(self.track, key, value)
                    
            if "cache" in config_data:
                for key, value in config_data["cache"].items():
                    setattr(self.cache, key, value)
                    
            if "providers" in config_data:
                for key, value in config_data["providers"].items():
                    setattr(self.providers, key, value)
                    
            if "app" in config_data:
                for key, value in config_data["app"].items():
                    setattr(self.app, key, value)
                    
            if "output" in config_data:
                for key, value in config_data["output"].items():
                    setattr(self.output, key, value)
                    
            if "download" in config_data:
                for key, value in config_data["download"].items():
                    setattr(self.download, key, value)
                    
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in configuration file: {e}")
        except Exception as e:
            raise ValueError(f"Error loading configuration file: {e}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        config_dict = {
            "providers": {
                k: str(v) if isinstance(v, Path) else v 
                for k, v in self.providers.__dict__.items()
            },
            "track": {
                k: str(v) if isinstance(v, Path) else v 
                for k, v in self.track.__dict__.items()
            },
            "cache": {
                k: str(v) if isinstance(v, Path) else v 
                for k, v in self.cache.__dict__.items()
            },
            "output": {
                k: str(v) if isinstance(v, Path) else v 
                for k, v in self.output.__dict__.items()
            },
            "download": {
                k: str(v) if isinstance(v, Path) else v 
                for k, v in self.download.__dict__.items()
            },
            "app": {
                k: str(v) if isinstance(v, Path) else v 
                for k, v in self.app.__dict__.items()
            }
        }
        
        # Mask sensitive data
        return mask_sensitive_data(config_dict)

    @property
    def rules(self) -> Dict[str, List[Any]]:
        """Get validation rules for documentation."""
        if not self._validator:
            self._validator = self._create_validator()
        return self._validator.rules

    def _create_validator(self) -> ConfigValidator:
        """Create and configure the configuration validator."""
        validator = ConfigValidator()
        
        # Type validation
        validator.add_type_rule("confidence_threshold", float, allow_none=False)
        validator.add_type_rule("segment_length", int, allow_none=False)
        validator.add_type_rule("overlap", int, allow_none=False)
        validator.add_type_rule("cache_enabled", bool, allow_none=True)
        validator.add_type_rule("time_threshold", int, allow_none=False)
        validator.add_type_rule("max_duplicates", int, allow_none=False)
        validator.add_type_rule("min_confidence", float, allow_none=False)
        
        # Range validation
        validator.add_range_rule(
            "confidence_threshold",
            min_value=0.0,
            max_value=1.0,
            include_min=True,
            include_max=True,
            message="Confidence threshold must be between 0 and 1"
        )
        validator.add_range_rule(
            "segment_length",
            min_value=1,
            max_value=60,
            message="Segment length must be between 1 and 60 seconds"
        )
        validator.add_range_rule(
            "overlap",
            min_value=0,
            max_value=30,
            message="Overlap must be between 0 and 30 seconds"
        )
        validator.add_range_rule(
            "time_threshold",
            min_value=1,
            max_value=300,
            message="Time threshold must be between 1 and 300 seconds"
        )
        validator.add_range_rule(
            "max_duplicates",
            min_value=1,
            max_value=10,
            message="Max duplicates must be between 1 and 10"
        )
        validator.add_range_rule(
            "min_confidence",
            min_value=0.0,
            max_value=1.0,
            include_min=True,
            include_max=True,
            message="Minimum confidence must be between 0 and 1"
        )
        
        # Path validation
        validator.add_path_rule(
            "cache_dir",
            {
                PathRequirement.IS_DIR,
                PathRequirement.WRITABLE,
                PathRequirement.IS_ABSOLUTE
            },
            create_if_missing=True,
            message="Cache directory must be an absolute, writable directory"
        )
        validator.add_path_rule(
            "output_dir",
            {
                PathRequirement.IS_DIR,
                PathRequirement.WRITABLE,
                PathRequirement.IS_ABSOLUTE
            },
            create_if_missing=True
        )
        
        # Pattern validation for provider credentials
        validator.add_pattern_rule(
            "spotify_client_id",
            pattern=r"^[0-9a-f]{32}$",
            is_regex=True,
            message="Invalid Spotify client ID format"
        )
        
        # Dependency validation
        validator.add_dependency_rule(
            "cache_dir",
            {"cache_enabled"},
            condition=lambda config: config.get("cache_enabled", False),
            message="cache_dir is required when cache_enabled is True"
        )
        
        # Provider dependencies
        spotify_fields = {"spotify_client_id", "spotify_client_secret"}
        validator.add_dependency_rule(
            "spotify",
            spotify_fields,
            condition=lambda config: any(
                field in config for field in spotify_fields
            ),
            message="Both Spotify credentials are required if using Spotify"
        )
        
        return validator

# Alias for backward compatibility
Config = TracklistifyConfig

# Global configuration instance
_config: Optional[Config] = None

def load_env_config() -> None:
    """
    Load environment variables from .env file with fallback to .env.example.
    """
    # Get project root directory (where .env files are located)
    project_root = Path(__file__).parent.parent.parent
    
    # Try loading .env first
    env_path = project_root / ".env"
    if not env_path.exists():
        # Fallback to .env.example
        env_path = project_root / ".env.example"
    
    if env_path.exists():
        load_dotenv(env_path)

def get_config(config_dir: Optional[Path] = None) -> Config:
    """
    Get the global configuration instance.
    
    Args:
        config_dir: Optional configuration directory path
        
    Returns:
        Config: Global configuration instance
    """
    global _config
    if _config is None:
        # Load environment variables first
        load_env_config()
        
        # Create and load configuration
        _config = Config(config_dir)
        _config.load()
    return _config

__all__ = [
    'Config',
    'TracklistifyConfig',
    'get_config',
    'load_env_config',
    'ValidationError',
    'SecureString',
    'mask_sensitive_data',
    'SENSITIVE_FIELDS'
]
