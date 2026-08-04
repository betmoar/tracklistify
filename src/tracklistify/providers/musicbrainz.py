"""MusicBrainz metadata provider — keyless, free ISRC enrichment.

Resolves canonical streaming URLs (Spotify/Deezer/Tidal/Apple/Beatport) per
track via MusicBrainz's ``isrc/<isrc>?inc=url-rels`` lookup. Unlike the
Spotify provider, MusicBrainz needs no credentials, no Premium, and no key —
the only requirement is a descriptive ``User-Agent`` (MusicBrainz blocks
generic agents). Used by the post-dedup enrichment hook as a second source
that runs after the Spotify client-credentials source.
"""

# Standard library imports
import asyncio
import os
from typing import Dict
from urllib.parse import urlparse

# Third-party imports
import aiohttp

# Local/package imports
from tracklistify.utils.logger import get_logger

logger = get_logger(__name__)

# Map a URL relation's host to a ``links`` key. Only canonical per-service
# track URLs are kept; unknown hosts are skipped (we do not invent keys).
# MusicBrainz exposes these under url-relation types "streaming" and
# "free streaming" (both carry real track URLs, not searches).
_SERVICE_HOSTS = {
    "open.spotify.com": "spotify",
    "deezer.com": "deezer",
    "tidal.com": "tidal",
    "music.apple.com": "apple",
    "beatport.com": "beatport",
}

# Default User-Agent when TRACKLISTIFY_MUSICBRAINZ_CONTACT is unset.
# MusicBrainz asks for a *descriptive* UA; a contact string is courteous but
# not required, and it is not a secret (hence env-only, not a config field).
_DEFAULT_UA = "Tracklistify/0.1 ( https://github.com/betmoar/tracklistify )"


class MusicBrainzProvider:
    """Keyless MusicBrainz ISRC enrichment provider."""

    API_BASE = "https://musicbrainz.org/ws/2"

    def __init__(self, user_agent: str | None = None):
        """Initialize.

        Args:
            user_agent: descriptive User-Agent string. Defaults to a generic
                one, or one incorporating ``TRACKLISTIFY_MUSICBRAINZ_CONTACT``
                if that env var is set.
        """
        self.user_agent = user_agent or self._default_user_agent()
        self._session = None

    @staticmethod
    def _default_user_agent() -> str:
        contact = os.getenv("TRACKLISTIFY_MUSICBRAINZ_CONTACT")
        if contact:
            return f"Tracklistify/0.1 ( {contact} )"
        return _DEFAULT_UA

    async def _ensure_session(self):
        """Ensure aiohttp session exists."""
        if self._session is None:
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": self.user_agent}
            )

    async def close(self) -> None:
        """Close the provider's aiohttp session. Re-entrant — safe to call
        again from ``close_all()`` after the enrichment hook's ``async with``
        has already closed it."""
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> "MusicBrainzProvider":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def lookup_isrc(self, isrc: str) -> Dict[str, str]:
        """Look up canonical streaming URLs for a track by its exact ISRC.

        ``GET isrc/{isrc}?inc=url-rels&fmt=json``. Returns a ``{service: url}``
        map (e.g. ``{"spotify": "https://open.spotify.com/track/..."}``)
        built from every ``streaming``/``free streaming`` url-relation across
        all recordings the ISRC resolves to. Empty dict on a miss — 404 (ISRC
        not in MusicBrainz) and 400 (malformed ISRC) are clean misses, not
        errors, so the enrichment hook counts them as ``none``.

        Raises on transport failure or a 5xx — the hook's generic ``except``
        treats that as a per-track miss and continues (R5).

        Args:
            isrc: International Standard Recording Code (e.g. ``USABC1234567``).

        Returns:
            ``{service_key: canonical_url}``; empty when no relations resolve.
        """
        await self._ensure_session()
        url = f"{self.API_BASE}/isrc/{isrc}"
        params = {"inc": "url-rels", "fmt": "json"}

        # MusicBrainz rate-limits with 503 under load even well under its
        # stated 1200/min ceiling — measured ~19% of ISRCs 503 on a first
        # attempt (2026-08-04). A 503 is transient, not a real miss: retry a
        # bounded number of times, honoring Retry-After when present, so a
        # resolvable link is not silently lost to a one-shot rate-limit blip.
        # Other 5xx/4xx surface to the hook unchanged.
        for attempt in range(self._MAX_503_RETRIES + 1):
            async with self._session.get(url, params=params) as response:
                if response.status in (400, 404):
                    # Clean miss: malformed ISRC, or ISRC not in MusicBrainz.
                    return {}
                if response.status == 503 and attempt < self._MAX_503_RETRIES:
                    retry_after = self._retry_after_seconds(response, attempt)
                    logger.debug(
                        f"MusicBrainz 503 for {isrc}; retry {attempt + 1} "
                        f"in {retry_after:.1f}s"
                    )
                    await asyncio.sleep(retry_after)
                    continue
                if not 200 <= response.status < 300:
                    # Exhausted retries (503) or a non-retryable error — surface
                    # to the hook, which treats it as a per-track miss (R5).
                    raise aiohttp.ClientResponseError(
                        response.request_info,
                        response.history,
                        status=response.status,
                        message=f"MusicBrainz API error: {response.status}",
                    )
                data = await response.json()
                return self._extract_links(data)
        # Unreachable: the loop returns or raises on every path.
        return {}

    # Max retries on a 503 before giving up on a track.
    _MAX_503_RETRIES = 2

    @staticmethod
    def _retry_after_seconds(response, attempt: int) -> float:
        """Honor Retry-After when present, else exponential backoff (2s, 4s)."""
        header = response.headers.get("Retry-After")
        if header:
            try:
                return float(header)
            except (TypeError, ValueError):
                logger.debug(f"Unparseable Retry-After header {header!r}; backoff")
        return 2.0 * (2**attempt)

    @staticmethod
    def _extract_links(data: dict) -> Dict[str, str]:
        """Build ``{service: url}`` from a MusicBrainz ISRC response.

        Iterates ``url-rels`` across every recording (an ISRC can map to
        multiple recordings). First occurrence of a service wins — the
        relations are canonical track URLs, not duplicates worth de-duping,
        but determinism matters for tests.
        """
        links: Dict[str, str] = {}
        for recording in data.get("recordings", []):
            for rel in recording.get("relations", []):
                resource = (rel.get("url") or {}).get("resource")
                if not resource:
                    continue
                host = urlparse(resource).netloc.lower()
                # Strip a leading "www." so "www.deezer.com" maps too.
                if host.startswith("www."):
                    host = host[4:]
                service = _SERVICE_HOSTS.get(host)
                if service and service not in links:
                    links[service] = resource
        return links
