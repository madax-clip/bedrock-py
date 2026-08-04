"""Process-local rolling-window rate limiter."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from .entities import RateLimitDecision
from .exc import InvalidRateLimitConfigError, InvalidRateLimitKeyError


class RateLimit:
    """Thread-safe, process-local rolling-window admission decider.

    State lives only in this instance's memory; it is not shared across
    processes, persisted, or registered globally. Decisions are deterministic
    when a fixed ``clock`` is injected.

    Args:
        limit: Maximum number of admitted events per key within ``window``.
        window: Length of the rolling window in seconds.
        clock: Monotonic time source returning seconds; defaults to
            :func:`time.monotonic`.

    Raises:
        InvalidRateLimitConfigError: If ``limit`` or ``window`` is not positive.
    """

    def __init__(self, limit: int, window: float, clock: Callable[[], float] = time.monotonic) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise InvalidRateLimitConfigError(f"Rate limit 'limit' must be a positive integer, got {limit!r}.")
        if isinstance(window, bool) or not isinstance(window, int | float) or window <= 0:
            raise InvalidRateLimitConfigError(f"Rate limit 'window' must be a positive number, got {window!r}.")
        self._limit = limit
        self._window = float(window)
        self._clock = clock
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    @property
    def limit(self) -> int:
        """Configured maximum admitted events per key within the window."""
        return self._limit

    @property
    def window(self) -> float:
        """Configured rolling window length in seconds."""
        return self._window

    def check(self, key: str) -> RateLimitDecision:
        """Decide whether one event for ``key`` is admitted right now.

        An event at exactly ``now - window`` is expired. A denied decision
        never consumes a slot.

        Args:
            key: Non-empty identifier of the limited subject.

        Returns:
            Immutable admission decision for this event.

        Raises:
            InvalidRateLimitKeyError: If ``key`` is not a non-empty string.
        """
        if not isinstance(key, str) or not key:
            raise InvalidRateLimitKeyError(f"Rate limit key must be a non-empty string, got {key!r}.")
        with self._lock:
            now = self._clock()
            events = self._events[key]
            cutoff = now - self._window
            while events and events[0] <= cutoff:
                events.popleft()
            if not events:
                # Drop the stale empty entry and re-create it on demand so a
                # key whose window fully expired leaves no state behind.
                del self._events[key]
                events = self._events[key]
            if len(events) >= self._limit:
                return RateLimitDecision(
                    allowed=False,
                    remaining=0,
                    retry_after=max(events[0] + self._window - now, 0.0),
                )
            events.append(now)
            return RateLimitDecision(allowed=True, remaining=self._limit - len(events), retry_after=None)
