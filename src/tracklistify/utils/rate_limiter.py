"""
Rate limiting functionality for API calls with metrics, circuit breaker, and alerts.
"""

# Standard library imports
import asyncio
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

# Local/package imports
from ..config import get_config
from .constants import TOKEN_REFILL_SLEEP

# Rate limiting constants
# 1ms threshold to detect actual rate limit
RATE_LIMIT_DETECTION_THRESHOLD_SECONDS = 0.001


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Rate limit exceeded, blocking requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class RateLimitMetrics:
    """Metrics for rate limiting."""

    total_requests: int = 0
    rate_limited_requests: int = 0
    total_wait_time: float = 0.0
    last_rate_limit: Optional[float] = None
    rate_limit_windows: List[Tuple[float, float]] = field(default_factory=list)
    circuit_trips: int = 0
    last_circuit_trip: Optional[float] = None


@dataclass
class ProviderLimits:
    """Rate limits for a specific provider.

    Uses asyncio.Lock instead of threading.Lock to avoid blocking the event loop.
    Async primitives are lazily initialized to support creation outside async context.
    """

    max_requests_per_minute: int = 25  # Default fallback (matches Shazam default)
    max_concurrent_requests: int = 1  # Default fallback (matches Shazam default)
    tokens: int = field(init=False)
    last_update: float = field(
        default_factory=time.monotonic
    )  # Use monotonic for elapsed time
    semaphore: Optional[asyncio.Semaphore] = field(init=False, default=None)
    lock: Optional[asyncio.Lock] = field(
        init=False, default=None
    )  # Changed from threading.Lock
    metrics: RateLimitMetrics = field(default_factory=RateLimitMetrics)
    circuit_state: CircuitState = field(default=CircuitState.CLOSED)
    circuit_open_time: Optional[float] = None
    consecutive_failures: int = 0

    def __post_init__(self):
        """Initialize fields after dataclass creation."""
        self.tokens = self.max_requests_per_minute
        # Try to create async primitives if event loop is running
        try:
            asyncio.get_running_loop()
            self.semaphore = asyncio.Semaphore(self.max_concurrent_requests)
            self.lock = asyncio.Lock()
        except RuntimeError:
            # No event loop running, defer creation
            self.semaphore = None
            self.lock = None

    def ensure_async_primitives(self):
        """Ensure async primitives are created.

        Call this method when you need to use the lock or semaphore
        from within an async context.
        """
        if self.semaphore is None:
            self.semaphore = asyncio.Semaphore(self.max_concurrent_requests)
        if self.lock is None:
            self.lock = asyncio.Lock()


class RateLimiter:
    """Advanced rate limiter with provider management, circuit breaker, metrics."""

    def __init__(self, config=None):
        self._provider_limits: Dict[Any, ProviderLimits] = {}
        self._alert_callbacks: List[Callable[[str], None]] = []
        # Use provided config or get global config
        self._config = config or get_config()

    def register_provider(
        self,
        provider: Any,
        max_requests_per_minute: int = None,
        max_concurrent_requests: int = None,
    ):
        """Register a provider with specific rate limits."""
        # Use provided values, or fall back to config values based on provider
        if max_requests_per_minute is None or max_concurrent_requests is None:
            provider_str = str(provider).lower()

            # Get provider-specific limits from config
            if provider_str == "shazam":
                rpm = max_requests_per_minute or getattr(
                    self._config, "shazam_max_rpm", 25
                )
                concurrent = max_concurrent_requests or getattr(
                    self._config, "shazam_max_concurrent", 1
                )
            elif provider_str == "acrcloud":
                rpm = max_requests_per_minute or getattr(
                    self._config, "acrcloud_max_rpm", 30
                )
                concurrent = max_concurrent_requests or getattr(
                    self._config, "acrcloud_max_concurrent", 5
                )
            elif provider_str == "spotify":
                rpm = max_requests_per_minute or getattr(
                    self._config, "spotify_max_rpm", 120
                )
                concurrent = max_concurrent_requests or getattr(
                    self._config, "spotify_max_concurrent", 20
                )
            else:
                # Fall back to global config or defaults
                rpm = max_requests_per_minute or getattr(
                    self._config, "max_requests_per_minute", 25
                )
                concurrent = max_concurrent_requests or getattr(
                    self._config, "max_concurrent_requests", 2
                )
        else:
            rpm = max_requests_per_minute
            concurrent = max_concurrent_requests

        self._provider_limits[provider] = ProviderLimits(
            max_requests_per_minute=rpm,
            max_concurrent_requests=concurrent,
        )

    def register_alert_callback(self, callback: Callable[[str], None]):
        """Register a callback for rate limiting alerts."""
        self._alert_callbacks.append(callback)

    def _send_alert(self, message: str):
        """Send alert to all registered callbacks."""
        for callback in self._alert_callbacks:
            callback(message)

    async def acquire(self, provider: Any, timeout: float = 30.0) -> bool:
        """Acquire permission to make a request.

        Uses asyncio.Lock to avoid blocking the event loop.

        Args:
            provider: Provider to acquire token for
            timeout: Maximum time to wait in seconds

        Returns:
            True if token acquired, False if timeout or circuit open
        """
        if provider not in self._provider_limits:
            self.register_provider(provider)

        limits = self._provider_limits[provider]

        # Ensure async primitives are created (handles lazy initialization)
        limits.ensure_async_primitives()

        # Check circuit breaker first (don't count rejected requests)
        circuit_breaker_enabled = getattr(self._config, "circuit_breaker_enabled", True)
        if circuit_breaker_enabled and limits.circuit_state == CircuitState.OPEN:
            circuit_reset_timeout = getattr(
                self._config, "circuit_breaker_reset_timeout", 60.0
            )
            if (
                limits.circuit_open_time
                and time.monotonic() - limits.circuit_open_time > circuit_reset_timeout
            ):
                limits.circuit_state = CircuitState.HALF_OPEN
            else:
                return False

        # Try to acquire semaphore for concurrent requests
        try:
            # Always attempt to acquire the semaphore with a timeout
            start_time = time.monotonic()
            await asyncio.wait_for(limits.semaphore.acquire(), timeout=timeout)
            wait_time = time.monotonic() - start_time
            limits.metrics.total_wait_time += wait_time
            # Note: Don't record semaphore waits as rate limit windows
            # This is concurrency control, not rate limiting
        except asyncio.TimeoutError:
            return False

        # At this point, we have semaphore access and will process the request.
        # On every non-True exit (timeout, cancellation, unexpected error) we
        # must release the semaphore, or callers block forever on subsequent
        # acquires once max_concurrent_requests is reached.
        try:
            limits.metrics.total_requests += 1

            # Check if rate limiting is enabled
            rate_limit_enabled = getattr(self._config, "rate_limit_enabled", True)
            if not rate_limit_enabled:
                return True

            # Check rate limiting tokens
            token_wait_start = time.monotonic()

            while time.monotonic() - token_wait_start < timeout:
                async with limits.lock:  # ASYNC lock - doesn't block event loop!
                    self._refill_tokens(limits)
                    if limits.tokens > 0:
                        limits.tokens -= 1
                        # Record metrics only if we had to wait for tokens
                        wait_time = time.monotonic() - token_wait_start
                        if wait_time >= RATE_LIMIT_DETECTION_THRESHOLD_SECONDS:
                            # Successful requests that were rate-limited
                            limits.metrics.rate_limited_requests += 1
                            limits.metrics.last_rate_limit = time.monotonic()
                            limits.metrics.rate_limit_windows.append(
                                (token_wait_start, time.monotonic())
                            )
                        return True

                # Wait a short time before checking again
                await asyncio.sleep(TOKEN_REFILL_SLEEP)

            # Timeout exceeded - rate limiting failure
            limits.metrics.last_rate_limit = time.monotonic()
            limits.metrics.rate_limit_windows.append(
                (token_wait_start, time.monotonic())
            )
            limits.semaphore.release()
            return False
        except BaseException:
            # Cancellation or unexpected error after semaphore was acquired:
            # release before propagating so we don't strand a slot.
            limits.semaphore.release()
            raise

    def release(self, provider: Any):
        """Release a concurrent request slot."""
        if provider in self._provider_limits:
            limits = self._provider_limits[provider]
            if limits.semaphore is not None:
                limits.semaphore.release()

    def _refill_tokens(self, limits: ProviderLimits):
        """Refill rate limiting tokens based on elapsed time."""
        now = time.monotonic()  # Use monotonic for elapsed time calculations
        elapsed = now - limits.last_update
        if elapsed >= 1.0:  # Refill every second
            tokens_to_add = int(elapsed * (limits.max_requests_per_minute / 60))
            if tokens_to_add > 0:
                limits.tokens = min(
                    limits.max_requests_per_minute, limits.tokens + tokens_to_add
                )
                limits.last_update = now

    def _update_circuit_breaker(self, provider: Any, success: bool):
        """Update circuit breaker state based on request success."""
        if provider not in self._provider_limits:
            return

        limits = self._provider_limits[provider]
        circuit_breaker_enabled = getattr(self._config, "circuit_breaker_enabled", True)

        if not circuit_breaker_enabled:
            return

        if success:
            limits.consecutive_failures = 0
            if limits.circuit_state == CircuitState.HALF_OPEN:
                limits.circuit_state = CircuitState.CLOSED
        else:
            limits.consecutive_failures += 1
            circuit_threshold = getattr(self._config, "circuit_breaker_threshold", 5)
            if (
                limits.consecutive_failures >= circuit_threshold
                and limits.circuit_state == CircuitState.CLOSED
            ):
                limits.circuit_state = CircuitState.OPEN
                limits.circuit_open_time = time.monotonic()  # Use monotonic
                limits.metrics.circuit_trips += 1
                limits.metrics.last_circuit_trip = time.monotonic()  # Use monotonic
                self._send_alert(
                    message=f"Circuit breaker opened for provider {provider} "
                    f"after {limits.consecutive_failures} failures"
                )

    def get_metrics(self, provider: Any) -> Dict[str, Any]:
        """Get metrics for a provider."""
        if provider not in self._provider_limits:
            return {}

        limits = self._provider_limits[provider]
        return {
            "total_requests": limits.metrics.total_requests,
            "rate_limited_requests": limits.metrics.rate_limited_requests,
            "total_wait_time": limits.metrics.total_wait_time,
            "last_rate_limit": limits.metrics.last_rate_limit,
            "rate_limit_windows": limits.metrics.rate_limit_windows,
            "circuit_trips": limits.metrics.circuit_trips,
            "last_circuit_trip": limits.metrics.last_circuit_trip,
            "circuit_state": limits.circuit_state.value,
            "current_tokens": limits.tokens,
        }


# Singleton instance with thread-safe access
_global_rate_limiter: Optional["RateLimiter"] = None
_global_rate_limiter_lock = threading.Lock()


def get_global_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance.

    Thread-safe via double-checked locking; concurrent first-access
    callers all receive the same instance.
    """
    global _global_rate_limiter
    # Fast path: already created
    if _global_rate_limiter is not None:
        return _global_rate_limiter
    # Slow path: serialise creation
    with _global_rate_limiter_lock:
        if _global_rate_limiter is None:
            _global_rate_limiter = RateLimiter()
    return _global_rate_limiter
