"""Secure local filesystem storage backend."""

import hashlib
import json
import mimetypes
import os
import tempfile
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path

from pydantic_settings import SettingsConfigDict

from ..base import FileBackend, IterableBytes, normalize_key
from ..entities import StoredFile
from ..exc import (
    StorageAlreadyExistsError,
    StorageNotFoundError,
    StorageOperationError,
    StorageUnsupportedOperationError,
    StorageValidationError,
)
from ..settings import StorageSettings

_METADATA_DIRECTORY = ".bedrock-storage-metadata"


class LocalStorageSettings(StorageSettings):
    """Settings for :class:`LocalFileBackend`."""

    model_config = SettingsConfigDict(env_prefix="STORAGE_LOCAL_", extra="ignore")

    root: Path = Path("storage")


class LocalFileBackend(FileBackend):
    """Local backend that confines object and metadata paths to one root."""

    def __init__(self, settings: LocalStorageSettings | None = None) -> None:
        self._settings = settings or LocalStorageSettings()
        self._settings.root.mkdir(parents=True, exist_ok=True)
        self._root = self._settings.root.resolve(strict=True)
        self._metadata_root = self._root / _METADATA_DIRECTORY
        self._metadata_root.mkdir(exist_ok=True)
        self._closed = False

    @property
    def settings(self) -> LocalStorageSettings:
        """Return the settings used by this backend."""
        return self._settings

    def _path(self, key: str) -> Path:
        normalized = normalize_key(key)
        if normalized.split("/", 1)[0] == _METADATA_DIRECTORY:
            raise StorageValidationError("Storage object key uses a reserved internal path.")
        candidate = self._root.joinpath(*normalized.split("/"))
        existing_parent = candidate.parent
        while not existing_parent.exists():
            existing_parent = existing_parent.parent
        if not existing_parent.resolve(strict=True).is_relative_to(self._root):
            raise StorageOperationError("Storage path resolves outside the configured local root.")
        if candidate.is_symlink() or (
            candidate.exists() and not candidate.resolve(strict=True).is_relative_to(self._root)
        ):
            raise StorageOperationError("Storage path resolves outside the configured local root.")
        return candidate

    @staticmethod
    def _digest(path: Path, algorithm: str) -> str:
        digest = hashlib.new(algorithm)
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(64 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _metadata_path(self, key: str) -> Path:
        return self._metadata_root / f"{hashlib.sha256(key.encode()).hexdigest()}.json"

    def _read_metadata(self, key: str) -> dict[str, str]:
        metadata_path = self._metadata_path(key)
        if not metadata_path.exists():
            return {}
        try:
            raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StorageOperationError("Failed to read local object metadata.") from exc
        if not isinstance(raw, dict) or not all(
            isinstance(name, str) and isinstance(value, str) for name, value in raw.items()
        ):
            raise StorageOperationError("Local object metadata is invalid.")
        return raw

    def _write_metadata(self, key: str, metadata: Mapping[str, str]) -> None:
        target = self._metadata_path(key)
        descriptor, temporary_name = tempfile.mkstemp(prefix=".bedrock-storage-", dir=self._metadata_root)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(dict(metadata), handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        except OSError as exc:
            raise StorageOperationError("Failed to write local object metadata.") from exc
        finally:
            if temporary.exists():
                temporary.unlink()

    def _remove_metadata(self, key: str) -> None:
        self._metadata_path(key).unlink(missing_ok=True)

    def _stored_file(self, key: str, target: Path) -> StoredFile:
        try:
            stat = target.stat()
        except FileNotFoundError as exc:
            raise StorageNotFoundError(f"Storage object not found: {key}") from exc
        except OSError as exc:
            raise StorageOperationError(f"Failed to inspect local object: {key}") from exc
        metadata = self._read_metadata(key)
        mime_type = metadata.get("mime_type") or mimetypes.guess_type(key)[0]
        return StoredFile(
            key=key,
            size=stat.st_size,
            mime_type=mime_type,
            etag=self._digest(target, "md5"),
            checksum=self._digest(target, "sha256"),
            last_modified=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            metadata={name: value for name, value in metadata.items() if name != "mime_type"},
            provider_metadata={"backend": "local"},
        )

    @staticmethod
    def _write_file(temporary: Path, content: bytes) -> None:
        with temporary.open("wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

    def put(
        self,
        path: str,
        content: bytes,
        *,
        mime_type: str | None = None,
        metadata: Mapping[str, str] | None = None,
        overwrite: bool = False,
    ) -> StoredFile:
        """Atomically write bytes and associated portable metadata."""
        if not isinstance(content, bytes):
            raise StorageValidationError("Storage content must be bytes.")
        key = normalize_key(path)
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.parent.resolve(strict=True).is_relative_to(self._root):
            raise StorageOperationError("Storage path resolves outside the configured local root.")
        descriptor, temporary_name = tempfile.mkstemp(prefix=".bedrock-storage-", dir=target.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            if overwrite:
                os.replace(temporary, target)
            else:
                try:
                    os.link(temporary, target)
                except FileExistsError as exc:
                    raise StorageAlreadyExistsError(f"Storage object already exists: {key}") from exc
                temporary.unlink()
        except StorageAlreadyExistsError:
            raise
        except OSError as exc:
            raise StorageOperationError(f"Failed to store local object: {key}") from exc
        finally:
            if temporary.exists():
                temporary.unlink()
        stored_metadata = dict(metadata or {})
        if mime_type:
            stored_metadata["mime_type"] = mime_type
        self._write_metadata(key, stored_metadata)
        return self._stored_file(key, target)

    def head(self, path: str) -> StoredFile:
        """Return metadata for a local object."""
        key = normalize_key(path)
        return self._stored_file(key, self._path(key))

    def download(self, path: str) -> bytes:
        """Read a local object's complete byte payload."""
        key = normalize_key(path)
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError as exc:
            raise StorageNotFoundError(f"Storage object not found: {key}") from exc
        except OSError as exc:
            raise StorageOperationError(f"Failed to read local object: {key}") from exc

    def stream(self, path: str, *, chunk_size: int = 64 * 1024) -> IterableBytes:
        """Yield local object chunks from an open file handle."""
        if chunk_size <= 0:
            raise StorageValidationError("Storage stream chunk_size must be greater than zero.")
        key = normalize_key(path)
        target = self._path(key)

        def chunks() -> Iterator[bytes]:
            try:
                with target.open("rb") as handle:
                    yield from iter(lambda: handle.read(chunk_size), b"")
            except FileNotFoundError as exc:
                raise StorageNotFoundError(f"Storage object not found: {key}") from exc
            except OSError as exc:
                raise StorageOperationError(f"Failed to stream local object: {key}") from exc

        return chunks()

    def delete(self, path: str) -> bool:
        """Delete an object and its sidecar metadata."""
        key = normalize_key(path)
        try:
            self._path(key).unlink()
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise StorageOperationError("Failed to delete local object.") from exc
        self._remove_metadata(key)
        return True

    def exists(self, path: str) -> bool:
        """Return whether a regular local object exists."""
        target = self._path(path)
        try:
            return target.is_file()
        except OSError as exc:
            raise StorageOperationError("Failed to inspect local object.") from exc

    def copy(self, source: str, destination: str, *, overwrite: bool = False) -> StoredFile:
        """Copy a local object using a hard-link create where possible."""
        source_key = normalize_key(source)
        destination_key = normalize_key(destination)
        source_path = self._path(source_key)
        destination_path = self._path(destination_key)
        if not source_path.is_file():
            raise StorageNotFoundError(f"Storage object not found: {source_key}")
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if overwrite:
                descriptor, temporary_name = tempfile.mkstemp(prefix=".bedrock-storage-", dir=destination_path.parent)
                temporary = Path(temporary_name)
                try:
                    with os.fdopen(descriptor, "wb") as output, source_path.open("rb") as input_file:
                        for chunk in iter(lambda: input_file.read(64 * 1024), b""):
                            output.write(chunk)
                        output.flush()
                        os.fsync(output.fileno())
                    os.replace(temporary, destination_path)
                finally:
                    if temporary.exists():
                        temporary.unlink()
            else:
                os.link(source_path, destination_path)
        except FileExistsError as exc:
            raise StorageAlreadyExistsError(f"Storage object already exists: {destination_key}") from exc
        except OSError as exc:
            raise StorageOperationError("Failed to copy local object.") from exc
        self._write_metadata(destination_key, self._read_metadata(source_key))
        return self.head(destination_key)

    def mv(self, source: str, destination: str, *, overwrite: bool = False) -> StoredFile:
        """Move a local object, atomically refusing existing destinations by default."""
        source_key = normalize_key(source)
        destination_key = normalize_key(destination)
        source_path = self._path(source_key)
        destination_path = self._path(destination_key)
        if not source_path.is_file():
            raise StorageNotFoundError(f"Storage object not found: {source_key}")
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if overwrite:
                os.replace(source_path, destination_path)
            else:
                os.link(source_path, destination_path)
                source_path.unlink()
        except FileExistsError as exc:
            raise StorageAlreadyExistsError(f"Storage object already exists: {destination_key}") from exc
        except OSError as exc:
            raise StorageOperationError("Failed to move local object.") from exc
        source_metadata = self._metadata_path(source_key)
        if source_metadata.exists():
            os.replace(source_metadata, self._metadata_path(destination_key))
        else:
            self._remove_metadata(destination_key)
        return self.head(destination_key)

    def get_signed_url(self, path: str, *, expires_in: int = 3600) -> str:
        """Reject local signed URLs because filesystem URLs are unsafe and non-portable."""
        normalize_key(path)
        if expires_in <= 0:
            raise StorageValidationError("Signed URL expiry must be greater than zero.")
        raise StorageUnsupportedOperationError("Local storage does not support signed URLs.")

    def close(self) -> None:
        """Mark this backend closed; local storage owns no persistent handles."""
        self._closed = True
