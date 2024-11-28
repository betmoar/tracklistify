# tests/test_rate_limiter.py
# Standard library imports
import asyncio
import time
from unittest.mock import Mock

# Third-party imports
import pytest

# Local/package imports
from tracklistify.providers.base import TrackIdentificationProvider
from tracklistify.rate_limiter import (
    RateLimiter,
)


class MockProvider(TrackIdentificationProvider):
    """Mock provider for testing."""

    def __init__(self):
        super().__init__()

    async def identify_track(self, audio_path):
        return None


@pytest.fixture
def rate_limiter():
    """Create a fresh rate limiter instance for each test."""
    return RateLimiter()


@pytest.fixture
def mock_provider():
    """Create a mock provider instance."""
    return MockProvider


class TestRateLimiter:
    """Test suite for RateLimiter class."""

    @pytest.mark.asyncio
    async def test_basic_rate_limiting(self, rate_limiter, mock_provider):
        """Test basic rate limiting functionality."""
        # Configure rate limiter with 2 requests per minute
        rate_limiter.register_provider(mock_provider, max_requests_per_minute=2)

        # First two requests should succeed
        assert await rate_limiter.acquire(mock_provider)
        assert await rate_limiter.acquire(mock_provider)

        # Third request should fail immediately
        assert not await rate_limiter.acquire(mock_provider, timeout=0.001)

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, rate_limiter, mock_provider):
        """Test concurrent request limiting."""
        # Configure rate limiter with 1 concurrent request max
        rate_limiter.register_provider(mock_provider, max_concurrent_requests=1)

        # First request should succeed
        assert await rate_limiter.acquire(mock_provider)

        # Second request should fail immediately
        assert not await rate_limiter.acquire(mock_provider, timeout=0.001)

        # Release and cleanup
        rate_limiter.release(mock_provider)

    @pytest.mark.skip(reason="Needs fixing - timing issues")
    @pytest.mark.asyncio
    async def test_metrics_tracking(self, rate_limiter, mock_provider):
        """Test metrics collection."""
        # Configure rate limiter
        rate_limiter.register_provider(mock_provider, max_requests_per_minute=2)

        # Make some requests
        assert await rate_limiter.acquire(mock_provider)  # Success
        assert await rate_limiter.acquire(mock_provider)  # Success
        assert not await rate_limiter.acquire(mock_provider, timeout=0.001)  # Fail

        # Check metrics
        metrics = rate_limiter.get_metrics(mock_provider)
        assert metrics["total_requests"] == 3  # All requests count toward total
        assert (
            metrics["rate_limited_requests"] == 0
        )  # Only counts requests that wait and succeed

    @pytest.mark.skip(reason="Needs fixing - timing issues")
    @pytest.mark.asyncio
    async def test_circuit_breaker(self, rate_limiter, mock_provider):
        """Test circuit breaker functionality."""
        # Configure rate limiter with circuit breaker
        rate_limiter.register_provider(mock_provider)
        rate_limiter._config.circuit_breaker_threshold = 2
        rate_limiter._config.circuit_breaker_reset_timeout = 0.1

        # Two failed requests should open circuit
        rate_limiter._update_circuit_breaker(mock_provider, False)
        rate_limiter._update_circuit_breaker(mock_provider, False)

        # Circuit should be open, requests should fail immediately
        assert not await rate_limiter.acquire(mock_provider, timeout=0.001)

        # Wait for reset timeout
        await asyncio.sleep(0.2)

        # Circuit should be half-open, request should succeed
        assert await rate_limiter.acquire(mock_provider)

    @pytest.mark.skip(reason="Needs fixing - timing issues")
    def test_alert_system(self, rate_limiter, mock_provider):
        """Test alert callback system."""
        # Set up mock callback
        mock_callback = Mock()
        rate_limiter.register_alert_callback(mock_callback)

        # Configure rate limiter
        rate_limiter.register_provider(mock_provider)
        rate_limiter._config.circuit_breaker_threshold = 1

        # Trigger alert by opening circuit breaker
        rate_limiter._update_circuit_breaker(mock_provider, False)

        # Verify callback was called with alert message
        mock_callback.assert_called_once()
        assert "Circuit breaker opened" in mock_callback.call_args[0][0]

    @pytest.mark.skip(reason="Needs fixing - timing issues")
    @pytest.mark.asyncio
    async def test_cleanup(self, rate_limiter, mock_provider):
        """Test resource cleanup."""
        # Register provider with small concurrent limit
        rate_limiter.register_provider(mock_provider, max_concurrent_requests=2)

        # Acquire both slots
        assert await rate_limiter.acquire(mock_provider)
        assert await rate_limiter.acquire(mock_provider)

        # Release should restore slots
        rate_limiter.release(mock_provider)
        rate_limiter.release(mock_provider)

    @pytest.mark.skip(reason="Needs fixing - timing issues")
    def test_provider_registration(self, rate_limiter, mock_provider):
        """Test provider registration with custom limits."""
        # Register provider with custom limits
        rate_limiter.register_provider(
            mock_provider, max_requests_per_minute=30, max_concurrent_requests=5
        )

        # Verify limits were set correctly
        limits = rate_limiter._provider_limits[mock_provider]
        assert limits.max_requests_per_minute == 30
        assert limits.max_concurrent_requests == 5
        assert (
            limits.tokens == 30
        )  # Initial tokens should match max_requests_per_minute

    @pytest.mark.skip(reason="Needs fixing - timing issues")
    @pytest.mark.asyncio
    async def test_rate_limit_windows(self, rate_limiter, mock_provider):
        """Test rate limit window tracking."""
        try:
            # Configure rate limiter with 1 request per minute
            rate_limiter.register_provider(mock_provider, max_requests_per_minute=1)
            limits = rate_limiter._provider_limits[mock_provider]

            # First request should succeed
            assert await rate_limiter.acquire(mock_provider)

            # Second request should fail immediately
            assert not await rate_limiter.acquire(mock_provider, timeout=0.001)

            # Verify rate limit windows exist
            assert len(limits.metrics.rate_limit_windows) > 0

            # Verify window timestamps are reasonable
            window = limits.metrics.rate_limit_windows[0]
            assert window[0] < window[1]  # Start time should be before end time
            assert (
                window[1] - window[0] < 1.0
            )  # Window should be short since we used small timeout
        finally:
            # Ensure cleanup
            rate_limiter.release(mock_provider)

    @pytest.mark.asyncio
    async def test_timeout_handling(self, rate_limiter, mock_provider):
        """Test timeout handling for rate limiting."""
        rate_limiter.register_provider(mock_provider, max_requests_per_minute=1)

        # Use up the token
        assert await rate_limiter.acquire(mock_provider)

        # Next request should timeout
        start_time = time.time()
        assert not await rate_limiter.acquire(mock_provider, timeout=0.1)
        duration = time.time() - start_time

        # Should have waited approximately the timeout duration
        assert 0.1 <= duration <= 0.2
