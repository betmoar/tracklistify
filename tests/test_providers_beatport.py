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
    session = _FakeSession(posts=[_FakeResponse(429)])
    provider = _provider(tmp_path, session, username="dj", password="pw")
    with pytest.raises(RateLimitError):
        await provider._authenticate()
