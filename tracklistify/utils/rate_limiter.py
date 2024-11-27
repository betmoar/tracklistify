"""
Rate limiting functionality for API calls with metrics, circuit breaker, and alerts.
"""

# Standard library imports
import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from threading import Lock, Semaphore
from typing import Dict, List, Optional, Tuple, Type

# Local/package imports
from tracklistify.providers.base import TrackIdentificationProvider
from tracklistify.utils.logger import logger


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

    max_requests_per_minute: int = 60
    max_concurrent_requests: int = 10
    tokens: int = field(default_factory=lambda: 60)
    last_update: float = field(default_factory=time.time)
    semaphore: Semaphore = field(default_factory=lambda: Semaphore(10))
    lock: Lock = field(default_factory=Lock)
    metrics: RateLimitMetrics = field(default_factory=RateLimitMetrics)
    circuit_state: CircuitState = field(default=CircuitState.CLOSED)
    circuit_open_time: Optional[float] = None
    consecutive_failures: int = 0


@dataclass
class RateLimiter:
    """Rate limiter implementation."""

    max_requests_per_minute: int
    max_concurrent_requests: int

    def __post_init__(self):
        self._lock = Lock()
        self._semaphore = Semaphore(self.max_concurrent_requests)
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


def get_rate_limiter(provider: str, config) -> RateLimiter:
    """Get rate limiter for the specified provider."""
    if provider == "shazam":
        return RateLimiter(
            max_requests_per_minute=config.shazam_max_rpm,
            max_concurrent_requests=config.shazam_max_concurrent,
        )
    elif provider == "acrcloud":
        return RateLimiter(
            max_requests_per_minute=config.acrcloud_max_rpm,
            max_concurrent_requests=config.acrcloud_max_concurrent,
        )
    else:
        raise ValueError(f"Unknown provider: {provider}")
