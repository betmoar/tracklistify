# tracklistify/cache/factory.py

# Standard library imports
import threading
from pathlib import Path
from typing import Optional, Union

# Local imports
from .base import BaseCache
from .invalidation import CompositeStrategy, LRUStrategy, SizeStrategy, TTLStrategy
from .storage import JSONStorage
from tracklistify.utils.constants import DEFAULT_CACHE_MAX_SIZE, DEFAULT_CACHE_TTL
from tracklistify.utils.logger import get_logger

logger = get_logger(__name__)

DEFAULT_CACHE_DIR = Path.home() / ".tracklistify" / "cache"

# Global cache instance with thread-safe access
_cache_instance = None
_cache_lock = threading.Lock()


def create_cache(
    cache_dir: Optional[Union[Path, str]] = None,
    ttl: int = DEFAULT_CACHE_TTL,
    max_size: int = DEFAULT_CACHE_MAX_SIZE,
) -> BaseCache:
    """Create a new cache instance.

    Resolves ``cache_dir`` (string or Path), expands ``~``, ensures the
    directory exists, and wires the standard CompositeStrategy
    (TTL + LRU + Size) onto a JSON-backed storage.
    """
    cache_path = cache_dir or DEFAULT_CACHE_DIR
    if isinstance(cache_path, str):
        cache_path = Path(cache_path)
    cache_path = cache_path.expanduser()
    cache_path.mkdir(parents=True, exist_ok=True)

    storage = JSONStorage(str(cache_path))
    strategy = CompositeStrategy(
        [TTLStrategy(ttl), LRUStrategy(ttl), SizeStrategy(max_size)]
    )
    logger.debug(f"Initializing cache in: {cache_path}")

    return BaseCache(
        storage=storage, invalidation_strategy=strategy, ttl=ttl, max_size=max_size
    )


def get_cache(force_refresh: bool = False) -> BaseCache:
    """Get global cache instance.

    This function is thread-safe using double-checked locking pattern.
    Multiple threads can safely call this function concurrently.

    Args:
        force_refresh: If True, discard the existing instance and create
            a fresh one. Use this from tests after ``get_config(force_refresh=True)``
            so the cache picks up the new config.

    Returns:
        BaseCache: The global cache instance.
    """
    global _cache_instance

    # Fast path: instance already exists and no refresh requested
    if not force_refresh and _cache_instance is not None:
        return _cache_instance

    # Slow path: need to (re)create instance (thread-safe)
    with _cache_lock:
        if force_refresh or _cache_instance is None:
            _cache_instance = create_cache()

    return _cache_instance


def clear_cache() -> None:
    """Clear global cache instance.

    This function is thread-safe.
    """
    global _cache_instance
    with _cache_lock:
        _cache_instance = None
