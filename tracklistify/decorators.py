"""
Decorators for function optimization and caching.
"""

import time
import functools
from typing import Any, Callable, Dict, Optional, TypeVar, cast
from threading import Lock

from .logger import logger
from .cache import get_cache

T = TypeVar('T')

def memoize(ttl: Optional[int] = None) -> Callable:
    """
    Memoize decorator that caches function results.
    
    Args:
        ttl: Time to live in seconds. If None, uses default cache TTL
        
    Returns:
        Decorated function with memoization
        
    Example:
        @memoize(ttl=3600)
        def expensive_operation(arg1, arg2):
            # Expensive computation here
            return result
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        # Use function name and module as cache key prefix
        prefix = f"memo_{func.__module__}_{func.__name__}"
        stats_lock = Lock()
        stats: Dict[str, Any] = {
            "hits": 0,
            "misses": 0,
            "total_time_saved_ms": 0,
            "avg_computation_time_ms": 0,
            "total_calls": 0
        }
        
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            # Create cache key from function arguments
            key = f"{prefix}_{hash(str(args) + str(sorted(kwargs.items())))}"
            cache = get_cache()
            
            # Try to get from cache
            cached_result = cache.get(key)
            if cached_result is not None:
                with stats_lock:
                    stats["hits"] += 1
                    stats["total_calls"] += 1
                    stats["total_time_saved_ms"] += stats["avg_computation_time_ms"]
                return cast(T, cached_result["result"])
            
            # Compute result if not in cache
            with stats_lock:
                stats["misses"] += 1
                stats["total_calls"] += 1
            
            start_time = time.time()
            result = func(*args, **kwargs)
            computation_time = (time.time() - start_time) * 1000  # Convert to ms
            
            # Update average computation time
            with stats_lock:
                stats["avg_computation_time_ms"] = (
                    (stats["avg_computation_time_ms"] * (stats["total_calls"] - 1) + computation_time)
                    / stats["total_calls"]
                )
            
            # Cache the result
            cache_data = {
                "result": result,
                "computation_time_ms": computation_time
            }
            cache.set(key, cache_data)
            
            return result
        
        def get_stats() -> Dict[str, Any]:
            """Get memoization statistics for this function."""
            with stats_lock:
                return {
                    **stats,
                    "hit_rate": stats["hits"] / stats["total_calls"] if stats["total_calls"] > 0 else 0,
                    "function": func.__name__,
                    "module": func.__module__
                }
        
        # Attach stats getter to the wrapper function
        wrapper.get_stats = get_stats  # type: ignore
        return wrapper
    
    return decorator
