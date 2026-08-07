"""Synchronous backend contract and object-key normalization for storage."""

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from pathlib import PurePosixPath

from .entities import StoredFile
from .exc import StorageValidationError

type IterableBytes = Iterable[bytes]


def normalize_key(key: str) -> str:
    """Validate and normalize a provider-neutral POSIX object key."""
    if not isinstance(key, str) or not key:
        raise StorageValidationError("Storage object key must be a non-empty string.")
    if "\x00" in key or "\\" in key:
        raise StorageValidationError("Storage object key cannot contain NUL bytes or backslashes.")
    path = PurePosixPath(key)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in key.split("/")):
        raise StorageValidationError("Storage object key must be a relative POSIX path without '.' or '..' segments.")
    return path.as_posix()


class FileBackend(ABC):
    """Synchronous, provider-neutral contract for object storage backends."""

    @abstractmethod
    def put(
        self,
        path: str,
        content: bytes,
        *,
        mime_type: str | None = None,
        metadata: Mapping[str, str] | None = None,
        overwrite: bool = False,
    ) -> StoredFile:
        """Store a complete byte payload and return its metadata."""

    @abstractmethod
    def head(self, path: str) -> StoredFile:
        """Return metadata without downloading the object's content."""

    @abstractmethod
    def download(self, path: str) -> bytes:
        """Return the complete content of *path*."""

    @abstractmethod
    def stream(self, path: str, *, chunk_size: int = 64 * 1024) -> IterableBytes:
        """Return an iterable that yields object chunks without buffering it all."""

    @abstractmethod
    def delete(self, path: str) -> bool:
        """Delete *path* and return whether an object was removed."""

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Return whether *path* exists."""

    @abstractmethod
    def mv(self, source: str, destination: str, *, overwrite: bool = False) -> StoredFile:
        """Move an object and return metadata for its destination."""

    @abstractmethod
    def copy(self, source: str, destination: str, *, overwrite: bool = False) -> StoredFile:
        """Copy an object and return metadata for its destination."""

    @abstractmethod
    def get_signed_url(self, path: str, *, expires_in: int = 3600) -> str:
        """Return a temporary URL for downloading *path* when supported."""

    @abstractmethod
    def close(self) -> None:
        """Release backend resources. Implementations must be idempotent."""
