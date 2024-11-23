"""
Base cache implementation with enhanced features.
"""

import time
from pathlib import Path
from typing import Any, Dict, Generic, Optional, TypeVar
import json
from datetime import datetime

from ..config import get_config
from ..logger import logger
from ..types import Cache, CacheEntry, CacheMetadata, CacheStorage, InvalidationStrategy

T = TypeVar('T')

class BaseCache(Generic[T]):
    """Base cache implementation with enhanced features."""
    
    def __init__(
        self,
        storage: CacheStorage[T],
        invalidation_strategy: InvalidationStrategy,
        config = None
    ):
        """Initialize cache with storage and invalidation strategy.
        
        Args:
            storage: Storage backend
            invalidation_strategy: Strategy for invalidating entries
            config: Optional configuration override
        """
        self._storage = storage
        self._invalidation_strategy = invalidation_strategy
        self._config = config or get_config()
        self._stats: Dict[str, Any] = {
            "hits": 0,
            "misses": 0,
            "invalidations": 0,
            "total_size_bytes": 0,
            "entries": 0
        }
    
    async def get(self, key: str) -> Optional[T]:
        """Get value from cache."""
        try:
            if not isinstance(key, str):
                raise TypeError("Cache key must be a string")
                
            # Get entry from storage
            entry = await self._storage.get(key)
            if entry is None:
                logger.debug(f"Cache miss: {key}")
                self._stats["misses"] += 1
                return None
                
            # Check if entry is valid
            is_valid = await self._invalidation_strategy.is_valid(entry)
            if not is_valid:
                logger.debug(f"Cache entry invalid: {key}")
                await self.delete(key)
                self._stats["invalidations"] += 1
                self._stats["misses"] += 1
                return None
                
            # Update metadata and stats for valid entries only
            try:
                updated_entry = await self._invalidation_strategy.update_metadata(entry)
                if updated_entry != entry:
                    await self._storage.set(key, updated_entry, compression=updated_entry["metadata"].get("compressed", False))
                    entry = updated_entry  # Use the updated entry for returning the value
                self._stats["hits"] += 1
                return entry["value"]
            except Exception as e:
                logger.error(f"Error updating metadata: {str(e)}")
                self._stats["hits"] += 1
                return entry["value"]
            
        except TypeError as e:
            logger.error(f"Type error getting cache entry: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error getting cache entry: {str(e)}")
            return None

    async def set(self, key: str, value: T, ttl: Optional[int] = None, compression: bool = False) -> None:
        """Set value in cache."""
        try:
            if not isinstance(key, str):
                raise TypeError("Cache key must be a string")
                
            if not isinstance(value, (dict, list, str, int, float, bool)) and value is not None:
                raise TypeError("Cache value must be JSON serializable")
                
            # Create entry with metadata
            entry: CacheEntry[T] = {
                "key": key,
                "value": value,
                "metadata": {
                    "created": time.time(),
                    "last_accessed": time.time(),
                    "ttl": ttl,
                    "compressed": compression,
                    "size": len(json.dumps(value))
                }
            }
            
            # Write to storage
            await self._storage.set(key, entry, compression=compression)
            self._stats["entries"] += 1
            
        except TypeError as e:
            logger.error(f"Type error setting cache entry: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error setting cache entry: {str(e)}")

    async def delete(self, key: str) -> None:
        """Delete value from cache."""
        try:
            if not isinstance(key, str):
                raise TypeError("Cache key must be a string")
                
            await self._storage.delete(key)
            self._stats["entries"] = max(0, self._stats["entries"] - 1)
            self._stats["invalidations"] += 1
            
        except TypeError as e:
            logger.error(f"Type error deleting cache entry: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error deleting cache entry: {str(e)}")
    
    async def clear(self) -> None:
        """Clear all values from cache."""
        if not self._config.cache_enabled:
            return
            
        try:
            await self._storage.clear()
            self._reset_stats()
        except Exception as e:
            logger.warning(f"Cache clear error: {str(e)}")
    
    async def cleanup(self, max_age: Optional[int] = None) -> int:
        """Clean up old entries.
        
        Args:
            max_age: Maximum age in seconds
            
        Returns:
            Number of entries cleaned up
        """
        try:
            return await self._storage.cleanup(max_age)
        except Exception as e:
            logger.warning(f"Cache cleanup error: {str(e)}")
            return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        hit_rate = self._stats["hits"] / (self._stats["hits"] + self._stats["misses"]) if (self._stats["hits"] + self._stats["misses"]) > 0 else 0
        return {
            **self._stats,
            "hit_rate": hit_rate,
            "enabled": self._config.cache_enabled,
            "compression_enabled": self._config.cache_compression_enabled,
            "storage_format": self._config.cache_storage_format
        }
    
    def _reset_stats(self) -> None:
        """Reset cache statistics."""
        self._stats = {
            "hits": 0,
            "misses": 0,
            "invalidations": 0,
            "total_size_bytes": 0,
            "entries": 0
        }
