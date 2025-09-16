"""
Cache storage backends.
"""

# Standard library imports
import asyncio
import hashlib
import json
import os
import zlib
from pathlib import Path
from typing import Dict, List, Optional, TypeVar, Union

# Third-party imports
import aiofiles

from tracklistify.cache.index import CacheIndex
from tracklistify.config.factory import get_config

# Local/package imports
from tracklistify.core.types import CacheEntry, CacheStorage
from tracklistify.utils.logger import get_logger

logger = get_logger(__name__)

# Magic bytes for compression detection
ZLIB_HEADER = b"\x78\x9c"

T = TypeVar("T")


class JSONStorage(CacheStorage[T]):
    """JSON file-based cache storage."""

    def __init__(self, cache_dir: Union[str, Path]):
        """Initialize storage with cache directory."""
        # Lazy import to avoid circular dependency
        from tracklistify.config import get_config

        self._config = get_config()
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._locks = {}
        self._index = CacheIndex(cache_dir)
        self._index_loaded = False

    def _get_file_path(self, key: str) -> str:
        """Get file path for key."""
        # Use hash to avoid filesystem issues with special characters
        hashed_key = hashlib.sha256(key.encode()).hexdigest()
        return os.path.join(self._cache_dir, f"{hashed_key}.cache")

    def _get_lock(self, key: str) -> asyncio.Lock:
        """Get or create a lock for the given key."""
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    async def _ensure_index_loaded(self) -> None:
        """Ensure the index is loaded."""
        if not self._index_loaded:
            await self._index.load()
            self._index_loaded = True

    async def get(self, key: str) -> Optional[CacheEntry[T]]:
        """Get entry from storage."""
        try:
            await self._ensure_index_loaded()

            # Get filename from index for faster lookup
            filename = await self._index.get_filename(key)
            if filename is None:
                return None

            file_path = os.path.join(self._cache_dir, filename)
            if not os.path.exists(file_path):
                # File missing but in index - remove from index
                await self._index.remove_entry(key)
                return None

            async with self._get_lock(key):
                async with aiofiles.open(file_path, "rb") as f:
                    data = await f.read()

                # Handle compression
                try:
                    if data.startswith(ZLIB_HEADER):
                        data = zlib.decompress(data)
                    entry = json.loads(data.decode("utf-8"))

                    # Update access time in index
                    await self._index.update_access_time(key)

                    return entry
                except (zlib.error, json.JSONDecodeError) as e:
                    logger.error(f"Error decoding cache entry: {str(e)}")
                    # Remove corrupted entry from index
                    await self._index.remove_entry(key)
                    return None

        except Exception as e:
            logger.error(f"Error reading cache entry: {str(e)}")
            return None

    async def set(
        self, key: str, entry: CacheEntry[T], compression: bool = False
    ) -> None:
        """Set entry in storage."""
        temp_path = None
        try:
            await self._ensure_index_loaded()

            file_path = self._get_file_path(key)
            filename = os.path.basename(file_path)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            async with self._get_lock(key):
                # Convert to JSON and optionally compress
                data = json.dumps(entry).encode("utf-8")
                if compression:
                    data = zlib.compress(data)

                # Write atomically using temporary file
                temp_path = file_path + ".tmp"
                async with aiofiles.open(temp_path, "wb") as f:
                    await f.write(data)
                    await f.flush()
                    os.fsync(f.fileno())

                os.replace(temp_path, file_path)
                temp_path = None  # Clear after successful move

                # Update index
                metadata = entry.get("metadata", {})
                metadata["size"] = len(data)
                await self._index.add_entry(key, filename, metadata)

        except Exception as e:
            logger.error(f"Error writing cache entry: {str(e)}")
            # Clean up temp file only if it was created and still exists
            if temp_path is not None and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass  # Ignore cleanup errors
            raise

    async def delete(self, key: str) -> None:
        """Delete entry from storage."""
        try:
            await self._ensure_index_loaded()

            # Get filename from index
            filename = await self._index.remove_entry(key)
            if filename is None:
                return  # Key not in index

            file_path = os.path.join(self._cache_dir, filename)
            async with self._get_lock(key):
                if os.path.exists(file_path):
                    os.unlink(file_path)
        except Exception as e:
            logger.error(f"Error deleting cache entry: {str(e)}")
            raise

    async def clear(self) -> None:
        """Clear all values from storage."""
        try:
            await self._ensure_index_loaded()

            for path in self._cache_dir.rglob("*.cache"):
                path.unlink()

            # Clear the index
            await self._index.clear()

            # Save cleared index
            await self._index.save()

        except OSError as e:
            logger.warning(f"Failed to clear cache: {str(e)}")

    async def cleanup(self, max_age: Optional[int] = None) -> int:
        """Clean up old entries.

        Args:
            max_age: Maximum age in seconds

        Returns:
            Number of entries cleaned up
        """
        if max_age is None:
            config = get_config()
            max_age = config.cache_max_age

        count = 0

        try:
            await self._ensure_index_loaded()

            # Get expired keys from index
            expired_keys = await self._index.cleanup_expired(max_age)

            # Delete expired entries
            for key in expired_keys:
                try:
                    await self.delete(key)
                    count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete expired entry {key}: {e}")

            # Verify integrity and clean up orphaned files
            integrity = await self._index.verify_integrity()
            for orphaned_file in integrity["orphaned_files"]:
                try:
                    orphaned_path = self._cache_dir / orphaned_file
                    orphaned_path.unlink(missing_ok=True)
                    count += 1
                except OSError as e:
                    logger.warning(f"Failed to delete orphaned file: {e}")

            # Save index changes
            await self._index.save()
            return count

        except Exception as e:
            logger.warning(f"Failed to cleanup cache: {str(e)}")
            return 0

    async def read(self, key: str) -> Optional[CacheEntry[T]]:
        """Read entry from storage."""
        return await self.get(key)

    async def write(self, key: str, entry: CacheEntry[T]) -> None:
        """Write entry to storage."""
        compression = entry["metadata"].get("compression", False)
        await self.set(key, entry, compression=compression)

    async def list_keys(self) -> List[str]:
        """List all cache keys efficiently using index."""
        try:
            await self._ensure_index_loaded()
            return await self._index.list_keys()
        except Exception as e:
            logger.error(f"Error listing cache keys: {str(e)}")
            return []

    async def get_storage_stats(self) -> Dict[str, any]:
        """Get storage statistics from index."""
        try:
            await self._ensure_index_loaded()
            return await self._index.get_stats()
        except Exception as e:
            logger.error(f"Error getting storage stats: {str(e)}")
            return {"entries": 0, "total_size_bytes": 0, "index_size_bytes": 0}
