"""Entity models for the Bedrock metrics system."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MetricSnapshot:
    """Immutable point-in-time view of a single metric.

    Attributes:
        name: Declared metric name (lowercase snake_case).
        value: Current metric value (``int`` for counters, ``int | float`` for gauges).
    """

    name: str
    value: int | float
