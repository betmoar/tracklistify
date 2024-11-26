"""
Rate limiting functionality for API calls.
"""

import time
import enum
from dataclasses import dataclass
from threading import Lock
from typing import Optional, Dict, Type

from .config import TrackIdentificationConfig, get_config
from .logger import logger


class RetryStrategy(enum.Enum):
    """Available retry strategies."""
    CONSTANT = "constant"
    LINEAR = "linear" 
    EXPONENTIAL = "exponential"


@dataclass
class RateLimitConfig:
    """Rate limit configuration for a specific provider."""
    max_requests: int
    time_window: float  # in seconds
    max_concurrent: Optional[int] = None


class RateLimiter:
    """Token bucket rate limiter with retry strategies and per-provider limits."""
    
    def __init__(self) -> None:
        """Initialize rate limiter."""
        self._config: TrackIdentificationConfig = get_config()
        self._tokens: Dict[str, int] = {}  # provider -> tokens
        self._last_update: Dict[str, float] = {}  # provider -> last update time
        self._concurrent: Dict[str, int] = {}  # provider -> current concurrent requests
        self._provider_configs: Dict[str, RateLimitConfig] = {
            # Default global config
            "default": RateLimitConfig(
                max_requests=self._config.max_requests_per_minute,
                time_window=60.0,
                max_concurrent=10
            ),
            # Provider-specific configs
            "shazam": RateLimitConfig(
                max_requests=self._config.max_requests_per_minute,
                time_window=60.0,
                max_concurrent=5
            ),
            "acrcloud": RateLimitConfig(
                max_requests=self._config.max_requests_per_minute,
                time_window=60.0,
                max_concurrent=5
            )
        }
        self._lock = Lock()
        
        # Initialize tokens for each provider
        for provider, config in self._provider_configs.items():
            self._tokens[provider] = config.max_requests
            self._last_update[provider] = time.time()
            self._concurrent[provider] = 0
            
        logger.info("Rate limiter initialized with per-provider limits")

    def _get_retry_delay(self, attempt: int, provider: str = "default") -> float:
        """
        Calculate retry delay based on strategy.
        
        Args:
            attempt: Current attempt number (1-based)
            provider: Provider name for rate limiting
            
        Returns:
            float: Delay in seconds before next attempt
        """
        base_delay = self._config.retry_base_delay
        max_delay = self._config.retry_max_delay
        
        if self._config.retry_strategy == RetryStrategy.CONSTANT.value:
            delay = base_delay
        elif self._config.retry_strategy == RetryStrategy.LINEAR.value:
            delay = base_delay * attempt
        else:  # EXPONENTIAL
            delay = base_delay * (2 ** (attempt - 1))
            
        return min(delay, max_delay)

    def _refill(self, provider: str = "default") -> None:
        """
        Refill tokens based on elapsed time.
        
        Args:
            provider: Provider name for rate limiting
        """
        if not self._config.rate_limit_enabled:
            return

        now = time.time()
        elapsed = now - self._last_update[provider]
        config = self._provider_configs[provider]
        
        # Calculate tokens to add based on time window
        new_tokens = int(elapsed / (config.time_window / config.max_requests))
        if new_tokens > 0:
            old_tokens = self._tokens[provider]
            self._tokens[provider] = min(
                self._tokens[provider] + new_tokens,
                config.max_requests
            )
            self._last_update[provider] = now
            logger.debug(
                f"[{provider}] Refilled {new_tokens} tokens "
                f"({old_tokens} -> {self._tokens[provider]})"
            )
            
    def acquire(
        self,
        timeout: Optional[float] = None,
        provider: str = "default",
        retry_count: int = 0
    ) -> bool:
        """
        Acquire a token, blocking if necessary.
        
        Args:
            timeout: Maximum time to wait in seconds
            provider: Provider name for rate limiting
            retry_count: Current retry attempt (0-based)
            
        Returns:
            bool: True if token acquired, False if timed out
        """
        if not self._config.rate_limit_enabled:
            return True

        if provider not in self._provider_configs:
            provider = "default"
            
        config = self._provider_configs[provider]
        start_time = time.time()
        wait_start = None
        
        while True:
            with self._lock:
                self._refill(provider)
                
                # Check both token and concurrent limits
                if (self._tokens[provider] > 0 and 
                    (config.max_concurrent is None or 
                     self._concurrent[provider] < config.max_concurrent)):
                    
                    self._tokens[provider] -= 1
                    self._concurrent[provider] += 1
                    
                    if wait_start:
                        wait_duration = time.time() - wait_start
                        logger.info(
                            f"[/n{provider}] Rate limit wait complete after "
                            f"{wait_duration:.2f}s, token acquired "
                            f"({self._tokens[provider]} remaining, "
                            f"{self._concurrent[provider]} concurrent)"
                        )
                    else:
                        logger.debug(
                            f"[/n{provider}] Token acquired immediately "
                            f"({self._tokens[provider]} remaining, "
                            f"{self._concurrent[provider]} concurrent)"
                        )
                    return True
                
                if wait_start is None:
                    wait_start = time.time()
                    logger.info(
                        f"[/n{provider}] Rate limit reached, waiting for token "
                        f"(0/{config.max_requests} available, "
                        f"{self._concurrent[provider]}/{config.max_concurrent} concurrent)"
                    )
                    
            # Check timeout
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    logger.warning(
                        f"[{provider}] Rate limit timeout reached after {elapsed:.2f}s"
                    )
                    return False
                    
            # Calculate and apply backoff delay
            delay = self._get_retry_delay(retry_count + 1, provider)
            time.sleep(delay)
            
    def release(self, provider: str = "default") -> None:
        """
        Release a concurrent request slot.
        
        Args:
            provider: Provider name for rate limiting
        """
        with self._lock:
            if provider in self._concurrent and self._concurrent[provider] > 0:
                self._concurrent[provider] -= 1
                logger.debug(
                    f"[{provider}] Released concurrent slot "
                    f"({self._concurrent[provider]} remaining)"
                )

    def get_remaining(self, provider: str = "default") -> int:
        """
        Get remaining tokens.
        
        Args:
            provider: Provider name for rate limiting
            
        Returns:
            int: Number of tokens remaining
        """
        with self._lock:
            self._refill(provider)
            return self._tokens[provider]


# Global rate limiter instance
_rate_limiter_instance: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    global _rate_limiter_instance
    if _rate_limiter_instance is None:
        _rate_limiter_instance = RateLimiter()
    return _rate_limiter_instance
