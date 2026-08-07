"""Abstract provider contract for Bedrock metrics exporters.

A :class:`MetricsProvider` only forwards already-validated metric events to an
external system. Input validation, structured logging, error policy, and
provider dispatch all live in
:class:`~bedrock.contrib.metrics.service.MetricsService`.

V0.2.1 ships no concrete exporter (no Prometheus/OpenTelemetry/StatsD); this
ABC is the stable extension point for future adapters.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Mapping


class MetricsProvider(ABC):
    """Abstract base class for metrics providers.

    Subclasses must implement :meth:`count` and :meth:`gauge`. The async
    variants :meth:`acount` and :meth:`agauge` default to running the sync
    implementation in a worker thread via :func:`asyncio.to_thread`, so
    blocking exporters do not stall the event loop; subclasses with a native
    async client should override them.

    Providers receive already-validated, freshly copied arguments and must not
    mutate the ``tags`` mapping they are given.
    """

    @property
    def name(self) -> str:
        """Human-readable provider name used in structured log events."""
        return type(self).__name__

    @abstractmethod
    def count(self, name: str, value: int | float = 1, tags: Mapping[str, str] | None = None) -> None:
        """Record a counter increment event.

        Args:
            name: Validated metric name.
            value: Non-negative increment amount.
            tags: Normalized, read-only tag mapping (never mutate it).
        """

    @abstractmethod
    def gauge(self, name: str, value: int | float, tags: Mapping[str, str] | None = None) -> None:
        """Record a gauge observation of the current value.

        Args:
            name: Validated metric name.
            value: Current observed value (finite, may be negative).
            tags: Normalized, read-only tag mapping (never mutate it).
        """

    async def acount(self, name: str, value: int | float = 1, tags: Mapping[str, str] | None = None) -> None:
        """Asynchronous variant of :meth:`count`, offloaded to a thread by default."""
        await asyncio.to_thread(self.count, name, value, tags)

    async def agauge(self, name: str, value: int | float, tags: Mapping[str, str] | None = None) -> None:
        """Asynchronous variant of :meth:`gauge`, offloaded to a thread by default."""
        await asyncio.to_thread(self.gauge, name, value, tags)

    def close(self) -> None:  # noqa: B027 — intentional no-op lifecycle hook for subclasses
        """Release provider resources. No-op by default."""

    async def aclose(self) -> None:
        """Asynchronous variant of :meth:`close`."""
        self.close()
