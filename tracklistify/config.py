"""
Configuration management for Tracklistify.
"""

import os
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, List, Dict, Union, Any
from dotenv import load_dotenv

from .config.security import (
    SecureConfigLoader, 
    log_masked_config,
    mask_sensitive_data,
    SENSITIVE_FIELDS
)

def ensure_directory(path: Union[str, Path]) -> Path:
    """Ensure directory exists and return Path object."""
    path = Path(path).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path

def validate_path(path: Union[str, Path]) -> Path:
    """Validate and normalize path."""
    return Path(path).expanduser().resolve()

@dataclass
class ProviderConfig:
    """Provider configuration with extended settings."""
    # Basic provider settings
    primary_provider: str = field(default="acrcloud")
    fallback_enabled: bool = field(default=True)
    fallback_providers: List[str] = field(default_factory=lambda: ["shazam"])
    
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
    rate_limit_requests: int = field(default=60)
    rate_limit_window: int = field(default=60)  # seconds
    
    # Concurrent operations
    max_concurrent_requests: int = field(default=5)
    request_timeout: int = field(default=30)
    connection_timeout: int = field(default=10)
    
    # Health checking
    health_check_enabled: bool = field(default=True)
    health_check_interval: int = field(default=300)  # seconds
    health_check_timeout: int = field(default=5)

@dataclass
class TrackConfig:
    """Track identification configuration."""
    segment_length: int = field(default=60)
    min_confidence: float = field(default=0.0)
    time_threshold: int = field(default=60)
    max_duplicates: int = field(default=2)

@dataclass
class CacheConfig:
    """Enhanced cache configuration with directory settings."""
    # Basic cache settings
    enabled: bool = field(default=True)
    ttl: int = field(default=3600)
    max_size: int = field(default=1000)
    
    # Directory settings
    base_directory: Path = field(
        default_factory=lambda: Path(os.path.expanduser("~")) / ".tracklistify" / "cache"
    )
    temp_directory: Path = field(
        default_factory=lambda: Path(os.path.expanduser("~")) / ".tracklistify" / "cache" / "temp"
    )
    
    # Storage settings
    storage_format: str = field(default="json")  # json, pickle, binary
    compression_enabled: bool = field(default=True)
    compression_level: int = field(default=6)  # 0-9 for zlib
    
    # Maintenance settings
    cleanup_enabled: bool = field(default=True)
    cleanup_interval: int = field(default=3600)  # seconds
    max_age: int = field(default=86400)  # seconds
    min_free_space: int = field(default=1024 * 1024 * 100)  # 100MB
    
    def __post_init__(self):
        """Ensure cache directories exist."""
        self.base_directory = ensure_directory(self.base_directory)
        self.temp_directory = ensure_directory(self.temp_directory)

@dataclass
class OutputConfig:
    """Output configuration with enhanced path handling."""
    directory: Path = field(
        default_factory=lambda: Path("output").resolve()
    )
    format: str = field(default="json")
    
    def __post_init__(self):
        """Ensure output directory exists."""
        self.directory = ensure_directory(self.directory)

@dataclass
class DownloadConfig:
    """Download configuration with enhanced path handling."""
    quality: str = field(default="192")
    format: str = field(default="mp3")
    temp_dir: Path = field(
        default_factory=lambda: Path(os.path.expanduser("~")) / ".tracklistify" / "temp"
    )
    max_retries: int = field(default=3)
    
    def __post_init__(self):
        """Ensure download directory exists."""
        self.temp_dir = ensure_directory(self.temp_dir)

@dataclass
class AppConfig:
    """Application configuration."""
    rate_limit_enabled: bool = field(default=True)
    max_requests_per_minute: int = field(default=60)
    debug: bool = field(default=False)
    verbose: bool = field(default=False)

@dataclass
class Config:
    """Global configuration."""
    providers: ProviderConfig = field(default_factory=ProviderConfig)
    track: TrackConfig = field(default_factory=TrackConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    app: AppConfig = field(default_factory=AppConfig)
    download: DownloadConfig = field(default_factory=DownloadConfig)
    
    def __post_init__(self):
        """Load configuration from environment."""
        # Initialize secure config loader
        self.secure_loader = SecureConfigLoader()
        
        # Define required secrets
        self.secure_loader.require_secrets(
            'ACR_ACCESS_KEY',
            'ACR_ACCESS_SECRET',
            'SPOTIFY_CLIENT_ID',
            'SPOTIFY_CLIENT_SECRET'
        )
        
        # Load configuration
        load_dotenv()
        self._load_provider_config()
        self._load_track_config()
        self._load_cache_config()
        self._load_app_config()
        self._load_output_config()
        self._load_download_config()
        self._setup_directories()
    
    def _setup_directories(self):
        """Ensure all required directories exist."""
        # Cache directories
        ensure_directory(self.cache.base_directory)
        ensure_directory(self.cache.temp_directory)
        
        # Output directory
        ensure_directory(self.output.directory)
        
        # Download directory
        ensure_directory(self.download.temp_dir)
    
    @log_masked_config
    def _load_provider_config(self) -> None:
        """Load provider configuration."""
        # Load secrets first
        secrets = self.secure_loader.load_secrets()
        
        self.providers = ProviderConfig(
            primary_provider=os.getenv('PRIMARY_PROVIDER', self.providers.primary_provider),
            fallback_enabled=os.getenv('PROVIDER_FALLBACK_ENABLED', 'true').lower() == 'true',
            fallback_providers=os.getenv('PROVIDER_FALLBACK_ORDER', 'shazam').split(','),
            acrcloud_host=os.getenv('ACR_HOST', self.providers.acrcloud_host),
            acrcloud_timeout=int(os.getenv('ACR_TIMEOUT', self.providers.acrcloud_timeout)),
            shazam_enabled=os.getenv('SHAZAM_ENABLED', 'true').lower() == 'true',
            shazam_timeout=int(os.getenv('SHAZAM_TIMEOUT', self.providers.shazam_timeout)),
            spotify_timeout=int(os.getenv('SPOTIFY_TIMEOUT', self.providers.spotify_timeout)),
            retry_strategy=os.getenv('PROVIDER_RETRY_STRATEGY', self.providers.retry_strategy),
            retry_max_attempts=int(os.getenv('PROVIDER_MAX_RETRIES', self.providers.retry_max_attempts)),
            retry_base_delay=float(os.getenv('PROVIDER_RETRY_DELAY', self.providers.retry_base_delay)),
            retry_max_delay=float(os.getenv('PROVIDER_MAX_RETRY_DELAY', self.providers.retry_max_delay)),
            rate_limit_enabled=os.getenv('RATE_LIMIT_ENABLED', 'true').lower() == 'true',
            rate_limit_requests=int(os.getenv('RATE_LIMIT_REQUESTS', self.providers.rate_limit_requests)),
            rate_limit_window=int(os.getenv('RATE_LIMIT_WINDOW', self.providers.rate_limit_window)),
            max_concurrent_requests=int(os.getenv('MAX_CONCURRENT_REQUESTS', self.providers.max_concurrent_requests))
        )

    def _load_track_config(self) -> None:
        """Load track identification configuration."""
        self.track = TrackConfig(
            segment_length=int(os.getenv('SEGMENT_LENGTH', self.track.segment_length)),
            min_confidence=float(os.getenv('MIN_CONFIDENCE', self.track.min_confidence)),
            time_threshold=int(os.getenv('TIME_THRESHOLD', self.track.time_threshold)),
            max_duplicates=int(os.getenv('MAX_DUPLICATES', self.track.max_duplicates))
        )

    def _load_cache_config(self) -> None:
        """Load cache configuration."""
        self.cache = CacheConfig(
            enabled=os.getenv('CACHE_ENABLED', 'true').lower() == 'true',
            ttl=int(os.getenv('CACHE_TTL', self.cache.ttl)),
            max_size=int(os.getenv('CACHE_MAX_SIZE', self.cache.max_size)),
            base_directory=Path(os.getenv('CACHE_BASE_DIR', self.cache.base_directory)),
            temp_directory=Path(os.getenv('CACHE_TEMP_DIR', self.cache.temp_directory)),
            storage_format=os.getenv('CACHE_STORAGE_FORMAT', self.cache.storage_format),
            compression_enabled=os.getenv('CACHE_COMPRESSION_ENABLED', 'true').lower() == 'true',
            compression_level=int(os.getenv('CACHE_COMPRESSION_LEVEL', self.cache.compression_level)),
            cleanup_enabled=os.getenv('CACHE_CLEANUP_ENABLED', 'true').lower() == 'true',
            cleanup_interval=int(os.getenv('CACHE_CLEANUP_INTERVAL', self.cache.cleanup_interval)),
            max_age=int(os.getenv('CACHE_MAX_AGE', self.cache.max_age)),
            min_free_space=int(os.getenv('CACHE_MIN_FREE_SPACE', self.cache.min_free_space))
        )

    def _load_app_config(self) -> None:
        """Load application configuration."""
        self.app = AppConfig(
            rate_limit_enabled=os.getenv('RATE_LIMIT_ENABLED', 'true').lower() == 'true',
            max_requests_per_minute=int(os.getenv('MAX_REQUESTS_PER_MINUTE', self.app.max_requests_per_minute)),
            debug=os.getenv('DEBUG', 'false').lower() == 'true',
            verbose=os.getenv('VERBOSE', 'false').lower() == 'true'
        )

    def _load_output_config(self) -> None:
        """Load output configuration."""
        self.output = OutputConfig(
            directory=Path(os.getenv('OUTPUT_DIRECTORY', self.output.directory)),
            format=os.getenv('OUTPUT_FORMAT', self.output.format)
        )

    def _load_download_config(self) -> None:
        """Load download configuration."""
        self.download = DownloadConfig(
            quality=os.getenv('DOWNLOAD_QUALITY', self.download.quality),
            format=os.getenv('DOWNLOAD_FORMAT', self.download.format),
            temp_dir=Path(os.getenv('DOWNLOAD_TEMP_DIR', self.download.temp_dir)),
            max_retries=int(os.getenv('DOWNLOAD_MAX_RETRIES', self.download.max_retries))
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return mask_sensitive_data(asdict(self))
    
    def __str__(self) -> str:
        """String representation with masked sensitive data."""
        return json.dumps(self.to_dict(), indent=2)

_config_instance = None

def get_config() -> Config:
    """Get global configuration instance."""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance
