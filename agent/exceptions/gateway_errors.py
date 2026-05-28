"""
Gateway Error Definitions
"""


class GatewayError(Exception):
    """Base exception for all gateway errors."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class APIError(GatewayError):
    """API related errors (non-2xx responses)."""

    def __init__(self, message: str, status_code: int = None, response_body: str = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class AuthenticationError(GatewayError):
    """Authentication/authorization failures."""

    pass


class RateLimitError(GatewayError):
    """Rate limit exceeded errors."""

    def __init__(self, message: str, retry_after: int = None):
        super().__init__(message)
        self.retry_after = retry_after


class TimeoutError(GatewayError):
    """Request timeout errors."""

    pass


class CircuitBreakerOpenError(GatewayError):
    """Circuit breaker is open and rejecting requests."""

    def __init__(self, message: str, failure_count: int = None, next_attempt_time: float = None):
        super().__init__(message)
        self.failure_count = failure_count
        self.next_attempt_time = next_attempt_time
