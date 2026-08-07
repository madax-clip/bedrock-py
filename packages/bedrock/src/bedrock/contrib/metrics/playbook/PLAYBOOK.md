# Bedrock Metrics Module

Lightweight `count`/`gauge` metrics with structured logging and a provider ABC extension point. Lives at `bedrock.contrib.metrics`. V0.2.1 ships **no** concrete exporter (no Prometheus/OpenTelemetry/StatsD) — every call is recorded as a structured log event, and a configured `MetricsProvider` receives a copy of each event.

## Quick Start

```python
from bedrock.contrib.metrics import metrics

# Counter increment event (default value=1, must be >= 0)
metrics.count("orders.created", tags={"channel": "web"})

# Gauge observation of the current value (may be negative, never NaN/Inf)
metrics.gauge("queue.depth", 42)

# Async variants (provider calls offload to a thread by default)
await metrics.acount("orders.created")
await metrics.agauge("queue.depth", 42)
```

Works with zero configuration: without a provider, calls are validated and logged only.

## Semantics

- The service is **stateless**. `count` is an increment *event*; `gauge` is an *observation* of the current value. Nothing is aggregated in-process.
- Every valid call emits **exactly one** structured log event (`metrics invoke`) with `metric_type`, `metric_name`, `value`, normalized `tags`, and `provider` as queryable fields.
- Metric names must match `^[a-zA-Z_][a-zA-Z0-9_.\-:]*$` (max 128 chars by default).
- Values must be finite `int`/`float` (`bool` is rejected). `count` values must be non-negative.
- Tags are `Mapping[str, str]`, copied before use — providers never see or mutate the caller's object. Limits (defaults): 20 tags, 64-char keys, 128-char values.

## Key APIs

### `metrics.count(name, value=1, tags=None) -> None`

Raises `MetricsValidationError` on invalid input. In strict mode, raises `MetricsProviderError` on provider failure.

### `metrics.gauge(name, value, tags=None) -> None`

Same contract as `count`; `value` is required and may be negative.

### `metrics.acount(...)` / `metrics.agauge(...)`

Async variants; provider dispatch runs via `asyncio.to_thread` unless the provider overrides the async methods.

### `metrics.configure(provider=None, settings=None) -> MetricsProvider | None`

Attach a provider and/or replace settings. `configure()` with no args selects logging-only mode.

### `metrics.close()` / `await metrics.aclose()`

Close the provider and return to logging-only mode.

## Configuration

`MetricsSettings` (env prefix `METRICS_`): `strict` (default `false`), `max_name_length` (128), `max_tags` (20), `max_tag_key_length` (64), `max_tag_value_length` (128).

```python
from bedrock.contrib.metrics import metrics, MetricsSettings

metrics.configure(settings=MetricsSettings(strict=True))  # tests / critical paths only
```

## Error Policy

- **Fail-open (default)**: provider exceptions are logged as a sanitized warning (exception type only — never the exception message, tag values, or object reprs) and never reach the business path.
- **Strict** (`METRICS_STRICT=true` or `MetricsSettings(strict=True)`): provider failures raise `MetricsProviderError`.

## Writing a Provider

```python
from collections.abc import Mapping

from bedrock.contrib.metrics import MetricsProvider, metrics


class StdoutProvider(MetricsProvider):
    def count(self, name: str, value: int | float = 1, tags: Mapping[str, str] | None = None) -> None:
        print("count", name, value, dict(tags or {}))

    def gauge(self, name: str, value: int | float, tags: Mapping[str, str] | None = None) -> None:
        print("gauge", name, value, dict(tags or {}))


metrics.configure(StdoutProvider())
```

`MetricsProvider` is a real `abc.ABC`: `count`/`gauge` are abstract; `acount`/`agauge` default to thread offload; `close`/`aclose` are optional no-ops. Override `name` to control the provider label in log events.

## Cardinality Safety

Keep tag values low-cardinality (e.g. `channel=web`, not `user_id=...`). Metric names and tags land in logs and (future) time-series backends — unbounded cardinality is a memory and cost hazard. The configured limits reject abusive payloads, but they cannot enforce semantic cardinality discipline.

## Anti-Patterns

- Don't use metric names/tags to carry payloads, credentials, or user identifiers.
- Don't expect aggregation: the service never sums counters or tracks gauge history.
- Don't enable `strict` in production request paths unless a metrics outage should break the business operation.
- Don't mutate the `tags` mapping inside a provider implementation.
- Don't import concrete exporters here — V0.2.1 intentionally ships none.
