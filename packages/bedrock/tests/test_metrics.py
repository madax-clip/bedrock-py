"""Tests for the Bedrock contrib metrics module."""

from __future__ import annotations

import threading

import pytest
from bedrock.contrib.metrics import (
    InvalidMetricNameError,
    MetricAlreadyDeclaredError,
    MetricKindMismatchError,
    MetricNotDeclaredError,
    MetricsError,
    MetricSnapshot,
    MetricsRegistry,
)
from bedrock.exc import BedrockExc


@pytest.fixture()
def registry() -> MetricsRegistry:
    """Return a fresh registry for each test."""
    return MetricsRegistry()


class TestDeclaration:
    """Declaration and name validation behavior."""

    @pytest.mark.parametrize(
        "name",
        ["", "Request_Count", "1count", "request-count", "request count", "_private", "req__x.y"],
    )
    def test_invalid_names_raise(self, registry: MetricsRegistry, name: str) -> None:
        with pytest.raises(InvalidMetricNameError):
            registry.counter(name)
        with pytest.raises(InvalidMetricNameError):
            registry.gauge(name)

    def test_invalid_name_error_is_bedrock_exc(self, registry: MetricsRegistry) -> None:
        with pytest.raises(BedrockExc):
            registry.counter("BAD NAME")

    def test_duplicate_declaration_raises(self, registry: MetricsRegistry) -> None:
        registry.counter("request_count")
        with pytest.raises(MetricAlreadyDeclaredError):
            registry.counter("request_count")
        with pytest.raises(MetricAlreadyDeclaredError):
            registry.gauge("request_count")

    def test_all_errors_are_metrics_error_subclasses(self) -> None:
        for exc in (
            InvalidMetricNameError,
            MetricAlreadyDeclaredError,
            MetricNotDeclaredError,
            MetricKindMismatchError,
        ):
            assert issubclass(exc, MetricsError)
            assert issubclass(exc, BedrockExc)


class TestOperations:
    """Counter/gauge mutation and snapshot contract."""

    def test_increment_undeclared_raises(self, registry: MetricsRegistry) -> None:
        with pytest.raises(MetricNotDeclaredError):
            registry.increment("missing")

    def test_set_gauge_undeclared_raises(self, registry: MetricsRegistry) -> None:
        with pytest.raises(MetricNotDeclaredError):
            registry.set_gauge("missing", 1)

    def test_increment_on_gauge_raises(self, registry: MetricsRegistry) -> None:
        registry.gauge("temperature")
        with pytest.raises(MetricKindMismatchError):
            registry.increment("temperature")

    def test_set_gauge_on_counter_raises(self, registry: MetricsRegistry) -> None:
        registry.counter("request_count")
        with pytest.raises(MetricKindMismatchError):
            registry.set_gauge("request_count", 5)

    def test_counter_increment(self, registry: MetricsRegistry) -> None:
        registry.counter("request_count")
        assert registry.increment("request_count") == 1
        assert registry.increment("request_count", 4) == 5

    def test_counter_negative_increment(self, registry: MetricsRegistry) -> None:
        registry.counter("delta")
        registry.increment("delta", 5)
        assert registry.increment("delta", -3) == 2

    def test_gauge_set(self, registry: MetricsRegistry) -> None:
        registry.gauge("temperature")
        registry.set_gauge("temperature", 21.5)
        registry.set_gauge("temperature", -3)
        (snap,) = registry.snapshot()
        assert snap.value == -3

    def test_snapshot_sorted_and_typed(self, registry: MetricsRegistry) -> None:
        registry.counter("zebra")
        registry.gauge("alpha", 1.5)
        registry.counter("middle")
        registry.increment("zebra", 2)
        snaps = registry.snapshot()
        assert [s.name for s in snaps] == ["alpha", "middle", "zebra"]
        assert [s.value for s in snaps] == [1.5, 0, 2]
        assert all(isinstance(s, MetricSnapshot) for s in snaps)

    def test_snapshot_is_immutable(self, registry: MetricsRegistry) -> None:
        registry.counter("request_count")
        (snap,) = registry.snapshot()
        with pytest.raises(AttributeError):
            snap.value = 99  # type: ignore[misc]

    def test_snapshot_exposes_no_internal_state(self, registry: MetricsRegistry) -> None:
        registry.counter("request_count")
        registry.increment("request_count")
        first = registry.snapshot()
        registry.increment("request_count", 10)
        # Earlier snapshot is unaffected by later mutations.
        assert first[0].value == 1
        assert registry.snapshot()[0].value == 11


class TestThreadSafety:
    """Concurrent mutation/snapshot must not corrupt state."""

    def test_concurrent_increments(self, registry: MetricsRegistry) -> None:
        registry.counter("hits")
        thread_count = 8
        increments_per_thread = 500

        def worker() -> None:
            for _ in range(increments_per_thread):
                registry.increment("hits")

        threads = [threading.Thread(target=worker) for _ in range(thread_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        (snap,) = registry.snapshot()
        assert snap.value == thread_count * increments_per_thread

    def test_concurrent_mixed_operations(self, registry: MetricsRegistry) -> None:
        registry.counter("hits")
        registry.gauge("level")

        def increment_worker() -> None:
            for _ in range(500):
                registry.increment("hits")
                registry.increment("hits", -1)
                registry.increment("hits")

        def gauge_worker() -> None:
            for i in range(500):
                registry.set_gauge("level", i)

        def snapshot_worker() -> None:
            for _ in range(500):
                snaps = registry.snapshot()
                assert [s.name for s in snaps] == ["hits", "level"]
                assert all(isinstance(s.value, int | float) for s in snaps)

        threads = [
            *(threading.Thread(target=increment_worker) for _ in range(4)),
            *(threading.Thread(target=gauge_worker) for _ in range(2)),
            *(threading.Thread(target=snapshot_worker) for _ in range(2)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        snaps = {s.name: s.value for s in registry.snapshot()}
        assert snaps["hits"] == 4 * 500
