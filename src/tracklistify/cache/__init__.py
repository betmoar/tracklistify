"""
Cache management for API responses and audio processing.

Public API is re-exported from `cache.factory` (thread-safe singleton)
to keep one canonical implementation per name.
"""

from .base import BaseCache
from .factory import (
    DEFAULT_CACHE_DIR,
    clear_cache,
    create_cache,
    get_cache,
)
from .invalidation import CompositeStrategy, LRUStrategy, SizeStrategy, TTLStrategy
from .storage import JSONStorage

__all__ = [
    "BaseCache",
    "create_cache",
    "get_cache",
    "clear_cache",
    "DEFAULT_CACHE_DIR",
    "TTLStrategy",
    "LRUStrategy",
    "SizeStrategy",
    "CompositeStrategy",
    "JSONStorage",
]
