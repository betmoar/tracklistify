"""Per-provider URL canonicalization for the download cache.

The download cache keys on a **canonical ID**, not the raw URL, so that
URL variants of the same media resolve to one cache entry. This is
necessary because ``clean_url`` strips the query string entirely — which
would destroy YouTube's ``?v=<id>`` and collapse every ``/watch`` URL to
one key. Each provider needs its own extraction logic:

- **YouTube:** the 11-char video ID is the stable identity, but it lives
  in different URL shapes (``watch?v=``, ``youtu.be/``, ``/shorts/``,
  ``/embed/``, ``/live/``). All must collapse to ``yt:<id>``.
- **SoundCloud / Mixcloud:** the URL path is the canonical identity;
  ``clean_url`` is safe (their query params are non-load-bearing).
- **Unknown:** best-effort ``raw:<clean_url(url)>`` fallback.

All extraction is **offline** (regex/path parsing) and deterministic —
no network resolution. This mirrors the precedent in
``SpotifyDownloader._extract_track_id``.
"""

import re
from urllib.parse import unquote, urlparse

from tracklistify.utils.validation import (
    clean_url,
    is_mixcloud_url,
    is_soundcloud_url,
    is_youtube_url,
)

# YouTube video IDs are exactly 11 chars of [A-Za-z0-9_-].
_YT_ID = r"([A-Za-z0-9_-]{11})"
# Order matters: longest/most-specific path prefixes first so a bare
# /watch?v= doesn't shadow a /shorts/ match by accident.
_YT_PATTERNS = [
    re.compile(rf"youtube\.com/watch\?v={_YT_ID}"),
    re.compile(rf"youtu\.be/{_YT_ID}"),
    re.compile(rf"youtube\.com/shorts/{_YT_ID}"),
    re.compile(rf"youtube\.com/embed/{_YT_ID}"),
    re.compile(rf"youtube\.com/live/{_YT_ID}"),
    re.compile(rf"music\.youtube\.com/watch\?v={_YT_ID}"),
    # Fallback: any v= query param on a youtube host (mobile subdomains etc.).
    re.compile(rf"[?&]v={_YT_ID}"),
]


def _canonicalize_youtube(url: str) -> str:
    for pattern in _YT_PATTERNS:
        if match := pattern.search(url):
            return f"yt:{match.group(1)}"
    # Should not happen for a valid YouTube URL, but degrade safely.
    return f"raw:{clean_url(url)}"


def _canonicalize_soundcloud(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    # Strip the www. prefix so www.soundcloud.com and soundcloud.com collide.
    if host.startswith("www."):
        host = host[4:]
    return f"sc:{host}{parsed.path.rstrip('/')}"


def _canonicalize_mixcloud(url: str) -> str:
    """``mc:<user>_<slug>`` from the path, matching yt-dlp's own extractor."""
    parsed = urlparse(url)
    parts = [unquote(p) for p in parsed.path.strip("/").split("/") if p]
    if len(parts) >= 2:
        return f"mc:{parts[0]}_{parts[1]}"
    return f"raw:{clean_url(url)}"


def canonicalize_url(url: str) -> str:
    """Return a per-provider canonical ID for a download URL.

    Offline and deterministic. Returns one of:
    - ``yt:<video_id>`` for YouTube URLs
    - ``sc:<host><path>`` for SoundCloud URLs
    - ``mc:<user>_<slug>`` for Mixcloud URLs
    - ``raw:<cleaned_url>`` as a best-effort fallback for anything else
    """
    if is_youtube_url(url):
        return _canonicalize_youtube(url)
    if is_soundcloud_url(url):
        return _canonicalize_soundcloud(url)
    if is_mixcloud_url(url):
        return _canonicalize_mixcloud(url)
    return f"raw:{clean_url(url)}"
