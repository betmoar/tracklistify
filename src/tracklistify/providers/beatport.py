"""Beatport v4 catalog provider — canonical links + DJ metadata.

Resolves a Beatport track URL plus the fields Spotify and MusicBrainz do not
carry (BPM, musical key, label, genre, remixers, catalog number) for each
identified track. Used by the post-dedup enrichment hook as a third source,
after Spotify and MusicBrainz.

Beatport has no self-serve API tier — partner access is a commercial-review
waitlist — so this module ships **no** client ID and does not scrape one.
Every credential is supplied by the user through the environment; without
them the factory returns ``None`` and the pass is a silent no-op.
"""

# Standard library imports
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

# Third-party imports
import aiohttp

from tracklistify.providers.base import (
    AuthenticationError,
    ProviderError,
    RateLimitError,
)

# Local/package imports
from tracklistify.utils.logger import get_logger

logger = get_logger(__name__)

API_BASE = "https://api.beatport.com/v4"
SITE_BASE = "https://www.beatport.com"
# Beatport's own swagger-ui redirect target; the authorization code comes back
# on this URL as a ?code= query parameter in the 302 Location header.
REDIRECT_URI = f"{API_BASE}/auth/o/post-message/"
# Treat a token expiring within this many seconds as already expired, so a
# long pass can't have its token die mid-run.
TOKEN_EXPIRY_BUFFER_SECONDS = 30
TOKEN_FILENAME = "beatport_token.json"


class BeatportProvider:
    """Beatport v4 enrichment provider (read-only catalog access)."""

    def __init__(
        self,
        client_id: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        token: Optional[str] = None,
        token_path: Optional[Path] = None,
    ):
        """Initialize.

        Args:
            client_id: OAuth client ID. Supplied by the user; never shipped.
            username: Beatport account username (with ``password``).
            password: Beatport account password (with ``username``).
            token: A pre-obtained access token, used as-is. Skips login.
            token_path: Where to cache the obtained token. ``None`` disables
                caching (tests, and any caller without a cache dir).
        """
        self.client_id = client_id
        self.username = username
        self.password = password
        self._pasted_token = token
        self._token_path = token_path
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._expires_at: float = 0.0
        self._session = None

    async def _ensure_session(self):
        """Ensure aiohttp session exists.

        A cookie jar is required for the login step: ``/auth/login/`` sets the
        session + CSRF cookies that ``/auth/o/authorize/`` then needs.
        """
        if self._session is None:
            self._session = aiohttp.ClientSession()

    async def close(self) -> None:
        """Close the aiohttp session.

        Re-entrant — safe to call again from ``close_all()`` after the
        enrichment hook's ``async with`` has already closed it.
        """
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def __aenter__(self) -> "BeatportProvider":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    # ---- token handling ------------------------------------------------

    @staticmethod
    def _is_expired(expires_at: float) -> bool:
        return time.time() + TOKEN_EXPIRY_BUFFER_SECONDS >= expires_at

    def _load_cached_token(self) -> Optional[Dict[str, Any]]:
        """Read the cached token, or None.

        Never raises: a missing, corrupt or unreadable file is a cache miss,
        not a run-ending error.
        """
        if self._token_path is None:
            return None
        try:
            data = json.loads(Path(self._token_path).read_text())
        except (OSError, ValueError) as e:
            logger.debug(f"Beatport token cache unreadable ({type(e).__name__}); miss")
            return None
        if not isinstance(data, dict) or not data.get("access_token"):
            logger.debug("Beatport token cache malformed; miss")
            return None
        # expires_at must be a usable float; a hand-edited or partially-corrupt
        # file (e.g. a string) would otherwise raise out of the call site's
        # float() on every track. Treat it as a miss, consistent with the
        # "never raises" contract above.
        if not isinstance(data.get("expires_at"), (int, float)):
            logger.debug("Beatport token cache has no usable expires_at; miss")
            return None
        return data

    def _save_cached_token(self) -> None:
        """Persist the current token at mode 0600.

        Best-effort: a failure to write costs a re-login next run, nothing
        more.
        """
        if self._token_path is None or not self._access_token:
            return
        path = Path(self._token_path)
        payload = {
            "access_token": self._access_token,
            "refresh_token": self._refresh_token or "",
            "expires_at": self._expires_at,
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload))
            path.chmod(0o600)
        except OSError as e:
            logger.debug(f"Could not cache Beatport token: {e}")

    def _store_token_response(self, data: Dict[str, Any]) -> str:
        """Adopt a ``/auth/o/token/`` response. Returns the access token."""
        self._access_token = str(data["access_token"])
        self._refresh_token = data.get("refresh_token") or None
        expires_in = data.get("expires_in")
        self._expires_at = time.time() + float(expires_in or 0)
        self._save_cached_token()
        return self._access_token

    async def _authenticate(self) -> str:
        """Return a usable bearer token, obtaining one if needed.

        Resolution order — cheapest first:

        1. a token already held in memory and not expired;
        2. ``TRACKLISTIFY_BEATPORT_TOKEN`` pasted by the user (used verbatim);
        3. a non-expired token from the on-disk cache;
        4. the username/password authorization-code flow.

        Raises:
            AuthenticationError: no usable credential, or login rejected.
            ProviderError: the OAuth dance broke in an unexpected place.
        """
        if self._access_token and not self._is_expired(self._expires_at):
            return self._access_token

        if self._pasted_token:
            self._access_token = self._pasted_token
            # A pasted token carries no expiry; trust it until a 401 says
            # otherwise (the hook disables the pass on that).
            self._expires_at = float("inf")
            return self._access_token

        cached = self._load_cached_token()
        if cached and not self._is_expired(float(cached.get("expires_at") or 0)):
            self._access_token = str(cached["access_token"])
            self._refresh_token = cached.get("refresh_token") or None
            self._expires_at = float(cached.get("expires_at") or 0)
            logger.debug("Beatport: using cached access token")
            return self._access_token

        if not (self.username and self.password):
            raise AuthenticationError(
                "Beatport needs TRACKLISTIFY_BEATPORT_USERNAME + "
                "TRACKLISTIFY_BEATPORT_PASSWORD, or a TRACKLISTIFY_BEATPORT_TOKEN "
                "pasted from the browser."
            )
        return await self._password_flow()

    async def _password_flow(self) -> str:
        """login -> authorize -> exchange code for a token.

        Beatport's swagger-ui frontend flow: POST the credentials to get
        session cookies, GET the authorize endpoint WITHOUT following the
        redirect (the code only exists in the Location header), then exchange.
        """
        await self._ensure_session()
        logger.debug("Beatport: authorizing with username and password")

        async with self._session.post(
            f"{API_BASE}/auth/login/",
            json={"username": self.username, "password": self.password},
        ) as response:
            if response.status == 429:
                raise RateLimitError(
                    "Beatport rate limit hit during login",
                    provider="beatport",
                    retry_after=self._retry_after_seconds(response),
                )
            # A server-side failure is not a credentials problem. Reporting it
            # as one is both misleading and wrong in effect: the hook treats
            # AuthenticationError as fatal and disables the pass for the whole
            # run, which a transient 503 does not warrant.
            if response.status >= 500:
                raise ProviderError(
                    f"Beatport login failed server-side (status {response.status})."
                )
            data = await self._json_or_none(response)
            # Beatport answers a bad login with 200 + an error body, so a 2xx
            # status alone is not the signal — the body has to be inspected.
            if not isinstance(data, dict) or "username" not in data:
                raise AuthenticationError(
                    "Beatport rejected the username/password login. Check "
                    "TRACKLISTIFY_BEATPORT_USERNAME / _PASSWORD, or paste a "
                    "token into TRACKLISTIFY_BEATPORT_TOKEN instead."
                )

        async with self._session.get(
            f"{API_BASE}/auth/o/authorize/",
            params={
                "response_type": "code",
                "client_id": self.client_id,
                "redirect_uri": REDIRECT_URI,
            },
            allow_redirects=False,
        ) as response:
            location = response.headers.get("Location")
            if response.status >= 500:
                # Transient server failure, not misconfig — must not disable the
                # pass for the whole run (only AuthenticationError does).
                raise ProviderError(
                    f"Beatport authorize failed server-side (status {response.status})."
                )
            if not location:
                # A 2xx/3xx with no Location means the client_id/redirect_uri was
                # rejected: a config problem, same class as a bad password, and it
                # will fail identically on every track. Promote it so the
                # enrichment hook disables the pass instead of re-running the full
                # OAuth dance once per track (identification.py _enrich_one_beatport).
                raise AuthenticationError(
                    "Beatport OAuth redirect carried no Location header "
                    f"(status {response.status}); the client ID or redirect URI "
                    "may be wrong. Check TRACKLISTIFY_BEATPORT_CLIENT_ID."
                )
            codes = parse_qs(urlparse(location).query).get("code")
            if not codes:
                raise AuthenticationError(
                    "Beatport OAuth redirect carried no authorization code."
                )
            auth_code = codes[0]

        async with self._session.post(
            f"{API_BASE}/auth/o/token/",
            params={
                "code": auth_code,
                "grant_type": "authorization_code",
                "redirect_uri": REDIRECT_URI,
                "client_id": self.client_id,
            },
        ) as response:
            if response.status == 429:
                raise RateLimitError(
                    "Beatport rate limit hit during token exchange",
                    provider="beatport",
                    retry_after=self._retry_after_seconds(response),
                )
            if response.status >= 500:
                # Transient server failure during exchange — must not disable the
                # pass (unlike an unrecoverable config problem).
                raise ProviderError(
                    "Beatport token exchange failed server-side "
                    f"(status {response.status})."
                )
            data = await self._json_or_none(response)
            if not isinstance(data, dict) or "access_token" not in data:
                raise AuthenticationError(
                    f"Beatport token exchange failed (status {response.status})."
                )
            logger.debug("Beatport: obtained access token")
            return self._store_token_response(data)

    # Fallback wait when a 429 carries no usable Retry-After.
    _DEFAULT_RETRY_AFTER_SECONDS = 60

    @classmethod
    def _retry_after_seconds(cls, response) -> int:
        """Parse ``Retry-After`` defensively, in seconds.

        RFC 9110 allows either delay-seconds or an HTTP-date, and the header
        may be absent entirely. Parsing it with a bare ``int()`` raises on a
        date — which the enrichment hook would swallow as an ordinary
        per-track miss, so a genuine 429 would stop disabling the pass and we
        would keep hammering a rate-limited API. Mirrors
        ``MusicBrainzProvider._retry_after_seconds``.
        """
        header = response.headers.get("Retry-After")
        if header:
            try:
                return int(float(header))
            except (TypeError, ValueError):
                # An HTTP-date. Not worth parsing: the fallback is the same
                # order of magnitude and this path is rare.
                logger.debug(f"Unparseable Retry-After header {header!r}; default")
        return cls._DEFAULT_RETRY_AFTER_SECONDS

    @staticmethod
    async def _json_or_none(response) -> Optional[Any]:
        """Decode a JSON body, or None.

        Third-party responses are not guaranteed to be JSON even when the
        status says success.
        """
        try:
            return await response.json()
        except Exception:
            return None

    # ---- catalog -------------------------------------------------------

    # How many search candidates to ask for. The enrichment hook gates them
    # in rank order, so a handful is plenty — the right match is near the top
    # or not there at all.
    _SEARCH_PER_PAGE = 5

    async def _api_request(self, endpoint: str, **params) -> Optional[Any]:
        """GET an authenticated catalog endpoint.

        Returns the decoded body, or ``None`` for a 404 (a clean miss — the
        caller turns that into an empty result, not an error).

        Raises:
            AuthenticationError: 401 — the token is dead; it is cleared so a
                later call re-authenticates.
            RateLimitError: 429, carrying ``retry_after`` as a structured
                attribute so callers can honor it.
            ProviderError: any other non-2xx.
        """
        await self._ensure_session()
        token = await self._authenticate()

        url = f"{API_BASE}/{endpoint.lstrip('/')}"
        async with self._session.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            params=params,
        ) as response:
            if response.status == 404:
                return None
            if response.status == 401:
                self._access_token = None
                self._expires_at = 0.0
                raise AuthenticationError("Beatport token rejected (401)")
            if response.status == 429:
                retry_after = self._retry_after_seconds(response)
                raise RateLimitError(
                    f"Beatport rate limit exceeded. Retry after {retry_after}s",
                    provider="beatport",
                    retry_after=retry_after,
                )
            if not 200 <= response.status < 300:
                raise ProviderError(f"Beatport API error: {response.status}")
            return await self._json_or_none(response)

    async def lookup_isrc(self, isrc: str) -> Dict[str, Any]:
        """Resolve a track by exact ISRC. ``{}`` on a miss.

        Whether ``/catalog/tracks/`` actually filters on ``isrc`` is
        unverified (backlog U11). The returned-ISRC check below makes the
        unverified case safe: an endpoint that ignores the filter returns
        some arbitrary track, whose ISRC will not match, and the caller falls
        through to gated search instead of attaching wrong metadata.
        """
        data = await self._api_request("catalog/tracks/", isrc=isrc, per_page=1)
        results = self._result_rows(data, "results")
        if not results:
            return {}
        extracted = self._extract(results[0])
        if extracted.get("isrc") != isrc:
            logger.debug(
                "Beatport ISRC lookup returned a different ISRC; treating as a miss"
            )
            return {}
        return extracted

    async def search_tracks(
        self, title: str, artist: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search the catalog by title (+ artist). Candidates in rank order.

        Deliberately returns every candidate rather than picking one: the
        acceptance gate lives in the enrichment hook, where the canonical
        title/artist comparison helpers live.
        """
        query = f"{artist} {title}".strip() if artist else title
        data = await self._api_request(
            "catalog/search/",
            q=query,
            type="tracks",
            per_page=self._SEARCH_PER_PAGE,
        )
        return [self._extract(row) for row in self._result_rows(data, "tracks")]

    @staticmethod
    def _result_rows(data: Any, key: str) -> List[dict]:
        """Pull the row list out of a v4 response body, defensively.

        v4 wraps list endpoints in ``{"results": [...]}`` and search in
        ``{"tracks": [...]}``, but a bare list is accepted too — a shape
        change should cost rows, not raise.
        """
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            rows = data.get(key) or data.get("results") or []
        else:
            rows = []
        return [r for r in rows if isinstance(r, dict)]

    @staticmethod
    def _extract(track: dict) -> Dict[str, Any]:
        """Normalize a v4 track object into our flat enrichment shape.

        Empty values are dropped rather than stored as ``None`` — the
        ``_extra_metadata`` convention, so ``Track.metadata`` stays free of
        null noise. Every read is defensive except ``id``/``name``, which are
        contract for any track object.
        """
        release = track.get("release")
        release = release if isinstance(release, dict) else {}

        def _name_of(value) -> Optional[str]:
            return value.get("name") if isinstance(value, dict) else None

        def _names(values) -> List[str]:
            if not isinstance(values, list):
                return []
            return [v["name"] for v in values if isinstance(v, dict) and v.get("name")]

        slug = track.get("slug")
        track_id = str(track["id"])

        out = {
            "beatport_id": track_id,
            "title": str(track["name"]),
            "mix_name": track.get("mix_name"),
            "artists": _names(track.get("artists")),
            "url": f"{SITE_BASE}/track/{slug}/{track_id}" if slug else None,
            "bpm": int(track["bpm"]) if track.get("bpm") else None,
            "key": _name_of(track.get("key")),
            "label": _name_of(release.get("label")),
            "genre": _name_of(track.get("genre")),
            "sub_genre": _name_of(track.get("sub_genre")),
            "remixers": _names(track.get("remixers")) or None,
            "catalog_number": release.get("catalog_number"),
            "release_date": release.get("publish_date"),
            "isrc": track.get("isrc"),
        }
        return {k: v for k, v in out.items() if v}
