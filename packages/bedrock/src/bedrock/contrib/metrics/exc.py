"""Exception types for the Bedrock metrics system."""

from __future__ import annotations

from ...exc import BedrockExc


class MetricsError(BedrockExc):
    """Base exception for metrics operation failures."""

    detail: str = "Metrics operation failed."


class MetricsValidationError(MetricsError):
    """Raised when a metric name, value, or tags fail validation."""

    detail: str = "Invalid metric name, value, or tags."


class MetricsProviderError(MetricsError):
    """Raised when a metrics provider fails and strict mode is enabled.

    In the default fail-open mode provider failures are only logged and
    never raised into the business path.
    """

    detail: str = "Metrics provider call failed."
