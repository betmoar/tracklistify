"""
Tests for Issue #5: Replace Blocking Locks with Async Locks

Validates that the rate limiter uses asyncio.Lock instead of threading.Lock
and doesn't block the event loop during operations.
"""

# Standard library imports
import asyncio
import threading
import time

# Third-party imports
import pytest

# Local/package imports
from tracklistify.utils.rate_limiter import (
    RateLimiter,
    ProviderLimits,
    CircuitState,
)


class TestAsyncLocks:
    """Test async lock implementation."""

    @pytest.mark.asyncio
    async def test_uses_asyncio_lock(self):
        """Ensure asyncio.Lock is used, not threading.Lock."""
        limiter = RateLimiter()
        limiter.register_provider("test", max_requests_per_minute=10)

        limits = limiter._provider_limits["test"]

        # Ensure primitives are created
        if hasattr(limits, "ensure_async_primitives"):
            limits.ensure_async_primitives()

        # Should be asyncio.Lock, not threading.Lock
        assert isinstance(limits.lock, asyncio.Lock), (
            f"Expected asyncio.Lock, got {type(limits.lock)}"
        )
        assert not isinstance(limits.lock, type(threading.Lock())), (
            "Should not be threading.Lock"
        )

    @pytest.mark.asyncio
    async def test_uses_asyncio_semaphore(self):
        """Ensure asyncio.Semaphore is used."""
        limiter = RateLimiter()
        limiter.register_provider("test", max_requests_per_minute=10)

        limits = limiter._provider_limits["test"]

        if hasattr(limits, "ensure_async_primitives"):
            limits.ensure_async_primitives()

        assert isinstance(limits.semaphore, asyncio.Semaphore), (
            f"Expected asyncio.Semaphore, got {type(limits.semaphore)}"
        )

    @pytest.mark.asyncio
    async def test_no_event_loop_blocking(self):
        """Ensure rate limiter doesn't block event loop."""
        limiter = RateLimiter()
        limiter.register_provider("test", max_requests_per_minute=60)

        # Acquire should be nearly instant for first request
        start = time.monotonic()
        result = await limiter.acquire("test")
        elapsed = time.monotonic() - start

        assert result is True
        assert elapsed < 0.1  # Less than 100ms (generous for test environments)

        limiter.release("test")

    @pytest.mark.asyncio
    async def test_concurrent_acquires_dont_deadlock(self):
        """Ensure concurrent acquires don't cause deadlock."""
        limiter = RateLimiter()
        limiter.register_provider(
            "test", max_requests_per_minute=100, max_concurrent_requests=5
        )

        results = []

        async def acquire_and_release():
            result = await limiter.acquire("test", timeout=5.0)
            if result:
                await asyncio.sleep(0.01)  # Simulate work
                limiter.release("test")
            return result

        # Run multiple concurrent acquires
        tasks = [acquire_and_release() for _ in range(10)]
        results = await asyncio.gather(*tasks)

        # All should eventually succeed (within timeout)
        assert sum(results) >= 5  # At least concurrent limit succeeded

    @pytest.mark.asyncio
    async def test_lock_is_async_context_manager(self):
        """Ensure lock can be used with async with statement."""
        limits = ProviderLimits(max_requests_per_minute=10, max_concurrent_requests=1)

        if hasattr(limits, "ensure_async_primitives"):
            limits.ensure_async_primitives()

        # Should be usable with async with
        async with limits.lock:
            # If we get here, async context manager works
            pass

    @pytest.mark.asyncio
    async def test_provider_limits_lazy_initialization(self):
        """Test that async primitives can be lazily initialized."""
        # Create outside of async context
        limits = ProviderLimits(max_requests_per_minute=10, max_concurrent_requests=1)

        # Ensure primitives method should exist and work
        if hasattr(limits, "ensure_async_primitives"):
            limits.ensure_async_primitives()
            assert limits.lock is not None
            assert limits.semaphore is not None


class TestAsyncAcquireRelease:
    """Test async acquire/release behavior."""

    @pytest.mark.asyncio
    async def test_acquire_returns_true_when_available(self):
        """Test that acquire returns True when tokens available."""
        limiter = RateLimiter()
        limiter.register_provider("test", max_requests_per_minute=60)

        result = await limiter.acquire("test")
        assert result is True
        limiter.release("test")

    @pytest.mark.asyncio
    async def test_acquire_respects_timeout(self):
        """Test that acquire respects timeout parameter."""
        limiter = RateLimiter()
        # Very low rate limit
        limiter.register_provider(
            "test", max_requests_per_minute=1, max_concurrent_requests=1
        )

        # First acquire should succeed
        result1 = await limiter.acquire("test")
        assert result1 is True

        # Second should timeout quickly (without blocking event loop)
        start = time.monotonic()
        result2 = await limiter.acquire("test", timeout=0.1)
        elapsed = time.monotonic() - start

        # Should timeout around 0.1s, not block indefinitely
        assert elapsed < 0.5  # Give some margin
        assert result2 is False

        limiter.release("test")

    @pytest.mark.asyncio
    async def test_release_frees_semaphore(self):
        """Test that release properly frees the semaphore."""
        limiter = RateLimiter()
        limiter.register_provider(
            "test", max_requests_per_minute=60, max_concurrent_requests=1
        )

        # Acquire
        await limiter.acquire("test")

        # Second acquire should fail (concurrent limit = 1)
        result = await limiter.acquire("test", timeout=0.05)
        assert result is False

        # Release
        limiter.release("test")

        # Now acquire should succeed
        result = await limiter.acquire("test")
        assert result is True
        limiter.release("test")


class TestMetricsWithAsyncLocks:
    """Test that metrics work correctly with async locks."""

    @pytest.mark.asyncio
    async def test_metrics_track_total_requests(self):
        """Test that total_requests metric is updated."""
        limiter = RateLimiter()
        limiter.register_provider("test", max_requests_per_minute=60)

        # Make several requests
        for _ in range(5):
            await limiter.acquire("test")
            limiter.release("test")

        metrics = limiter.get_metrics("test")
        assert metrics["total_requests"] >= 5

    @pytest.mark.asyncio
    async def test_metrics_available_after_operations(self):
        """Test that metrics are available and populated."""
        limiter = RateLimiter()
        limiter.register_provider("test", max_requests_per_minute=60)

        await limiter.acquire("test")
        limiter.release("test")

        metrics = limiter.get_metrics("test")

        # Check metrics structure exists
        assert "total_requests" in metrics
        assert "rate_limited_requests" in metrics
        assert "circuit_state" in metrics
        assert metrics["total_requests"] >= 1


class TestCircuitBreakerWithAsyncLocks:
    """Test circuit breaker behavior with async locks."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_failures(self):
        """Test that circuit breaker opens after consecutive failures."""
        from unittest.mock import MagicMock

        # Create config mock with circuit breaker enabled
        config = MagicMock()
        config.circuit_breaker_enabled = True
        config.circuit_breaker_threshold = 3
        config.circuit_breaker_reset_timeout = 60.0
        config.rate_limit_enabled = True
        # Must mock max_concurrent_requests to be a valid int for Semaphore
        config.max_concurrent_requests = 2

        limiter = RateLimiter(config=config)
        # Explicitly provide values to avoid config lookup
        limiter.register_provider(
            "test", max_requests_per_minute=60, max_concurrent_requests=2
        )

        # Simulate failures to trigger circuit breaker
        limits = limiter._provider_limits["test"]
        for _ in range(5):
            limiter._update_circuit_breaker("test", success=False)

        # Circuit should be open
        assert limits.circuit_state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks_when_open(self):
        """Test that requests are blocked when circuit is open."""
        from unittest.mock import MagicMock

        config = MagicMock()
        config.circuit_breaker_enabled = True
        config.circuit_breaker_threshold = 3
        config.circuit_breaker_reset_timeout = 60.0
        config.rate_limit_enabled = True
        # Must mock max_concurrent_requests to be a valid int for Semaphore
        config.max_concurrent_requests = 2

        limiter = RateLimiter(config=config)
        # Explicitly provide values to avoid config lookup
        limiter.register_provider(
            "test", max_requests_per_minute=60, max_concurrent_requests=2
        )

        # Open the circuit
        limits = limiter._provider_limits["test"]
        limits.circuit_state = CircuitState.OPEN
        limits.circuit_open_time = (
            time.monotonic()
        )  # Use monotonic to match implementation

        # Acquire should return False immediately
        result = await limiter.acquire("test")
        assert result is False


class TestBackwardCompatibility:
    """Test backward compatibility with existing code."""

    @pytest.mark.asyncio
    async def test_register_provider_still_works(self):
        """Test that register_provider API hasn't changed."""
        limiter = RateLimiter()

        # Should work with all parameter combinations
        limiter.register_provider("test1")
        limiter.register_provider("test2", max_requests_per_minute=30)
        limiter.register_provider("test3", max_concurrent_requests=5)
        limiter.register_provider(
            "test4", max_requests_per_minute=30, max_concurrent_requests=5
        )

        assert "test1" in limiter._provider_limits
        assert "test2" in limiter._provider_limits
        assert "test3" in limiter._provider_limits
        assert "test4" in limiter._provider_limits

    @pytest.mark.asyncio
    async def test_release_is_sync(self):
        """Test that release() is still a sync method."""
        limiter = RateLimiter()
        limiter.register_provider("test", max_requests_per_minute=60)

        await limiter.acquire("test")

        # release() should be callable without await
        limiter.release("test")  # Should not raise

    @pytest.mark.asyncio
    async def test_get_metrics_is_sync(self):
        """Test that get_metrics() is still a sync method."""
        limiter = RateLimiter()
        limiter.register_provider("test", max_requests_per_minute=60)

        await limiter.acquire("test")
        limiter.release("test")

        # get_metrics() should be callable without await
        metrics = limiter.get_metrics("test")  # Should not raise
        assert isinstance(metrics, dict)
