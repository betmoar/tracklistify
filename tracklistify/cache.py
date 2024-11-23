"""
Cache management for API responses and audio processing.

This module is maintained for backward compatibility.
All functionality has been moved to the cache package.
"""

from .cache import Cache, get_cache

# Re-export for backward compatibility
__all__ = ['Cache', 'get_cache']
