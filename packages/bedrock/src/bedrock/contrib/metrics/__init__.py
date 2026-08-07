"""Public Bedrock metrics API.

Usage::

    from bedrock.contrib.metrics import metrics

    metrics.count("orders.created", tags={"channel": "web"})
    metrics.gauge("queue.depth", 42)

    await metrics.acount("orders.created")
    await metrics.agauge("queue.depth", 42)
"""

from __future__ import annotations

from .base import MetricsProvider
from .exc import MetricsError, MetricsProviderError, MetricsValidationError
from .service import MetricsService, metrics
from .settings import MetricsSettings

__all__ = [
    "MetricsError",
    "MetricsProvider",
    "MetricsProviderError",
    "MetricsService",
    "MetricsSettings",
    "MetricsValidationError",
    "metrics",
]
