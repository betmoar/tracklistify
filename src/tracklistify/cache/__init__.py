"""
Cache management for API responses and audio processing.
"""

# Standard library imports
import asyncio
from pathlib import Path
from typing import Optional, TypeVar

from tracklistify.utils.logger import get_logger

# Local/package imports (using relative imports to avoid cycles)
from .base import BaseCache
from .invalidation import CompositeStrategy, LRUStrategy, SizeStrategy, TTLStrategy
from .storage import JSONStorage

# Global logger instance
logger = get_logger(__name__)

T = TypeVar("T")

# Default config values if config loading fails
DEFAULT_CACHE_DIR = Path.home() / ".tracklistify" / "cache"
DEFAULT_CACHE_TTL = 3600
DEFAULT_CACHE_MAX_SIZE = 1_000_000

# Global cache instance
_cache_instance = None


def create_cache(
    cache_dir: Optional[Path] = None,
    ttl: int = DEFAULT_CACHE_TTL,
    max_size: int = DEFAULT_CACHE_MAX_SIZE,
) -> BaseCache:
    """Create cache instance with default or provided values."""
    try:
        # Resolve cache directory path
        cache_path = cache_dir or DEFAULT_CACHE_DIR
        if isinstance(cache_path, str):
            cache_path = Path(cache_path)

        # Ensure directory exists
        cache_path = cache_path.expanduser()
        cache_path.mkdir(parents=True, exist_ok=True)

        # Create storage with string path
        storage = JSONStorage(str(cache_path))

        # Create invalidation strategy
        strategy = CompositeStrategy(
            [TTLStrategy(ttl), LRUStrategy(ttl), SizeStrategy(max_size)]
        )

        logger.debug(f"Initializing cache in: {cache_path}")

        return BaseCache(
            storage=storage, invalidation_strategy=strategy, ttl=ttl, max_size=max_size
        )

    except Exception as e:
        logger.error(f"Failed to create cache: {e}")
        raise


def get_cache() -> BaseCache:
    """Get global cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = create_cache()
    return _cache_instance


def run_async(coro):
    """
    Helper function to run coroutines either in existing event loop or new one.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running event loop, create new one
        return asyncio.run(coro)

    if loop.is_running():
        # Create new loop in separate thread if needed
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    else:
        return loop.run_until_complete(coro)


__all__ = [
    "BaseCache",
    "create_cache",
    "get_cache",
    "TTLStrategy",
    "LRUStrategy",
    "SizeStrategy",
    "CompositeStrategy",
    "JSONStorage",
]
