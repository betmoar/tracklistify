"""Base configuration types and interfaces."""

# Standard library imports
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

# Local imports
from .validation import ConfigValidator, PathRequirement, PathRule


@dataclass
class BaseConfig:
    """Base configuration class."""

    output_dir: Path = field(default=Path(".tracklistify/output"))
    cache_dir: Path = field(default=Path(".tracklistify/cache"))
    temp_dir: Path = field(default=Path(".tracklistify/temp"))
    log_dir: Path = field(default=Path(".tracklistify/log"))
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
                        # Handle paths
                        value = Path(os.path.expanduser(env_value))
                    elif field_type == List[str]:
                        # Handle string lists (comma-separated)
                        value = [s.strip() for s in env_value.split(",") if s.strip()]
                    elif field_type in (int, float):
                        # Handle numeric types
                        try:
                            value = field_type(env_value)
                        except ValueError:
                            # Try evaluating numeric expressions
                            value = field_type(eval(env_value))
                    else:
                        # Handle other types
                        value = field_type(env_value)

                    # Set the value on the instance
                    setattr(self, field_name, value)
                except Exception as e:
                    raise ValueError(
                        f"Invalid value for {env_key}: {env_value} - {str(e)}"
                    ) from e

    def _setup_validation(self):
        """Set up validation rules."""
        # Rest of validation setup...

    def _validate(self) -> None:
        """Validate configuration values."""
        # Add any base validation here
        pass


@dataclass
class TrackIdentificationConfig(BaseConfig):
    """Track identification configuration."""

    # Base config fields are inherited

    # Track identification specific fields
    segment_length: int = field(default=30)
    overlap_duration: int = field(default=10)
    min_confidence: float = field(default=0.5)
    time_threshold: float = field(default=60.0)
    max_duplicates: int = field(default=2)
    primary_provider: str = field(default="shazam")
    fallback_enabled: bool = field(default=True)
    fallback_providers: List[str] = field(default_factory=list)

    # Global rate limiting settings
    max_requests_per_minute: int = field(default=25)
    max_concurrent_requests: int = field(default=2)

    cache_enabled: bool = field(default=True)
    cache_ttl: int = field(default=86400)
    cache_max_size: int = field(default=1000000)
    cache_storage_format: str = field(default="json")
    cache_compression_enabled: bool = field(default=True)
    cache_compression_level: int = field(default=6)
    cache_cleanup_enabled: bool = field(default=True)
    cache_cleanup_interval: int = field(default=3600)
    cache_max_age: int = field(default=604800)
    cache_min_free_space: int = field(default=104857600)
    acrcloud_max_rpm: int = field(default=300)
    acrcloud_max_concurrent: int = field(default=10)
    shazam_max_rpm: int = field(default=25)
    shazam_max_concurrent: int = field(default=1)
    shazam_cooldown_seconds: float = field(default=2.25)
    output_format: str = field(default="json")

    def __post_init__(self):
        """Initialize configuration after dataclass creation."""
        # Load environment variables first
        self._load_from_env()

        # Then call parent's post_init to set up base config and create directories
        super().__post_init__()

        # Set up additional validation rules
        self._setup_validation()
        self._validate()

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
