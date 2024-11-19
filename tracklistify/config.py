"""
Configuration management for Tracklistify.
"""

import os
from dataclasses import dataclass, field
from typing import Optional, List
from dotenv import load_dotenv

@dataclass
class ProviderConfig:
    """Provider configuration."""
    primary_provider: str = field(default="acrcloud")
    fallback_enabled: bool = field(default=True)
    fallback_providers: List[str] = field(default_factory=lambda: ["shazam"])
    acrcloud_host: str = field(default="identify-eu-west-1.acrcloud.com")
    acrcloud_timeout: int = field(default=10)
    shazam_enabled: bool = field(default=True)
    shazam_timeout: int = field(default=10)
    spotify_timeout: int = field(default=10)

@dataclass
class TrackConfig:
    """Track identification configuration."""
    segment_length: int = field(default=60)
    min_confidence: float = field(default=0.0)
    time_threshold: int = field(default=60)
    max_duplicates: int = field(default=2)

@dataclass
class CacheConfig:
    """Cache configuration."""
    enabled: bool = field(default=True)
    ttl: int = field(default=3600)
    max_size: int = field(default=1000)

@dataclass
class OutputConfig:
    """Output configuration."""
    directory: str = field(default="output")
    format: str = field(default="json")

@dataclass
class AppConfig:
    """Application configuration."""
    rate_limit_enabled: bool = field(default=True)
    max_requests_per_minute: int = field(default=60)  # Used by RateLimiter
    debug: bool = field(default=False)
    verbose: bool = field(default=False)

@dataclass
class Config:
    """Global configuration."""
    providers: ProviderConfig = field(default_factory=ProviderConfig)
    track: TrackConfig = field(default_factory=TrackConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    app: AppConfig = field(default_factory=AppConfig)
    output: OutputConfig = field(default_factory=OutputConfig)

    def __post_init__(self):
        """Load configuration from environment."""
        load_dotenv()
        self._load_provider_config()
        self._load_track_config()
        self._load_cache_config()
        self._load_app_config()
        self._load_output_config()

    def _load_provider_config(self) -> None:
        """Load provider configuration."""
        self.providers = ProviderConfig(
            primary_provider=os.getenv('PRIMARY_PROVIDER', self.providers.primary_provider),
            fallback_enabled=os.getenv('PROVIDER_FALLBACK_ENABLED', 'true').lower() == 'true',
            fallback_providers=os.getenv('PROVIDER_FALLBACK_ORDER', 'shazam').split(','),
            acrcloud_host=os.getenv('ACR_HOST', self.providers.acrcloud_host),
            acrcloud_timeout=int(os.getenv('ACR_TIMEOUT', self.providers.acrcloud_timeout)),
            shazam_enabled=os.getenv('SHAZAM_ENABLED', 'true').lower() == 'true',
            shazam_timeout=int(os.getenv('SHAZAM_TIMEOUT', self.providers.shazam_timeout)),
            spotify_timeout=int(os.getenv('SPOTIFY_TIMEOUT', self.providers.spotify_timeout))
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
            max_size=int(os.getenv('CACHE_MAX_SIZE', self.cache.max_size))
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
            directory=os.getenv('OUTPUT_DIRECTORY', self.output.directory),
            format=os.getenv('OUTPUT_FORMAT', self.output.format)
        )

_config_instance = None

def get_config() -> Config:
    """Get global configuration instance."""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance
