"""Exception types for the Bedrock metrics system."""

from __future__ import annotations

from ...exc import BedrockExc


class MetricsError(BedrockExc):
    """Base exception for metrics operation failures."""

    detail: str = "Metrics operation failed."


class InvalidMetricNameError(MetricsError):
    """Raised when a metric name is empty or not lowercase snake_case."""

    detail: str = "Metric name must be non-empty lowercase snake_case."


class MetricAlreadyDeclaredError(MetricsError):
    """Raised when declaring a metric name that is already declared."""

    detail: str = "Metric name is already declared."


class MetricNotDeclaredError(MetricsError):
    """Raised when operating on a metric that has not been declared."""

    detail: str = "Metric has not been declared."


class MetricKindMismatchError(MetricsError):
    """Raised when an operation does not match the declared metric kind."""

    detail: str = "Operation does not match the declared metric kind."
