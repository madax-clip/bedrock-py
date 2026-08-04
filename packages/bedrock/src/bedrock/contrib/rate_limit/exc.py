"""Exception types for the Bedrock rate limit package."""

from __future__ import annotations

from ...exc import BedrockExc


class RateLimitError(BedrockExc):
    """Base exception for rate limit failures."""

    detail: str = "Rate limit error."


class InvalidRateLimitConfigError(RateLimitError):
    """Raised when a rate limit is configured with a non-positive limit or window."""

    detail: str = "Rate limit configuration must use a positive limit and window."


class InvalidRateLimitKeyError(RateLimitError):
    """Raised when a rate limit check is performed with an empty key."""

    detail: str = "Rate limit key must be a non-empty string."
