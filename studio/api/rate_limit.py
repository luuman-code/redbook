"""API rate limiting"""
import os
from fastapi import Request, HTTPException, status
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Rate limit config
RATE_LIMIT_GENERAL = os.getenv("RATE_LIMIT_GENERAL", "100/minute")
RATE_LIMIT_GENERATE = os.getenv("RATE_LIMIT_GENERATE", "10/minute")

# Create limiter
limiter = Limiter(key_func=get_remote_address)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Rate limit exceeded handler"""
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Too many requests, please try again later. Limit: {RATE_LIMIT_GENERAL}",
    )