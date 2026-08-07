"""Synchronous storage service and dynamic backend registry."""

from collections.abc import Mapping
from typing import Any

from ...common.registry import ClassRegistry
from ...logging import get_logger
from .base import FileBackend, IterableBytes, normalize_key
from .entities import StoredFile
from .exc import StorageConfigurationError, StorageError, StorageValidationError

_logger = get_logger(__name__)
_BACKEND_REGISTRY = ClassRegistry(
    {
        "local": "bedrock.contrib.storage.backends.local:LocalFileBackend",
        "s3": "bedrock.contrib.storage.backends.s3:S3FileBackend",
    }
)


def register_backend(name: str, backend_cls: type[FileBackend]) -> None:
    """Register a file backend under a unique name."""
    _BACKEND_REGISTRY.register(name, backend_cls)


class StorageService:
    """Provider-neutral facade for synchronous object-storage operations."""

    def __init__(self) -> None:
        self._backend: FileBackend | None = None

    def configure(self, backend_name: str = "local", settings: Any | None = None) -> FileBackend:
        """Create and select a backend, closing an existing backend first."""
        if not _BACKEND_REGISTRY.has(name=backend_name):
            available = ", ".join(sorted(_BACKEND_REGISTRY.keys()))
            raise StorageConfigurationError(f"Unknown storage backend '{backend_name}'. Available: {available}.")
        backend_cls = _BACKEND_REGISTRY.get(backend_name)
        if backend_cls is None:
            raise StorageConfigurationError(f"Failed to load storage backend '{backend_name}'.")
        try:
            new_backend = backend_cls(settings=settings)
        except StorageError:
            raise
        except Exception as exc:
            raise StorageConfigurationError(f"Failed to configure storage backend '{backend_name}'.") from exc
        previous_backend = self._backend
        if previous_backend is not None:
            previous_backend.close()
        self._backend = new_backend
        return new_backend

    def get_backend(self) -> FileBackend:
        """Return the selected backend, lazily configuring local storage."""
        if self._backend is None:
            return self.configure()
        return self._backend

    def list_backends(self) -> list[str]:
        """Return registered backend names."""
        return sorted(_BACKEND_REGISTRY.keys())

    @staticmethod
    def _put_values(
        path: str,
        content: bytes,
        metadata: Mapping[str, str] | None,
    ) -> tuple[str, dict[str, str] | None]:
        key = normalize_key(path)
        if not isinstance(content, bytes):
            raise StorageValidationError("Storage content must be bytes.")
        if metadata is None:
            return key, None
        if not isinstance(metadata, Mapping) or not all(
            isinstance(name, str) and isinstance(value, str) for name, value in metadata.items()
        ):
            raise StorageValidationError("Storage metadata must be a mapping of strings to strings.")
        return key, dict(metadata)

    def put(
        self,
        path: str,
        content: bytes,
        *,
        mime_type: str | None = None,
        metadata: Mapping[str, str] | None = None,
        overwrite: bool = False,
    ) -> StoredFile:
        """Store bytes and return complete provider-neutral metadata."""
        key, validated_metadata = self._put_values(path, content, metadata)
        result = self.get_backend().put(
            key, content, mime_type=mime_type, metadata=validated_metadata, overwrite=overwrite
        )
        _logger.info("storage put backend={} key={} result=success", type(self.get_backend()).__name__, key)
        return result

    def head(self, path: str) -> StoredFile:
        """Return object metadata without downloading its body."""
        key = normalize_key(path)
        result = self.get_backend().head(key)
        _logger.info("storage head backend={} key={} result=success", type(self.get_backend()).__name__, key)
        return result

    def download(self, path: str) -> bytes:
        """Download a complete object."""
        key = normalize_key(path)
        result = self.get_backend().download(key)
        _logger.info("storage download backend={} key={} result=success", type(self.get_backend()).__name__, key)
        return result

    def stream(self, path: str, *, chunk_size: int = 64 * 1024) -> IterableBytes:
        """Return a synchronous iterable of bounded object chunks."""
        key = normalize_key(path)
        result = self.get_backend().stream(key, chunk_size=chunk_size)
        _logger.info("storage stream backend={} key={} result=started", type(self.get_backend()).__name__, key)
        return result

    def delete(self, path: str) -> bool:
        """Delete an object and return whether it was removed."""
        key = normalize_key(path)
        result = self.get_backend().delete(key)
        _logger.info("storage delete backend={} key={} result={}", type(self.get_backend()).__name__, key, result)
        return result

    def exists(self, path: str) -> bool:
        """Return whether an object exists."""
        key = normalize_key(path)
        result = self.get_backend().exists(key)
        _logger.info("storage exists backend={} key={} result={}", type(self.get_backend()).__name__, key, result)
        return result

    def copy(self, source: str, destination: str, *, overwrite: bool = False) -> StoredFile:
        """Copy an object inside the selected backend."""
        source_key = normalize_key(source)
        destination_key = normalize_key(destination)
        result = self.get_backend().copy(source_key, destination_key, overwrite=overwrite)
        _logger.info("storage copy backend={} key={} result=success", type(self.get_backend()).__name__, source_key)
        return result

    def mv(self, source: str, destination: str, *, overwrite: bool = False) -> StoredFile:
        """Move an object inside the selected backend."""
        source_key = normalize_key(source)
        destination_key = normalize_key(destination)
        result = self.get_backend().mv(source_key, destination_key, overwrite=overwrite)
        _logger.info("storage mv backend={} key={} result=success", type(self.get_backend()).__name__, source_key)
        return result

    def get_signed_url(self, path: str, *, expires_in: int = 3600) -> str:
        """Return a temporary download URL when the selected backend supports it."""
        key = normalize_key(path)
        result = self.get_backend().get_signed_url(key, expires_in=expires_in)
        _logger.info("storage get_signed_url backend={} key={} result=success", type(self.get_backend()).__name__, key)
        return result

    def close(self) -> None:
        """Close the selected backend; repeated calls are harmless."""
        if self._backend is None:
            return
        backend, self._backend = self._backend, None
        backend.close()


storage = StorageService()
