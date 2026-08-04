"""Public Bedrock metrics API.

Usage::

    from bedrock.contrib.metrics import MetricsRegistry

    metrics = MetricsRegistry()
    metrics.counter("request_count")
    metrics.increment("request_count")
    metrics.gauge("active_connections")
    metrics.set_gauge("active_connections", 12)
    metrics.snapshot()
"""

from __future__ import annotations

from .entities import MetricSnapshot
from .exc import (
    InvalidMetricNameError,
    MetricAlreadyDeclaredError,
    MetricKindMismatchError,
    MetricNotDeclaredError,
    MetricsError,
)
from .service import MetricsRegistry

__all__ = [
    "InvalidMetricNameError",
    "MetricAlreadyDeclaredError",
    "MetricKindMismatchError",
    "MetricNotDeclaredError",
    "MetricSnapshot",
    "MetricsError",
    "MetricsRegistry",
]
