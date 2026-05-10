# tracklistify/cache/factory.py

# Standard library imports
import threading
from pathlib import Path
from typing import Optional

# Local imports
from .base import BaseCache
from .invalidation import CompositeStrategy, LRUStrategy, SizeStrategy, TTLStrategy
from .storage import JSONStorage
from tracklistify.utils.constants import DEFAULT_CACHE_MAX_SIZE, DEFAULT_CACHE_TTL
from tracklistify.utils.logger import get_logger

logger = get_logger(__name__)

# Global cache instance with thread-safe access
_cache_instance = None
_cache_lock = threading.Lock()


def create_cache(
    cache_dir: Optional[Path] = None,
    ttl: int = DEFAULT_CACHE_TTL,
    max_size: int = DEFAULT_CACHE_MAX_SIZE,
) -> BaseCache:
    """Create new cache instance."""
    storage = JSONStorage(cache_dir or Path.home() / ".tracklistify" / "cache")

    strategy = CompositeStrategy(
        [TTLStrategy(ttl), LRUStrategy(ttl), SizeStrategy(max_size)]
    )

    return BaseCache(
        storage=storage, invalidation_strategy=strategy, ttl=ttl, max_size=max_size
    )


def get_cache() -> BaseCache:
    """Get global cache instance.

    This function is thread-safe using double-checked locking pattern.
    Multiple threads can safely call this function concurrently.

    Returns:
        BaseCache: The global cache instance.
    """
    global _cache_instance

    # Fast path: instance already exists
    if _cache_instance is not None:
        return _cache_instance

    # Slow path: need to create instance (thread-safe)
    with _cache_lock:
        # Double-check inside lock
        if _cache_instance is None:
            _cache_instance = create_cache()

    return _cache_instance


def clear_cache() -> None:
    """Clear global cache instance.

    This function is thread-safe.
    """
    global _cache_instance
    with _cache_lock:
        _cache_instance = None
