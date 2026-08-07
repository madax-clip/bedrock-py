"""Unit tests for the Bedrock metrics contrib module."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import pytest
from bedrock.contrib.metrics import (
    MetricsProvider,
    MetricsProviderError,
    MetricsService,
    MetricsSettings,
    MetricsValidationError,
    metrics,
)
from bedrock.contrib.metrics.service import logger as metrics_logger


@pytest.fixture
def captured_records():
    """Capture loguru records emitted through the metrics service logger."""
    records: list[Any] = []
    sink_id = metrics_logger.add(lambda message: records.append(message.record), level="DEBUG")
    yield records
    metrics_logger.remove(sink_id)


def _invoke_records(records: list[Any]) -> list[Any]:
    return [r for r in records if "metric_type" in r["extra"] and r["level"].name == "INFO"]


def _failure_records(records: list[Any]) -> list[Any]:
    return [r for r in records if r["level"].name == "WARNING"]


class FakeProvider(MetricsProvider):
    """In-memory fake provider proving the extension point works."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int | float, Mapping[str, str]]] = []
        self.closed = False

    def count(self, name: str, value: int | float = 1, tags: Mapping[str, str] | None = None) -> None:
        self.calls.append(("count", name, value, tags or {}))

    def gauge(self, name: str, value: int | float, tags: Mapping[str, str] | None = None) -> None:
        self.calls.append(("gauge", name, value, tags or {}))

    def close(self) -> None:
        self.closed = True


class FailingProvider(MetricsProvider):
    """Provider that always raises, carrying sensitive data in the exception."""

    def count(self, name: str, value: int | float = 1, tags: Mapping[str, str] | None = None) -> None:
        raise RuntimeError("connection refused with token=super-secret-credential")

    def gauge(self, name: str, value: int | float, tags: Mapping[str, str] | None = None) -> None:
        raise RuntimeError("connection refused with token=super-secret-credential")


class TestProviderContract:
    """The provider ABC is a real abc.ABC extension point."""

    def test_provider_is_abstract_and_not_instantiable(self) -> None:
        with pytest.raises(TypeError):
            MetricsProvider()  # type: ignore[abstract]

    def test_partial_implementation_is_not_instantiable(self) -> None:
        class OnlyCount(MetricsProvider):
            def count(self, name: str, value: int | float = 1, tags: Mapping[str, str] | None = None) -> None:
                pass

        with pytest.raises(TypeError):
            OnlyCount()  # type: ignore[abstract]

    def test_fake_provider_default_name_is_class_name(self) -> None:
        assert FakeProvider().name == "FakeProvider"


class TestSyncCountGauge:
    """Sync count/gauge calls validate, log once, and dispatch."""

    def test_count_defaults_to_increment_one(self, captured_records: list[Any]) -> None:
        service = MetricsService()
        provider = FakeProvider()
        service.configure(provider)

        service.count("orders.created")

        assert provider.calls == [("count", "orders.created", 1, {})]
        invoke = _invoke_records(captured_records)
        assert len(invoke) == 1
        extra = invoke[0]["extra"]
        assert extra["metric_type"] == "count"
        assert extra["metric_name"] == "orders.created"
        assert extra["value"] == 1
        assert extra["tags"] == {}
        assert extra["provider"] == "FakeProvider"

    def test_gauge_records_current_value_with_tags(self, captured_records: list[Any]) -> None:
        service = MetricsService()
        provider = FakeProvider()
        service.configure(provider)

        service.gauge("queue.depth", -3.5, tags={"queue": "default"})

        assert provider.calls == [("gauge", "queue.depth", -3.5, {"queue": "default"})]
        invoke = _invoke_records(captured_records)
        assert len(invoke) == 1
        extra = invoke[0]["extra"]
        assert extra["metric_type"] == "gauge"
        assert extra["value"] == -3.5
        assert extra["tags"] == {"queue": "default"}

    def test_each_valid_call_emits_exactly_one_invoke_log(self, captured_records: list[Any]) -> None:
        service = MetricsService()
        service.count("a.b", 2)
        service.count("a.b", 3)
        service.gauge("a.c", 1.5)

        assert len(_invoke_records(captured_records)) == 3

    def test_no_provider_logs_with_none_provider_name(self, captured_records: list[Any]) -> None:
        service = MetricsService()

        service.count("orders.created", tags={"channel": "web"})

        invoke = _invoke_records(captured_records)
        assert len(invoke) == 1
        assert invoke[0]["extra"]["provider"] == "none"
        assert invoke[0]["extra"]["tags"] == {"channel": "web"}

    def test_invoke_log_is_structured_not_concatenated_text(self, captured_records: list[Any]) -> None:
        service = MetricsService()
        service.count("orders.created", 5, tags={"channel": "web"})

        record = _invoke_records(captured_records)[0]
        assert record["message"] == "metrics invoke"
        # Queryable fields live in ``extra``, not in the message text.
        assert "orders.created" not in record["message"]


class TestAsyncCountGauge:
    """Async variants share validation/logging and offload to a thread."""

    def test_acount_and_agauge_dispatch(self, captured_records: list[Any]) -> None:
        service = MetricsService()
        provider = FakeProvider()
        service.configure(provider)

        async def scenario() -> None:
            await service.acount("orders.created", 2, tags={"channel": "web"})
            await service.agauge("queue.depth", 7)

        asyncio.run(scenario())

        assert provider.calls == [
            ("count", "orders.created", 2, {"channel": "web"}),
            ("gauge", "queue.depth", 7, {}),
        ]
        assert len(_invoke_records(captured_records)) == 2

    def test_async_without_provider_only_logs(self, captured_records: list[Any]) -> None:
        service = MetricsService()

        async def scenario() -> None:
            await service.acount("orders.created")

        asyncio.run(scenario())

        assert len(_invoke_records(captured_records)) == 1

    def test_async_validation_errors_raise_before_logging(self, captured_records: list[Any]) -> None:
        service = MetricsService()

        async def scenario() -> None:
            with pytest.raises(MetricsValidationError):
                await service.acount("bad name!")

        asyncio.run(scenario())

        assert _invoke_records(captured_records) == []


class TestInputValidation:
    """Boundary rules for names, values, and tags."""

    def test_rejects_empty_and_non_string_names(self) -> None:
        service = MetricsService()
        with pytest.raises(MetricsValidationError):
            service.count("")
        with pytest.raises(MetricsValidationError):
            service.count(None)  # type: ignore[arg-type]

    def test_rejects_names_with_disallowed_characters(self) -> None:
        service = MetricsService()
        for bad in ("has space", "9starts.with.digit", "slash/name", "uni代码"):
            with pytest.raises(MetricsValidationError):
                service.count(bad)

    def test_accepts_documented_name_characters(self) -> None:
        service = MetricsService()
        service.count("_private.metric-name:v2", tags={"k_1": "v"})

    def test_rejects_overlong_names(self) -> None:
        service = MetricsService(settings=MetricsSettings(max_name_length=8))
        with pytest.raises(MetricsValidationError):
            service.count("a" * 9)

    def test_count_rejects_negative_values(self) -> None:
        service = MetricsService()
        with pytest.raises(MetricsValidationError):
            service.count("orders.created", -1)

    def test_count_allows_zero(self) -> None:
        service = MetricsService()
        service.count("orders.created", 0)

    def test_rejects_nan_and_inf_values(self) -> None:
        service = MetricsService()
        for bad in (float("nan"), float("inf"), float("-inf")):
            with pytest.raises(MetricsValidationError):
                service.count("orders.created", bad)
            with pytest.raises(MetricsValidationError):
                service.gauge("queue.depth", bad)

    def test_gauge_allows_negative_values(self) -> None:
        service = MetricsService()
        service.gauge("temperature.celsius", -12.5)

    def test_rejects_bool_and_non_numeric_values(self) -> None:
        service = MetricsService()
        for bad in (True, "1", None, object()):
            with pytest.raises(MetricsValidationError):
                service.count("orders.created", bad)  # type: ignore[arg-type]

    def test_rejects_too_many_tags(self) -> None:
        service = MetricsService(settings=MetricsSettings(max_tags=2))
        with pytest.raises(MetricsValidationError):
            service.count("orders.created", tags={"a": "1", "b": "2", "c": "3"})

    def test_rejects_overlong_tag_keys_and_values(self) -> None:
        service = MetricsService(settings=MetricsSettings(max_tag_key_length=4, max_tag_value_length=4))
        with pytest.raises(MetricsValidationError):
            service.count("orders.created", tags={"abcde": "v"})
        with pytest.raises(MetricsValidationError):
            service.count("orders.created", tags={"k": "v" * 5})

    def test_rejects_non_string_tag_keys_and_values(self) -> None:
        service = MetricsService()
        with pytest.raises(MetricsValidationError):
            service.count("orders.created", tags={1: "v"})  # type: ignore[dict-item]
        with pytest.raises(MetricsValidationError):
            service.count("orders.created", tags={"k": 1})  # type: ignore[dict-item]
        with pytest.raises(MetricsValidationError):
            service.count("orders.created", tags={"k": object()})  # type: ignore[dict-item]

    def test_rejects_non_mapping_tags(self) -> None:
        service = MetricsService()
        with pytest.raises(MetricsValidationError):
            service.count("orders.created", tags=[("k", "v")])  # type: ignore[arg-type]


class TestTagsImmutability:
    """Providers never see or affect the caller's tag object."""

    def test_caller_mutation_after_call_does_not_affect_recorded_tags(self) -> None:
        service = MetricsService()
        provider = FakeProvider()
        service.configure(provider)
        tags = {"channel": "web"}

        service.count("orders.created", tags=tags)
        tags["channel"] = "mutated"
        tags["extra"] = "added"

        assert provider.calls[0][3] == {"channel": "web"}

    def test_provider_receives_a_copy_not_the_caller_object(self) -> None:
        service = MetricsService()
        seen: list[Mapping[str, str]] = []

        class RecordingProvider(FakeProvider):
            def count(self, name: str, value: int | float = 1, tags: Mapping[str, str] | None = None) -> None:
                seen.append(tags or {})

        service.configure(RecordingProvider())
        tags = {"channel": "web"}
        service.count("orders.created", tags=tags)

        assert seen[0] == tags
        assert seen[0] is not tags

    def test_provider_tag_mutation_does_not_pollute_invoke_log(self, captured_records: list[Any]) -> None:
        class MutatingProvider(FakeProvider):
            def count(self, name: str, value: int | float = 1, tags: Mapping[str, str] | None = None) -> None:
                assert isinstance(tags, dict)
                tags["channel"] = "mutated-by-provider"  # misbehaving provider

        service = MetricsService()
        service.configure(MutatingProvider())

        service.count("orders.created", tags={"channel": "web"})

        assert _invoke_records(captured_records)[0]["extra"]["tags"] == {"channel": "web"}

    def test_logged_tags_are_a_snapshot(self, captured_records: list[Any]) -> None:
        service = MetricsService()
        tags = {"channel": "web"}

        service.count("orders.created", tags=tags)
        tags["channel"] = "mutated"

        assert _invoke_records(captured_records)[0]["extra"]["tags"] == {"channel": "web"}


class TestErrorPolicy:
    """Fail-open by default; strict mode raises MetricsProviderError."""

    def test_fail_open_logs_warning_and_does_not_raise(self, captured_records: list[Any]) -> None:
        service = MetricsService()
        service.configure(FailingProvider())

        service.count("orders.created", tags={"channel": "web"})

        failures = _failure_records(captured_records)
        assert len(failures) == 1
        extra = failures[0]["extra"]
        assert extra["metric_type"] == "count"
        assert extra["metric_name"] == "orders.created"
        assert extra["provider"] == "FailingProvider"
        assert extra["error_type"] == "builtins.RuntimeError"

    def test_fail_open_log_is_sanitized(self, captured_records: list[Any]) -> None:
        service = MetricsService()
        service.configure(FailingProvider())

        service.count("orders.created", tags={"api_key": "super-secret-credential", "channel": "web"})

        failure = _failure_records(captured_records)[0]
        rendered = f"{failure['message']} {failure['extra']}"
        assert "super-secret-credential" not in rendered
        assert "api_key" not in rendered
        assert "tags" not in failure["extra"]

    def test_fail_open_applies_to_async_calls(self, captured_records: list[Any]) -> None:
        service = MetricsService()
        service.configure(FailingProvider())

        async def scenario() -> None:
            await service.agauge("queue.depth", 3)

        asyncio.run(scenario())

        assert len(_failure_records(captured_records)) == 1

    def test_provider_raised_validation_error_is_fail_open(self, captured_records: list[Any]) -> None:
        class ValidationFailingProvider(FakeProvider):
            def count(self, name: str, value: int | float = 1, tags: Mapping[str, str] | None = None) -> None:
                raise MetricsValidationError("provider-internal validation failure")

        service = MetricsService()
        service.configure(ValidationFailingProvider())

        # A provider-raised MetricsValidationError must not escape fail-open:
        # provider failures never reach the business path.
        service.count("orders.created")

        failures = _failure_records(captured_records)
        assert len(failures) == 1
        assert "MetricsValidationError" in failures[0]["extra"]["error_type"]

    def test_provider_raised_validation_error_strict_raises_provider_error(self) -> None:
        class ValidationFailingProvider(FakeProvider):
            def gauge(self, name: str, value: int | float, tags: Mapping[str, str] | None = None) -> None:
                raise MetricsValidationError("provider-internal validation failure")

        service = MetricsService(settings=MetricsSettings(strict=True))
        service.configure(ValidationFailingProvider())

        with pytest.raises(MetricsProviderError):
            service.gauge("queue.depth", 3)

    def test_strict_mode_raises_metrics_provider_error(self) -> None:
        service = MetricsService(settings=MetricsSettings(strict=True))
        service.configure(FailingProvider())

        with pytest.raises(MetricsProviderError):
            service.count("orders.created")
        with pytest.raises(MetricsProviderError):
            service.gauge("queue.depth", 3)

    def test_strict_mode_async_raises(self) -> None:
        service = MetricsService(settings=MetricsSettings(strict=True))
        service.configure(FailingProvider())

        async def scenario() -> None:
            with pytest.raises(MetricsProviderError):
                await service.acount("orders.created")

        asyncio.run(scenario())

    def test_strict_mode_still_emits_invoke_log_before_raising(self, captured_records: list[Any]) -> None:
        service = MetricsService(settings=MetricsSettings(strict=True))
        service.configure(FailingProvider())

        with pytest.raises(MetricsProviderError):
            service.count("orders.created")

        assert len(_invoke_records(captured_records)) == 1


class TestLifecycle:
    """configure/close manage the provider lifecycle."""

    def test_configure_rejects_non_provider(self) -> None:
        service = MetricsService()
        with pytest.raises(MetricsValidationError):
            service.configure(object())  # type: ignore[arg-type]

    def test_configure_returns_provider(self) -> None:
        service = MetricsService()
        provider = FakeProvider()
        assert service.configure(provider) is provider
        assert service.provider is provider

    def test_close_calls_provider_close_and_resets(self, captured_records: list[Any]) -> None:
        service = MetricsService()
        provider = FakeProvider()
        service.configure(provider)

        service.close()

        assert provider.closed is True
        assert service.provider is None
        service.count("orders.created")
        assert _invoke_records(captured_records)[-1]["extra"]["provider"] == "none"

    def test_close_without_provider_is_noop(self) -> None:
        MetricsService().close()

    def test_configure_without_provider_keeps_existing_provider(self) -> None:
        service = MetricsService()
        provider = FakeProvider()
        service.configure(provider)

        # Omitting ``provider`` (e.g. settings-only reconfiguration or a bare
        # ``configure()``) must never detach an already configured provider.
        service.configure(settings=MetricsSettings(strict=True))
        assert service.provider is provider
        service.configure()
        assert service.provider is provider

    def test_configure_explicit_none_detaches_provider(self) -> None:
        service = MetricsService()
        service.configure(FakeProvider())

        assert service.configure(None) is None
        assert service.provider is None

    def test_close_failure_still_detaches_provider(self, captured_records: list[Any]) -> None:
        class CloseFailingProvider(FakeProvider):
            def close(self) -> None:
                raise RuntimeError("close failed with token=super-secret-credential")

        service = MetricsService()
        provider = CloseFailingProvider()
        service.configure(provider)

        service.close()  # fail-open: no exception escapes

        assert service.provider is None
        failures = _failure_records(captured_records)
        assert len(failures) == 1
        assert failures[0]["extra"]["provider"] == "CloseFailingProvider"
        assert failures[0]["extra"]["error_type"] == "builtins.RuntimeError"
        assert "super-secret-credential" not in f"{failures[0]['message']} {failures[0]['extra']}"
        service.count("orders.created")
        assert _invoke_records(captured_records)[-1]["extra"]["provider"] == "none"

    def test_close_failure_strict_raises_but_still_detaches(self) -> None:
        class CloseFailingProvider(FakeProvider):
            def close(self) -> None:
                raise RuntimeError("boom")

        service = MetricsService(settings=MetricsSettings(strict=True))
        service.configure(CloseFailingProvider())

        with pytest.raises(MetricsProviderError):
            service.close()
        assert service.provider is None

    def test_aclose_failure_still_detaches_provider(self) -> None:
        class CloseFailingProvider(FakeProvider):
            async def aclose(self) -> None:
                raise RuntimeError("boom")

        service = MetricsService()
        service.configure(CloseFailingProvider())

        asyncio.run(service.aclose())

        assert service.provider is None

    def test_aclose_calls_provider_aclose(self) -> None:
        service = MetricsService()
        provider = FakeProvider()
        service.configure(provider)

        asyncio.run(service.aclose())

        assert provider.closed is True
        assert service.provider is None

    def test_default_async_methods_offload_to_thread(self) -> None:
        import threading

        main_thread = threading.get_ident()
        seen_threads: list[int] = []

        class ThreadRecordingProvider(FakeProvider):
            def count(self, name: str, value: int | float = 1, tags: Mapping[str, str] | None = None) -> None:
                seen_threads.append(threading.get_ident())

        service = MetricsService()
        service.configure(ThreadRecordingProvider())

        async def scenario() -> None:
            await service.acount("orders.created")

        asyncio.run(scenario())

        assert seen_threads and seen_threads[0] != main_thread


class TestGlobalSingleton:
    """The module exposes the stable public contract only."""

    def test_metrics_singleton_is_a_service(self) -> None:
        assert isinstance(metrics, MetricsService)

    def test_public_all_contains_only_stable_contract(self) -> None:
        import bedrock.contrib.metrics as metrics_module

        assert set(metrics_module.__all__) == {
            "MetricsError",
            "MetricsProvider",
            "MetricsProviderError",
            "MetricsService",
            "MetricsSettings",
            "MetricsValidationError",
            "metrics",
        }
