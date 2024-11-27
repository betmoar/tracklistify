"""
Cache management for API responses and audio processing.
"""

# Standard library imports
import asyncio
import concurrent.futures
from pathlib import Path
from typing import Any, Dict, Optional, TypeVar

from tracklistify.utils.logger import logger

# Local/package imports (using relative imports to avoid cycles)
from .base import BaseCache
from .invalidation import CompositeStrategy, LRUStrategy, SizeStrategy, TTLStrategy
from .storage import JSONStorage

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


class Cache:
    """Backward-compatible cache interface using enhanced cache system."""

    def __init__(self, cache_dir: Optional[str] = None):
        """Initialize cache with directory."""
        config = get_config()
        self.cache_dir = Path(cache_dir) if cache_dir else config.cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._config = config

        # Initialize enhanced cache components
        self._storage = JSONStorage(str(self.cache_dir))
        self._strategy = CompositeStrategy(
            [
                TTLStrategy(self._config.cache_ttl),
                LRUStrategy(self._config.cache_ttl),
                SizeStrategy(self._config.cache_max_size),
            ]
        )
        self._cache = BaseCache[Dict[str, Any]](
            storage=self._storage, invalidation_strategy=self._strategy
        )

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get value from cache.

        Args:
            key: Cache key (usually a hash of the audio segment)

        Returns:
            Dict containing cached data if valid, None otherwise
        """
        if not self._config.cache_enabled:
            return None

        try:
            value = run_async(self._cache.get(key))
            if value is not None:
                logger.debug(f"Cache hit for key: {key}")
            return value

        except Exception as e:
            logger.warning(f"Failed to read cache for key {key}: {str(e)}")
            return None

    def set(self, key: str, value: Dict[str, Any]) -> None:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Data to cache
        """
        if not self._config.cache_enabled:
            return

        try:
            run_async(
                self._cache.set(
                    key=key,
                    value=value,
                    ttl=self._config.cache_ttl,
                    compression=self._config.cache_compression_enabled,
                )
            )
            logger.debug(f"Cached response for key: {key}")

        except Exception as e:
            logger.warning(f"Failed to write cache for key {key}: {str(e)}")

    def clear(self, max_age: Optional[int] = None) -> None:
        """
        Clear expired cache entries.

        Args:
            max_age: Maximum age in seconds, defaults to cache ttl from config
        """
        if not self._config.cache_enabled:
            return

        try:
            cleaned = run_async(self._cache.cleanup(max_age))
            logger.info(f"Cleared {cleaned} expired cache entries")

        except Exception as e:
            logger.warning(f"Failed to clear cache: {str(e)}")

    def delete(self, key: str) -> None:
        """
        Delete cache entry.

        Args:
            key: Cache key
        """
        try:
            run_async(self._cache.delete(key))

        except Exception as e:
            logger.warning(f"Failed to delete cache key {key}: {str(e)}")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return self._cache.get_stats()


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
