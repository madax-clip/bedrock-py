"""Bootstrap hooks for the Bedrock metrics module."""

from __future__ import annotations

from bedrock.module import AppConfig, ModuleRegistry


def ready(*, registry: ModuleRegistry, app: AppConfig) -> None:
    """Called when all modules are installed and ready.

    Intentionally a no-op: the metrics service works with zero configuration
    (logging-only mode), and ``metrics.configure()`` must not run here because
    it would risk interfering with providers configured by other modules.
    """


def on_shutdown(*, registry: ModuleRegistry, app: AppConfig) -> None:
    """Called when the registry shuts down."""
    from .service import metrics

    metrics.close()
