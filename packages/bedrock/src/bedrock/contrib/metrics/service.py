"""Stateless metrics service with structured logging and provider dispatch."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping

from ...logging import get_logger
from .base import MetricsProvider
from .exc import MetricsProviderError, MetricsValidationError
from .settings import MetricsSettings

logger = get_logger(__name__)

METRIC_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_.\-:]*$")
"""Allowed metric name characters.

Names must start with an ASCII letter or underscore, followed by ASCII
letters, digits, underscores, dots, hyphens, or colons. This matches the
union of Prometheus, OpenTelemetry, and StatsD name rules so any future
provider adapter can consume names without rewriting.
"""

_COUNT = "count"
_GAUGE = "gauge"
_NO_PROVIDER = "none"


class MetricsService:
    """Stateless metrics entry point.

    The service validates input, emits exactly one structured invoke log event
    per valid call, and forwards the event to the configured
    :class:`MetricsProvider`. No counter/gauge state is kept in-process:
    ``count`` is an increment event and ``gauge`` is an observation of the
    current value.

    Without a configured provider the service still works: every call is
    recorded to the Bedrock logger and nothing is forwarded.

    Usage::

        from bedrock.contrib.metrics import metrics

        metrics.count("orders.created", tags={"channel": "web"})
        metrics.gauge("queue.depth", 42)

        await metrics.acount("orders.created")
        await metrics.agauge("queue.depth", 42)
    """

    def __init__(self, settings: MetricsSettings | None = None) -> None:
        self._settings = settings or MetricsSettings()
        self._provider: MetricsProvider | None = None

    @property
    def settings(self) -> MetricsSettings:
        """Return the active metrics settings."""
        return self._settings

    @property
    def provider(self) -> MetricsProvider | None:
        """Return the configured provider, or ``None`` in logging-only mode."""
        return self._provider

    def configure(
        self,
        provider: MetricsProvider | None = None,
        settings: MetricsSettings | None = None,
    ) -> MetricsProvider | None:
        """Configure the service with a provider and/or new settings.

        Args:
            provider: Provider instance to forward events to. ``None`` keeps or
                selects the default logging-only mode.
            settings: Replacement settings instance. ``None`` keeps the current
                settings.

        Returns:
            The configured provider, or ``None`` in logging-only mode.

        Raises:
            MetricsValidationError: If ``provider`` is not a ``MetricsProvider``.
        """
        if settings is not None:
            self._settings = settings
        if provider is not None and not isinstance(provider, MetricsProvider):
            raise MetricsValidationError("Metrics provider must be a MetricsProvider instance.")
        self._provider = provider
        return self._provider

    def count(self, name: str, value: int | float = 1, tags: Mapping[str, str] | None = None) -> None:
        """Record a counter increment event.

        Args:
            name: Metric name matching :data:`METRIC_NAME_RE`.
            value: Non-negative finite increment (default ``1``).
            tags: Optional tag mapping; copied and normalized before use.

        Raises:
            MetricsValidationError: If name, value, or tags are invalid.
            MetricsProviderError: If the provider fails and strict mode is on.
        """
        self._invoke_sync(_COUNT, name, value, tags)

    def gauge(self, name: str, value: int | float, tags: Mapping[str, str] | None = None) -> None:
        """Record a gauge observation of the current value.

        Args:
            name: Metric name matching :data:`METRIC_NAME_RE`.
            value: Finite current value; may be negative.
            tags: Optional tag mapping; copied and normalized before use.

        Raises:
            MetricsValidationError: If name, value, or tags are invalid.
            MetricsProviderError: If the provider fails and strict mode is on.
        """
        self._invoke_sync(_GAUGE, name, value, tags)

    async def acount(self, name: str, value: int | float = 1, tags: Mapping[str, str] | None = None) -> None:
        """Asynchronous variant of :meth:`count`."""
        await self._invoke_async(_COUNT, name, value, tags)

    async def agauge(self, name: str, value: int | float, tags: Mapping[str, str] | None = None) -> None:
        """Asynchronous variant of :meth:`gauge`."""
        await self._invoke_async(_GAUGE, name, value, tags)

    def close(self) -> None:
        """Close the configured provider and return to logging-only mode."""
        if self._provider is not None:
            self._provider.close()
            self._provider = None

    async def aclose(self) -> None:
        """Asynchronous variant of :meth:`close`."""
        if self._provider is not None:
            await self._provider.aclose()
            self._provider = None

    # -- Internal ---------------------------------------------------------

    def _validate_name(self, name: str) -> str:
        if not isinstance(name, str) or not name:
            raise MetricsValidationError("Metric name must be a non-empty string.")
        if len(name) > self._settings.max_name_length:
            raise MetricsValidationError(f"Metric name exceeds the {self._settings.max_name_length} character limit.")
        if METRIC_NAME_RE.match(name) is None:
            raise MetricsValidationError(
                "Metric name must start with a letter or underscore and contain only "
                "letters, digits, '_', '.', '-', or ':'."
            )
        return name

    def _validate_value(self, metric_type: str, value: int | float) -> int | float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise MetricsValidationError("Metric value must be an int or float.")
        if not math.isfinite(value):
            raise MetricsValidationError("Metric value must be finite (no NaN or Inf).")
        if metric_type == _COUNT and value < 0:
            raise MetricsValidationError("Count value must not be negative.")
        return value

    def _validate_tags(self, tags: Mapping[str, str] | None) -> dict[str, str]:
        if tags is None:
            return {}
        if not isinstance(tags, Mapping):
            raise MetricsValidationError("Metric tags must be a mapping of string keys to string values.")
        if len(tags) > self._settings.max_tags:
            raise MetricsValidationError(f"Metric tags exceed the {self._settings.max_tags} tag limit.")
        normalized: dict[str, str] = {}
        for key, tag_value in tags.items():
            if not isinstance(key, str) or not key:
                raise MetricsValidationError("Metric tag keys must be non-empty strings.")
            if len(key) > self._settings.max_tag_key_length:
                raise MetricsValidationError(
                    f"Metric tag key exceeds the {self._settings.max_tag_key_length} character limit."
                )
            if METRIC_NAME_RE.match(key) is None:
                raise MetricsValidationError(
                    "Metric tag keys must start with a letter or underscore and contain only "
                    "letters, digits, '_', '.', '-', or ':'."
                )
            if not isinstance(tag_value, str):
                raise MetricsValidationError("Metric tag values must be strings.")
            if len(tag_value) > self._settings.max_tag_value_length:
                raise MetricsValidationError(
                    f"Metric tag value exceeds the {self._settings.max_tag_value_length} character limit."
                )
            normalized[key] = tag_value
        return normalized

    def _log_invoke(self, metric_type: str, name: str, value: int | float, tags: dict[str, str]) -> None:
        provider_name = self._provider.name if self._provider is not None else _NO_PROVIDER
        logger.bind(
            metric_type=metric_type,
            metric_name=name,
            value=value,
            tags=tags,
            provider=provider_name,
        ).info("metrics invoke")

    def _handle_provider_error(self, metric_type: str, name: str, exc: Exception) -> None:
        provider_name = self._provider.name if self._provider is not None else _NO_PROVIDER
        if self._settings.strict:
            raise MetricsProviderError(f"Metrics provider '{provider_name}' failed to record '{name}'.") from exc
        # Fail-open: log only the exception type and bounded metric context.
        # Never log the exception message, tag values, or object reprs here —
        # they may carry credentials or unbounded content.
        logger.bind(
            metric_type=metric_type,
            metric_name=name,
            provider=provider_name,
            error_type=f"{type(exc).__module__}.{type(exc).__qualname__}",
        ).warning("metrics provider call failed")

    def _invoke_sync(self, metric_type: str, name: str, value: int | float, tags: Mapping[str, str] | None) -> None:
        clean_name = self._validate_name(name)
        clean_value = self._validate_value(metric_type, value)
        clean_tags = self._validate_tags(tags)
        self._log_invoke(metric_type, clean_name, clean_value, clean_tags)
        if self._provider is None:
            return
        try:
            if metric_type == _COUNT:
                self._provider.count(clean_name, clean_value, clean_tags)
            else:
                self._provider.gauge(clean_name, clean_value, clean_tags)
        except MetricsValidationError:
            raise
        except Exception as exc:
            self._handle_provider_error(metric_type, clean_name, exc)

    async def _invoke_async(
        self, metric_type: str, name: str, value: int | float, tags: Mapping[str, str] | None
    ) -> None:
        clean_name = self._validate_name(name)
        clean_value = self._validate_value(metric_type, value)
        clean_tags = self._validate_tags(tags)
        self._log_invoke(metric_type, clean_name, clean_value, clean_tags)
        if self._provider is None:
            return
        try:
            if metric_type == _COUNT:
                await self._provider.acount(clean_name, clean_value, clean_tags)
            else:
                await self._provider.agauge(clean_name, clean_value, clean_tags)
        except MetricsValidationError:
            raise
        except Exception as exc:
            self._handle_provider_error(metric_type, clean_name, exc)


metrics = MetricsService()
