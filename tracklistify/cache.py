"""
Cache management for API responses and audio processing.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .config import get_config
from .logger import logger

class Cache:
    """Simple file-based cache for API responses."""
    
    def __init__(self, cache_dir: str = ".cache"):
        """Initialize cache with directory."""
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._config = get_config()
        
    def _get_cache_path(self, key: str) -> Path:
        """Get cache file path for key."""
        # Use first 2 chars of key as subdirectory to avoid too many files in one dir
        subdir = key[:2] if len(key) > 2 else "default"
        cache_subdir = self.cache_dir / subdir
        cache_subdir.mkdir(exist_ok=True)
        return cache_subdir / f"{key}.json"
        
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get value from cache.
        
        Args:
            key: Cache key (usually a hash of the audio segment)
            
        Returns:
            Dict containing cached data if valid, None otherwise
        """
        cache_path = self._get_cache_path(key)
        if not cache_path.exists():
            return None
            
        try:
            with open(cache_path, 'r') as f:
                data = json.load(f)
                
            # Check if cache is expired using ttl
            if time.time() - data['timestamp'] > self._config.cache.ttl:
                logger.debug(f"Cache expired for key {key}")
                self.delete(key)
                return None
                
            logger.debug(f"Cache hit for key: {key}")
            return data['value']
            
        except (json.JSONDecodeError, KeyError, OSError) as e:
            logger.warning(f"Failed to read cache for key {key}: {str(e)}")
            return None
            
    def set(self, key: str, value: Dict[str, Any]) -> None:
        """
        Set value in cache.
        
        Args:
            key: Cache key
            value: Data to cache
        """
        cache_path = self._get_cache_path(key)
        try:
            cache_data = {
                'timestamp': time.time(),
                'value': value
            }
            with open(cache_path, 'w') as f:
                json.dump(cache_data, f)
            logger.debug(f"Cached response for key: {key}")
            
        except OSError as e:
            logger.warning(f"Failed to write cache for key {key}: {str(e)}")
            
    def clear(self, max_age: Optional[int] = None) -> None:
        """
        Clear expired cache entries.
        
        Args:
            max_age: Maximum age in seconds, defaults to cache ttl from config
        """
        if max_age is None:
            max_age = self._config.cache.ttl
            
        now = time.time()
        count = 0
        
        for cache_file in self.cache_dir.rglob("*.json"):
            try:
                if cache_file.stat().st_mtime + max_age < now:
                    cache_file.unlink()
                    count += 1
            except OSError:
                continue
                
        logger.info(f"Cleared {count} expired cache entries")

    def delete(self, key: str) -> None:
        """
        Delete cache entry.
        
        Args:
            key: Cache key
        """
        cache_path = self._get_cache_path(key)
        try:
            cache_path.unlink()
        except OSError:
            pass

# Global cache instance
_cache_instance = None

def get_cache() -> Cache:
    """Get the global cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = Cache()
    return _cache_instance
