"""
Decorators for function optimization and caching.
"""

# Standard library imports
import functools
import hashlib
import time
from threading import Lock
from typing import Any, Callable, Dict, Optional, TypeVar, cast

# Local/package imports
from tracklistify.utils.constants import MILLISECONDS_PER_SECOND, STABLE_HASH_LENGTH

T = TypeVar("T")


def _stable_hash(data: str) -> str:
    """Create a stable hash from string data.

    Uses SHA-256 for deterministic hashing across Python runs.
    Unlike built-in hash(), this is stable and has very low collision risk.

    Args:
        data: String to hash

    Returns:
        Hexadecimal hash string (first 16 chars for reasonable key length)
    """
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:STABLE_HASH_LENGTH]


def memoize(ttl: Optional[int] = None) -> Callable:
    """
    Memoize decorator that caches function results.

    Uses stable SHA-256 hashing for cache keys to ensure consistency
    across Python runs and prevent hash collisions.

    Note: Uses in-memory cache since BaseCache is async.

    Args:
        ttl: Time to live in seconds (currently unused, reserved for future)

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
            "total_calls": 0,
        }
        # In-memory cache for sync access (BaseCache is async)
        _local_cache: Dict[str, Any] = {}

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            # Create cache key from function arguments using stable hash
            args_str = str(args) + str(sorted(kwargs.items()))
            key = f"{prefix}_{_stable_hash(args_str)}"

            # Use local in-memory cache (sync-compatible)
            if key in _local_cache:
                with stats_lock:
                    stats["hits"] += 1
                    stats["total_calls"] += 1
                    stats["total_time_saved_ms"] += stats["avg_computation_time_ms"]
                return cast(T, _local_cache[key]["result"])

            # Compute result if not in cache
            with stats_lock:
                stats["misses"] += 1
                stats["total_calls"] += 1

            start_time = time.monotonic()
            result = func(*args, **kwargs)
            computation_time = (time.monotonic() - start_time) * MILLISECONDS_PER_SECOND

            # Update average computation time (misses only — hits don't compute)
            with stats_lock:
                misses = stats["misses"]
                stats["avg_computation_time_ms"] = (
                    stats["avg_computation_time_ms"] * (misses - 1) + computation_time
                ) / misses

            # Cache the result in local memory
            cache_data = {"result": result, "computation_time_ms": computation_time}
            _local_cache[key] = cache_data

            return result

        def get_stats() -> Dict[str, Any]:
            """Get memoization statistics for this function."""
            with stats_lock:
                return {
                    **stats,
                    "hit_rate": (
                        stats["hits"] / stats["total_calls"]
                        if stats["total_calls"] > 0
                        else 0
                    ),
                    "function": func.__name__,
                    "module": func.__module__,
                }

        def clear_cache() -> None:
            """Clear the memoization cache for this function."""
            _local_cache.clear()
            with stats_lock:
                stats["hits"] = 0
                stats["misses"] = 0
                stats["total_calls"] = 0
                stats["total_time_saved_ms"] = 0
                stats["avg_computation_time_ms"] = 0

        # Attach stats getter and clear function to the wrapper
        wrapper.get_stats = get_stats  # type: ignore
        wrapper.clear_cache = clear_cache  # type: ignore
        return wrapper

    return decorator
