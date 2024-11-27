"""Tests for the cache system."""

# Standard library imports
import asyncio
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

# Third-party imports
import pytest

# Local/package imports
from tracklistify.cache import BaseCache, get_cache
from tracklistify.cache.invalidation import (
    CompositeStrategy,
    LRUStrategy,
    SizeStrategy,
    TTLStrategy,
)
from tracklistify.cache.storage import JSONStorage
from tracklistify.config import get_config
from tracklistify.types import CacheEntry

# Test data
TEST_DATA = {
    "key1": {"value": "test1", "metadata": {"size": 100}},
    "key2": {"value": "test2", "metadata": {"size": 200}},
    "key3": {"value": "test3", "metadata": {"size": 300}},
}


@pytest.fixture
def temp_cache_dir(tmp_path: Path) -> Path:
    """Create a temporary cache directory."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    return cache_dir


@pytest.fixture
def cache(temp_cache_dir: Path) -> BaseCache[Dict[str, Any]]:
    """Create a cache instance with temporary directory."""
    storage = JSONStorage(temp_cache_dir)
    strategy = TTLStrategy()  # Default TTL strategy for basic tests
    return BaseCache[Dict[str, Any]](storage=storage, invalidation_strategy=strategy)


@pytest.mark.asyncio
async def test_basic_cache_operations(cache: BaseCache[Dict[str, Any]]):
    """Test basic cache operations (get/set/delete)."""
    # Test set and get
    key = "test_key"
    value = {"data": "test_value"}
    await cache.set(key, value)

    result = await cache.get(key)
    assert result == value

    # Test delete
    await cache.delete(key)
    result = await cache.get(key)
    assert result is None

    # Test clear
    await cache.set(key, value)
    await cache.clear()
    result = await cache.get(key)
    assert result is None


@pytest.mark.asyncio
async def test_cache_ttl_invalidation(temp_cache_dir: Path):
    """Test TTL-based cache invalidation."""
    storage = JSONStorage(temp_cache_dir)
    strategy = TTLStrategy(default_ttl=1)  # 1 second TTL
    cache = BaseCache[Dict[str, Any]](storage=storage, invalidation_strategy=strategy)

    # Set value
    key = "ttl_test"
    value = {"data": "test"}
    await cache.set(key, value, ttl=1)

    # Verify value exists
    result = await cache.get(key)
    assert result == value

    # Wait for TTL to expire
    time.sleep(1.1)

    # Verify value is invalidated
    result = await cache.get(key)
    assert result is None


@pytest.mark.asyncio
async def test_cache_lru_invalidation(temp_cache_dir: Path):
    """Test LRU-based cache invalidation."""
    storage = JSONStorage(temp_cache_dir)
    strategy = LRUStrategy(max_age=1)
    base_cache = BaseCache[Dict[str, Any]](
        storage=storage, invalidation_strategy=strategy
    )

    # Set multiple values
    for key, data in TEST_DATA.items():
        await base_cache.set(key, data["value"])

    # Wait for max_age
    await asyncio.sleep(1.2)

    # All entries should be invalid due to age
    assert await base_cache.get("key1") is None
    assert await base_cache.get("key2") is None
    assert await base_cache.get("key3") is None

    # Set values again
    for key, data in TEST_DATA.items():
        await base_cache.set(key, data["value"])

    # Access key1 to make it most recently used
    assert await base_cache.get("key1") == TEST_DATA["key1"]["value"]

    # Wait for slightly less than max_age
    await asyncio.sleep(0.5)

    # key1 should still be valid since it was accessed recently and hasn't exceeded max_age
    assert await base_cache.get("key1") == TEST_DATA["key1"]["value"]

    # Wait for more than max_age
    await asyncio.sleep(1.0)

    # Now key1 should be invalid
    assert await base_cache.get("key1") is None


@pytest.mark.asyncio
async def test_cache_size_invalidation(temp_cache_dir: Path):
    """Test size-based cache invalidation."""
    storage = JSONStorage(temp_cache_dir)
    strategy = SizeStrategy(max_size=200)  # Only allow entries up to 200 bytes
    cache = BaseCache[Dict[str, Any]](storage=storage, invalidation_strategy=strategy)

    # Set value that exceeds size limit
    key = "large_value"
    value = {"data": "x" * 1000}  # Large value
    await cache.set(key, value)

    # Value should be immediately invalidated
    result = await cache.get(key)
    assert result is None


@pytest.mark.asyncio
async def test_cache_compression(cache: BaseCache[Dict[str, Any]]):
    """Test cache compression functionality."""
    key = "compressed_key"
    value = {"data": "x" * 1000}  # Large value to benefit from compression

    # Set with compression
    await cache.set(key, value, compression=True)

    # Get compressed value
    result = await cache.get(key)
    assert result == value


@pytest.mark.asyncio
async def test_cache_error_handling(cache: BaseCache[Dict[str, Any]]):
    """Test cache error handling."""
    # Test invalid key type
    with pytest.raises(TypeError):
        await cache.get(123)  # type: ignore

    # Test invalid value type
    with pytest.raises(TypeError):
        await cache.set("key", lambda: None)  # type: ignore


@pytest.mark.asyncio
async def test_cache_statistics(cache: BaseCache[Dict[str, Any]]):
    """Test cache statistics tracking."""
    # Initial stats
    stats = cache.get_stats()
    assert stats["hits"] == 0
    assert stats["misses"] == 0

    # Add some cache operations
    key = "stats_test"
    value = {"data": "test"}

    # Miss (get non-existent key)
    await cache.get(key)
    stats = cache.get_stats()
    assert stats["misses"] == 1

    # Hit (set and get key)
    await cache.set(key, value)
    await cache.get(key)
    stats = cache.get_stats()
    assert stats["hits"] == 1


@pytest.mark.asyncio
async def test_cache_concurrent_access(cache: BaseCache[Dict[str, Any]]):
    """Test concurrent cache access."""
    key = "concurrent_test"
    value = {"data": "test"}

    async def cache_operation():
        await cache.set(key, value)
        result = await cache.get(key)
        assert result == value

    # Run multiple cache operations concurrently
    tasks = [cache_operation() for _ in range(5)]
    await asyncio.gather(*tasks)


@pytest.mark.asyncio
async def test_global_cache_instance():
    """Test global cache instance."""
    cache1 = get_cache()
    cache2 = get_cache()
    assert cache1 is cache2  # Same instance


def test_cache_configuration():
    """Test cache configuration validation."""
    config = get_config()

    # Test required config values
    assert config.cache_enabled is not None
    assert config.cache_ttl > 0
    assert config.cache_max_size > 0
    assert config.cache_storage_format in ["json"]
    assert isinstance(config.cache_compression_enabled, bool)
    assert 0 <= config.cache_compression_level <= 9


@pytest.mark.asyncio
async def test_cache_cleanup(cache: BaseCache[Dict[str, Any]]):
    """Test cache cleanup functionality."""
    # Add some entries
    for key, data in TEST_DATA.items():
        await cache.set(key, data["value"])

    # Perform cleanup
    cleaned = await cache.cleanup(max_age=0)  # Cleanup all entries
    assert cleaned > 0

    # Verify all entries are cleaned
    for key in TEST_DATA:
        assert await cache.get(key) is None


@pytest.mark.asyncio
async def test_composite_strategy(tmp_path):
    """Test composite invalidation strategy."""
    storage = JSONStorage(tmp_path)
    ttl = TTLStrategy(timedelta(seconds=1))
    size = SizeStrategy(max_size=1000)
    composite = CompositeStrategy([ttl, size])

    entry = CacheEntry(
        key="test",
        value="test_value",
        metadata={"created_at": datetime.now().isoformat(), "size": 100},
    )

    # Test should_invalidate
    assert not composite.should_invalidate(entry)

    # Test last access update
    composite.update_last_access(entry)
    assert "last_accessed" in entry["metadata"]

    # Test cleanup
    await storage.write("test", entry)
    await composite.cleanup(storage)
    result = await storage.read("test")
    assert result is not None


@pytest.mark.asyncio
async def test_compression_handling(tmp_path):
    """Test compression handling in storage."""
    storage = JSONStorage(tmp_path)

    # Test with compression
    entry = CacheEntry(
        key="compressed",
        value="test_value" * 1000,  # Large value to benefit from compression
        metadata={"compression": True, "created_at": datetime.now().isoformat()},
    )

    await storage.write("compressed", entry)
    result = await storage.read("compressed")
    assert result is not None
    assert result["value"] == entry["value"]

    # Test without compression
    entry = CacheEntry(
        key="uncompressed",
        value="test_value",
        metadata={"compression": False, "created_at": datetime.now().isoformat()},
    )

    await storage.write("uncompressed", entry)
    result = await storage.read("uncompressed")
    assert result is not None
    assert result["value"] == entry["value"]
