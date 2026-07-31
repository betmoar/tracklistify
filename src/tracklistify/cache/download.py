"""URL-keyed download cache for full audio files + metadata sidecars.

Separate from ``BaseCache`` (which stores JSON-serializable values and
rejects binary blobs). The download cache holds the **full downloaded
audio** keyed by a per-provider canonical ID + ``stream_copy`` flag, so
re-running the same URL skips the network entirely.

Storage layout (under ``cache_dir/downloads/``)::

    <sha256>            # the audio blob (no extension; sidecar records ext)
    <sha256>.meta.json  # title, uploader, duration, ext, source_url

The key material is ``f"{canonicalize_url(url)}|stream_copy={stream_copy}"``
— ``stream_copy`` is included because it produces different bytes (MP3
transcode vs source-container opus/webm/m4a). ``format``/``quality`` are
not yet wired through the factory, so excluded (add when wired).

v1 has no TTL or eviction — audio is large and ``cache_max_size`` (1MB) is
far too small to enforce against audio files. Cleanup is manual
(``rm -rf cache_dir/downloads``). Future: a ``download_cache_ttl`` knob.
"""

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from tracklistify.downloaders.cache_key import canonicalize_url
from tracklistify.utils.logger import get_logger

logger = get_logger(__name__)

_DOWNLOADS_SUBDIR = "downloads"


@dataclass
class DownloadCacheEntry:
    """A cache hit: the audio path on disk + its persisted metadata."""

    audio_path: Path
    metadata: Dict[str, Any]


class DownloadCache:
    """Blob store for downloaded audio, keyed by canonical URL + stream_copy."""

    def __init__(self, cache_dir: Path):
        """Resolve the downloads subdir under ``cache_dir``.

        The directory is created lazily on first ``set`` so a read-only
        ``cache_dir`` (or a disabled cache that is never written to) does
        not fail at construction.
        """
        self._downloads_dir = Path(cache_dir) / _DOWNLOADS_SUBDIR

    def _key_hash(self, url: str, stream_copy: bool) -> str:
        key_material = f"{canonicalize_url(url)}|stream_copy={stream_copy}"
        return hashlib.sha256(key_material.encode()).hexdigest()

    def _audio_path(self, h: str) -> Path:
        return self._downloads_dir / h

    def _sidecar_path(self, h: str) -> Path:
        return self._downloads_dir / f"{h}.meta.json"

    async def get(self, url: str, stream_copy: bool) -> Optional[DownloadCacheEntry]:
        """Return the cached audio + metadata, or None on any miss/failure.

        Misses include: no entry, missing audio blob, corrupt/unreadable
        sidecar. All degrade silently — callers fall back to a live download.
        """
        h = self._key_hash(url, stream_copy)
        audio = self._audio_path(h)
        sidecar = self._sidecar_path(h)
        if not audio.is_file() or not sidecar.is_file():
            return None
        try:
            metadata = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.debug(f"Download cache sidecar unreadable ({h}): {e}")
            return None
        return DownloadCacheEntry(audio_path=audio, metadata=metadata)

    async def set(
        self,
        url: str,
        stream_copy: bool,
        audio_path: Path,
        metadata: Dict[str, Any],
    ) -> Path:
        """Copy ``audio_path`` into the cache and persist ``metadata``.

        Returns the cached audio path. Best-effort: on failure logs at debug
        and returns the original ``audio_path`` so the caller can proceed
        with the live file even if the cache write failed.
        """
        h = self._key_hash(url, stream_copy)
        try:
            self._downloads_dir.mkdir(parents=True, exist_ok=True)
            cached_audio = self._audio_path(h)
            shutil.copy2(audio_path, cached_audio)
            sidecar = {
                "title": metadata.get("title", ""),
                "uploader": metadata.get("uploader", ""),
                "duration": metadata.get("duration", 0),
                "ext": metadata.get("ext", audio_path.suffix.lstrip(".")),
                "source_url": url,
            }
            self._sidecar_path(h).write_text(json.dumps(sidecar), encoding="utf-8")
            logger.debug(f"Download cache stored: {canonicalize_url(url)}")
            return cached_audio
        except OSError as e:
            logger.debug(f"Download cache write failed ({url}): {e}")
            return Path(audio_path)

    async def has(self, url: str, stream_copy: bool) -> bool:
        """Whether a non-corrupt entry exists."""
        return await self.get(url, stream_copy) is not None
