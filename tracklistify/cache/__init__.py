"""
Cache management for API responses and audio processing.
"""

from typing import Optional, TypeVar, Dict, Any
from pathlib import Path
import time
import asyncio

from .base import BaseCache
from .invalidation import TTLStrategy, LRUStrategy, SizeStrategy, CompositeStrategy
from .storage import JSONStorage
from ..config import get_config
from ..logger import logger

T = TypeVar('T')

# Global cache instance
_cache_instance = None

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
        self._storage = JSONStorage(self.cache_dir)
        self._strategy = CompositeStrategy([
            TTLStrategy(self._config.cache_ttl),
            LRUStrategy(self._config.cache_ttl),
            SizeStrategy(self._config.cache_max_size)
        ])
        self._cache = BaseCache[Dict[str, Any]](
            storage=self._storage,
            invalidation_strategy=self._strategy,
            config=self._config
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
            run_async(self._cache.set(
                key=key,
                value=value,
                ttl=self._config.cache_ttl,
                compression=self._config.cache_compression_enabled
            ))
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

def get_cache() -> Cache:
    """Get the global cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = Cache()
    return _cache_instance

__all__ = [
    'BaseCache',
    'TTLStrategy',
    'LRUStrategy',
    'SizeStrategy',
    'CompositeStrategy',
    'JSONStorage',
    'Cache',
    'get_cache'
]
