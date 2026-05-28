"""
Retry Utilities
"""

import asyncio
import functools
from typing import Any, Callable, Optional, Type, Tuple


def retry_with_backoff(
    max_retries: int = 3,
    initial_backoff: float = 1.0,
    max_backoff: float = 60.0,
    backoff_multiplier: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
):
    """
    Decorator for retrying async functions with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        initial_backoff: Initial backoff delay in seconds
        max_backoff: Maximum backoff delay in seconds
        backoff_multiplier: Multiplier for exponential backoff
        exceptions: Tuple of exception types to catch and retry
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = min(initial_backoff * (backoff_multiplier**attempt), max_backoff)
                        await asyncio.sleep(delay)
                    else:
                        raise
            if last_exception:
                raise last_exception

        return wrapper

    return decorator


class RetryContext:
    """Context manager for retry operations with state tracking."""

    def __init__(
        self,
        max_retries: int = 3,
        initial_backoff: float = 1.0,
        max_backoff: float = 60.0,
    ):
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.attempt = 0
        self.last_exception: Optional[Exception] = None

    async def __aenter__(self) -> "RetryContext":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_val is not None:
            self.last_exception = exc_val
            self.attempt += 1
            if self.attempt <= self.max_retries:
                delay = min(self.initial_backoff * (2 ** (self.attempt - 1)), self.max_backoff)
                await asyncio.sleep(delay)
                return True  # Suppress exception and retry
        return False  # Don't suppress - either success or exhausted retries

    @property
    def should_retry(self) -> bool:
        return self.attempt < self.max_retries and self.last_exception is not None
