"""
Cache storage backends.
"""

# Standard library imports
import asyncio
import base64
import copy
import hashlib
import json
import os
import time
import zlib
from pathlib import Path
from typing import Any, Dict, Generic, Optional, TypeVar, Union

# Third-party imports
import aiofiles

# Local/package imports
from tracklistify.core.types import CacheEntry, CacheStorage
from tracklistify.utils.logger import logger

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

    async def get(self, key: str) -> Optional[CacheEntry[T]]:
        """Get entry from storage."""
        try:
            file_path = self._get_file_path(key)
            if not os.path.exists(file_path):
                return None

            async with self._get_lock(key):
                async with aiofiles.open(file_path, "rb") as f:
                    data = await f.read()

                # Handle compression
                try:
                    if data.startswith(b"\x78\x9c"):  # zlib header
                        data = zlib.decompress(data)
                    entry = json.loads(data.decode("utf-8"))
                    return entry
                except (zlib.error, json.JSONDecodeError) as e:
                    logger.error(f"Error decoding cache entry: {str(e)}")
                    return None

        except Exception as e:
            logger.error(f"Error reading cache entry: {str(e)}")
            return None

    async def set(
        self, key: str, entry: CacheEntry[T], compression: bool = False
    ) -> None:
        """Set entry in storage."""
        try:
            file_path = self._get_file_path(key)
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

        except Exception as e:
            logger.error(f"Error writing cache entry: {str(e)}")
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    async def delete(self, key: str) -> None:
        """Delete entry from storage."""
        try:
            file_path = self._get_file_path(key)
            async with self._get_lock(key):
                if os.path.exists(file_path):
                    os.unlink(file_path)
        except Exception as e:
            logger.error(f"Error deleting cache entry: {str(e)}")
            raise

    async def clear(self) -> None:
        """Clear all values from storage."""
        try:
            for path in self._cache_dir.rglob("*.cache"):
                path.unlink()
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
        now = time.time()

        try:
            for path in self._cache_dir.rglob("*.cache"):
                try:
                    # Read entry to check metadata
                    entry = json.loads(path.read_bytes().decode("utf-8"))
                    last_accessed = entry.get("last_accessed")

                    if last_accessed is None:
                        # Delete entries without last_accessed timestamp
                        path.unlink()
                        count += 1
                        continue

                    # Convert string timestamp to float if needed
                    if isinstance(last_accessed, str):
                        from dateutil import parser

                        last_accessed = float(parser.parse(last_accessed).timestamp())

                    # Check if entry is expired
                    if now - float(last_accessed) > float(max_age):
                        path.unlink()
                        count += 1
                except (OSError, json.JSONDecodeError, ValueError, TypeError) as e:
                    # Delete invalid entries
                    try:
                        path.unlink()
                        count += 1
                    except OSError:
                        continue

            return count

        except OSError as e:
            logger.warning(f"Failed to cleanup cache: {str(e)}")
            return 0

    async def read(self, key: str) -> Optional[CacheEntry[T]]:
        """Read entry from storage."""
        return await self.get(key)

    async def write(self, key: str, entry: CacheEntry[T]) -> None:
        """Write entry to storage."""
        compression = entry["metadata"].get("compression", False)
        await self.set(key, entry, compression=compression)
