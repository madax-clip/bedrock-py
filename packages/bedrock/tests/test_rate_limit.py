"""Tests for the process-local rate limiter in ``bedrock.contrib.rate_limit``.

All admission tests inject a deterministic clock; wall-clock time is only
used for the concurrency invariants.
"""

from __future__ import annotations

import threading
import time

import pytest
from bedrock.contrib.rate_limit import (
    InvalidRateLimitConfigError,
    InvalidRateLimitKeyError,
    RateLimit,
    RateLimitDecision,
)
from bedrock.exc import BedrockExc


class FakeClock:
    """Deterministic monotonic clock controlled by the test."""

    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class TestRateLimitConfigValidation:
    """Constructor validation for limit and window."""

    @pytest.mark.parametrize("limit", [0, -1, -100, 1.5, True, "5"])
    def test_invalid_limit_raises(self, limit: object) -> None:
        with pytest.raises(InvalidRateLimitConfigError):
            RateLimit(limit=limit, window=60.0, clock=FakeClock())

    @pytest.mark.parametrize("window", [0, 0.0, -1, -0.5, True, "60"])
    def test_invalid_window_raises(self, window: object) -> None:
        with pytest.raises(InvalidRateLimitConfigError):
            RateLimit(limit=5, window=window, clock=FakeClock())

    def test_config_errors_are_bedrock_exc(self) -> None:
        with pytest.raises(BedrockExc) as exc_info:
            RateLimit(limit=0, window=0, clock=FakeClock())
        assert "positive" in exc_info.value.detail

    def test_valid_config_exposes_limit_and_window(self) -> None:
        rate_limit = RateLimit(limit=5, window=60, clock=FakeClock())
        assert rate_limit.limit == 5
        assert rate_limit.window == 60.0


class TestRateLimitKeyValidation:
    """Key validation on check."""

    @pytest.mark.parametrize("key", ["", b"bytes", None, 42])
    def test_invalid_key_raises(self, key: object) -> None:
        rate_limit = RateLimit(limit=5, window=60.0, clock=FakeClock())
        with pytest.raises(InvalidRateLimitKeyError):
            rate_limit.check(key)

    def test_key_error_is_bedrock_exc_with_detail(self) -> None:
        rate_limit = RateLimit(limit=5, window=60.0, clock=FakeClock())
        with pytest.raises(BedrockExc) as exc_info:
            rate_limit.check("")
        assert "non-empty" in exc_info.value.detail

    def test_invalid_key_does_not_consume_a_slot(self) -> None:
        clock = FakeClock()
        rate_limit = RateLimit(limit=1, window=60.0, clock=clock)
        with pytest.raises(InvalidRateLimitKeyError):
            rate_limit.check("")
        assert rate_limit.check("user:1").allowed is True


class TestAdmissionAndDenial:
    """Deterministic admission, denial, remaining count, and retry-after."""

    def test_decision_is_immutable(self) -> None:
        rate_limit = RateLimit(limit=1, window=60.0, clock=FakeClock())
        decision = rate_limit.check("user:1")
        assert decision == RateLimitDecision(allowed=True, remaining=0, retry_after=None)
        with pytest.raises(AttributeError):
            decision.allowed = False

    def test_admission_up_to_limit_then_denial(self) -> None:
        clock = FakeClock()
        rate_limit = RateLimit(limit=3, window=60.0, clock=clock)

        first = rate_limit.check("user:1")
        second = rate_limit.check("user:1")
        third = rate_limit.check("user:1")
        denied = rate_limit.check("user:1")

        assert (first.allowed, first.remaining, first.retry_after) == (True, 2, None)
        assert (second.allowed, second.remaining, second.retry_after) == (True, 1, None)
        assert (third.allowed, third.remaining, third.retry_after) == (True, 0, None)
        assert denied.allowed is False
        assert denied.remaining == 0

    def test_retry_after_is_exact_time_until_oldest_event_expires(self) -> None:
        clock = FakeClock()
        rate_limit = RateLimit(limit=2, window=60.0, clock=clock)

        rate_limit.check("user:1")  # t=1000
        clock.advance(20.0)
        rate_limit.check("user:1")  # t=1020
        clock.advance(15.0)  # t=1035

        denied = rate_limit.check("user:1")
        assert denied.allowed is False
        # Oldest event (t=1000) expires at t=1060 -> 25s remaining.
        assert denied.retry_after == pytest.approx(25.0)

    def test_denial_does_not_consume_a_slot(self) -> None:
        clock = FakeClock()
        rate_limit = RateLimit(limit=1, window=60.0, clock=clock)

        assert rate_limit.check("user:1").allowed is True  # t=1000
        clock.advance(59.0)
        assert rate_limit.check("user:1").allowed is False  # t=1059, denied
        clock.advance(1.0)  # t=1060, the recorded event expires
        decision = rate_limit.check("user:1")
        assert decision.allowed is True
        assert decision.remaining == 0

    def test_independent_keys_do_not_affect_each_other(self) -> None:
        clock = FakeClock()
        rate_limit = RateLimit(limit=1, window=60.0, clock=clock)

        assert rate_limit.check("user:1").allowed is True
        assert rate_limit.check("user:1").allowed is False
        assert rate_limit.check("user:2").allowed is True
        assert rate_limit.check("user:3").remaining == 0

    def test_fully_expired_key_leaves_no_state_on_next_check(self) -> None:
        clock = FakeClock()
        rate_limit = RateLimit(limit=1, window=60.0, clock=clock)
        for _ in range(100):
            rate_limit.check("user:1")
            clock.advance(61.0)
        assert len(rate_limit._events) == 1  # single live event from the last check
        assert len(rate_limit._events["user:1"]) == 1


class TestRollingWindowBoundary:
    """Events at exactly ``now - window`` are expired."""

    def test_event_exactly_at_boundary_is_expired(self) -> None:
        clock = FakeClock()
        rate_limit = RateLimit(limit=1, window=60.0, clock=clock)

        rate_limit.check("user:1")  # t=1000
        clock.advance(60.0)  # t=1060; event at 1000 == now - window

        decision = rate_limit.check("user:1")
        assert decision.allowed is True
        assert decision.remaining == 0

    def test_event_just_inside_boundary_is_live(self) -> None:
        clock = FakeClock()
        rate_limit = RateLimit(limit=1, window=60.0, clock=clock)

        rate_limit.check("user:1")  # t=1000
        clock.advance(59.999)  # t=1059.999; event still inside the window

        denied = rate_limit.check("user:1")
        assert denied.allowed is False
        assert denied.retry_after == pytest.approx(0.001)

    def test_window_rolls_as_time_advances(self) -> None:
        clock = FakeClock()
        rate_limit = RateLimit(limit=2, window=10.0, clock=clock)

        rate_limit.check("user:1")  # t=1000
        clock.advance(6.0)
        rate_limit.check("user:1")  # t=1006
        assert rate_limit.check("user:1").allowed is False
        clock.advance(4.0)  # t=1010; first event expires
        assert rate_limit.check("user:1").allowed is True


class TestThreadSafety:
    """Concurrent checks preserve the limit invariant."""

    def test_concurrent_checks_never_exceed_limit(self) -> None:
        rate_limit = RateLimit(limit=50, window=60.0, clock=time.monotonic)
        decisions: list[RateLimitDecision] = []
        decisions_lock = threading.Lock()

        def hammer() -> None:
            local = [rate_limit.check("shared-key") for _ in range(100)]
            with decisions_lock:
                decisions.extend(local)

        threads = [threading.Thread(target=hammer) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        allowed = [d for d in decisions if d.allowed]
        denied = [d for d in decisions if not d.allowed]
        assert len(decisions) == 1_000
        assert len(allowed) == 50
        assert len(denied) == 950
        # Remaining counts on allowed decisions are unique and exhaustive.
        remaining_counts = sorted(d.remaining for d in allowed)
        assert remaining_counts == list(range(50))
        assert all(d.retry_after is not None and d.retry_after >= 0 for d in denied)

    def test_concurrent_checks_on_distinct_keys_are_independent(self) -> None:
        rate_limit = RateLimit(limit=5, window=60.0, clock=time.monotonic)
        allowed_per_key: dict[str, int] = {}
        counts_lock = threading.Lock()

        def hammer(key: str) -> None:
            allowed = sum(1 for _ in range(20) if rate_limit.check(key).allowed)
            with counts_lock:
                allowed_per_key[key] = allowed

        keys = [f"user:{i}" for i in range(20)]
        threads = [threading.Thread(target=hammer, args=(key,)) for key in keys]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert allowed_per_key == dict.fromkeys(keys, 5)
