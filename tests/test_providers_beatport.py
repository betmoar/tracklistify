"""Tests for BeatportProvider — auth flow, token cache, error posture.

Mocks the aiohttp session; never hits the network.
"""

import json
import os
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

    # NTFS has ACLs, not POSIX mode bits: CPython's Path.chmod only toggles
    # the read-only flag there, so st_mode comes back 0o666 no matter what
    # the source asked for. The 0600 on the token cache is still the point
    # of the test on the platforms where the bits mean something (#85).
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.asyncio
async def test_cached_token_skips_login(tmp_path):
    path = tmp_path / "beatport_token.json"
    path.write_text(
        json.dumps(
            {
                "access_token": "CACHED",
                "refresh_token": "R",
                "expires_at": time.time() + 9999,
            }
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
async def test_non_numeric_expires_at_is_a_miss_not_a_crash(tmp_path):
    """A cache file whose expires_at isn't a number (hand-edited, partially
    corrupt) must be a miss, not a ValueError on every track. _load_cached_token
    documents 'never raises' — the type check enforces it at the source."""
    path = tmp_path / "beatport_token.json"
    path.write_text(
        json.dumps(
            {"access_token": "CACHED", "refresh_token": "R", "expires_at": "soon"}
        )
    )
    session = _FakeSession(
        posts=[
            _FakeResponse(200, {"username": "dj", "email": "e@x.com"}),
            _FakeResponse(
                200, {"access_token": "FRESH", "refresh_token": "R", "expires_in": 3600}
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
        json.dumps(
            {"access_token": "OLD", "refresh_token": "", "expires_at": time.time() + 5}
        )
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
async def test_authorize_without_code_raises_authentication_error(tmp_path):
    """A redirect with no auth code means the client_id/redirect_uri was
    rejected — a config problem, not a transient blip. It must surface as
    AuthenticationError so the enrichment hook disables the whole pass instead
    of re-running the full OAuth dance once per track."""
    session = _FakeSession(
        posts=[_FakeResponse(200, {"username": "dj", "email": "e@x.com"})],
        gets=[_FakeResponse(302, headers={"Location": "/post-message/"})],
    )
    provider = _provider(tmp_path, session, username="dj", password="pw")
    with pytest.raises(AuthenticationError):
        await provider._authenticate()


@pytest.mark.asyncio
async def test_authorize_5xx_is_a_provider_error(tmp_path):
    """A transient server failure during authorize must NOT disable the whole
    pass — only AuthenticationError does that. Mirror of the login-5xx rule."""
    session = _FakeSession(
        posts=[_FakeResponse(200, {"username": "dj", "email": "e@x.com"})],
        gets=[_FakeResponse(503)],
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
                {
                    "access_token": "AT-SECRET",
                    "refresh_token": "RT-SECRET",
                    "expires_in": 3600,
                },
            ),
        ],
        gets=[_FakeResponse(302, headers={"Location": "?code=CODE-SECRET"})],
    )
    provider = _provider(tmp_path, session, username="djsecret", password="pw-secret")
    await provider._authenticate()

    text = caplog.text
    for secret in (
        "pw-secret",
        "AT-SECRET",
        "RT-SECRET",
        "CODE-SECRET",
        "cid",
        "djsecret",
        "me@example.com",
    ):
        assert secret not in text


@pytest.mark.asyncio
async def test_close_is_reentrant(tmp_path):
    session = _FakeSession()
    provider = _provider(tmp_path, session)
    await provider.close()
    await provider.close()
    assert session.closed is True


@pytest.mark.asyncio
async def test_rate_limit_during_login_raises_rate_limit_error(tmp_path):
    """A 429 during login carries the Retry-After header into the error so the
    caller can honor it (not just the flat 60s default)."""
    session = _FakeSession(posts=[_FakeResponse(429, headers={"Retry-After": "17"})])
    provider = _provider(tmp_path, session, username="dj", password="pw")
    with pytest.raises(RateLimitError) as excinfo:
        await provider._authenticate()
    assert excinfo.value.retry_after == 17


@pytest.mark.asyncio
async def test_rate_limit_during_token_exchange_carries_retry_after(tmp_path):
    session = _FakeSession(
        posts=[
            _FakeResponse(200, {"username": "dj", "email": "e@x.com"}),
            _FakeResponse(429, headers={"Retry-After": "23"}),
        ],
        gets=[_FakeResponse(302, headers={"Location": "?code=C"})],
    )
    provider = _provider(tmp_path, session, username="dj", password="pw")
    with pytest.raises(RateLimitError) as excinfo:
        await provider._authenticate()
    assert excinfo.value.retry_after == 23


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
    assert out["url"] == "https://www.beatport.com/track/hard-dance/12345"
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
    session = _FakeSession(gets=[_FakeResponse(200, {"results": [_track_json()]})])
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
                {
                    "tracks": [
                        _track_json(id=1, name="First"),
                        _track_json(id=2, name="Second"),
                    ]
                },
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


@pytest.mark.asyncio
async def test_non_numeric_retry_after_falls_back_to_a_default(tmp_path):
    """Retry-After may be an HTTP date, not seconds. int() on that raises,
    which the hook would swallow as a per-track miss — so a real 429 would
    stop disabling the pass and we would keep hammering a limited API."""
    session = _FakeSession(
        gets=[
            _FakeResponse(429, headers={"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"})
        ]
    )
    provider = _provider(tmp_path, session, token="T")
    with pytest.raises(RateLimitError) as excinfo:
        await provider.search_tracks("x", "y")
    assert excinfo.value.retry_after == 60


@pytest.mark.asyncio
async def test_missing_retry_after_falls_back_to_a_default(tmp_path):
    session = _FakeSession(gets=[_FakeResponse(429)])
    provider = _provider(tmp_path, session, token="T")
    with pytest.raises(RateLimitError) as excinfo:
        await provider.search_tracks("x", "y")
    assert excinfo.value.retry_after == 60


@pytest.mark.asyncio
async def test_login_5xx_is_a_provider_error_not_bad_credentials(tmp_path):
    """A server-side failure during login must not be reported as (and must
    not be treated as) rejected credentials: AuthenticationError disables the
    pass for the whole run, which is wrong for a transient 503."""
    session = _FakeSession(posts=[_FakeResponse(503)])
    provider = _provider(tmp_path, session, username="dj", password="pw")
    with pytest.raises(ProviderError):
        await provider._authenticate()


@pytest.mark.asyncio
async def test_login_401_is_an_authentication_error(tmp_path):
    """A 4xx from the login endpoint really is a credentials problem."""
    session = _FakeSession(posts=[_FakeResponse(401)])
    provider = _provider(tmp_path, session, username="dj", password="pw")
    with pytest.raises(AuthenticationError):
        await provider._authenticate()


@pytest.mark.asyncio
async def test_token_exchange_5xx_is_a_provider_error(tmp_path):
    session = _FakeSession(
        posts=[
            _FakeResponse(200, {"username": "dj", "email": "e@x.com"}),
            _FakeResponse(503),
        ],
        gets=[_FakeResponse(302, headers={"Location": "?code=C"})],
    )
    provider = _provider(tmp_path, session, username="dj", password="pw")
    with pytest.raises(ProviderError):
        await provider._authenticate()


# ---- refresh-token grant -------------------------------------------------
# The docs client supports refresh (the storefront client does not). A cached
# token that has expired is renewed from its refresh_token without re-login.


@pytest.mark.asyncio
async def test_refresh_flow_renews_an_expired_cached_token(tmp_path):
    """An expired cache entry with a refresh_token is renewed via the
    refresh grant — the common path on every run after the first."""
    path = tmp_path / "beatport_token.json"
    path.write_text(
        json.dumps(
            {
                "access_token": "OLD",
                "refresh_token": "RT",
                "expires_at": time.time() - 60,  # already expired
            }
        )
    )
    session = _FakeSession(
        posts=[
            _FakeResponse(
                200, {"access_token": "NEW", "refresh_token": "RT2", "expires_in": 3600}
            )
        ],
    )
    provider = _provider(tmp_path, session)

    token = await provider._authenticate()

    assert token == "NEW"
    # Refresh hit the token endpoint with grant_type=refresh_token.
    assert session.post_calls[0][0].endswith("/auth/o/token/")
    assert session.post_calls[0][1]["params"]["grant_type"] == "refresh_token"
    assert session.post_calls[0][1]["params"]["refresh_token"] == "RT"
    # The rotated refresh_token is adopted and re-cached.
    assert provider._refresh_token == "RT2"
    cached = json.loads(path.read_text())
    assert cached["access_token"] == "NEW"
    assert cached["refresh_token"] == "RT2"


@pytest.mark.asyncio
async def test_refresh_failure_falls_back_to_password(tmp_path):
    """A dead refresh_token (invalid_grant) falls through to a full re-login
    rather than disabling the pass."""
    path = tmp_path / "beatport_token.json"
    path.write_text(
        json.dumps(
            {
                "access_token": "OLD",
                "refresh_token": "DEAD-RT",
                "expires_at": time.time() - 60,
            }
        )
    )
    session = _FakeSession(
        posts=[
            _FakeResponse(400, {"error": "invalid_grant"}),  # refresh rejected
            _FakeResponse(200, {"username": "dj", "email": "e@x.com"}),  # login
            _FakeResponse(
                200,
                {"access_token": "FRESH", "refresh_token": "RT", "expires_in": 3600},
            ),
        ],
        gets=[_FakeResponse(302, headers={"Location": "?code=C"})],
    )
    provider = _provider(tmp_path, session, username="dj", password="pw")

    assert await provider._authenticate() == "FRESH"


@pytest.mark.asyncio
async def test_resolve_client_id_scrapes_from_docs_js(tmp_path):
    """With no client_id supplied, the provider scrapes API_CLIENT_ID from the
    docs page's JS bundle (it rotates, so scraping beats hardcoding)."""
    docs_html = '<script src="/static/btprt/abc.js"></script>'
    js_bundle = "var x = 1; API_CLIENT_ID: 'SCRAPED-CID'; var y = 2;"

    class _ScrapeSession:
        """GET returns a _FakeResponse context manager (like _FakeSession)."""

        def __init__(self):
            self.calls = []

        def get(self, url, **kwargs):
            self.calls.append(url)
            if url.endswith("/docs/"):
                return _FakeResponse(200, body=docs_html)
            if url.endswith("abc.js"):
                return _FakeResponse(200, body=js_bundle)
            return _FakeResponse(404)

    provider = BeatportProvider(client_id=None, token_path=tmp_path / "t.json")
    provider._session = _ScrapeSession()

    resolved = await provider._resolve_client_id()

    assert resolved == "SCRAPED-CID"
    assert any(u.endswith("/docs/") for u in provider._session.calls)


# ---- _json_or_none: clean miss vs transport failure ----------------------


@pytest.mark.asyncio
async def test_json_or_none_returns_none_on_parse_failure(tmp_path):
    """A body that isn't JSON (HTML error page with a 200) is a clean miss."""

    class _NotJson:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def json(self):
            raise json.JSONDecodeError("no", "doc", 0)

    assert await BeatportProvider._json_or_none(_NotJson()) is None


@pytest.mark.asyncio
async def test_json_or_none_raises_provider_error_on_transport_failure(tmp_path):
    """A transport failure (connection reset, truncated body) is NOT a clean
    miss — it must surface as ProviderError, not silently return None and be
    misreported downstream as a credentials rejection."""

    class _TransportError:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def json(self):
            raise ConnectionResetError("pipe broken")

    with pytest.raises(ProviderError):
        await BeatportProvider._json_or_none(_TransportError())
