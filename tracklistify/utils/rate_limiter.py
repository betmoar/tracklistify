"""
Rate limiting functionality for API calls with metrics, circuit breaker, alerts.
"""

# Standard library imports
import asyncio
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, Tuple

# Local/package imports

# Rate limiting constants
RATE_LIMIT_DETECTION_THRESHOLD_MS = 0.001  # 1ms threshold to detect actual rate limit
# This threshold distinguishes between:
# - Normal processing delays (< 1ms): Not counted as rate limiting
# - Actual rate limiting waits (≥ 1ms): Counted in rate_limited_requests metric
# The 1ms threshold accounts for typical system call and lock acquisition overhead

# Default rate limit values
DEFAULT_MAX_REQUESTS_PER_MINUTE = 20
DEFAULT_MAX_CONCURRENT_REQUESTS = 1


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
    """Rate limits for a specific provider."""

    max_requests_per_minute: int = DEFAULT_MAX_REQUESTS_PER_MINUTE
    max_concurrent_requests: int = DEFAULT_MAX_CONCURRENT_REQUESTS
    tokens: int = field(init=False)
    last_update: float = field(default_factory=time.time)
    semaphore: asyncio.Semaphore = field(init=False)
    lock: Lock = field(default_factory=Lock)
    metrics: RateLimitMetrics = field(default_factory=RateLimitMetrics)
    circuit_state: CircuitState = field(default=CircuitState.CLOSED)
    circuit_open_time: Optional[float] = None
    consecutive_failures: int = 0

    def __post_init__(self):
        self.tokens = self.max_requests_per_minute
        self.semaphore = asyncio.Semaphore(self.max_concurrent_requests)


@dataclass
class RateLimiterConfig:
    """Configuration for the rate limiter."""

    circuit_breaker_threshold: int = 5
    circuit_breaker_reset_timeout: float = 60.0


class RateLimiter:
    """Advanced rate limiter with provider management, circuit breaker, metrics."""

    def __init__(self):
        self._provider_limits: Dict[Any, ProviderLimits] = {}
        self._alert_callbacks: List[Callable[[str], None]] = []
        self._config = RateLimiterConfig()

    def register_provider(
        self,
        provider: Any,
        max_requests_per_minute: int = 20,
        max_concurrent_requests: int = 1,
    ):
        """Register a provider with specific rate limits."""
        self._provider_limits[provider] = ProviderLimits(
            max_requests_per_minute=max_requests_per_minute,
            max_concurrent_requests=max_concurrent_requests,
        )

    def register_alert_callback(self, callback: Callable[[str], None]):
        """Register a callback for rate limiting alerts."""
        self._alert_callbacks.append(callback)

    def _send_alert(self, message: str):
        """Send alert to all registered callbacks."""
        for callback in self._alert_callbacks:
            callback(message)

    async def acquire(self, provider: Any, timeout: float = 30.0) -> bool:
        """Acquire permission to make a request."""
        if provider not in self._provider_limits:
            self.register_provider(provider)

        limits = self._provider_limits[provider]

        # Check circuit breaker first (don't count rejected requests)
        if limits.circuit_state == CircuitState.OPEN:
            if (
                limits.circuit_open_time
                and time.time() - limits.circuit_open_time
                > self._config.circuit_breaker_reset_timeout
            ):
                limits.circuit_state = CircuitState.HALF_OPEN
            else:
                return False

        # Try to acquire semaphore for concurrent requests
        try:
            # Try non-blocking acquire first
            if limits.semaphore.locked():
                # Wait with timeout - this is concurrency limiting, not rate limiting
                start_time = time.time()
                await asyncio.wait_for(limits.semaphore.acquire(), timeout=timeout)
                wait_time = time.time() - start_time
                limits.metrics.total_wait_time += wait_time
                # Note: Don't record semaphore waits as rate limit windows
                # This is concurrency control, not rate limiting
            else:
                await limits.semaphore.acquire()
        except asyncio.TimeoutError:
            return False

        # At this point, we have semaphore access and will process the request
        limits.metrics.total_requests += 1

        # Check rate limiting tokens
        token_wait_start = time.time()

        while time.time() - token_wait_start < timeout:
            with limits.lock:
                self._refill_tokens(limits)
                if limits.tokens > 0:
                    limits.tokens -= 1
                    # Record metrics only if we had to wait for tokens (rate limiting)
                    wait_time = time.time() - token_wait_start
                    if wait_time >= RATE_LIMIT_DETECTION_THRESHOLD_MS:
                        # Count successful requests that were rate-limited
                        limits.metrics.rate_limited_requests += 1
                        limits.metrics.last_rate_limit = time.time()
                        limits.metrics.rate_limit_windows.append(
                            (token_wait_start, time.time())
                        )
                    return True

            # Wait a short time before checking again
            await asyncio.sleep(0.01)

        # Timeout exceeded - this is a rate limiting failure
        # Record the window and update last_rate_limit but don't increment
        # rate_limited_requests (that's only for successful requests that waited)
        limits.metrics.last_rate_limit = time.time()
        limits.metrics.rate_limit_windows.append((token_wait_start, time.time()))

        limits.semaphore.release()
        return False

    def release(self, provider: Any):
        """Release a concurrent request slot."""
        if provider in self._provider_limits:
            limits = self._provider_limits[provider]
            limits.semaphore.release()

    def _refill_tokens(self, limits: ProviderLimits):
        """Refill rate limiting tokens."""
        now = time.time()
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

        if success:
            limits.consecutive_failures = 0
            if limits.circuit_state == CircuitState.HALF_OPEN:
                limits.circuit_state = CircuitState.CLOSED
        else:
            limits.consecutive_failures += 1
            if (
                limits.consecutive_failures >= self._config.circuit_breaker_threshold
                and limits.circuit_state == CircuitState.CLOSED
            ):
                limits.circuit_state = CircuitState.OPEN
                limits.circuit_open_time = time.time()
                limits.metrics.circuit_trips += 1
                limits.metrics.last_circuit_trip = time.time()
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


# Legacy support for the simple RateLimiter
@dataclass
class SimpleLimiter:
    """Simple rate limiter implementation."""

    max_requests_per_minute: int
    max_concurrent_requests: int

    def __post_init__(self):
        self._lock = Lock()
        self._semaphore = threading.Semaphore(self.max_concurrent_requests)
        self._tokens = self.max_requests_per_minute
        self._last_refill = time.monotonic()

    def acquire(self) -> bool:
        """Acquire a token from the rate limiter."""
        with self._lock:
            self._refill()
            if self._tokens > 0:
                self._tokens -= 1
                return True
            return False

    def _refill(self):
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        refill_tokens = int(elapsed * (self.max_requests_per_minute / 60))
        if refill_tokens > 0:
            self._tokens = min(
                self.max_requests_per_minute, self._tokens + refill_tokens
            )
            self._last_refill = now


# Singleton instance
_rate_limiter_instance = None
_global_rate_limiter = None


def get_global_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    global _global_rate_limiter
    if _global_rate_limiter is None:
        _global_rate_limiter = RateLimiter()
    return _global_rate_limiter


def get_rate_limiter(provider: str, config) -> SimpleLimiter:
    """Get rate limiter for the specified provider."""
    if provider == "shazam":
        return SimpleLimiter(
            max_requests_per_minute=config.shazam_max_rpm,
            max_concurrent_requests=config.shazam_max_concurrent,
        )
    elif provider == "acrcloud":
        return SimpleLimiter(
            max_requests_per_minute=config.acrcloud_max_rpm,
            max_concurrent_requests=config.acrcloud_max_concurrent,
        )
    else:
        raise ValueError(f"Unknown provider: {provider}")
