"""Tests for P1: wiring the cache into IdentificationManager.identify_tracks.

Design (per docs/BACKLOG.md P1):
- Cache key is ``f"{provider_name}:{sha256(segment_file_bytes)}"`` — content-
  addressed, since temp segment paths differ per run.
- Before each provider's network call, consult the cache; on hit, use the
  cached provider response and skip the call.
- After a provider returns a usable (non-None) response, store it.
- All cache I/O is best-effort: failures degrade to live identification,
  never abort the run.
- Gated by ``config.cache_enabled``.
"""

import hashlib

import pytest

from tracklistify.core.types import AudioSegment

# ---------------------------------------------------------------------------
# Stubs — mirror the pattern in tests/test_handoff_invariants.py so the
# cache tests exercise IdentificationManager through the same shape.
# ---------------------------------------------------------------------------


class _StubProvider:
    """Minimal TrackIdentificationProvider stand-in."""

    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = 0

    async def identify_track(self, segment):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.response

    async def close(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()


class _StubFactory:
    def __init__(self, providers):
        self._providers = providers

    def get_identification_provider(self, name):
        return self._providers[name]

    async def close_all(self):
        pass


def _match(title="Cached Song", score=90):
    return {
        "metadata": {
            "music": [{"title": title, "artists": [{"name": "A"}], "score": score}]
        }
    }


class _FakeCache:
    """In-memory cache double.

    - ``hit``: if not None, every ``get()`` returns this value.
    - Otherwise behaves as an empty cache (all gets miss).
    Records all get/set calls for assertions.
    """

    def __init__(self, hit=None, fail_get=False, fail_set=False):
        self._hit = hit
        self._fail_get = fail_get
        self._fail_set = fail_set
        self.get_calls = []
        self.set_calls = []

    async def get(self, key):
        self.get_calls.append(key)
        if self._fail_get:
            raise RuntimeError("cache get exploded")
        return self._hit

    async def set(self, key, value, **kwargs):
        self.set_calls.append((key, value))
        if self._fail_set:
            raise RuntimeError("cache set exploded")


def _make_manager(monkeypatch, providers, cache=None):
    from tracklistify.config import get_config
    from tracklistify.utils import rate_limiter as rl
    from tracklistify.utils.identification import IdentificationManager
    import tracklistify.utils.identification as ident_mod

    # Fresh RateLimiter so circuit-breaker state doesn't bleed between tests.
    monkeypatch.setattr(
        rl, "get_global_rate_limiter", lambda force_refresh=False: rl.RateLimiter()
    )
    monkeypatch.setattr(ident_mod, "get_global_rate_limiter", lambda: rl.RateLimiter())

    config = get_config(force_refresh=True)
    config.primary_provider = "primary"
    config.fallback_enabled = False
    config.cache_enabled = True
    return IdentificationManager(
        config=config, provider_factory=_StubFactory(providers), cache=cache
    )


def _expected_key(provider_name: str, segment_bytes: bytes) -> str:
    return f"{provider_name}:{hashlib.sha256(segment_bytes).hexdigest()}"


class TestCacheWiring:
    """P1: cache wired into identify_tracks."""

    @pytest.mark.asyncio
    async def test_cache_hit_skips_provider(self, monkeypatch, tmp_path):
        """A cached identification is used; the provider is never called."""
        seg_file = tmp_path / "seg.wav"
        seg_bytes = b"audio-bytes"
        seg_file.write_bytes(seg_bytes)

        cached = _match("Cached Song")
        cache = _FakeCache(hit=cached)
        primary = _StubProvider(response=_match("Live Song"))
        manager = _make_manager(monkeypatch, {"primary": primary}, cache=cache)

        segments = [AudioSegment(file_path=str(seg_file), start_time=0, duration=60)]
        tracks = await manager.identify_tracks(segments)

        assert primary.calls == 0, "provider must not be called on cache hit"
        assert len(tracks) == 1
        assert tracks[0].song_name == "Cached Song"
        assert len(cache.get_calls) == 1
        assert cache.get_calls[0] == _expected_key("primary", seg_bytes)


class TestCacheMissStoresResult:
    """On a cache miss, the live provider response is stored for next time."""

    @pytest.mark.asyncio
    async def test_miss_stores_live_result(self, monkeypatch, tmp_path):
        seg_file = tmp_path / "seg.wav"
        seg_bytes = b"audio-bytes"
        seg_file.write_bytes(seg_bytes)

        cache = _FakeCache(hit=None)
        primary = _StubProvider(response=_match("Live Song"))
        manager = _make_manager(monkeypatch, {"primary": primary}, cache=cache)

        segments = [AudioSegment(file_path=str(seg_file), start_time=0, duration=60)]
        tracks = await manager.identify_tracks(segments)

        assert primary.calls == 1
        assert len(tracks) == 1
        assert tracks[0].song_name == "Live Song"
        assert len(cache.set_calls) == 1
        key, stored = cache.set_calls[0]
        assert key == _expected_key("primary", seg_bytes)
        assert stored == _match("Live Song")


class TestCacheGatingAndFailure:
    """cache_enabled=False disables the cache; cache I/O failures degrade."""

    @pytest.mark.asyncio
    async def test_disabled_cache_never_touched(self, monkeypatch, tmp_path):
        seg_file = tmp_path / "seg.wav"
        seg_file.write_bytes(b"audio-bytes")

        cache = _FakeCache(hit=_match("Cached Song"))
        primary = _StubProvider(response=_match("Live Song"))

        from tracklistify.config import get_config
        from tracklistify.utils import rate_limiter as rl
        from tracklistify.utils.identification import IdentificationManager
        import tracklistify.utils.identification as ident_mod

        monkeypatch.setattr(
            rl, "get_global_rate_limiter", lambda force_refresh=False: rl.RateLimiter()
        )
        monkeypatch.setattr(
            ident_mod, "get_global_rate_limiter", lambda: rl.RateLimiter()
        )

        config = get_config(force_refresh=True)
        config.primary_provider = "primary"
        config.fallback_enabled = False
        config.cache_enabled = False  # disabled
        manager = IdentificationManager(
            config=config,
            provider_factory=_StubFactory({"primary": primary}),
            cache=cache,
        )

        segments = [AudioSegment(file_path=str(seg_file), start_time=0, duration=60)]
        tracks = await manager.identify_tracks(segments)

        assert primary.calls == 1, "live call must happen when cache disabled"
        assert len(cache.get_calls) == 0, "cache must not be read when disabled"
        assert len(cache.set_calls) == 0, "cache must not be written when disabled"
        assert tracks[0].song_name == "Live Song"

    @pytest.mark.asyncio
    async def test_cache_get_failure_degrades_to_live(self, monkeypatch, tmp_path):
        seg_file = tmp_path / "seg.wav"
        seg_file.write_bytes(b"audio-bytes")

        cache = _FakeCache(fail_get=True)
        primary = _StubProvider(response=_match("Live Song"))
        manager = _make_manager(monkeypatch, {"primary": primary}, cache=cache)

        segments = [AudioSegment(file_path=str(seg_file), start_time=0, duration=60)]
        tracks = await manager.identify_tracks(segments)

        assert primary.calls == 1, "provider must run after cache.get() raises"
        assert len(tracks) == 1
        assert tracks[0].song_name == "Live Song"

    @pytest.mark.asyncio
    async def test_cache_set_failure_does_not_abort(self, monkeypatch, tmp_path):
        seg_file = tmp_path / "seg.wav"
        seg_file.write_bytes(b"audio-bytes")

        cache = _FakeCache(fail_set=True)
        primary = _StubProvider(response=_match("Live Song"))
        manager = _make_manager(monkeypatch, {"primary": primary}, cache=cache)

        segments = [AudioSegment(file_path=str(seg_file), start_time=0, duration=60)]
        tracks = await manager.identify_tracks(segments)

        assert primary.calls == 1
        assert len(tracks) == 1
        assert tracks[0].song_name == "Live Song", "set() failure must not abort run"

    @pytest.mark.asyncio
    async def test_unmatched_response_is_not_cached(self, monkeypatch, tmp_path):
        """A provider response that yields no Track (None / empty music) is
        consulted live next time, not cached as a no-match."""
        seg_file = tmp_path / "seg.wav"
        seg_file.write_bytes(b"audio-bytes")

        cache = _FakeCache(hit=None)
        # Provider returns an empty-music response → _track_from_info → None.
        primary = _StubProvider(response={"metadata": {"music": []}})
        manager = _make_manager(monkeypatch, {"primary": primary}, cache=cache)

        segments = [AudioSegment(file_path=str(seg_file), start_time=0, duration=60)]
        tracks = await manager.identify_tracks(segments)

        assert tracks == []
        assert cache.set_calls == [], "no-match response must not be cached"


class TestCacheKeyIsContentAddressed:
    """Key is sha256 of segment bytes, not the temp file path."""

    @pytest.mark.asyncio
    async def test_same_bytes_different_path_same_key(self, monkeypatch, tmp_path):
        seg_a = tmp_path / "a.wav"
        seg_b = tmp_path / "b.wav"
        seg_a.write_bytes(b"identical-audio")
        seg_b.write_bytes(b"identical-audio")

        cache = _FakeCache(hit=None)
        primary = _StubProvider(response=_match("Live Song"))
        manager = _make_manager(monkeypatch, {"primary": primary}, cache=cache)

        segments = [
            AudioSegment(file_path=str(seg_a), start_time=0, duration=60),
            AudioSegment(file_path=str(seg_b), start_time=60, duration=60),
        ]
        await manager.identify_tracks(segments)

        # Same content → same key, even though paths differ.
        keys = [k for (k, _) in cache.set_calls]
        assert len(keys) == 2
        assert keys[0] == keys[1]

    @pytest.mark.asyncio
    async def test_different_bytes_different_key(self, monkeypatch, tmp_path):
        seg_a = tmp_path / "a.wav"
        seg_b = tmp_path / "b.wav"
        seg_a.write_bytes(b"audio-one")
        seg_b.write_bytes(b"audio-two")

        cache = _FakeCache(hit=None)
        primary = _StubProvider(response=_match("Live Song"))
        manager = _make_manager(monkeypatch, {"primary": primary}, cache=cache)

        segments = [
            AudioSegment(file_path=str(seg_a), start_time=0, duration=60),
            AudioSegment(file_path=str(seg_b), start_time=60, duration=60),
        ]
        await manager.identify_tracks(segments)

        keys = [k for (k, _) in cache.set_calls]
        assert keys[0] != keys[1], "distinct audio must key differently"

    @pytest.mark.asyncio
    async def test_key_includes_provider_name(self, monkeypatch, tmp_path):
        """Same segment bytes, two providers → two distinct keys.

        Only successful matches are cached, so we run two single-provider
        managers over the same bytes and compare the keys each produced.
        """
        seg_file = tmp_path / "seg.wav"
        seg_bytes = b"audio-bytes"
        seg_file.write_bytes(seg_bytes)

        segments = [AudioSegment(file_path=str(seg_file), start_time=0, duration=60)]

        # Run A: primary provider only.
        cache_a = _FakeCache(hit=None)
        mgr_a = _make_manager(
            monkeypatch, {"primary": _StubProvider(response=_match())}, cache=cache_a
        )
        await mgr_a.identify_tracks(segments)

        # Run B: a differently-named provider over the same bytes.
        cache_b = _FakeCache(hit=None)
        # _make_manager hardcodes primary_provider="primary"; override it.
        mgr_b = _make_manager(
            monkeypatch, {"other": _StubProvider(response=_match())}, cache=cache_b
        )
        mgr_b.config.primary_provider = "other"
        await mgr_b.identify_tracks(segments)

        key_a = cache_a.set_calls[0][0]
        key_b = cache_b.set_calls[0][0]
        assert key_a == _expected_key("primary", seg_bytes)
        assert key_b == _expected_key("other", seg_bytes)
        assert key_a != key_b, (
            "same bytes under different providers must key differently"
        )
