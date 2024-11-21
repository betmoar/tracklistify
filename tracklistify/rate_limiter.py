"""
Rate limiting functionality for API calls.
"""

import time
from threading import Lock
from typing import Optional

from .config import TrackIdentificationConfig, get_config
from .logger import logger

class RateLimiter:
    """Token bucket rate limiter."""
    
    def __init__(self):
        """Initialize rate limiter."""
        self._config = get_config()
        self._tokens = self._config.max_requests_per_minute
        self._last_update = time.time()
        self._lock = Lock()
        logger.info(f"Rate limiter initialized with {self._tokens} tokens per minute")
        
    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        if not self._config.rate_limit_enabled:
            return

        now = time.time()
        elapsed = now - self._last_update
        
        # Calculate tokens to add (1 token per (60/max_requests) seconds)
        new_tokens = int(elapsed / (60.0 / self._config.max_requests_per_minute))
        if new_tokens > 0:
            old_tokens = self._tokens
            self._tokens = min(
                self._tokens + new_tokens,
                self._config.max_requests_per_minute
            )
            self._last_update = now
            logger.debug(f"Refilled {new_tokens} tokens ({old_tokens} -> {self._tokens})")
            
    def acquire(self, timeout: Optional[float] = None) -> bool:
        """
        Acquire a token, blocking if necessary.
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            bool: True if token acquired, False if timed out
        """
        if not self._config.rate_limit_enabled:
            return True

        start_time = time.time()
        wait_start = None
        
        while True:
            with self._lock:
                self._refill()
                
                if self._tokens > 0:
                    self._tokens -= 1
                    if wait_start:
                        wait_duration = time.time() - wait_start
                        logger.info(f"Rate limit wait complete after {wait_duration:.2f}s, token acquired ({self._tokens} remaining)")
                    else:
                        logger.debug(f"Token acquired immediately ({self._tokens} remaining)")
                    return True
                
                if wait_start is None:
                    wait_start = time.time()
                    logger.info(f"Rate limit reached, waiting for token (0/{self._config.max_requests_per_minute} available)")
                    
            # Check timeout
            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    logger.warning(f"Rate limit timeout reached after {elapsed:.2f}s")
                    return False
                    
            # Wait before trying again
            time.sleep(0.1)
            
    def get_remaining(self) -> int:
        """Get remaining tokens."""
        with self._lock:
            self._refill()
            return self._tokens

# Global rate limiter instance
_rate_limiter_instance = None

def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    global _rate_limiter_instance
    if _rate_limiter_instance is None:
        _rate_limiter_instance = RateLimiter()
    return _rate_limiter_instance
