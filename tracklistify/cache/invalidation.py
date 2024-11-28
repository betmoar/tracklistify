"""
Cache invalidation strategies.
"""

# Standard library imports
import copy
import json
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Generic, List, Optional, TypeVar

# Local/package imports
from tracklistify.core.types import CacheEntry, CacheStorage
from tracklistify.utils.logger import logger

T = TypeVar("T")


class InvalidationStrategy(Generic[T], ABC):
    """Base class for cache invalidation strategies."""

    @abstractmethod
    async def is_valid(self, entry: CacheEntry[T]) -> bool:
        """Check if entry is still valid."""
        pass

    @abstractmethod
    async def update_metadata(self, entry: CacheEntry[T]) -> CacheEntry[T]:
        """Update entry metadata."""
        pass

    def _update_access_stats(self, entry: CacheEntry[T]) -> None:
        """Update last access time for the entry."""
        entry["metadata"]["last_accessed"] = datetime.now().isoformat()
        entry["metadata"]["access_count"] = entry["metadata"].get("access_count", 0) + 1

    @abstractmethod
    async def cleanup(self, storage: CacheStorage[T]) -> None:
        """Clean up expired entries."""
        pass

    @abstractmethod
    def should_invalidate(self, entry: CacheEntry[Any]) -> bool:
        """Check if entry should be invalidated."""
        pass


class TTLStrategy(InvalidationStrategy[T]):
    """Time-based invalidation strategy."""

    def __init__(self, default_ttl: Optional[int] = None):
        self.default_ttl = default_ttl

    async def is_valid(self, entry: CacheEntry[T]) -> bool:
        """Check if entry is still valid based on TTL."""
        try:
            metadata = entry["metadata"]
            created_time = metadata.get("created", 0)
            ttl = metadata.get("ttl", self.default_ttl)

            if ttl is None:
                return True

            return time.time() - created_time < ttl

        except Exception as e:
            logger.error(f"Error checking TTL validity: {str(e)}")
            return False

    async def update_metadata(self, entry: CacheEntry[T]) -> CacheEntry[T]:
        """Update entry metadata."""
        try:
            entry = copy.deepcopy(entry)
            entry["metadata"]["last_accessed"] = time.time()
            return entry
        except Exception as e:
            logger.error(f"Error updating TTL metadata: {str(e)}")
            return entry

    async def cleanup(self, storage: CacheStorage[T]) -> None:
        """Clean up expired entries."""
        await storage.cleanup()

    def should_invalidate(self, entry: CacheEntry[Any]) -> bool:
        """Check if entry should be invalidated based on TTL."""
        try:
            metadata = entry["metadata"]
            created_at = metadata.get("created_at")
            if not created_at:
                return True

            if isinstance(created_at, str):
                created_time = datetime.fromisoformat(created_at)
            else:
                created_time = datetime.fromtimestamp(created_at)

            current_time = datetime.now()
            age = current_time - created_time

            logger.debug(
                f"TTL check: current={current_time}, created={created_time}, age={age}, ttl={self.default_ttl}"
            )

            return age > self.default_ttl

        except Exception as e:
            logger.error(f"Error in TTL invalidation check: {str(e)}")
            return True

    def _update_access_stats(self, entry: CacheEntry[T]) -> None:
        """Update last access time for the entry."""
        entry["metadata"]["last_accessed"] = datetime.now().isoformat()
        entry["metadata"]["access_count"] = entry["metadata"].get("access_count", 0) + 1

    def update_last_access(self, entry: CacheEntry[T]) -> None:
        """Update last access time."""
        current_time = datetime.now()
        entry["metadata"]["last_accessed"] = current_time.isoformat()
        logger.debug(f"TTL update: last_accessed={current_time}")


class LRUStrategy(InvalidationStrategy[T]):
    """Least Recently Used invalidation strategy."""

    def __init__(self, max_age: Optional[int] = None):
        self.max_age = max_age

    async def is_valid(self, entry: CacheEntry[T]) -> bool:
        """Check if entry is valid based on last access time."""
        try:
            if self.max_age is None:
                return True

            if "metadata" not in entry:
                return False

            metadata = entry["metadata"]
            if "last_accessed" not in metadata:
                # If no last_accessed time, fall back to created time
                if "created" not in metadata:
                    return False
                last_accessed = metadata["created"]
            else:
                last_accessed = metadata["last_accessed"]

            current_time = time.time()
            age = current_time - last_accessed

            logger.debug(
                f"LRU check: current={current_time}, last={last_accessed}, age={age}, max_age={self.max_age}"
            )

            # Add a small buffer to account for timing variations
            return age < (self.max_age - 0.001)

        except Exception as e:
            logger.error(f"Error checking LRU validity: {str(e)}")
            return False

    async def update_metadata(self, entry: CacheEntry[T]) -> CacheEntry[T]:
        """Update entry metadata with current access time."""
        try:
            # Only update metadata if entry is valid
            if not await self.is_valid(entry):
                return entry

            current_time = time.time()

            # Initialize metadata if not present
            if "metadata" not in entry:
                entry["metadata"] = {}

            # Set initial created time if not present
            if "created" not in entry["metadata"]:
                entry["metadata"]["created"] = current_time

            # Create a new entry to avoid modifying the original
            updated_entry = entry.copy()
            updated_entry["metadata"] = entry["metadata"].copy()

            # Update last accessed time
            updated_entry["metadata"]["last_accessed"] = current_time
            logger.debug(f"LRU update: last_accessed={current_time}")

            return updated_entry
        except Exception as e:
            logger.error(f"Error updating LRU metadata: {str(e)}")
            return entry

    async def cleanup(self, storage: CacheStorage[T]) -> None:
        """Clean up expired entries."""
        try:
            # Implement cleanup if needed
            pass
        except Exception as e:
            logger.error(f"Error in LRU cleanup: {str(e)}")

    def should_invalidate(self, entry: CacheEntry[T]) -> bool:
        """Check if entry should be invalidated based on age."""
        try:
            if self.max_age is None:
                return False

            metadata = entry["metadata"]
            last_accessed = metadata.get("last_accessed")

            # If no last_accessed, use created time
            if last_accessed is None:
                return True

            # Convert ISO format to timestamp if needed
            if isinstance(last_accessed, str):
                try:
                    last_accessed = datetime.fromisoformat(last_accessed).timestamp()
                except ValueError:
                    return True

            current_time = time.time()
            age = current_time - float(last_accessed)

            logger.debug(
                f"LRU check: current={current_time}, last={last_accessed}, age={age}, max_age={self.max_age}"
            )

            # Entry is valid if age is less than max_age
            return age >= self.max_age

        except Exception as e:
            logger.error(f"Error checking LRU validity: {str(e)}")
            return True

    def update_last_access(self, entry: CacheEntry[T]) -> None:
        """Update last access time."""
        current_time = time.time()
        entry["metadata"]["last_accessed"] = current_time
        logger.debug(f"LRU update: last_accessed={current_time}")


class SizeStrategy(InvalidationStrategy[T]):
    """Size-based invalidation strategy."""

    def __init__(self, max_size: Optional[int] = None):
        self.max_size = max_size

    async def is_valid(self, entry: CacheEntry[T]) -> bool:
        """Check if entry is still valid based on size."""
        try:
            if self.max_size is None:
                return True

            metadata = entry["metadata"]
            size = metadata.get("size", 0)

            return size <= self.max_size

        except Exception as e:
            logger.error(f"Error checking size validity: {str(e)}")
            return False

    async def update_metadata(self, entry: CacheEntry[T]) -> CacheEntry[T]:
        """Update entry metadata."""
        try:
            entry = copy.deepcopy(entry)
            entry["metadata"]["size"] = len(json.dumps(entry["value"]))
            return entry
        except Exception as e:
            logger.error(f"Error updating size metadata: {str(e)}")
            return entry

    async def cleanup(self, storage: CacheStorage[T]) -> None:
        """Clean up large entries."""
        await storage.cleanup()

    def should_invalidate(self, entry: CacheEntry[Any]) -> bool:
        """Check if entry should be invalidated based on size."""
        size = entry["metadata"].get("size", len(json.dumps(entry["value"])))
        return size > self.max_size

    def _update_access_stats(self, entry: CacheEntry[T]) -> None:
        """Update last access time for the entry."""
        entry["metadata"]["last_accessed"] = datetime.now().isoformat()
        entry["metadata"]["access_count"] = entry["metadata"].get("access_count", 0) + 1


class CompositeStrategy(InvalidationStrategy[T]):
    """Composite invalidation strategy that combines multiple strategies."""

    def __init__(self, strategies: List[InvalidationStrategy[T]]):
        self.strategies = strategies

    async def is_valid(self, entry: CacheEntry[T]) -> bool:
        """Check if entry is valid according to all strategies."""
        try:
            for strategy in self.strategies:
                if not await strategy.is_valid(entry):
                    logger.debug(
                        f"Entry invalid according to strategy: {strategy.__class__.__name__}"
                    )
                    return False
            return True
        except Exception as e:
            logger.error(f"Error in composite validity check: {str(e)}")
            return False

    async def update_metadata(self, entry: CacheEntry[T]) -> CacheEntry[T]:
        """Update metadata using all strategies."""
        try:
            updated_entry = copy.deepcopy(entry)
            for strategy in self.strategies:
                updated_entry = await strategy.update_metadata(updated_entry)
            return updated_entry
        except Exception as e:
            logger.error(f"Error updating composite metadata: {str(e)}")
            return entry

    async def cleanup(self, storage: CacheStorage[T]) -> None:
        """Clean up expired entries based on all strategies."""
        try:
            # Get all keys
            keys = await storage.list_keys()

            # Check each key
            for key in keys:
                entry = await storage.read(key)
                if entry is not None and self.should_invalidate(entry):
                    logger.debug(f"Cleaning up key {key} due to composite invalidation")
                    await storage.delete(key)

            # Run cleanup for each strategy
            for strategy in self.strategies:
                await strategy.cleanup(storage)
        except Exception as e:
            logger.error(f"Error in composite cleanup: {str(e)}")

    def should_invalidate(self, entry: CacheEntry[T]) -> bool:
        """Check if any strategy indicates the entry should be invalidated."""
        try:
            for strategy in self.strategies:
                if strategy.should_invalidate(entry):
                    logger.debug(
                        f"Strategy {strategy.__class__.__name__} indicates entry should be invalidated"
                    )
                    return True
            return False
        except Exception as e:
            logger.error(f"Error in composite invalidation check: {str(e)}")
            return True

    def update_last_access(self, entry: CacheEntry[T]) -> None:
        """Update last access time in all strategies."""
        for strategy in self.strategies:
            if hasattr(strategy, "update_last_access"):
                strategy.update_last_access(entry)
