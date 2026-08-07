"""Public API for Bedrock's provider-neutral file storage."""

from .base import FileBackend, IterableBytes
from .entities import StoredFile
from .exc import (
    StorageAlreadyExistsError,
    StorageConfigurationError,
    StorageConnectionError,
    StorageError,
    StorageNotFoundError,
    StorageOperationError,
    StorageUnsupportedOperationError,
    StorageValidationError,
)
from .service import StorageService, register_backend, storage

__all__ = [
    "FileBackend",
    "IterableBytes",
    "StorageAlreadyExistsError",
    "StorageConfigurationError",
    "StorageConnectionError",
    "StorageError",
    "StorageNotFoundError",
    "StorageOperationError",
    "StorageUnsupportedOperationError",
    "StorageService",
    "StorageValidationError",
    "StoredFile",
    "register_backend",
    "storage",
]
