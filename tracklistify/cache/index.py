"""
Cache index management for efficient key-to-filename mapping.
"""

# Standard library imports
import asyncio
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, TypeVar, Union

# Third-party imports
import aiofiles

# Local/package imports
from tracklistify.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class CacheIndex:
    """Manages cache index for efficient key-to-filename mapping."""

    def __init__(self, cache_dir: Union[str, Path]):
        """Initialize cache index.

        Args:
            cache_dir: Directory where cache files are stored
        """
        self._cache_dir = Path(cache_dir)
        self._index_file = self._cache_dir / "cache.index.json"
        self._index: Dict[str, Dict[str, any]] = {}
        self._lock = asyncio.Lock()
        self._dirty = False

    async def load(self) -> None:
        """Load index from disk or rebuild if missing/corrupted."""
        async with self._lock:
            try:
                if self._index_file.exists():
                    async with aiofiles.open(self._index_file, "r") as f:
                        content = await f.read()
                        self._index = json.loads(content)
                    logger.debug(f"Loaded cache index with {len(self._index)} entries")
                else:
                    logger.info("Index file not found, rebuilding from cache files")
                    await self._rebuild_index()
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Index file corrupted: {e}, rebuilding")
                await self._rebuild_index()

    async def save(self) -> None:
        """Save index to disk atomically."""
        if not self._dirty:
            return

        async with self._lock:
            temp_file = None
            try:
                # Write to temporary file first
                temp_file = self._index_file.with_suffix(".tmp")
                async with aiofiles.open(temp_file, "w") as f:
                    await f.write(json.dumps(self._index, indent=2))
                    await f.flush()

                # Atomic replace
                temp_file.replace(self._index_file)
                self._dirty = False
                logger.debug(f"Saved cache index with {len(self._index)} entries")

            except OSError as e:
                logger.error(f"Failed to save cache index: {e}")
                # Clean up temp file if it exists
                if temp_file and temp_file.exists():
                    temp_file.unlink(missing_ok=True)
                raise

    async def add_entry(
        self, key: str, filename: str, metadata: Dict[str, any]
    ) -> None:
        """Add or update entry in index.

        Args:
            key: Cache key
            filename: Hashed filename
            metadata: Entry metadata including size, created time, etc.
        """
        async with self._lock:
            self._index[key] = {
                "filename": filename,
                "created": metadata.get("created", time.time()),
                "last_accessed": metadata.get("last_accessed", time.time()),
                "size": metadata.get("size", 0),
                "ttl": metadata.get("ttl"),
                "compression": metadata.get("compression", False),
            }
            self._dirty = True

    async def remove_entry(self, key: str) -> Optional[str]:
        """Remove entry from index.

        Args:
            key: Cache key to remove

        Returns:
            Filename of removed entry, or None if key not found
        """
        async with self._lock:
            if key in self._index:
                entry = self._index.pop(key)
                self._dirty = True
                return entry["filename"]
            return None

    async def get_filename(self, key: str) -> Optional[str]:
        """Get filename for cache key.

        Args:
            key: Cache key

        Returns:
            Hashed filename or None if key not found
        """
        return self._index.get(key, {}).get("filename")

    async def get_metadata(self, key: str) -> Optional[Dict[str, any]]:
        """Get metadata for cache key.

        Args:
            key: Cache key

        Returns:
            Metadata dict or None if key not found
        """
        entry = self._index.get(key)
        if entry:
            # Return copy without filename
            metadata = entry.copy()
            metadata.pop("filename", None)
            return metadata
        return None

    async def update_access_time(self, key: str) -> None:
        """Update last access time for key.

        Args:
            key: Cache key to update
        """
        async with self._lock:
            if key in self._index:
                self._index[key]["last_accessed"] = time.time()
                self._dirty = True

    async def list_keys(self) -> List[str]:
        """Get list of all cache keys.

        Returns:
            List of cache keys
        """
        return list(self._index.keys())

    async def get_stats(self) -> Dict[str, any]:
        """Get cache statistics from index.

        Returns:
            Statistics dictionary
        """
        total_size = sum(entry.get("size", 0) for entry in self._index.values())
        total_entries = len(self._index)

        return {
            "entries": total_entries,
            "total_size_bytes": total_size,
            "index_size_bytes": len(json.dumps(self._index)),
        }

    async def cleanup_expired(self, max_age: int) -> List[str]:
        """Get list of expired cache keys.

        Args:
            max_age: Maximum age in seconds

        Returns:
            List of expired cache keys
        """
        now = time.time()
        expired_keys = []

        for key, entry in self._index.items():
            last_accessed = entry.get("last_accessed", 0)
            if now - last_accessed > max_age:
                expired_keys.append(key)

        return expired_keys

    async def verify_integrity(self) -> Dict[str, List[str]]:
        """Verify index integrity against filesystem.

        Returns:
            Dict with 'missing_files' and 'orphaned_files' lists
        """
        # Get all cache files from filesystem
        cache_files = set()
        for path in self._cache_dir.rglob("*.cache"):
            cache_files.add(path.name)

        # Get all files from index
        index_files = set()
        for entry in self._index.values():
            filename = entry["filename"]
            if not filename.endswith(".cache"):
                filename += ".cache"
            index_files.add(filename)

        missing_files = list(index_files - cache_files)
        orphaned_files = list(cache_files - index_files)

        return {
            "missing_files": missing_files,
            "orphaned_files": orphaned_files,
        }

    async def _rebuild_index(self) -> None:
        """Rebuild index from existing cache files."""
        self._index.clear()
        rebuilt_count = 0

        try:
            for path in self._cache_dir.rglob("*.cache"):
                try:
                    # Read cache file to extract key and metadata
                    async with aiofiles.open(path, "rb") as f:
                        data = await f.read()

                    # Handle compressed files
                    if data.startswith(b"\x78\x9c"):  # zlib header
                        import zlib

                        data = zlib.decompress(data)

                    entry = json.loads(data.decode("utf-8"))
                    key = entry.get("key")
                    metadata = entry.get("metadata", {})

                    if key:
                        # Add entry directly without calling add_entry
                        self._index[key] = {
                            "filename": path.name,
                            "created": metadata.get("created", time.time()),
                            "last_accessed": metadata.get("last_accessed", time.time()),
                            "size": metadata.get("size", 0),
                            "ttl": metadata.get("ttl"),
                            "compression": metadata.get("compression", False),
                        }
                        rebuilt_count += 1

                except (json.JSONDecodeError, OSError, KeyError) as e:
                    logger.warning(f"Skipping corrupted cache file {path}: {e}")
                    continue

            self._dirty = True
            logger.info(f"Rebuilt index with {rebuilt_count} entries")

        except Exception as e:
            logger.error(f"Failed to rebuild index: {e}")
            raise

    async def clear(self) -> None:
        """Clear the index."""
        async with self._lock:
            self._index.clear()
            self._dirty = True
