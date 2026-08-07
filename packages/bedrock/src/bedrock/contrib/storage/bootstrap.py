"""Lifecycle hooks for Bedrock storage."""

from bedrock.module import AppConfig, ModuleRegistry


def ready(*, registry: ModuleRegistry, app: AppConfig) -> None:
    """Initialize lazy local storage after the module registry is ready."""
    from .service import storage

    storage.configure()


def on_shutdown(*, registry: ModuleRegistry, app: AppConfig) -> None:
    """Close the configured storage backend during registry shutdown."""
    from .service import storage

    storage.close()
