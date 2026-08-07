"""Tests for synchronous local and S3 storage backends."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from bedrock.contrib.storage.backends.local import LocalFileBackend, LocalStorageSettings
from bedrock.contrib.storage.backends.s3 import S3FileBackend, S3StorageSettings
from bedrock.contrib.storage.exc import (
    StorageAlreadyExistsError,
    StorageConfigurationError,
    StorageConnectionError,
    StorageNotFoundError,
    StorageOperationError,
    StorageUnsupportedOperationError,
    StorageValidationError,
)
from bedrock.contrib.storage.service import StorageService


class ClientError(Exception):
    """Small botocore-compatible error fake without network access."""

    def __init__(self, code: str) -> None:
        self.response = {"Error": {"Code": code}}


class TestLocalStorage:
    """Exercise local storage safety, metadata, and complete object operations."""

    def _backend(self, root: Path) -> LocalFileBackend:
        return LocalFileBackend(LocalStorageSettings(root=root))

    def test_put_head_download_stream_delete_and_metadata(self, tmp_path: Path) -> None:
        backend = self._backend(tmp_path / "objects")

        stored = backend.put("nested/file.txt", b"first", mime_type="text/plain", metadata={"source": "test"})

        assert stored.key == "nested/file.txt"
        assert stored.size == 5
        assert stored.mime_type == "text/plain"
        assert stored.etag == "8b04d5e3775d298e78455efc5ca404d5"
        assert stored.checksum
        assert stored.metadata == {"source": "test"}
        assert stored.provider_metadata == {"backend": "local"}
        assert backend.head("nested/file.txt").metadata == {"source": "test"}
        assert backend.download("nested/file.txt") == b"first"
        assert b"".join(backend.stream("nested/file.txt", chunk_size=2)) == b"first"
        assert backend.exists("nested/file.txt")
        assert backend.delete("nested/file.txt")
        assert not backend.delete("nested/file.txt")
        with pytest.raises(StorageNotFoundError):
            backend.head("nested/file.txt")

    @pytest.mark.parametrize("key", ["", "/absolute", "../escape", "a/../b", "a\\b", "nul\x00key", "./file"])
    def test_rejects_unsafe_keys(self, tmp_path: Path, key: str) -> None:
        backend = self._backend(tmp_path / "objects")

        with pytest.raises(StorageValidationError):
            backend.put(key, b"content")

    def test_rejects_parent_symlink_escape(self, tmp_path: Path) -> None:
        root = tmp_path / "objects"
        outside = tmp_path / "outside"
        outside.mkdir()
        backend = self._backend(root)
        (root / "linked").symlink_to(outside, target_is_directory=True)

        with pytest.raises(StorageOperationError, match="outside"):
            backend.put("linked/escape.txt", b"content")

        assert not (outside / "escape.txt").exists()

    def test_non_overwrite_create_is_atomic_under_concurrency(self, tmp_path: Path) -> None:
        backend = self._backend(tmp_path / "objects")

        def create(value: int) -> bool:
            try:
                backend.put("same.txt", str(value).encode())
            except StorageAlreadyExistsError:
                return False
            return True

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(create, range(20)))

        assert sum(results) == 1
        assert backend.download("same.txt").isdigit()

    def test_copy_move_and_signed_url_contract(self, tmp_path: Path) -> None:
        backend = self._backend(tmp_path / "objects")
        backend.put("source.txt", b"content", metadata={"source": "test"})

        copied = backend.copy("source.txt", "copied.txt")
        assert copied.metadata == {"source": "test"}
        with pytest.raises(StorageAlreadyExistsError):
            backend.copy("source.txt", "copied.txt")
        moved = backend.mv("copied.txt", "moved.txt")
        assert moved.key == "moved.txt"
        assert not backend.exists("copied.txt")
        with pytest.raises(StorageUnsupportedOperationError):
            backend.get_signed_url("source.txt")


class TestStorageService:
    """Exercise facade validation and lifecycle behavior."""

    def test_validates_content_and_metadata(self, tmp_path: Path) -> None:
        service = StorageService()
        service.configure("local", LocalStorageSettings(root=tmp_path / "objects"))

        with pytest.raises(StorageValidationError):
            service.put("file.txt", "not-bytes")  # type: ignore[arg-type]
        with pytest.raises(StorageValidationError):
            service.put("file.txt", b"content", metadata={"ok": 1})  # type: ignore[dict-item]

    def test_close_and_reconfigure_are_idempotent(self, tmp_path: Path) -> None:
        service = StorageService()
        service.configure("local", LocalStorageSettings(root=tmp_path / "one"))
        service.configure("local", LocalStorageSettings(root=tmp_path / "two"))
        service.close()
        service.close()

    def test_failed_reconfigure_preserves_the_open_existing_backend(self, tmp_path: Path) -> None:
        service = StorageService()
        existing = service.configure("local", LocalStorageSettings(root=tmp_path / "objects"))

        with pytest.raises(StorageConfigurationError, match="BUCKET"):
            service.configure("s3", S3StorageSettings())

        assert service.get_backend() is existing
        assert not existing._closed


class TestS3Storage:
    """Test S3 calls against fakes without credentials or network access."""

    def _backend(self, client: Mock, **settings: object) -> S3FileBackend:
        return S3FileBackend(S3StorageSettings(bucket="bucket", **settings), client=client)

    def test_put_uses_prefix_conditional_create_and_response_metadata(self) -> None:
        client = Mock()
        client.put_object.return_value = {"ETag": '"etag-value"', "ChecksumSHA256": "checksum", "VersionId": "v1"}
        backend = self._backend(client, prefix="prefix/")

        stored = backend.put("file.txt", b"content", mime_type="text/plain", metadata={"kind": "test"})

        assert stored.etag == "etag-value"
        assert stored.checksum == "checksum"
        assert stored.provider_metadata == {"backend": "s3", "VersionId": "v1"}
        client.put_object.assert_called_once_with(
            Bucket="bucket",
            Key="prefix/file.txt",
            Body=b"content",
            ContentType="text/plain",
            Metadata={"kind": "test"},
            IfNoneMatch="*",
        )

    def test_head_stream_copy_move_and_signed_url(self) -> None:
        client = Mock()
        client.head_object.return_value = {
            "ContentLength": 7,
            "ContentType": "text/plain",
            "ETag": '"etag"',
            "ChecksumSHA256": "checksum",
            "LastModified": datetime(2026, 8, 7, tzinfo=UTC),
            "Metadata": {"source": "test"},
        }
        body = Mock()
        body.iter_chunks.return_value = iter([b"con", b"tent"])
        client.get_object.return_value = {"Body": body}
        client.generate_presigned_url.return_value = "https://example.invalid/signed"
        backend = self._backend(client, prefix="prefix")

        assert backend.head("source.txt").size == 7
        assert b"".join(backend.stream("source.txt", chunk_size=3)) == b"content"
        body.close.assert_called_once()
        assert backend.get_signed_url("source.txt", expires_in=120) == "https://example.invalid/signed"
        client.generate_presigned_url.assert_called_once_with(
            "get_object", Params={"Bucket": "bucket", "Key": "prefix/source.txt"}, ExpiresIn=120
        )

        backend.copy("source.txt", "copy.txt", overwrite=True)
        client.copy_object.assert_called_once_with(
            Bucket="bucket",
            Key="prefix/copy.txt",
            CopySource={"Bucket": "bucket", "Key": "prefix/source.txt"},
        )
        backend.mv("source.txt", "moved.txt", overwrite=True)
        client.delete_object.assert_called_once_with(Bucket="bucket", Key="prefix/source.txt")

    def test_s3_errors_and_endpoint_configuration(self) -> None:
        client = Mock()
        client.head_object.side_effect = ClientError("404")
        client.get_object.side_effect = ClientError("404")
        backend = self._backend(client)

        with pytest.raises(StorageNotFoundError):
            backend.download("missing.txt")
        assert not backend.exists("missing.txt")
        assert not backend.delete("missing.txt")
        with pytest.raises(StorageConfigurationError, match="BUCKET"):
            S3FileBackend(S3StorageSettings(), client=Mock())
        with pytest.raises(StorageConfigurationError, match="https"):
            S3FileBackend(S3StorageSettings(bucket="bucket", endpoint_url="http://localhost"), client=Mock())

    @pytest.mark.parametrize(
        ("code", "expected_error"),
        [
            ("403", StorageOperationError),
            ("503", StorageConnectionError),
            ("PreconditionFailed", StorageAlreadyExistsError),
        ],
    )
    def test_put_maps_provider_errors(self, code: str, expected_error: type[Exception]) -> None:
        client = Mock()
        client.put_object.side_effect = ClientError(code)
        backend = self._backend(client)

        with pytest.raises(expected_error):
            backend.put("object.txt", b"content")
