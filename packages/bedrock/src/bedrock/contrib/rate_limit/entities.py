"""Domain entities for the Bedrock rate limit package."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """Immutable result of a single admission check.

    Attributes:
        allowed: Whether the request is admitted within the rolling window.
        remaining: Number of slots left for the key after this decision.
        retry_after: Seconds until the oldest live event expires when denied,
            otherwise ``None``.
    """

    allowed: bool
    remaining: int
    retry_after: float | None
