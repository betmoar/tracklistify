"""Tests that the identification loop feeds request outcomes to the circuit
breaker, so repeated provider failures trip it and stop hammering the provider.
"""

from types import SimpleNamespace

import pytest

from tracklistify.utils.identification import IdentificationManager
from tracklistify.utils.rate_limiter import (
    get_global_rate_limiter,
    reset_global_rate_limiter,
)


class _FailingProvider:
    """Async-context-manager provider whose identify_track always raises."""

    def __init__(self):
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def identify_track(self, segment):
        self.calls += 1
        raise RuntimeError("provider boom")

    async def close(self):
        pass


class _FakeFactory:
    def __init__(self, provider):
        self._provider = provider

    def get_identification_provider(self, name):
        return self._provider

    async def close_all(self):
        pass


class _FakeConfig:
    primary_provider = "circuit-test-provider"


@pytest.fixture(autouse=True)
def _fresh_global_limiter():
    reset_global_rate_limiter()
    yield
    reset_global_rate_limiter()


@pytest.mark.asyncio
async def test_circuit_breaker_trips_after_repeated_failures(monkeypatch):
    limiter = get_global_rate_limiter()
    monkeypatch.setattr(limiter._config, "circuit_breaker_enabled", True)
    monkeypatch.setattr(limiter._config, "circuit_breaker_threshold", 2)
    # Keep the circuit open for the duration of the run.
    monkeypatch.setattr(limiter._config, "circuit_breaker_reset_timeout", 60.0)

    provider = _FailingProvider()
    manager = IdentificationManager(
        config=_FakeConfig(), provider_factory=_FakeFactory(provider)
    )

    segments = [
        SimpleNamespace(start_time=i, file_path=f"/tmp/seg{i}.mp3") for i in range(6)
    ]
    result = await manager.identify_tracks(segments)

    assert result == []
    # Only the threshold number of failures actually reach the provider; once
    # the circuit opens, the remaining segments are rejected by acquire().
    assert provider.calls == 2
    metrics = limiter.get_metrics("circuit-test-provider")
    assert metrics["circuit_state"] == "open"


def test_record_result_resets_failure_streak_on_success():
    limiter = get_global_rate_limiter()
    limiter.register_provider("p")

    limiter.record_result("p", success=False)
    limiter.record_result("p", success=False)
    assert limiter._provider_limits["p"].consecutive_failures == 2

    limiter.record_result("p", success=True)
    assert limiter._provider_limits["p"].consecutive_failures == 0
