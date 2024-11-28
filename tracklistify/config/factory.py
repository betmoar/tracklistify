"""Configuration factory module."""

# Standard library imports
from typing import Dict, Type, TypeVar

# Local imports
from .base import BaseConfig, TrackIdentificationConfig

T = TypeVar("T", bound=BaseConfig)


class ConfigFactory:
    """Factory for creating and managing configuration instances."""

    _instances: Dict[Type[BaseConfig], BaseConfig] = {}

    @classmethod
    def get_config(
        cls,
        config_type: Type[T] = TrackIdentificationConfig,
        force_refresh: bool = False,
    ) -> T:
        """
        Get configuration instance of the specified type.

        Args:
            config_type: Type of configuration to create.
            force_refresh: Whether to force creation of a new instance.

        Returns:
            Configuration instance.
        """
        if force_refresh or config_type not in cls._instances:
            cls._instances[config_type] = config_type()
        return cls._instances[config_type]

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached configuration instances."""
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
    ConfigFactory.clear_cache(TrackIdentificationConfig)
