# Beatport enrichment — Implementation Plan

> Execute with dev-flow: subagent per task, review after each task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in, post-dedup Beatport enrichment pass that resolves a
canonical Beatport track URL plus BPM / key / label / genre / remixers /
catalog number for each unique track.
**Architecture:** Three units mirroring the shipped MusicBrainz work — a
credential-free-of-the-dataclass provider (`providers/beatport.py`) that knows
HTTP and Beatport's payload shape; a factory accessor that reads env and
returns `None` when unconfigured; and a third sibling pass in
`IdentificationManager` that knows `Track`, the limiter and the counters.
**Tech stack:** Python 3.11–3.13, `aiohttp`, `pytest` + `pytest-asyncio`
(strict), `uv`, `ruff`.
**Spec:** `docs/dev/2026-08-05-beatport-enrichment-spec.md`
**Baseline:** `uv run python -m pytest -q` → **21 failed, 565 passed,
4 skipped** (2026-08-05). All 21 failures are in `tests/test_ytdlp.py` with
`FileNotFoundError: FFmpeg not found` (`downloaders/base.py:50`) — ffmpeg is
absent from the execution container. Environmental and pre-existing; every
delta below is reported against 21 failed / 565 passed.

## Global Constraints

Copied from the spec; every task's requirements implicitly include these.

- **Secrets are env-only.** `TRACKLISTIFY_BEATPORT_CLIENT_ID`,
  `_USERNAME`, `_PASSWORD`, `_TOKEN` are read with `os.getenv` and are **never**
  fields on `TrackIdentificationConfig` (spec R9, ACRCloud rule).
- **No client ID ships.** The source tree must never contain a literal
  Beatport client-ID value, and nothing scrapes `api.beatport.com/v4/docs/`
  (spec §2, §4).
- **Never log a secret** at any level, including `--debug`; redact account
  username/email (spec R9).
- **Best-effort:** no Beatport failure may fail a run or lose an identified
  track (spec R7). `asyncio.CancelledError` is always re-raised, never
  swallowed.
- **Limiter pairing:** every `await limiter.acquire("beatport")` is matched by
  `limiter.release("beatport")` in `finally`, and every outcome reported via
  `limiter.record_result("beatport", success=...)` (spec R8, invariant I6).
- **Defensive reads:** provider payloads are third-party JSON — `.get()`, no
  bare subscripts, except `id`/`name` which are contract.
- Test command is `uv run python -m pytest`, **never** bare `pytest`.
- Every async test carries `@pytest.mark.asyncio` (strict mode).
- Logger is `get_logger(__name__)` — never a literal module string.
- Config tests that touch env must `monkeypatch.delenv` the
  `TRACKLISTIFY_*` keys first and use `clear_config()` / `force_refresh=True`.
- Ruff must pass: `uv run ruff check src/ tests/ scripts/` and
  `uv run ruff format --check src/ tests/ scripts/`.
- Conventional Commits (commitizen) — `feat`, `test`, `docs`, `chore`.

## File map

| File | Responsibility | Task |
| --- | --- | --- |
| `src/tracklistify/config/base.py` | 3 new non-secret fields | 1 |
| `src/tracklistify/utils/rate_limiter.py` | `beatport` branch in `register_provider` | 1 |
| `scripts/generate_env_example.py` | `FIELD_SECTIONS`, `INLINE_COMMENTS`, `CREDENTIALS_BLOCK` | 1 |
| `.env.example` | regenerated | 1 |
| `src/tracklistify/providers/beatport.py` (new) | auth + token cache | 2 |
| `src/tracklistify/providers/beatport.py` | catalog lookup/search + field extraction | 3 |
| `src/tracklistify/providers/factory.py` | `get_beatport_provider()` | 4 |
| `src/tracklistify/utils/identification.py` | `_enrich_beatport`, `_enrich_one_beatport`, gate | 5 |
| `tests/test_config.py`, `tests/test_rate_limiter.py` | Task 1 tests | 1 |
| `tests/test_providers_beatport.py` (new) | Tasks 2–3 tests | 2, 3 |
| `tests/test_providers_factory.py` | Task 4 tests | 4 |
| `tests/test_beatport_enrichment.py` (new) | Task 5 tests | 5 |
| `docs/BACKLOG.md` | close the P3 item, record U11–U13 measurements | 6 |

**Note on U11** (does `/v4/catalog/tracks/?isrc=` actually filter?): it does
**not** block implementation. Task 3 builds the ISRC path with a
returned-ISRC-mismatch guard, so if the filter is silently ignored the guard
rejects the result and the track falls through to gated search. The live probe
in Task 6 records the answer; no code changes if it comes back "no".

---

### Task 1: Config fields, limiter branch, env example

**Files:**
- Modify: `src/tracklistify/config/base.py` (after the `musicbrainz_*` block, ~line 251)
- Modify: `src/tracklistify/utils/rate_limiter.py` (`register_provider`, after the `musicbrainz` branch, ~line 138)
- Modify: `scripts/generate_env_example.py` (`FIELD_SECTIONS`, `INLINE_COMMENTS`, `CREDENTIALS_BLOCK`)
- Modify: `.env.example` (regenerated, never hand-edited)
- Test: `tests/test_config.py`, `tests/test_rate_limiter.py`

**Interfaces:**
- Produces: `config.beatport_enabled: bool = False`,
  `config.beatport_max_rpm: int = 60`,
  `config.beatport_max_concurrent: int = 1`;
  `RateLimiter.register_provider("beatport")` resolving from those fields.

- [ ] **Step 1: Write the failing tests**

In `tests/test_config.py` (next to `test_musicbrainz_config_defaults_and_override`):

```python
def test_beatport_config_defaults_and_override(monkeypatch):
    """beatport_enabled defaults OFF (opt-in: needs a personal account and a
    user-supplied client ID) and the rate-limit fields override from env."""
    for key in [k for k in os.environ if k.startswith("TRACKLISTIFY_")]:
        monkeypatch.delenv(key, raising=False)

    clear_config()
    cfg = get_config()
    assert cfg.beatport_enabled is False
    assert cfg.beatport_max_rpm == 60
    assert cfg.beatport_max_concurrent == 1

    monkeypatch.setenv("TRACKLISTIFY_BEATPORT_ENABLED", "true")
    monkeypatch.setenv("TRACKLISTIFY_BEATPORT_MAX_RPM", "20")
    clear_config()
    cfg = get_config()
    assert cfg.beatport_enabled is True
    assert cfg.beatport_max_rpm == 20


def test_beatport_secrets_are_not_config_fields(monkeypatch):
    """Beatport credentials are env-only (R9) — they must never become
    dataclass fields, or they leak through repr() and validation messages."""
    for key in [k for k in os.environ if k.startswith("TRACKLISTIFY_")]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("TRACKLISTIFY_BEATPORT_CLIENT_ID", "super-secret-id")
    monkeypatch.setenv("TRACKLISTIFY_BEATPORT_PASSWORD", "hunter2")
    clear_config()
    cfg = get_config()

    for name in ("beatport_client_id", "beatport_username",
                 "beatport_password", "beatport_token"):
        assert not hasattr(cfg, name)
    assert "super-secret-id" not in repr(cfg)
    assert "hunter2" not in repr(cfg)
```

In `tests/test_rate_limiter.py` (next to `test_register_provider_musicbrainz_reads_config_fields`):

```python
def test_register_provider_beatport_reads_config_fields():
    """register_provider('beatport') resolves limits from the config fields,
    same parametric-branch pattern as spotify/musicbrainz."""
    from types import SimpleNamespace

    from tracklistify.utils.rate_limiter import RateLimiter

    cfg = SimpleNamespace(
        beatport_max_rpm=44,
        beatport_max_concurrent=3,
        shazam_max_rpm=25,
        shazam_max_concurrent=1,
        acrcloud_max_rpm=300,
        acrcloud_max_concurrent=10,
        spotify_max_rpm=120,
        spotify_max_concurrent=20,
        musicbrainz_max_rpm=30,
        musicbrainz_max_concurrent=1,
        max_requests_per_minute=25,
        max_concurrent_requests=2,
    )
    limiter = RateLimiter(config=cfg)
    limiter.register_provider("beatport")
    limits = limiter._provider_limits["beatport"]
    assert limits.max_requests_per_minute == 44
    assert limits.max_concurrent_requests == 3
```

- [ ] **Step 2: Run them, verify they fail correctly**

Run:
```bash
uv run python -m pytest tests/test_config.py::test_beatport_config_defaults_and_override \
  tests/test_rate_limiter.py::test_register_provider_beatport_reads_config_fields -v
```
Expected: FAIL — `AttributeError: 'TrackIdentificationConfig' object has no
attribute 'beatport_enabled'` and the limiter test asserting 44 but getting
the global fallback 25. Not an import error, not a collection error.

- [ ] **Step 3: Minimal implementation**

`config/base.py`, immediately after `musicbrainz_max_concurrent`:

```python
    # Beatport link + DJ-metadata enrichment (opt-in, default OFF). Unlike
    # MusicBrainz this needs a Beatport account AND a client ID the user
    # supplies themselves — the repo ships neither — so it stays off until
    # somebody turns it on. A no-op without credentials either way.
    # Credentials are env-only (TRACKLISTIFY_BEATPORT_CLIENT_ID / _USERNAME /
    # _PASSWORD / _TOKEN), deliberately NOT fields here: dataclass fields leak
    # through repr() and validation error messages.
    beatport_enabled: bool = field(default=False)
    # Beatport publishes no official rate limit; community guidance is ~500ms
    # between requests. Serialize (concurrent=1) and pace at 60rpm, with the
    # explicit inter-request sleep in the enrichment hook doing the real work
    # (the token bucket seeds full and would otherwise permit a burst — the
    # MusicBrainz 3%-vs-25% lesson).
    beatport_max_rpm: int = field(default=60)
    beatport_max_concurrent: int = field(default=1)
```

`utils/rate_limiter.py`, after the `musicbrainz` branch:

```python
            elif provider_str == "beatport":
                rpm = max_requests_per_minute or getattr(
                    self._config, "beatport_max_rpm", 60
                )
                concurrent = max_concurrent_requests or getattr(
                    self._config, "beatport_max_concurrent", 1
                )
```

`scripts/generate_env_example.py` — add to the `"Per-provider rate limits"`
section list, after `"spotify_max_concurrent"`:

```python
            "beatport_max_rpm",
            "beatport_max_concurrent",
```

add to the `"Metadata enrichment"` section list, after
`"musicbrainz_max_concurrent"`:

```python
            "beatport_enabled",
```

add to `INLINE_COMMENTS`:

```python
    "beatport_enabled": "Beatport links + BPM/key (opt-in; needs own creds)",
    "beatport_max_rpm": "requests/min (no official Beatport limit; be polite)",
    "beatport_max_concurrent": "concurrent Beatport requests (1 = serialize)",
```

and append to `CREDENTIALS_BLOCK`, before the closing `"""`:

```
#
# Beatport (opt-in, off by default — set TRACKLISTIFY_BEATPORT_ENABLED=true).
# Resolves a canonical Beatport track link plus BPM, musical key, label,
# genre and remixers per identified track. Beatport has no self-serve API
# tier: partner access is a commercial-review waitlist, so this project ships
# NO client ID and does not scrape one. Supply your own — the client ID used
# by Beatport's own API docs frontend is visible in devtools on
# https://api.beatport.com/v4/docs/, and the beets-beatport4 project
# documents the same approach. Requests are made as YOUR Beatport account,
# under your own relationship with Beatport.
# Provide the client ID plus EITHER username+password OR a pasted access
# token (devtools -> Network -> the /v4/auth/o/token/ response).
# TRACKLISTIFY_BEATPORT_CLIENT_ID=
# TRACKLISTIFY_BEATPORT_USERNAME=
# TRACKLISTIFY_BEATPORT_PASSWORD=
# TRACKLISTIFY_BEATPORT_TOKEN=
```

Then regenerate (never hand-edit `.env.example`):

```bash
uv run python scripts/generate_env_example.py
```

- [ ] **Step 4: Run tests, verify pass + no regressions vs baseline**

```bash
uv run python -m pytest tests/test_config.py tests/test_rate_limiter.py -q
uv run python scripts/generate_env_example.py --check   # exit 0 = no drift
uv run ruff check src/ tests/ scripts/ && uv run ruff format --check src/ tests/ scripts/
uv run python -m pytest -q
```
Expected: new tests PASS; drift check exits 0; full suite matches baseline
plus 3 new passes.

- [ ] **Step 5: Commit**

```bash
git add src/tracklistify/config/base.py src/tracklistify/utils/rate_limiter.py \
        scripts/generate_env_example.py .env.example \
        tests/test_config.py tests/test_rate_limiter.py
git commit -m "feat(config): beatport_enabled + per-provider rate limits"
```

---

### Task 2: `BeatportProvider` authentication + token cache

**Files:**
- Create: `src/tracklistify/providers/beatport.py`
- Test: `tests/test_providers_beatport.py` (new)

**Interfaces:**
- Consumes: `config.beatport_*` (Task 1) — not directly; the provider takes
  plain constructor args.
- Produces:
  - `BeatportProvider(client_id: str, username: str | None = None, password: str | None = None, token: str | None = None, token_path: Path | None = None)`
  - `await provider._authenticate() -> str` (bearer access token)
  - `await provider.close()` — re-entrant; `__aenter__` / `__aexit__`
  - module constants `API_BASE`, `SITE_BASE`, `REDIRECT_URI`,
    `TOKEN_EXPIRY_BUFFER_SECONDS`, `TOKEN_FILENAME`
  - exceptions raised: `AuthenticationError`, `RateLimitError`,
    `ProviderError` from `tracklistify.providers.base`

Not a subclass of `MetadataProvider` — same choice as `MusicBrainzProvider`:
the ABC's `search_track`/`enrich_metadata` signatures don't fit a
list-returning catalog search, and the enrichment hook duck-types.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_providers_beatport.py`:

```python
"""Tests for BeatportProvider — auth flow, token cache, error posture.

Mocks the aiohttp session; never hits the network.
"""

import json
import time

import pytest

from tracklistify.providers.base import (
    AuthenticationError,
    ProviderError,
    RateLimitError,
)
from tracklistify.providers.beatport import BeatportProvider


class _FakeResponse:
    def __init__(self, status=200, json_data=None, headers=None, body=""):
        self.status = status
        self._json = json_data
        self.headers = headers or {}
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None

    async def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json

    async def text(self):
        return self._body


class _FakeSession:
    """Records every call; returns queued responses in order per method."""

    def __init__(self, posts=None, gets=None):
        self._posts = list(posts or [])
        self._gets = list(gets or [])
        self.post_calls = []
        self.get_calls = []
        self.closed = False

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return self._posts.pop(0)

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        return self._gets.pop(0)

    def request(self, method, url, **kwargs):
        return self.get(url, **kwargs) if method == "GET" else self.post(url, **kwargs)

    async def close(self):
        self.closed = True


def _provider(tmp_path, session, **kwargs):
    p = BeatportProvider(
        client_id="cid",
        token_path=tmp_path / "beatport_token.json",
        **kwargs,
    )
    p._session = session
    return p


@pytest.mark.asyncio
async def test_password_flow_exchanges_code_for_token(tmp_path):
    """login -> authorize (302 with ?code=) -> token exchange."""
    session = _FakeSession(
        posts=[
            _FakeResponse(200, {"username": "dj", "email": "dj@example.com"}),
            _FakeResponse(
                200,
                {"access_token": "AT", "refresh_token": "RT", "expires_in": 3600},
            ),
        ],
        gets=[
            _FakeResponse(
                302,
                headers={"Location": "/auth/o/post-message/?code=THECODE"},
            )
        ],
    )
    provider = _provider(tmp_path, session, username="dj", password="pw")

    token = await provider._authenticate()

    assert token == "AT"
    # The authorize GET must not follow redirects, or the code is lost.
    assert session.get_calls[0][1]["allow_redirects"] is False
    # The code reached the token exchange.
    assert session.post_calls[1][1]["params"]["code"] == "THECODE"
    assert session.post_calls[1][1]["params"]["grant_type"] == "authorization_code"


@pytest.mark.asyncio
async def test_password_flow_writes_token_cache_0600(tmp_path):
    session = _FakeSession(
        posts=[
            _FakeResponse(200, {"username": "dj", "email": "e@x.com"}),
            _FakeResponse(
                200,
                {"access_token": "AT", "refresh_token": "RT", "expires_in": 3600},
            ),
        ],
        gets=[_FakeResponse(302, headers={"Location": "?code=C"})],
    )
    provider = _provider(tmp_path, session, username="dj", password="pw")
    await provider._authenticate()

    path = tmp_path / "beatport_token.json"
    stored = json.loads(path.read_text())
    assert stored["access_token"] == "AT"
    assert stored["refresh_token"] == "RT"
    assert stored["expires_at"] > time.time()
    assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.asyncio
async def test_cached_token_skips_login(tmp_path):
    path = tmp_path / "beatport_token.json"
    path.write_text(
        json.dumps(
            {"access_token": "CACHED", "refresh_token": "R", "expires_at": time.time() + 9999}
        )
    )
    session = _FakeSession()
    provider = _provider(tmp_path, session, username="dj", password="pw")

    assert await provider._authenticate() == "CACHED"
    assert session.post_calls == []


@pytest.mark.asyncio
async def test_corrupt_token_cache_is_a_miss_not_a_crash(tmp_path):
    path = tmp_path / "beatport_token.json"
    path.write_text("{ not json")
    session = _FakeSession(
        posts=[
            _FakeResponse(200, {"username": "dj", "email": "e@x.com"}),
            _FakeResponse(
                200,
                {"access_token": "FRESH", "refresh_token": "R", "expires_in": 3600},
            ),
        ],
        gets=[_FakeResponse(302, headers={"Location": "?code=C"})],
    )
    provider = _provider(tmp_path, session, username="dj", password="pw")
    assert await provider._authenticate() == "FRESH"


@pytest.mark.asyncio
async def test_expired_cached_token_is_not_used(tmp_path):
    """Expiry uses a safety buffer: a token expiring inside it is expired."""
    path = tmp_path / "beatport_token.json"
    path.write_text(
        json.dumps({"access_token": "OLD", "refresh_token": "", "expires_at": time.time() + 5})
    )
    session = _FakeSession(
        posts=[
            _FakeResponse(200, {"username": "dj", "email": "e@x.com"}),
            _FakeResponse(
                200,
                {"access_token": "NEW", "refresh_token": "R", "expires_in": 3600},
            ),
        ],
        gets=[_FakeResponse(302, headers={"Location": "?code=C"})],
    )
    provider = _provider(tmp_path, session, username="dj", password="pw")
    assert await provider._authenticate() == "NEW"


@pytest.mark.asyncio
async def test_pasted_token_is_used_without_login(tmp_path):
    session = _FakeSession()
    provider = _provider(tmp_path, session, token="PASTED")
    assert await provider._authenticate() == "PASTED"
    assert session.post_calls == []


@pytest.mark.asyncio
async def test_login_rejection_raises_authentication_error(tmp_path):
    """A 200 whose body lacks username/email is Beatport's auth failure."""
    session = _FakeSession(posts=[_FakeResponse(200, {"detail": "bad creds"})])
    provider = _provider(tmp_path, session, username="dj", password="wrong")
    with pytest.raises(AuthenticationError):
        await provider._authenticate()


@pytest.mark.asyncio
async def test_no_credentials_at_all_raises_authentication_error(tmp_path):
    provider = _provider(tmp_path, _FakeSession())
    with pytest.raises(AuthenticationError):
        await provider._authenticate()


@pytest.mark.asyncio
async def test_authorize_without_code_raises_provider_error(tmp_path):
    session = _FakeSession(
        posts=[_FakeResponse(200, {"username": "dj", "email": "e@x.com"})],
        gets=[_FakeResponse(302, headers={"Location": "/post-message/"})],
    )
    provider = _provider(tmp_path, session, username="dj", password="pw")
    with pytest.raises(ProviderError):
        await provider._authenticate()


@pytest.mark.asyncio
async def test_secrets_never_appear_in_logs(tmp_path, caplog):
    import logging

    caplog.set_level(logging.DEBUG)
    session = _FakeSession(
        posts=[
            _FakeResponse(200, {"username": "djsecret", "email": "me@example.com"}),
            _FakeResponse(
                200,
                {"access_token": "AT-SECRET", "refresh_token": "RT-SECRET", "expires_in": 3600},
            ),
        ],
        gets=[_FakeResponse(302, headers={"Location": "?code=CODE-SECRET"})],
    )
    provider = _provider(tmp_path, session, username="djsecret", password="pw-secret")
    await provider._authenticate()

    text = caplog.text
    for secret in ("pw-secret", "AT-SECRET", "RT-SECRET", "CODE-SECRET", "cid",
                   "djsecret", "me@example.com"):
        assert secret not in text


@pytest.mark.asyncio
async def test_close_is_reentrant(tmp_path):
    session = _FakeSession()
    provider = _provider(tmp_path, session)
    await provider.close()
    await provider.close()
    assert session.closed is True
```

- [ ] **Step 2: Run them, verify they fail correctly**

```bash
uv run python -m pytest tests/test_providers_beatport.py -v
```
Expected: FAIL at collection —
`ModuleNotFoundError: No module named 'tracklistify.providers.beatport'`.

- [ ] **Step 3: Minimal implementation**

Create `src/tracklistify/providers/beatport.py`:

```python
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
import os
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
        """Ensure aiohttp session exists (cookie jar required for the login
        step: /auth/login/ sets the session + CSRF cookies that
        /auth/o/authorize/ then needs)."""
        if self._session is None:
            self._session = aiohttp.ClientSession()

    async def close(self) -> None:
        """Close the aiohttp session. Re-entrant — safe to call again from
        ``close_all()`` after the hook's ``async with`` already closed it."""
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
        """Read the cached token, or None. Never raises: a missing, corrupt
        or unreadable file is a cache miss, not a run-ending error."""
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
        """Persist the current token at mode 0600. Best-effort: a failure to
        write costs a re-login next run, nothing more."""
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
        """Adopt a /auth/o/token/ response. Returns the access token."""
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
        """Decode a JSON body, or None. Third-party responses are not
        guaranteed to be JSON even when the status says success."""
        try:
            return await response.json()
        except Exception:
            return None
```

Nothing in this module logs a credential: the debug lines carry no
interpolated secret, and account username/email from the login response are
never logged at all (spec R9).

- [ ] **Step 4: Run tests, verify pass + no regressions vs baseline**

```bash
uv run python -m pytest tests/test_providers_beatport.py -v
uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/
uv run python -m pytest -q
```
Expected: all Task-2 tests PASS; full suite = baseline + 11 new passes.

- [ ] **Step 5: Commit**

```bash
git add src/tracklistify/providers/beatport.py tests/test_providers_beatport.py
git commit -m "feat(providers): Beatport v4 auth flow + token cache"
```

---

### Task 3: Catalog lookup, search, and field extraction

**Files:**
- Modify: `src/tracklistify/providers/beatport.py` (append to the class)
- Test: `tests/test_providers_beatport.py` (append)

**Interfaces:**
- Consumes: `_authenticate()`, `_ensure_session()`, `API_BASE`, `SITE_BASE`
  from Task 2.
- Produces:
  - `await provider.lookup_isrc(isrc: str) -> Dict[str, Any]` — `{}` on miss
  - `await provider.search_tracks(title: str, artist: str | None) -> List[Dict[str, Any]]`
    — candidates in API rank order, `[]` on miss
  - `BeatportProvider._extract(track_json: dict) -> Dict[str, Any]` with keys
    `beatport_id, title, mix_name, artists, url, bpm, key, label, genre,
    sub_genre, remixers, catalog_number, release_date, isrc` (empty values
    dropped, `beatport_id` and `title` always present)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_providers_beatport.py`:

```python
def _track_json(**overrides):
    """A v4 catalog track payload, shaped as beets-beatport4 documents it."""
    data = {
        "id": 12345,
        "name": "Hard Dance",
        "mix_name": "Original Mix",
        "slug": "hard-dance",
        "isrc": "GBABC1234567",
        "bpm": 150,
        "key": {"name": "A Minor"},
        "genre": {"name": "Techno"},
        "sub_genre": {"name": "Peak Time"},
        "artists": [{"name": "DJ One"}, {"name": "DJ Two"}],
        "remixers": [{"name": "Remixer X"}],
        "release": {
            "name": "The EP",
            "catalog_number": "CAT001",
            "publish_date": "2024-03-01",
            "label": {"name": "Hard Label"},
        },
    }
    data.update(overrides)
    return data


def test_extract_maps_every_field():
    out = BeatportProvider._extract(_track_json())
    assert out["beatport_id"] == "12345"
    assert out["title"] == "Hard Dance"
    assert out["mix_name"] == "Original Mix"
    assert out["artists"] == ["DJ One", "DJ Two"]
    assert out["url"] == "https://beatport.com/track/hard-dance/12345"
    assert out["bpm"] == 150
    assert out["key"] == "A Minor"
    assert out["label"] == "Hard Label"
    assert out["genre"] == "Techno"
    assert out["sub_genre"] == "Peak Time"
    assert out["remixers"] == ["Remixer X"]
    assert out["catalog_number"] == "CAT001"
    assert out["release_date"] == "2024-03-01"
    assert out["isrc"] == "GBABC1234567"


def test_extract_drops_empty_values_and_survives_a_thin_payload():
    """A payload missing everything optional yields fewer keys, not an
    exception, and never stores None (the _extra_metadata convention)."""
    out = BeatportProvider._extract({"id": 7, "name": "Bare"})
    assert out == {"beatport_id": "7", "title": "Bare"}


def test_extract_url_is_none_without_a_slug():
    out = BeatportProvider._extract({"id": 7, "name": "Bare", "bpm": 0})
    assert "url" not in out
    assert "bpm" not in out  # 0 bpm is not data


@pytest.mark.asyncio
async def test_lookup_isrc_returns_the_match(tmp_path):
    session = _FakeSession(
        gets=[_FakeResponse(200, {"results": [_track_json()]})]
    )
    provider = _provider(tmp_path, session, token="T")
    out = await provider.lookup_isrc("GBABC1234567")
    assert out["beatport_id"] == "12345"
    assert session.get_calls[0][1]["params"]["isrc"] == "GBABC1234567"


@pytest.mark.asyncio
async def test_lookup_isrc_rejects_a_mismatched_isrc(tmp_path):
    """Guards U11: if the endpoint ignores the isrc filter and returns an
    arbitrary track, that is a miss, not a match."""
    session = _FakeSession(
        gets=[_FakeResponse(200, {"results": [_track_json(isrc="USZZZ9999999")]})]
    )
    provider = _provider(tmp_path, session, token="T")
    assert await provider.lookup_isrc("GBABC1234567") == {}


@pytest.mark.asyncio
async def test_lookup_isrc_empty_results_is_a_miss(tmp_path):
    session = _FakeSession(gets=[_FakeResponse(200, {"results": []})])
    provider = _provider(tmp_path, session, token="T")
    assert await provider.lookup_isrc("GBABC1234567") == {}


@pytest.mark.asyncio
async def test_search_tracks_returns_candidates_in_rank_order(tmp_path):
    session = _FakeSession(
        gets=[
            _FakeResponse(
                200,
                {"tracks": [_track_json(id=1, name="First"),
                            _track_json(id=2, name="Second")]},
            )
        ]
    )
    provider = _provider(tmp_path, session, token="T")
    out = await provider.search_tracks("First", "DJ One")
    assert [c["title"] for c in out] == ["First", "Second"]
    params = session.get_calls[0][1]["params"]
    assert params["type"] == "tracks"
    assert "First" in params["q"] and "DJ One" in params["q"]


@pytest.mark.asyncio
async def test_401_raises_authentication_error_and_clears_the_token(tmp_path):
    session = _FakeSession(gets=[_FakeResponse(401)])
    provider = _provider(tmp_path, session, token="T")
    with pytest.raises(AuthenticationError):
        await provider.search_tracks("x", "y")
    assert provider._access_token is None


@pytest.mark.asyncio
async def test_429_raises_rate_limit_error_with_retry_after(tmp_path):
    session = _FakeSession(gets=[_FakeResponse(429, headers={"Retry-After": "17"})])
    provider = _provider(tmp_path, session, token="T")
    with pytest.raises(RateLimitError) as excinfo:
        await provider.search_tracks("x", "y")
    assert excinfo.value.retry_after == 17


@pytest.mark.asyncio
async def test_5xx_raises_provider_error(tmp_path):
    session = _FakeSession(gets=[_FakeResponse(503)])
    provider = _provider(tmp_path, session, token="T")
    with pytest.raises(ProviderError):
        await provider.search_tracks("x", "y")


@pytest.mark.asyncio
async def test_404_on_isrc_lookup_is_a_clean_miss(tmp_path):
    session = _FakeSession(gets=[_FakeResponse(404)])
    provider = _provider(tmp_path, session, token="T")
    assert await provider.lookup_isrc("GBABC1234567") == {}
```

- [ ] **Step 2: Run them, verify they fail correctly**

```bash
uv run python -m pytest tests/test_providers_beatport.py -v -k "extract or lookup or search or 401 or 429 or 5xx or 404"
```
Expected: FAIL — `AttributeError: type object 'BeatportProvider' has no
attribute '_extract'` and `'BeatportProvider' object has no attribute
'lookup_isrc'`. Task-2 tests still pass.

- [ ] **Step 3: Minimal implementation**

Append to `BeatportProvider` in `src/tracklistify/providers/beatport.py`:

```python
    # Beatport publishes no ISRC-filter contract; ask for one row and verify
    # the returned ISRC matches (see _ISRC_ENDPOINT usage in lookup_isrc).
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
                retry_after = int(response.headers.get("Retry-After", 60))
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
```

- [ ] **Step 4: Run tests, verify pass + no regressions vs baseline**

```bash
uv run python -m pytest tests/test_providers_beatport.py -v
uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/
uv run python -m pytest -q
```
Expected: all Task-2 and Task-3 tests PASS; full suite = baseline + 22 new.

- [ ] **Step 5: Commit**

```bash
git add src/tracklistify/providers/beatport.py tests/test_providers_beatport.py
git commit -m "feat(providers): Beatport catalog lookup, search, field extraction"
```

---

### Task 4: Factory accessor

**Files:**
- Modify: `src/tracklistify/providers/factory.py` (after `get_musicbrainz_provider`, ~line 171)
- Test: `tests/test_providers_factory.py`

**Interfaces:**
- Consumes: `BeatportProvider(client_id=…, username=…, password=…, token=…, token_path=…)` (Task 2).
- Produces: `ProviderFactory.get_beatport_provider() -> Optional[BeatportProvider]`,
  cached under `_BEATPORT_ENRICHMENT_KEY = "_beatport_enrichment"` so
  `close_all()` closes its session.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_providers_factory.py`:

```python
def test_get_beatport_provider_returns_none_without_client_id(monkeypatch):
    """Absent credentials are a skip, not an error (unlike ACRCloud, where
    identification cannot proceed without them)."""
    from tracklistify.providers.factory import ProviderFactory

    for key in ("TRACKLISTIFY_BEATPORT_CLIENT_ID", "TRACKLISTIFY_BEATPORT_USERNAME",
                "TRACKLISTIFY_BEATPORT_PASSWORD", "TRACKLISTIFY_BEATPORT_TOKEN"):
        monkeypatch.delenv(key, raising=False)

    assert ProviderFactory().get_beatport_provider() is None


def test_get_beatport_provider_returns_none_without_any_auth_path(monkeypatch):
    """A client ID alone cannot obtain a token — no username/password and no
    pasted token means there is nothing to do."""
    from tracklistify.providers.factory import ProviderFactory

    monkeypatch.setenv("TRACKLISTIFY_BEATPORT_CLIENT_ID", "cid")
    for key in ("TRACKLISTIFY_BEATPORT_USERNAME", "TRACKLISTIFY_BEATPORT_PASSWORD",
                "TRACKLISTIFY_BEATPORT_TOKEN"):
        monkeypatch.delenv(key, raising=False)

    assert ProviderFactory().get_beatport_provider() is None


def test_get_beatport_provider_builds_and_caches(monkeypatch):
    from tracklistify.providers.factory import ProviderFactory

    monkeypatch.setenv("TRACKLISTIFY_BEATPORT_CLIENT_ID", "cid")
    monkeypatch.setenv("TRACKLISTIFY_BEATPORT_USERNAME", "dj")
    monkeypatch.setenv("TRACKLISTIFY_BEATPORT_PASSWORD", "pw")

    factory = ProviderFactory()
    provider = factory.get_beatport_provider()
    assert provider is not None
    assert provider.client_id == "cid"
    # Cached under a key that cannot collide with an identification provider,
    # so close_all() closes its session.
    assert factory.get_beatport_provider() is provider
    assert "_beatport_enrichment" in factory.providers
    assert "_beatport_enrichment" not in KNOWN_PROVIDERS


def test_get_beatport_provider_accepts_a_pasted_token(monkeypatch):
    from tracklistify.providers.factory import ProviderFactory

    monkeypatch.setenv("TRACKLISTIFY_BEATPORT_CLIENT_ID", "cid")
    monkeypatch.setenv("TRACKLISTIFY_BEATPORT_TOKEN", "PASTED")
    for key in ("TRACKLISTIFY_BEATPORT_USERNAME", "TRACKLISTIFY_BEATPORT_PASSWORD"):
        monkeypatch.delenv(key, raising=False)

    provider = ProviderFactory().get_beatport_provider()
    assert provider is not None
    assert provider._pasted_token == "PASTED"
```

`KNOWN_PROVIDERS` is already imported at the top of that test module; add the
import if it is not.

- [ ] **Step 2: Run them, verify they fail correctly**

```bash
uv run python -m pytest tests/test_providers_factory.py -v -k beatport
```
Expected: FAIL — `AttributeError: 'ProviderFactory' object has no attribute
'get_beatport_provider'`.

- [ ] **Step 3: Minimal implementation**

In `src/tracklistify/providers/factory.py`, add to the `TYPE_CHECKING` block:

```python
    from tracklistify.providers.beatport import BeatportProvider
```

and after `get_musicbrainz_provider`:

```python
    # Cache key for the Beatport enrichment provider. Distinct from any
    # identification provider name so it cannot collide; the leading
    # underscore keeps it out of the identification name space.
    _BEATPORT_ENRICHMENT_KEY = "_beatport_enrichment"

    def get_beatport_provider(self) -> "Optional[BeatportProvider]":
        """Return a configured Beatport enrichment provider, or None.

        Every credential is env-only, following the ACRCloud rule — secrets on
        the config dataclass leak through ``repr()`` and validation errors.
        This project deliberately ships NO client ID and does not scrape one:
        Beatport has no self-serve API tier, so the user supplies their own
        (see .env.example). Missing credentials return ``None`` rather than
        raising: enrichment is optional, identification is not.

        Requires the client ID plus at least one auth path — username +
        password, or a pasted access token. A client ID on its own cannot
        obtain a token, so that is treated as unconfigured.
        """
        cached = self.providers.get(self._BEATPORT_ENRICHMENT_KEY)
        if cached is not None:
            return cached

        client_id = os.getenv("TRACKLISTIFY_BEATPORT_CLIENT_ID")
        username = os.getenv("TRACKLISTIFY_BEATPORT_USERNAME")
        password = os.getenv("TRACKLISTIFY_BEATPORT_PASSWORD")
        token = os.getenv("TRACKLISTIFY_BEATPORT_TOKEN")
        if not client_id or not (token or (username and password)):
            return None

        from tracklistify.config.factory import get_config
        from tracklistify.providers.beatport import TOKEN_FILENAME, BeatportProvider

        # Cache the obtained token next to the run cache so a normal run does
        # not re-run the whole login dance. Best-effort: the provider treats a
        # missing or unwritable path as "no cache".
        token_path = None
        try:
            token_path = get_config().cache_dir / TOKEN_FILENAME
        except Exception as e:  # pragma: no cover - config always resolves
            logger.debug(f"No cache_dir for the Beatport token cache: {e}")

        provider = BeatportProvider(
            client_id=client_id,
            username=username,
            password=password,
            token=token,
            token_path=token_path,
        )
        self.providers[self._BEATPORT_ENRICHMENT_KEY] = provider
        return provider
```

`factory.py` has no logger today — add at the top, next to the `ConfigError`
import:

```python
from tracklistify.utils.logger import get_logger

logger = get_logger(__name__)
```

- [ ] **Step 4: Run tests, verify pass + no regressions vs baseline**

```bash
uv run python -m pytest tests/test_providers_factory.py -v
uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/
uv run python -m pytest -q
```
Expected: 4 new PASS; full suite = baseline + 26 new. In particular
`tests/test_handoff_invariants.py` (provider constructibility) must be
unchanged — `get_beatport_provider` is not an identification provider and
must not appear in `KNOWN_PROVIDERS`.

- [ ] **Step 5: Commit**

```bash
git add src/tracklistify/providers/factory.py tests/test_providers_factory.py
git commit -m "feat(providers): env-only Beatport factory accessor"
```

---

### Task 5: The enrichment pass

**Files:**
- Modify: `src/tracklistify/utils/identification.py` (`_enrich_tracks` ~line 331; new methods after `_enrich_one_mb` ~line 595; new module constant next to `_MUSICBRAINZ_REQUEST_INTERVAL` ~line 35)
- Test: `tests/test_beatport_enrichment.py` (new)

**Interfaces:**
- Consumes: `factory.get_beatport_provider()` (Task 4);
  `provider.lookup_isrc(isrc)`, `provider.search_tracks(title, artist)`,
  `BeatportProvider._extract`'s output keys (Task 3);
  `config.beatport_enabled` (Task 1);
  `_comparison_title`, `_artists_match` from `tracklistify.core.track`.
- Produces: `IdentificationManager._enrich_beatport(unique_tracks)`,
  `_enrich_one_beatport(provider, limiter, track) -> str`
  (`"isrc"` | `"search"` | `"none"` | `"disabled"`),
  module-level `_beatport_candidate_matches(track, candidate) -> bool`,
  `_BEATPORT_REQUEST_INTERVAL = 0.5`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_beatport_enrichment.py`:

```python
"""Tests for the Beatport enrichment pass.

Exercises ``_enrich_tracks`` / ``_enrich_beatport`` / ``_enrich_one_beatport``
with a fake Beatport provider and a counting limiter. No network.
"""

import pytest

from tracklistify.core.track import Track
from tracklistify.providers.base import AuthenticationError, RateLimitError
from tracklistify.utils.identification import IdentificationManager


def _track(song_name="Hard Dance", artist="DJ One", metadata=None):
    return Track(
        song_name=song_name,
        artist=artist,
        time_in_mix="00:00:10",
        confidence=90.0,
        metadata=metadata or {},
    )


def _candidate(**overrides):
    data = {
        "beatport_id": "12345",
        "title": "Hard Dance",
        "mix_name": "Original Mix",
        "artists": ["DJ One"],
        "url": "https://beatport.com/track/hard-dance/12345",
        "bpm": 150,
        "key": "A Minor",
        "label": "Hard Label",
        "genre": "Techno",
        "sub_genre": "Peak Time",
        "remixers": ["Remixer X"],
        "catalog_number": "CAT001",
        "release_date": "2024-03-01",
        "isrc": "GBABC1234567",
    }
    data.update(overrides)
    return data


class _FakeBeatportProvider:
    def __init__(self, isrc_result=None, search_results=None):
        self.isrc_result = isrc_result or {}
        self.search_results = search_results or []
        self.isrc_calls = 0
        self.search_calls = 0
        self.exc = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return None

    async def lookup_isrc(self, isrc):
        self.isrc_calls += 1
        if self.exc:
            raise self.exc
        return self.isrc_result

    async def search_tracks(self, title, artist=None):
        self.search_calls += 1
        if self.exc:
            raise self.exc
        return self.search_results

    async def close(self):
        pass


class _CountingLimiter:
    def __init__(self, acquire_ok=True):
        self.acquire_ok = acquire_ok
        self.acquires = 0
        self.releases = 0
        self.results = []

    async def acquire(self, provider):
        self.acquires += 1
        return self.acquire_ok

    def release(self, provider):
        self.releases += 1

    def record_result(self, provider, success):
        self.results.append((provider, success))


class _BPFactory:
    """Beatport-only factory: no Spotify/MB accessors, so those passes no-op."""

    def __init__(self, provider):
        self._bp = provider

    def get_beatport_provider(self):
        return self._bp


def _mgr(provider, limiter, monkeypatch, enabled=True):
    from types import SimpleNamespace

    monkeypatch.setattr(
        "tracklistify.utils.identification.get_global_rate_limiter", lambda: limiter
    )
    monkeypatch.setattr(
        "tracklistify.utils.identification._BEATPORT_REQUEST_INTERVAL", 0
    )
    config = SimpleNamespace(
        enrichment_enabled=True,
        musicbrainz_enabled=False,
        beatport_enabled=enabled,
        min_confidence=0.0,
        time_threshold=0.0,
        segment_length=60,
        overlap_duration=10,
    )
    return IdentificationManager(
        config=config, provider_factory=_BPFactory(provider), cache=object()
    )


@pytest.mark.asyncio
async def test_disabled_makes_no_calls(monkeypatch):
    provider = _FakeBeatportProvider(search_results=[_candidate()])
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch, enabled=False)

    await mgr._enrich_tracks([_track()])

    assert provider.isrc_calls == 0 and provider.search_calls == 0
    assert limiter.acquires == 0


@pytest.mark.asyncio
async def test_no_provider_is_a_silent_noop(monkeypatch):
    limiter = _CountingLimiter()
    mgr = _mgr(None, limiter, monkeypatch)
    track = _track()

    await mgr._enrich_tracks([track])

    assert track.metadata == {}
    assert limiter.acquires == 0


@pytest.mark.asyncio
async def test_isrc_path_writes_links_and_dj_metadata(monkeypatch):
    provider = _FakeBeatportProvider(isrc_result=_candidate())
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)
    track = _track(metadata={"isrc": "GBABC1234567"})

    await mgr._enrich_tracks([track])

    md = track.metadata
    assert md["links"]["beatport"] == "https://beatport.com/track/hard-dance/12345"
    assert md["beatport_id"] == "12345"
    assert md["bpm"] == 150
    assert md["key"] == "A Minor"
    assert md["genre"] == "Techno"
    assert md["sub_genre"] == "Peak Time"
    assert md["remixers"] == ["Remixer X"]
    assert md["catalog_number"] == "CAT001"
    assert md["label"] == "Hard Label"
    assert md["beatport_match"] == "isrc"
    assert provider.search_calls == 0  # ISRC hit short-circuits search


@pytest.mark.asyncio
async def test_search_path_accepts_a_matching_candidate(monkeypatch):
    provider = _FakeBeatportProvider(search_results=[_candidate()])
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)
    track = _track()

    await mgr._enrich_tracks([track])

    assert track.metadata["beatport_match"] == "search"
    assert track.metadata["bpm"] == 150


@pytest.mark.asyncio
async def test_gate_rejects_a_wrong_title(monkeypatch):
    """A search hit that isn't the same track must leave it untouched — a
    wrong BPM/key/label presented as fact is worse than no data."""
    provider = _FakeBeatportProvider(
        search_results=[_candidate(title="Completely Different Song")]
    )
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)
    track = _track()

    await mgr._enrich_tracks([track])

    assert track.metadata == {}


@pytest.mark.asyncio
async def test_gate_rejects_a_wrong_artist(monkeypatch):
    provider = _FakeBeatportProvider(search_results=[_candidate(artists=["Someone Else"])])
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)
    track = _track()

    await mgr._enrich_tracks([track])

    assert track.metadata == {}


@pytest.mark.asyncio
async def test_gate_takes_the_first_accepted_candidate_in_rank_order(monkeypatch):
    provider = _FakeBeatportProvider(
        search_results=[
            _candidate(beatport_id="999", title="Wrong Song"),
            _candidate(beatport_id="12345"),
        ]
    )
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)
    track = _track()

    await mgr._enrich_tracks([track])

    assert track.metadata["beatport_id"] == "12345"


@pytest.mark.asyncio
async def test_mix_name_variant_still_matches(monkeypatch):
    """Beatport splits name/mix_name; '(Original Mix)' is a non-distinguishing
    suffix that _comparison_title already folds away."""
    provider = _FakeBeatportProvider(
        search_results=[_candidate(title="Hard Dance", mix_name="Club Mix")]
    )
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)
    track = _track(song_name="Hard Dance (Club Mix)")

    await mgr._enrich_tracks([track])

    assert track.metadata["beatport_match"] == "search"


@pytest.mark.asyncio
async def test_existing_beatport_link_is_not_overwritten(monkeypatch):
    """First-writer-wins per link key: a MusicBrainz-resolved URL survives,
    but the DJ metadata is still written (no other source supplies it)."""
    provider = _FakeBeatportProvider(search_results=[_candidate()])
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)
    track = _track(metadata={"links": {"beatport": "https://beatport.com/mb-set"}})

    await mgr._enrich_tracks([track])

    assert track.metadata["links"]["beatport"] == "https://beatport.com/mb-set"
    assert track.metadata["bpm"] == 150


@pytest.mark.asyncio
async def test_existing_label_is_not_overwritten(monkeypatch):
    provider = _FakeBeatportProvider(search_results=[_candidate()])
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)
    track = _track(metadata={"label": "Shazam Label"})

    await mgr._enrich_tracks([track])

    assert track.metadata["label"] == "Shazam Label"


@pytest.mark.asyncio
async def test_limiter_is_paired_and_outcomes_recorded(monkeypatch):
    provider = _FakeBeatportProvider(search_results=[_candidate()])
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)

    await mgr._enrich_tracks([_track(), _track(song_name="Other Song")])

    assert limiter.acquires == limiter.releases == 2
    assert all(p == "beatport" for p, _ in limiter.results)
    assert len(limiter.results) == 2


@pytest.mark.asyncio
async def test_rate_limiter_rejection_does_not_call_the_provider(monkeypatch):
    provider = _FakeBeatportProvider(search_results=[_candidate()])
    limiter = _CountingLimiter(acquire_ok=False)
    mgr = _mgr(provider, limiter, monkeypatch)

    await mgr._enrich_tracks([_track()])

    assert provider.search_calls == 0
    assert limiter.releases == 0  # nothing was acquired


@pytest.mark.asyncio
async def test_authentication_error_disables_the_pass_for_the_run(monkeypatch):
    provider = _FakeBeatportProvider(search_results=[_candidate()])
    provider.exc = AuthenticationError("bad token")
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)

    await mgr._enrich_tracks([_track(), _track(song_name="B"), _track(song_name="C")])

    assert provider.search_calls == 1  # stopped after the first failure
    assert limiter.acquires == limiter.releases == 1


@pytest.mark.asyncio
async def test_rate_limit_error_stops_but_keeps_earlier_work(monkeypatch):
    provider = _FakeBeatportProvider(search_results=[_candidate()])
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)
    first, second = _track(), _track(song_name="B")

    await mgr._enrich_beatport([first])
    provider.exc = RateLimitError("429")
    await mgr._enrich_beatport([second])

    assert first.metadata["bpm"] == 150
    assert second.metadata == {}


@pytest.mark.asyncio
async def test_a_raising_provider_never_fails_the_run(monkeypatch):
    provider = _FakeBeatportProvider(search_results=[_candidate()])
    provider.exc = RuntimeError("boom")
    limiter = _CountingLimiter()
    mgr = _mgr(provider, limiter, monkeypatch)
    track = _track()

    await mgr._enrich_tracks([track])  # must not raise

    assert track.metadata == {}
    assert limiter.results == [("beatport", False)]
```

- [ ] **Step 2: Run it, verify it fails correctly**

```bash
uv run python -m pytest tests/test_beatport_enrichment.py -v
```
Expected: FAIL — `AttributeError: module
'tracklistify.utils.identification' has no attribute
'_BEATPORT_REQUEST_INTERVAL'` on the monkeypatch, then missing
`_enrich_beatport`. Not an import error.

- [ ] **Step 3: Minimal implementation**

In `src/tracklistify/utils/identification.py`, extend the imports:

```python
from tracklistify.core.track import Track, TrackMatcher, _artists_match, _comparison_title
```

Add next to `_MUSICBRAINZ_REQUEST_INTERVAL`:

```python
# Beatport publishes no official rate limit; community guidance is ~500ms
# between requests. Explicit spacing, for the same reason MusicBrainz needs it:
# the token bucket seeds full, so the limiter alone permits a burst.
_BEATPORT_REQUEST_INTERVAL = 0.5
```

Add the module-level gate helper, above `IdentificationManager`:

```python
def _beatport_candidate_matches(track: Track, candidate: Dict[str, Any]) -> bool:
    """True when a Beatport search candidate is the same track.

    Beatport search is fuzzy text matching, so an ungated hit would attach a
    confident-looking BPM, key and label from the wrong record — the failure
    mode unknown U3 exists to make auditable. The gate reuses the dedup
    identity helpers so "same title" and "same artist" have exactly one
    definition in this codebase: ``_comparison_title`` already folds away
    non-distinguishing suffixes like ``(Original Mix)`` and canonicalizes
    ``feat.`` spellings.

    Beatport splits a title into ``title`` plus a separate ``mix_name``, so
    the comparison title is rebuilt in the bracketed form our own titles use —
    except for "Original Mix", which is Beatport's default for "no mix name"
    and carries no information.
    """
    title = candidate.get("title")
    if not title:
        return False
    mix_name = candidate.get("mix_name")
    if mix_name and mix_name != "Original Mix":
        title = f"{title} ({mix_name})"

    if _comparison_title(title) != _comparison_title(track.song_name):
        return False

    artists = candidate.get("artists") or []
    return _artists_match(", ".join(artists), track.artist)
```

Extend `_enrich_tracks`, after the MusicBrainz block:

```python
        if getattr(self.config, "beatport_enabled", False):
            await self._enrich_beatport(unique_tracks)
```

and add the two methods after `_enrich_one_mb`:

```python
    async def _enrich_beatport(self, unique_tracks: List[Track]) -> None:
        """Beatport enrichment pass — links plus DJ metadata.

        Runs last of the three sources. Unlike the other two it is opt-in
        (``beatport_enabled``, default false): Beatport has no self-serve API
        tier, so it needs a personal account and a client ID the user supplies
        themselves.

        A track that already carries ``links.beatport`` (MusicBrainz resolved
        it) is still queried — the API call is what supplies BPM, key and
        label; the URL is the cheap part.
        """
        get_bp = getattr(self.provider_factory, "get_beatport_provider", None)
        provider = get_bp() if get_bp is not None else None
        if provider is None:
            # No credentials — a skip, not an error. Never touch the limiter.
            logger.debug("Beatport enrichment skipped: no credentials configured")
            return

        limiter = get_global_rate_limiter()
        counts = {"isrc": 0, "search": 0, "none": 0}

        async with provider:
            for track in unique_tracks:
                match = await self._enrich_one_beatport(provider, limiter, track)
                if match == "disabled":
                    break
                if match in counts:
                    counts[match] += 1
                # Polite inter-request spacing (Beatport documents no limit).
                await asyncio.sleep(_BEATPORT_REQUEST_INTERVAL)

        matched = counts["isrc"] + counts["search"]
        if matched:
            logger.info(
                f"Beatport enrichment: {matched} tracks matched "
                f"(isrc={counts['isrc']}, search={counts['search']}, "
                f"none={counts['none']})"
            )

    async def _enrich_one_beatport(self, provider, limiter, track: Track) -> str:
        """Enrich one track via Beatport; return the match kind or sentinel.

        Returns ``"isrc"`` / ``"search"`` / ``"none"``, or ``"disabled"`` when
        an AuthenticationError or RateLimitError has halted the pass for the
        rest of the run (the caller breaks its loop on that sentinel).

        Acquire/release pairing and outcome reporting are verbatim from the
        Spotify and MusicBrainz passes (invariant I6).
        """
        acquired = False
        try:
            acquired = await limiter.acquire("beatport")
            if not acquired:
                logger.debug("Beatport enrichment: rate limiter rejected request")
                return "none"

            isrc = track.metadata.get("isrc")
            try:
                result = {}
                match_kind = "none"
                if isrc:
                    result = await provider.lookup_isrc(isrc)
                    if result:
                        match_kind = "isrc"
                if not result:
                    candidates = await provider.search_tracks(
                        title=track.song_name, artist=track.artist
                    )
                    for candidate in candidates:
                        if _beatport_candidate_matches(track, candidate):
                            result = candidate
                            match_kind = "search"
                            break
            except AuthenticationError:
                logger.warning(
                    "Beatport enrichment disabled for this run: authentication "
                    "failed. Check TRACKLISTIFY_BEATPORT_CLIENT_ID and either "
                    "_USERNAME/_PASSWORD or a fresh _TOKEN."
                )
                limiter.record_result("beatport", success=False)
                return "disabled"
            except RateLimitError:
                logger.warning(
                    "Beatport enrichment stopped: rate limit hit; tracks "
                    "enriched so far are kept"
                )
                limiter.record_result("beatport", success=False)
                return "disabled"
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.debug(f"Beatport enrichment failed for one track: {e}")
                limiter.record_result("beatport", success=False)
                return "none"

            limiter.record_result("beatport", success=True)
            if not result:
                return "none"

            self._apply_beatport_metadata(track, result, match_kind)
            return match_kind
        finally:
            if acquired:
                limiter.release("beatport")

    @staticmethod
    def _apply_beatport_metadata(
        track: Track, result: Dict[str, Any], match_kind: str
    ) -> None:
        """Write a matched Beatport record onto a Track.

        Three write policies, deliberately different:
        * ``links.beatport`` — first-writer-wins (a MusicBrainz-resolved URL
          survives), consistent with every other link key;
        * ``label`` / ``release_date`` — only when absent, because Shazam may
          already have supplied them and its value is the identification's own;
        * everything else — written unconditionally, because no other source
          in the pipeline supplies BPM, key, genre, remixers or catalog number.
        """
        if result.get("url"):
            track.metadata.setdefault("links", {}).setdefault(
                "beatport", result["url"]
            )
        for key in ("label", "release_date"):
            if result.get(key) and not track.metadata.get(key):
                track.metadata[key] = result[key]
        for key in (
            "beatport_id",
            "bpm",
            "key",
            "genre",
            "sub_genre",
            "remixers",
            "catalog_number",
        ):
            if result.get(key):
                track.metadata[key] = result[key]
        track.metadata["beatport_match"] = match_kind
```

- [ ] **Step 4: Run tests, verify pass + no regressions vs baseline**

```bash
uv run python -m pytest tests/test_beatport_enrichment.py -v
uv run python -m pytest tests/test_spotify_enrichment.py tests/test_musicbrainz_enrichment.py \
  tests/test_identification_utils.py -q      # the two shipped passes are untouched
uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/
uv run python -m pytest -q
```
Expected: 16 new PASS, shipped enrichment tests unchanged, full suite =
baseline + 42 new.

- [ ] **Step 5: Commit**

```bash
git add src/tracklistify/utils/identification.py tests/test_beatport_enrichment.py
git commit -m "feat(enrichment): Beatport links + BPM/key/label pass"
```

---

### Task 6: Live probe, measurements, backlog close-out

This task is **manual and requires real credentials**; it cannot run in CI or
in a sandbox. It resolves U11–U13 and is the only place the spec's success
criteria are actually checked.

**Files:**
- Modify: `docs/BACKLOG.md` (U11–U13 rows + the Fixed table entry)
- Modify: `docs/CHANGELOG.md` (via `uv run cz changelog --incremental` — never
  `cz bump`'s full regeneration; see CLAUDE.md)

- [ ] **Step 1: Configure credentials locally**

In a local `.env` (never committed):

```bash
TRACKLISTIFY_BEATPORT_ENABLED=true
TRACKLISTIFY_BEATPORT_CLIENT_ID=<from devtools on api.beatport.com/v4/docs/>
TRACKLISTIFY_BEATPORT_USERNAME=<your beatport account>
TRACKLISTIFY_BEATPORT_PASSWORD=<your beatport password>
```

- [ ] **Step 2: Probe U11 — does `?isrc=` actually filter?**

Run one real mix with `--debug` and grep the log:

```bash
uv run tracklistify --debug <a mix whose tracks have ISRCs> 2>&1 | tee /tmp/bp-run.log
grep -c "returned a different ISRC" /tmp/bp-run.log
```
Interpretation: near-zero mismatch lines with `beatport_match: "isrc"` in the
JSON ⇒ the filter works (U11 = yes). A mismatch line for essentially every
ISRC ⇒ the filter is ignored (U11 = no) and every match arrives via gated
search — no code change, but record it so nobody re-derives it.

- [ ] **Step 3: Measure U12 — match rate**

From the run's `tracklist.json`:

```bash
python - <<'PY'
import json, collections, sys, pathlib
p = sorted(pathlib.Path("output").rglob("tracklist.json"))[-1]
tracks = json.loads(p.read_text())["tracks"]
c = collections.Counter(t.get("metadata", {}).get("beatport_match", "none") for t in tracks)
print(p, dict(c), f"{(len(tracks)-c['none'])/len(tracks):.0%} matched")
PY
```

- [ ] **Step 4: Measure U13 — token lifetime**

Read `expires_at` out of the token cache and check whether a second run
minutes later re-authenticates:

```bash
python -c "import json,time;d=json.load(open('.tracklistify/cache/beatport_token.json'));print('valid for', round((d['expires_at']-time.time())/3600, 1), 'h')"
```

- [ ] **Step 5: Verify the spec's success criteria**

Open two or three matched tracks' `links.beatport` URLs and confirm each
resolves to the track actually playing at that timestamp, and that the BPM
matches the audio. A wrong match here means the gate in Task 5 is too loose —
that is a backward loop to the spec, not a test fix.

- [ ] **Step 6: Record and commit**

Add U11/U12/U13 rows to the "Open unknowns" table with the measured answers,
move the P3 Beatport item into the "Fixed" section with a
fix/where/test table like the MusicBrainz entry, and note explicitly what is
verified by live run rather than by unit test (the 0.5 s pacing and the ISRC
filter behavior).

```bash
uv run cz changelog --incremental
git add docs/BACKLOG.md docs/CHANGELOG.md
git commit -m "docs(backlog): close P3 Beatport; record U11-U13 measurements"
```

---

## Plan self-review

**1. Spec coverage.**

| Spec req | Task |
| --- | --- |
| R1 default off, zero calls | 1 (config default), 5 (`test_disabled_makes_no_calls`) |
| R2 no creds → debug + return | 4 (factory returns None), 5 (`test_no_provider_is_a_silent_noop`) |
| R3 token from either path | 2 (password flow, pasted token, cache) |
| R4 fields + provenance | 3 (`_extract`), 5 (`_apply_beatport_metadata`) |
| R5 acceptance gate | 5 (`_beatport_candidate_matches`, 4 gate tests) |
| R6 first-writer-wins on the link | 5 (`test_existing_beatport_link_is_not_overwritten`) |
| R7 best-effort | 5 (`test_a_raising_provider_never_fails_the_run`), 2 (corrupt cache) |
| R8 limiter pairing | 5 (`test_limiter_is_paired_and_outcomes_recorded`) |
| R9 secrets env-only, unlogged | 1 (`test_beatport_secrets_are_not_config_fields`), 2 (`test_secrets_never_appear_in_logs`), 4 (env-only reads) |
| R10 offline suite | every test mocks the session; Task 6 is the only live step and is manual |
| §5.5 pacing | 1 (limiter branch), 5 (`_BEATPORT_REQUEST_INTERVAL`) |
| §5.6 ordering | 5 (`_enrich_tracks` appends the pass last) |
| §6 config surface + env drift | 1 |
| §9 U11–U13 | 6 |

No requirement is unassigned.

**2. Placeholder scan.** No TBD/TODO, no "handle edge cases", no "similar to
Task N", no test described without its code. Task 6's steps are manual by
necessity and each names the exact command and the interpretation rule.

**3. Type consistency.** `lookup_isrc` returns `Dict` and `search_tracks`
returns `List[Dict]` in Task 3, and Task 5 consumes exactly those shapes. The
`_extract` key set in Task 3 matches the keys read in Task 5's
`_apply_beatport_metadata` and `_beatport_candidate_matches`
(`title`/`mix_name`/`artists`/`url`/`bpm`/`key`/`label`/`genre`/`sub_genre`/
`remixers`/`catalog_number`/`release_date`/`isrc`/`beatport_id`). The factory
constructor call in Task 4 matches the `__init__` signature in Task 2
(`client_id`, `username`, `password`, `token`, `token_path`).
`_BEATPORT_ENRICHMENT_KEY` is used consistently in Task 4's code and test.
