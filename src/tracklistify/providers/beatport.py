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
from typing import Any, Dict, Optional
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
SITE_BASE = "https://beatport.com"
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
                raise RateLimitError("Beatport rate limit hit during login")
            data = await self._json_or_none(response)
            # Beatport answers a bad login with 200 + an error body, so the
            # status alone is not the signal.
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
            if not location:
                raise ProviderError(
                    "Beatport OAuth redirect carried no Location header "
                    f"(status {response.status}); the client ID may be wrong."
                )
            codes = parse_qs(urlparse(location).query).get("code")
            if not codes:
                raise ProviderError(
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
                raise RateLimitError("Beatport rate limit hit during token exchange")
            data = await self._json_or_none(response)
            if not isinstance(data, dict) or "access_token" not in data:
                raise ProviderError(
                    f"Beatport token exchange failed (status {response.status})."
                )
            logger.debug("Beatport: obtained access token")
            return self._store_token_response(data)

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
