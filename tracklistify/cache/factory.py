# tracklistify/cache/factory.py

# Standard library imports
from pathlib import Path
from typing import Optional

# Local imports
from .base import BaseCache
from .invalidation import CompositeStrategy, LRUStrategy, SizeStrategy, TTLStrategy
from .storage import JSONStorage
from tracklistify.utils.logger import get_logger

logger = get_logger(__name__)

# Global cache instance
_cache_instance = None


def create_cache(
    cache_dir: Optional[Path] = None, ttl: int = 3600, max_size: int = 1_000_000
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
    """Get global cache instance."""
    global _cache_instance

    if _cache_instance is None:
        _cache_instance = create_cache()

    return _cache_instance
