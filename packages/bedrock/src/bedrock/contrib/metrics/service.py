"""Thread-safe in-process metrics registry."""

from __future__ import annotations

import re
import threading
from enum import StrEnum

from .entities import MetricSnapshot
from .exc import (
    InvalidMetricNameError,
    MetricAlreadyDeclaredError,
    MetricKindMismatchError,
    MetricNotDeclaredError,
)

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class _MetricKind(StrEnum):
    """Internal metric kind discriminator."""

    COUNTER = "counter"
    GAUGE = "gauge"


class MetricsRegistry:
    """In-process, thread-safe registry of declared counters and gauges.

    Metrics must be declared before use with :meth:`counter` or :meth:`gauge`.
    Counters are mutated with :meth:`increment` (negative deltas allowed);
    gauges are mutated with :meth:`set_gauge`. Use :meth:`snapshot` to obtain
    an immutable, name-sorted view of all declared metrics.
    """

    def __init__(self) -> None:
        """Initialize an empty registry with its own mutation lock."""
        self._lock = threading.Lock()
        self._metrics: dict[str, tuple[_MetricKind, int | float]] = {}

    @staticmethod
    def _validate_name(name: str) -> None:
        """Validate that a metric name is non-empty lowercase snake_case.

        Args:
            name: Candidate metric name.

        Raises:
            InvalidMetricNameError: If the name is invalid.
        """
        if not isinstance(name, str) or not _NAME_PATTERN.fullmatch(name):
            raise InvalidMetricNameError(
                f"Metric name must be non-empty lowercase snake_case (e.g. 'request_count'), got {name!r}."
            )

    def _declare(self, name: str, kind: _MetricKind, initial: int | float) -> None:
        """Declare a new metric.

        Args:
            name: Metric name to declare.
            kind: Kind of metric to declare.
            initial: Initial metric value.

        Raises:
            InvalidMetricNameError: If the name is invalid.
            MetricAlreadyDeclaredError: If the name is already declared.
        """
        self._validate_name(name)
        with self._lock:
            if name in self._metrics:
                raise MetricAlreadyDeclaredError(f"Metric {name!r} is already declared.")
            self._metrics[name] = (kind, initial)

    def counter(self, name: str) -> None:
        """Declare a counter metric initialized to ``0``.

        Args:
            name: Metric name (lowercase snake_case).
        """
        self._declare(name, _MetricKind.COUNTER, 0)

    def gauge(self, name: str, initial: int | float = 0) -> None:
        """Declare a gauge metric.

        Args:
            name: Metric name (lowercase snake_case).
            initial: Initial gauge value.
        """
        self._declare(name, _MetricKind.GAUGE, initial)

    def _get_kind(self, name: str) -> _MetricKind:
        """Return the declared kind of a metric.

        Args:
            name: Metric name.

        Raises:
            MetricNotDeclaredError: If the metric has not been declared.
        """
        try:
            return self._metrics[name][0]
        except KeyError:
            raise MetricNotDeclaredError(f"Metric {name!r} has not been declared.") from None

    def increment(self, name: str, amount: int | float = 1) -> int | float:
        """Increment a declared counter and return its new value.

        Negative amounts are allowed and decrement the counter.

        Args:
            name: Declared counter name.
            amount: Delta to add (may be negative).

        Returns:
            The counter value after the increment.

        Raises:
            MetricNotDeclaredError: If the metric has not been declared.
            MetricKindMismatchError: If the metric is not a counter.
        """
        with self._lock:
            if self._get_kind(name) is not _MetricKind.COUNTER:
                raise MetricKindMismatchError(f"Metric {name!r} is not a counter; use set_gauge() instead.")
            kind, value = self._metrics[name]
            new_value = value + amount
            self._metrics[name] = (kind, new_value)
            return new_value

    def set_gauge(self, name: str, value: int | float) -> None:
        """Set the value of a declared gauge.

        Args:
            name: Declared gauge name.
            value: New gauge value.

        Raises:
            MetricNotDeclaredError: If the metric has not been declared.
            MetricKindMismatchError: If the metric is not a gauge.
        """
        with self._lock:
            if self._get_kind(name) is not _MetricKind.GAUGE:
                raise MetricKindMismatchError(f"Metric {name!r} is not a gauge; use increment() instead.")
            self._metrics[name] = (_MetricKind.GAUGE, value)

    def snapshot(self) -> tuple[MetricSnapshot, ...]:
        """Return an immutable, name-sorted snapshot of all declared metrics.

        Returns:
            Tuple of :class:`MetricSnapshot` ordered deterministically by name.
            Snapshots are copies and expose no mutable internal state.
        """
        with self._lock:
            items = sorted(self._metrics.items())
            return tuple(MetricSnapshot(name=name, value=value) for name, (_, value) in items)
