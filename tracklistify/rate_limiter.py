"""
Rate limiting functionality for API calls with metrics, circuit breaker, and alerts.
"""

import asyncio
import time
from dataclasses import dataclass, field
from threading import Lock, Semaphore
from typing import Dict, Optional, Type, List, Tuple
from enum import Enum
from datetime import datetime, timedelta

from .config import TrackIdentificationConfig, get_config
from .logger import logger
from .providers.base import TrackIdentificationProvider

class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"      # Rate limit exceeded, blocking requests
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

class RateLimiter:
    """Token bucket rate limiter with metrics, circuit breaker, and alerts."""
    
    def __init__(self):
        """Initialize rate limiter."""
        self._config = get_config()
        self._provider_limits: Dict[Type[TrackIdentificationProvider], ProviderLimits] = {}
        self._lock = Lock()
        self._alert_callbacks: List[callable] = []
        logger.info("Rate limiter initialized with per-provider limits and circuit breaker")
        
    def register_alert_callback(self, callback: callable) -> None:
        """
        Register a callback for rate limit alerts.
        
        Args:
            callback: Function to call with alert message
        """
        self._alert_callbacks.append(callback)
        
    def _send_alert(self, provider_class: Type[TrackIdentificationProvider], message: str) -> None:
        """Send alert to all registered callbacks."""
        for callback in self._alert_callbacks:
            try:
                callback(f"Rate Limit Alert - {provider_class.__name__}: {message}")
            except Exception as e:
                logger.error(f"Failed to send rate limit alert: {e}")
                
    def _check_circuit_breaker(self, provider_class: Type[TrackIdentificationProvider]) -> bool:
        """
        Check if circuit breaker allows requests.
        
        Args:
            provider_class: Provider class to check
            
        Returns:
            bool: True if requests allowed, False if circuit is open
        """
        limits = self._provider_limits[provider_class]
        
        if limits.circuit_state == CircuitState.OPEN:
            # Check if enough time has passed to try half-open state
            if time.time() - limits.circuit_open_time > self._config.circuit_breaker_reset_timeout:
                limits.circuit_state = CircuitState.HALF_OPEN
                logger.info(f"Circuit breaker for {provider_class.__name__} entering half-open state")
                self._send_alert(provider_class, "Circuit breaker entering half-open state")
            else:
                return False
                
        return True
        
    def _update_circuit_breaker(self, provider_class: Type[TrackIdentificationProvider], success: bool) -> None:
        """Update circuit breaker state based on request result."""
        limits = self._provider_limits[provider_class]
        
        if success:
            if limits.circuit_state == CircuitState.HALF_OPEN:
                limits.circuit_state = CircuitState.CLOSED
                limits.consecutive_failures = 0
                logger.info(f"Circuit breaker for {provider_class.__name__} closed")
                self._send_alert(provider_class, "Circuit breaker closed - service recovered")
        else:
            limits.consecutive_failures += 1
            if limits.consecutive_failures >= self._config.circuit_breaker_threshold:
                if limits.circuit_state != CircuitState.OPEN:
                    limits.circuit_state = CircuitState.OPEN
                    limits.circuit_open_time = time.time()
                    limits.metrics.circuit_trips += 1
                    limits.metrics.last_circuit_trip = time.time()
                    logger.warning(f"Circuit breaker for {provider_class.__name__} opened")
                    self._send_alert(provider_class, 
                                   f"Circuit breaker opened after {limits.consecutive_failures} failures")

    def get_metrics(self, provider_class: Type[TrackIdentificationProvider]) -> Dict:
        """
        Get rate limiting metrics for a provider.
        
        Args:
            provider_class: Provider class to get metrics for
            
        Returns:
            Dict containing metrics
        """
        limits = self._provider_limits.get(provider_class)
        if not limits:
            return {}
            
        metrics = limits.metrics
        return {
            "total_requests": metrics.total_requests,
            "rate_limited_requests": metrics.rate_limited_requests,
            "rate_limited_percentage": (metrics.rate_limited_requests / metrics.total_requests * 100 
                                      if metrics.total_requests > 0 else 0),
            "average_wait_time": (metrics.total_wait_time / metrics.rate_limited_requests 
                                if metrics.rate_limited_requests > 0 else 0),
            "last_rate_limit": metrics.last_rate_limit,
            "circuit_trips": metrics.circuit_trips,
            "last_circuit_trip": metrics.last_circuit_trip,
            "current_state": limits.circuit_state.value,
            "consecutive_failures": limits.consecutive_failures
        }

    def register_provider(self, provider_class: Type[TrackIdentificationProvider], 
                         max_requests_per_minute: Optional[int] = None,
                         max_concurrent_requests: Optional[int] = None) -> None:
        """
        Register a provider with custom rate limits.
        
        Args:
            provider_class: Provider class to register
            max_requests_per_minute: Maximum requests per minute (defaults to config value)
            max_concurrent_requests: Maximum concurrent requests (defaults to config value)
        """
        with self._lock:
            if provider_class not in self._provider_limits:
                limits = ProviderLimits(
                    max_requests_per_minute=max_requests_per_minute or self._config.max_requests_per_minute,
                    max_concurrent_requests=max_concurrent_requests or self._config.max_concurrent_requests,
                    tokens=max_requests_per_minute or self._config.max_requests_per_minute,
                    semaphore=Semaphore(max_concurrent_requests or self._config.max_concurrent_requests)
                )
                self._provider_limits[provider_class] = limits
                logger.info(f"Registered rate limits for {provider_class.__name__}: "
                          f"{limits.max_requests_per_minute} rpm, "
                          f"{limits.max_concurrent_requests} concurrent")

    def _refill(self, provider_class: Type[TrackIdentificationProvider]) -> None:
        """
        Refill tokens for a specific provider.
        
        Args:
            provider_class: Provider class to refill tokens for
        """
        if not self._config.rate_limit_enabled:
            return

        limits = self._provider_limits.get(provider_class)
        if not limits:
            return

        now = time.time()
        elapsed = now - limits.last_update
        
        # Calculate tokens to add (1 token per (60/max_requests) seconds)
        new_tokens = int(elapsed / (60.0 / limits.max_requests_per_minute))
        if new_tokens > 0:
            old_tokens = limits.tokens
            limits.tokens = min(
                limits.tokens + new_tokens,
                limits.max_requests_per_minute
            )
            limits.last_update = now
            logger.debug(f"Refilled {new_tokens} tokens for {provider_class.__name__} "
                        f"({old_tokens} -> {limits.tokens})")
            
    async def acquire(self, provider_class: Type[TrackIdentificationProvider], 
                     timeout: Optional[float] = None) -> bool:
        """
        Acquire both a rate limit token and a concurrent request slot.
        
        Args:
            provider_class: Provider class requesting the token
            timeout: Maximum time to wait in seconds
            
        Returns:
            bool: True if both token and slot acquired, False if timed out
        """
        if not self._config.rate_limit_enabled:
            return True

        limits = self._provider_limits.get(provider_class)
        if not limits:
            self.register_provider(provider_class)
            limits = self._provider_limits[provider_class]

        # Update metrics
        limits.metrics.total_requests += 1

        # Check circuit breaker
        if not self._check_circuit_breaker(provider_class):
            logger.warning(f"Circuit breaker open for {provider_class.__name__}, request rejected")
            return False

        start_time = time.time()
        wait_start = None
        
        # Try to acquire both rate limit token and concurrent slot
        while True:
            with limits.lock:
                self._refill(provider_class)
                
                if limits.tokens > 0:
                    try:
                        # Try to acquire concurrent slot with timeout
                        if timeout is not None:
                            elapsed = time.time() - start_time
                            if elapsed >= timeout:
                                self._update_circuit_breaker(provider_class, False)
                                return False
                            remaining_timeout = timeout - elapsed
                        else:
                            remaining_timeout = None
                            
                        # Use asyncio to handle the semaphore timeout
                        if await asyncio.wait_for(
                            asyncio.get_event_loop().run_in_executor(
                                None, limits.semaphore.acquire
                            ),
                            timeout=remaining_timeout
                        ):
                            limits.tokens -= 1
                            if wait_start:
                                wait_duration = time.time() - wait_start
                                limits.metrics.total_wait_time += wait_duration
                                limits.metrics.rate_limited_requests += 1
                                limits.metrics.last_rate_limit = time.time()
                                limits.metrics.rate_limit_windows.append((wait_start, time.time()))
                                
                                # Clean up old rate limit windows
                                cutoff = time.time() - 3600  # Keep last hour
                                limits.metrics.rate_limit_windows = [
                                    w for w in limits.metrics.rate_limit_windows if w[1] > cutoff
                                ]
                                
                                logger.info(f"Rate limit wait complete for {provider_class.__name__} "
                                          f"after {wait_duration:.2f}s, token acquired "
                                          f"({limits.tokens}/{limits.max_requests_per_minute} remaining)")
                                
                                # Send alert if wait time exceeds threshold
                                if wait_duration > self._config.rate_limit_alert_threshold:
                                    self._send_alert(
                                        provider_class,
                                        f"High rate limit wait time: {wait_duration:.2f}s"
                                    )
                            else:
                                logger.debug(f"Token acquired immediately for {provider_class.__name__} "
                                           f"({limits.tokens}/{limits.max_requests_per_minute} remaining)")
                            
                            self._update_circuit_breaker(provider_class, True)
                            return True
                            
                    except asyncio.TimeoutError:
                        logger.warning(f"Concurrent request timeout for {provider_class.__name__}")
                        self._update_circuit_breaker(provider_class, False)
                        return False
                
                if wait_start is None:
                    wait_start = time.time()
                    logger.info(f"Rate limit reached for {provider_class.__name__}, "
                              f"waiting for token (0/{limits.max_requests_per_minute} available)")
                    
            # Check overall timeout
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    logger.warning(f"Rate limit timeout reached for {provider_class.__name__} "
                                 f"after {elapsed:.2f}s")
                    self._update_circuit_breaker(provider_class, False)
                    return False
                    
            # Wait before trying again
            await asyncio.sleep(0.1)

    def release(self, provider_class: Type[TrackIdentificationProvider]) -> None:
        """
        Release a concurrent request slot for a provider.
        
        Args:
            provider_class: Provider class to release slot for
        """
        limits = self._provider_limits.get(provider_class)
        if limits:
            limits.semaphore.release()
            logger.debug(f"Released concurrent slot for {provider_class.__name__}")
            
    def get_remaining(self, provider_class: Type[TrackIdentificationProvider]) -> int:
        """
        Get remaining tokens for a provider.
        
        Args:
            provider_class: Provider class to get remaining tokens for
            
        Returns:
            int: Number of remaining tokens
        """
        limits = self._provider_limits.get(provider_class)
        if not limits:
            return 0
            
        with limits.lock:
            self._refill(provider_class)
            return limits.tokens

# Global rate limiter instance
_rate_limiter_instance = None

def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    global _rate_limiter_instance
    if _rate_limiter_instance is None:
        _rate_limiter_instance = RateLimiter()
    return _rate_limiter_instance
