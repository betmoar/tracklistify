"""Configuration factory module."""

# Standard library imports
import threading
from typing import Dict, Type, TypeVar

# Local imports
from .base import BaseConfig, TrackIdentificationConfig

# Import ConfigError from canonical location for re-export
from tracklistify.core.exceptions import ConfigError

__all__ = ["ConfigFactory", "get_config", "clear_config", "ConfigError"]

T = TypeVar("T", bound=BaseConfig)

# Thread safety lock for singleton access
_config_lock = threading.Lock()


class ConfigFactory:
    """Factory for creating and managing configuration instances.

    This class is thread-safe. Multiple threads can safely call get_config()
    concurrently without creating duplicate instances.
    """

    _instances: Dict[Type[BaseConfig], BaseConfig] = {}

    @classmethod
    def get_config(
        cls,
        config_type: Type[T] = TrackIdentificationConfig,
        force_refresh: bool = False,
    ) -> T:
        """
        Get configuration instance of the specified type.

        This method is thread-safe using double-checked locking pattern.

        Args:
            config_type: Type of configuration to create.
            force_refresh: Whether to force creation of a new instance.

        Returns:
            Configuration instance.
        """
        # Fast path: instance exists and no refresh needed
        if not force_refresh and config_type in cls._instances:
            return cls._instances[config_type]

        # Slow path: need to create instance (thread-safe)
        with _config_lock:
            # Double-check inside lock
            if force_refresh or config_type not in cls._instances:
                cls._instances[config_type] = config_type()
            return cls._instances[config_type]

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached configuration instances."""
        with _config_lock:
            cls._instances.clear()


def get_config(force_refresh: bool = False) -> TrackIdentificationConfig:
    """Get global configuration instance.

    Args:
        force_refresh: If True, create a new config instance even if one exists

    Returns:
        TrackIdentificationConfig instance
    """
    return ConfigFactory.get_config(
        TrackIdentificationConfig, force_refresh=force_refresh
    )


def clear_config() -> None:
    """Clear global configuration instance."""
    ConfigFactory.clear_cache()
