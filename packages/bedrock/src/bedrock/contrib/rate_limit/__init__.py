"""Process-local rate limiting for the Bedrock runtime.

Usage::

    from bedrock.contrib.rate_limit import RateLimit

    rate_limit = RateLimit(limit=5, window=60.0)
    decision = rate_limit.check("user:42")
    if not decision.allowed:
        ...  # retry after decision.retry_after seconds

The limiter keeps all state in process memory. It provides no persistence,
distributed consistency, HTTP middleware, or identity extraction; adapters
compose it with their own framework of choice.
"""

from __future__ import annotations

from .entities import RateLimitDecision
from .exc import InvalidRateLimitConfigError, InvalidRateLimitKeyError, RateLimitError
from .service import RateLimit

__all__ = [
    "InvalidRateLimitConfigError",
    "InvalidRateLimitKeyError",
    "RateLimit",
    "RateLimitDecision",
    "RateLimitError",
]
