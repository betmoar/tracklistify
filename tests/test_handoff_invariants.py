"""Invariant tests from the 2026-07 handoff audit.

Each test class locks one named invariant that the production pipeline
depends on. If one of these fails, something load-bearing broke — read
docs/ARCHITECTURE.md before "fixing" the test.

INVARIANTS COVERED
  I1  Config validation rules are enforced at construction time.
  I2  Segmentation step (segment_length - overlap_duration) is positive,
      both at config load and again inside split_audio (config attrs are
      mutable after load).
  I3  Every provider name in providers.factory.KNOWN_PROVIDERS is
      constructible through the factory, or fails with an actionable
      ConfigError — never a TypeError.
  I4  ACRCloudProvider.identify_track accepts the pipeline's AudioSegment
      (an object with file_path), not just raw bytes.
  I5  Provider fallback: when fallback_enabled and the primary yields
      nothing, fallback providers are tried in order; when disabled, they
      are not.
  I6  Provider failures feed the rate limiter's circuit breaker via
      RateLimiter.record_result.
  I7  Cache TTL expiry works (a set() without explicit ttl inherits the
      cache-level TTL instead of storing None, which disabled expiry).
  I8  Cache index is persisted on every set/delete, so a second process
      (fresh CacheIndex) sees entries written by the first.
"""

import time
from unittest.mock import AsyncMock, patch

import pytest

from tracklistify.core.exceptions import ConfigError
from tracklistify.core.types import AudioSegment


# ---------------------------------------------------------------------------
# I1 / I2 — config validation
# ---------------------------------------------------------------------------


class TestConfigValidationEnforced:
    def _fresh_config(self, monkeypatch, tmp_path, **env):
        for key in ("SEGMENT_LENGTH", "OVERLAP_DURATION", "MIN_CONFIDENCE"):
            monkeypatch.delenv(f"TRACKLISTIFY_{key}", raising=False)
        monkeypatch.setenv("TRACKLISTIFY_OUTPUT_DIR", str(tmp_path / "out"))
        monkeypatch.setenv("TRACKLISTIFY_CACHE_DIR", str(tmp_path / "cache"))
        monkeypatch.setenv("TRACKLISTIFY_TEMP_DIR", str(tmp_path / "temp"))
        monkeypatch.setenv("TRACKLISTIFY_LOG_DIR", str(tmp_path / "log"))
        for key, value in env.items():
            monkeypatch.setenv(f"TRACKLISTIFY_{key}", value)
        from tracklistify.config import get_config

        return get_config(force_refresh=True)

    def test_out_of_range_segment_length_rejected(self, monkeypatch, tmp_path):
        """I1: range rules registered in _setup_validation actually run."""
        with pytest.raises(Exception, match="segment_length"):
            self._fresh_config(monkeypatch, tmp_path, SEGMENT_LENGTH="5000")

    def test_out_of_range_min_confidence_rejected(self, monkeypatch, tmp_path):
        with pytest.raises(Exception, match="min_confidence"):
            self._fresh_config(monkeypatch, tmp_path, MIN_CONFIDENCE="7.5")

    def test_overlap_must_be_smaller_than_segment(self, monkeypatch, tmp_path):
        """I2 (config half): step <= 0 would hang split_audio forever."""
        with pytest.raises(ValueError, match="overlap_duration"):
            self._fresh_config(
                monkeypatch, tmp_path, SEGMENT_LENGTH="20", OVERLAP_DURATION="20"
            )

    def test_valid_config_still_loads(self, monkeypatch, tmp_path):
        cfg = self._fresh_config(
            monkeypatch, tmp_path, SEGMENT_LENGTH="120", OVERLAP_DURATION="10"
        )
        assert cfg.segment_length == 120


class TestSplitAudioStepGuard:
    def test_split_audio_refuses_non_positive_step(self, monkeypatch, tmp_path):
        """I2 (runtime half): guard fires even when config is mutated
        after construction, which validation can't see."""
        monkeypatch.setenv("TRACKLISTIFY_TEMP_DIR", str(tmp_path))
        from tracklistify.config import get_config
        from tracklistify.core.base import AsyncApp

        config = get_config(force_refresh=True)
        app = AsyncApp(config)
        app.config.segment_length = 10
        app.config.overlap_duration = 10  # step == 0
        with pytest.raises(ValueError, match="non-positive step"):
            app.split_audio(str(tmp_path / "whatever.mp3"), duration_hint=60.0)


# ---------------------------------------------------------------------------
# I3 / I4 — provider construction and pipeline compatibility
# ---------------------------------------------------------------------------


class TestProviderFactoryInvariants:
    def test_all_known_providers_construct_or_config_error(self, monkeypatch):
        """I3: `-p <name>` must never die with a bare TypeError."""
        monkeypatch.delenv("TRACKLISTIFY_ACR_ACCESS_KEY", raising=False)
        monkeypatch.delenv("TRACKLISTIFY_ACR_ACCESS_SECRET", raising=False)
        from tracklistify.providers.factory import KNOWN_PROVIDERS, ProviderFactory

        for name in KNOWN_PROVIDERS:
            factory = ProviderFactory()
            try:
                provider = factory.get_identification_provider(name)
                assert provider is not None
            except ConfigError as e:
                # Acceptable: missing credentials, with an actionable message.
                assert "TRACKLISTIFY_" in str(e), (
                    f"ConfigError for {name!r} must name the env vars to set"
                )

    def test_acrcloud_constructs_with_credentials(self, monkeypatch):
        monkeypatch.setenv("TRACKLISTIFY_ACR_ACCESS_KEY", "test-key")
        monkeypatch.setenv("TRACKLISTIFY_ACR_ACCESS_SECRET", "test-secret")
        from tracklistify.providers.factory import ProviderFactory

        provider = ProviderFactory().get_identification_provider("acrcloud")
        assert provider.access_key == "test-key"

    def test_unknown_provider_names_known_ones(self):
        from tracklistify.providers.factory import ProviderFactory

        with pytest.raises(ValueError, match="shazam"):
            ProviderFactory().get_identification_provider("nope")

    @pytest.mark.asyncio
    async def test_acrcloud_identify_accepts_audio_segment(self, tmp_path):
        """I4: the pipeline passes AudioSegment, not bytes."""
        from tracklistify.providers.acrcloud import ACRCloudProvider

        audio_file = tmp_path / "seg.mp3"
        audio_file.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 100)
        segment = AudioSegment(file_path=str(audio_file), start_time=0, duration=60)

        provider = ACRCloudProvider(access_key="k", access_secret="s")
        captured = {}

        class FakeResponse:
            status = 200

            async def text(self):
                return (
                    '{"status": {"code": 0, "msg": "ok"}, "metadata": {"music": '
                    '[{"title": "Song", "artists": [{"name": "Artist"}], '
                    '"score": 95}]}}'
                )

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

        class FakeSession:
            def post(self, url, data=None):
                captured["posted"] = True
                return FakeResponse()

        provider._get_session = AsyncMock(return_value=FakeSession())
        result = await provider.identify_track(segment)
        assert captured.get("posted"), "identify_track never reached the API call"
        assert result["metadata"]["music"][0]["title"] == "Song"


# ---------------------------------------------------------------------------
# I5 / I6 — fallback chain and circuit-breaker wiring
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


def _match(title="Fallback Song"):
    return {
        "metadata": {
            "music": [{"title": title, "artists": [{"name": "A"}], "score": 90}]
        }
    }


class TestFallbackChain:
    def _manager(self, monkeypatch, providers, fallback_enabled):
        from tracklistify.config import get_config
        from tracklistify.utils.identification import IdentificationManager
        from tracklistify.utils import rate_limiter as rl

        monkeypatch.setattr(
            rl, "get_global_rate_limiter", lambda force_refresh=False: rl.RateLimiter()
        )
        # identification.py imported the symbol directly; patch there too.
        import tracklistify.utils.identification as ident_mod

        monkeypatch.setattr(
            ident_mod, "get_global_rate_limiter", lambda: rl.RateLimiter()
        )

        config = get_config(force_refresh=True)
        config.primary_provider = "primary"
        config.fallback_enabled = fallback_enabled
        config.fallback_providers = ["backup"]
        return IdentificationManager(
            config=config, provider_factory=_StubFactory(providers)
        )

    @pytest.mark.asyncio
    async def test_fallback_used_when_primary_returns_nothing(self, monkeypatch):
        """I5: primary miss -> fallback provider is consulted."""
        primary = _StubProvider(response=None)
        backup = _StubProvider(response=_match())
        manager = self._manager(
            monkeypatch, {"primary": primary, "backup": backup}, fallback_enabled=True
        )
        segments = [AudioSegment(file_path="x", start_time=0, duration=60)]
        tracks = await manager.identify_tracks(segments)
        assert backup.calls == 1
        assert len(tracks) == 1 and tracks[0].song_name == "Fallback Song"

    @pytest.mark.asyncio
    async def test_fallback_not_used_when_disabled(self, monkeypatch):
        primary = _StubProvider(response=None)
        backup = _StubProvider(response=_match())
        manager = self._manager(
            monkeypatch, {"primary": primary, "backup": backup}, fallback_enabled=False
        )
        segments = [AudioSegment(file_path="x", start_time=0, duration=60)]
        tracks = await manager.identify_tracks(segments)
        assert backup.calls == 0
        assert tracks == []

    @pytest.mark.asyncio
    async def test_fallback_skipped_when_primary_matches(self, monkeypatch):
        primary = _StubProvider(response=_match("Primary Song"))
        backup = _StubProvider(response=_match())
        manager = self._manager(
            monkeypatch, {"primary": primary, "backup": backup}, fallback_enabled=True
        )
        segments = [AudioSegment(file_path="x", start_time=0, duration=60)]
        tracks = await manager.identify_tracks(segments)
        assert backup.calls == 0
        assert tracks[0].song_name == "Primary Song"

    @pytest.mark.asyncio
    async def test_provider_exception_falls_through_to_backup(self, monkeypatch):
        primary = _StubProvider(error=RuntimeError("provider down"))
        backup = _StubProvider(response=_match())
        manager = self._manager(
            monkeypatch, {"primary": primary, "backup": backup}, fallback_enabled=True
        )
        segments = [AudioSegment(file_path="x", start_time=0, duration=60)]
        tracks = await manager.identify_tracks(segments)
        assert len(tracks) == 1


class TestCircuitBreakerWiring:
    def test_record_result_trips_breaker(self):
        """I6: repeated failures open the circuit via the public API."""
        from tracklistify.utils.rate_limiter import CircuitState, RateLimiter

        limiter = RateLimiter()
        limiter.register_provider("prov", 10, 2)
        threshold = getattr(limiter._config, "circuit_breaker_threshold", 5)
        for _ in range(threshold):
            limiter.record_result("prov", success=False)
        assert limiter._provider_limits["prov"].circuit_state == CircuitState.OPEN, (
            "circuit breaker did not open after threshold failures"
        )

    @pytest.mark.asyncio
    async def test_identification_reports_failures_to_breaker(self, monkeypatch):
        """The identify loop must call record_result on provider errors."""
        from tracklistify.config import get_config
        from tracklistify.utils.identification import IdentificationManager
        from tracklistify.utils.rate_limiter import RateLimiter
        import tracklistify.utils.identification as ident_mod

        limiter = RateLimiter()
        recorded = []
        monkeypatch.setattr(
            limiter,
            "record_result",
            lambda provider, success: recorded.append((provider, success)),
        )
        monkeypatch.setattr(ident_mod, "get_global_rate_limiter", lambda: limiter)

        config = get_config(force_refresh=True)
        config.primary_provider = "primary"
        config.fallback_enabled = False
        failing = _StubProvider(error=RuntimeError("boom"))
        manager = IdentificationManager(
            config=config, provider_factory=_StubFactory({"primary": failing})
        )
        await manager.identify_tracks(
            [AudioSegment(file_path="x", start_time=0, duration=60)]
        )
        assert ("primary", False) in recorded


# ---------------------------------------------------------------------------
# I7 / I8 — cache subsystem safety (unwired today, but must be safe to wire)
# ---------------------------------------------------------------------------


class TestCacheTTL:
    @pytest.mark.asyncio
    async def test_entries_expire_after_ttl(self, tmp_path, monkeypatch):
        """I7: set() without explicit ttl inherits the cache TTL."""
        monkeypatch.setenv("TRACKLISTIFY_CACHE_DIR", str(tmp_path))
        from tracklistify.cache.factory import create_cache

        cache = create_cache(cache_dir=tmp_path, ttl=10)
        await cache.set("key", {"data": 1})
        assert await cache.get("key") == {"data": 1}

        # Age the entry past its TTL by rewriting its created timestamp.
        entry = await cache._storage.get("key")
        assert entry["metadata"]["ttl"] == 10, (
            "set() must stamp the cache-level TTL, not None (None disables expiry)"
        )
        entry["metadata"]["created"] = time.time() - 11
        entry["metadata"]["last_accessed"] = time.time() - 11
        await cache._storage.set("key", entry)

        assert await cache.get("key") is None, "entry older than ttl must expire"


class TestCacheIndexPersistence:
    @pytest.mark.asyncio
    async def test_second_storage_instance_sees_entries(self, tmp_path, monkeypatch):
        """I8: a fresh process (new index object) must see prior writes."""
        monkeypatch.setenv("TRACKLISTIFY_CACHE_DIR", str(tmp_path))
        from tracklistify.cache.storage import JSONStorage

        storage_a = JSONStorage(tmp_path)
        entry = {
            "key": "k1",
            "value": {"x": 1},
            "metadata": {
                "created": time.time(),
                "last_accessed": time.time(),
                "ttl": 3600,
                "compression": False,
                "size": 8,
            },
        }
        await storage_a.set("k1", entry)

        # Simulate a new process: brand-new storage + index over same dir.
        storage_b = JSONStorage(tmp_path)
        loaded = await storage_b.get("k1")
        assert loaded is not None and loaded["value"] == {"x": 1}, (
            "index was not persisted on set(); entries written by one "
            "process are invisible (and later deleted as orphans) in the next"
        )


# ---------------------------------------------------------------------------
# CLI fail-fast
# ---------------------------------------------------------------------------


class TestCliFfmpegCheck:
    def test_cli_exits_early_without_ffmpeg(self, monkeypatch):
        from tracklistify import cli as cli_mod

        monkeypatch.setattr(cli_mod.shutil, "which", lambda name: None)
        monkeypatch.setattr(
            cli_mod.sys, "argv", ["tracklistify", "http://youtube.com/watch?v=x"]
        )
        with pytest.raises(SystemExit) as exc_info:
            cli_mod.cli()
        assert exc_info.value.code == 1

    def test_cli_proceeds_with_ffmpeg(self, monkeypatch):
        """With ffmpeg present, cli() must get past the check (we stop it
        at asyncio.run to avoid a real run)."""
        from tracklistify import cli as cli_mod

        monkeypatch.setattr(cli_mod.shutil, "which", lambda name: "/usr/bin/ffmpeg")
        monkeypatch.setattr(
            cli_mod.sys, "argv", ["tracklistify", "http://youtube.com/watch?v=x"]
        )

        def fake_asyncio_run(coro):
            coro.close()  # avoid "coroutine never awaited" warnings
            return 0

        with patch.object(
            cli_mod.asyncio, "run", side_effect=fake_asyncio_run
        ) as fake_run:
            with pytest.raises(SystemExit) as exc_info:
                cli_mod.cli()
        assert fake_run.called
        assert exc_info.value.code == 0


def test_cache_max_age_does_not_undercut_cache_ttl():
    """Two independent expiry gates; the shorter one wins.

    ``TTLStrategy`` reads ``cache_ttl`` on lookup, while
    ``JSONStorage.cleanup()`` (via ``BaseCache.cleanup()``) reads
    ``cache_max_age`` and deletes files outright. If max_age is the shorter
    of the two, the janitor reaps entries the TTL still considers valid and
    the longer TTL is a lie. Shipping 3600s TTL against an 86400s max_age
    hid this — raising only the TTL would have capped effective cache life
    at 24h with no visible symptom beyond a silent miss.

    Currently latent: no production code calls ``BaseCache.cleanup()``. The
    invariant is held anyway so that scheduling the janitor later is a safe
    change rather than a silent data-loss one.
    """
    from tracklistify.config import get_config

    cfg = get_config(force_refresh=True)
    assert cfg.cache_max_age >= cfg.cache_ttl, (
        f"cache_max_age ({cfg.cache_max_age}s) is shorter than cache_ttl "
        f"({cfg.cache_ttl}s); cleanup would delete entries the TTL still "
        f"treats as live"
    )
