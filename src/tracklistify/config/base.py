"""Base configuration types and interfaces."""

# Standard library imports
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

# Local imports
from .paths import get_root
from .security import mask_sensitive_value
from .validation import ConfigValidator, PathRequirement, PathRule


@dataclass
class BaseConfig:
    """Base configuration class."""

    project_root = get_root()

    # Directories
    log_dir: Path = field(default=project_root / ".tracklistify/log")
    temp_dir: Path = field(default=project_root / ".tracklistify/temp")
    cache_dir: Path = field(default=project_root / ".tracklistify/cache")
    output_dir: Path = field(default=project_root / ".tracklistify/output")

    # Log settings
    verbose: bool = field(default=False)
    debug: bool = field(default=False)

    def __post_init__(self):
        """Initialize configuration after creation."""
        self._validator = ConfigValidator()
        self._load_from_env()
        self._create_directories()
        self._setup_validation()
        self._validate()

    def _create_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        directories = [self.output_dir, self.cache_dir, self.temp_dir, self.log_dir]

        for directory in directories:
            if isinstance(directory, Path):
                # Expand user directory (e.g., ~/)
                directory = directory.expanduser()
                try:
                    directory.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    raise ValueError(
                        f"Failed to create directory {directory}: {e}"
                    ) from e

    def _load_from_env(self) -> None:
        """Load configuration from environment variables."""
        for field_name, field_value in self.__class__.__dataclass_fields__.items():
            env_key = f"TRACKLISTIFY_{field_name.upper()}"
            env_value = os.getenv(env_key)

            if env_value is not None:
                # Strip any comments and whitespace
                env_value = env_value.split("#")[0].strip()

                # Convert string value to appropriate type
                field_type = field_value.type
                try:
                    if field_type is bool:
                        # Handle boolean values
                        value = env_value.lower() in ("true", "1", "yes", "on")
                    elif field_type == Path:
                        # Handle paths - resolve relative paths relative to project root
                        path = Path(os.path.expanduser(env_value))
                        if not path.is_absolute():
                            # Relative path - resolve relative to project root
                            path = get_root() / path
                        value = path
                    elif field_type == List[str]:
                        # Handle string lists (comma-separated)
                        value = [s.strip() for s in env_value.split(",") if s.strip()]
                    elif field_type in (int, float):
                        # Handle numeric types
                        try:
                            value = field_type(env_value)
                        except ValueError as e:
                            # Do NOT use eval() - security vulnerability!
                            # Mask the value in case a user mis-pasted a secret
                            # (e.g. API key) into a numeric field.
                            safe_value = mask_sensitive_value(env_key, env_value)
                            raise ValueError(
                                f"Invalid {field_type.__name__} value for "
                                f"{env_key}: {safe_value}. "
                                f"Expected a valid {field_type.__name__}."
                            ) from e
                    else:
                        # Handle other types
                        value = field_type(env_value)

                    # Set the value on the instance
                    setattr(self, field_name, value)
                except Exception as e:
                    safe_value = mask_sensitive_value(env_key, env_value)
                    raise ValueError(
                        f"Invalid value for {env_key}: {safe_value} - {str(e)}"
                    ) from e

    def _setup_validation(self) -> None:
        """Set up validation rules for configuration fields.

        This is a template method that subclasses should override to add
        their specific validation rules. Called automatically during
        __post_init__.

        Subclasses should call super()._setup_validation() first, then
        add their own rules using self._validator.

        Example:
            def _setup_validation(self):
                super()._setup_validation()
                self._validator.add_range_rule("my_field", 0, 100)
        """
        # Base class has no validation rules to set up
        # Subclasses override this to add their specific rules

    def _validate(self) -> None:
        """Validate all configuration values against defined rules.

        This is a template method that subclasses can override to add
        custom validation logic beyond the declarative rules.
        Called automatically during __post_init__ after _setup_validation.

        Subclasses should call super()._validate() first, then add
        any additional validation that can't be expressed as rules.

        Raises:
            ValueError: If any configuration value is invalid.
        """
        # Base class validation is handled by _validator
        # Subclasses can override to add custom validation logic


@dataclass
class TrackIdentificationConfig(BaseConfig):
    """Track identification configuration."""

    # Base config fields are inherited

    # Track identification specific fields
    segment_length: int = field(default=60)
    min_confidence: float = field(default=0.5)
    time_threshold: float = field(default=30.0)
    max_duplicates: int = field(default=2)
    overlap_duration: int = field(default=10)
    overlap_strategy: str = field(default="weighted")
    min_segment_length: int = field(default=10)

    # Provider settings
    primary_provider: str = field(default="shazam")
    fallback_enabled: bool = field(default=False)
    fallback_providers: List[str] = field(default_factory=list)

    # Caching settings
    cache_enabled: bool = field(default=True)
    cache_ttl: int = field(default=3600)
    # Byte budget for the cache (matches SizeStrategy / BaseCache semantics).
    # Previously defaulted to 1000 — meant as "entries" but interpreted as
    # bytes, which was so small the cache rejected every Shazam response.
    cache_max_size: int = field(default=1_000_000)
    cache_storage_format: str = field(default="json")
    cache_compression_enabled: bool = field(default=True)
    cache_compression_level: int = field(default=6)
    cache_cleanup_enabled: bool = field(default=True)
    cache_cleanup_interval: int = field(default=3600)
    cache_max_age: int = field(default=86400)
    cache_min_free_space: int = field(default=104857600)

    # Rate limiting settings
    rate_limit_enabled: bool = field(default=True)
    max_requests_per_minute: int = field(default=25)
    max_concurrent_requests: int = field(default=2)

    # Circuit-breaker settings (consumed by RateLimiter via getattr; declared
    # here so env-var overrides land on the dataclass instance).
    circuit_breaker_enabled: bool = field(default=True)
    circuit_breaker_threshold: int = field(default=5)
    circuit_breaker_reset_timeout: float = field(default=60.0)

    # ACRCloud settings
    acrcloud_max_rpm: int = field(default=300)
    acrcloud_max_concurrent: int = field(default=10)

    # Shazam settings
    shazam_max_rpm: int = field(default=25)
    shazam_max_concurrent: int = field(default=1)
    shazam_cooldown_seconds: float = field(default=2.25)

    # Spotify rate limits (consumed by RateLimiter.register_provider)
    spotify_max_rpm: int = field(default=120)
    spotify_max_concurrent: int = field(default=20)

    # Output formats
    output_format: str = field(default="json")

    # Downloader settings
    download_quality: str = field(default="192")
    download_format: str = field(default="mp3")
    download_max_retries: int = field(default=3)

    def __post_init__(self):
        """Initialize configuration after dataclass creation.

        Delegates fully to ``BaseConfig.__post_init__``; via virtual dispatch the
        parent calls ``self._setup_validation`` and ``self._validate``, which
        resolve to the subclass overrides — so the additional validation rules
        defined here are still applied without running twice.
        """
        super().__post_init__()

    def _setup_validation(self):
        """Set up validation rules."""
        super()._setup_validation()  # Call parent's validation setup

        # Add type validation rules
        self._validator.add_type_rule("segment_length", int)
        self._validator.add_type_rule("overlap_duration", int)
        self._validator.add_type_rule("min_confidence", float)
        self._validator.add_type_rule("time_threshold", float)
        self._validator.add_type_rule("max_duplicates", int)

        # Add range validation rules
        self._validator.add_range_rule("segment_length", 10, 300)
        self._validator.add_range_rule("overlap_duration", 0, 30)
        self._validator.add_range_rule("min_confidence", 0.0, 1.0)
        self._validator.add_range_rule("time_threshold", 0.0, 300.0)
        self._validator.add_range_rule("max_duplicates", 0, 10)

        # Add path validation rules for directories
        path_requirements = {PathRequirement.IS_DIR, PathRequirement.WRITABLE}
        self._validator.add_rule(
            PathRule("output_dir", path_requirements, create_if_missing=True)
        )
        self._validator.add_rule(
            PathRule("cache_dir", path_requirements, create_if_missing=True)
        )
        self._validator.add_rule(
            PathRule("temp_dir", path_requirements, create_if_missing=True)
        )
