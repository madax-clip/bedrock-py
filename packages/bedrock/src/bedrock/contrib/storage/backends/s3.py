"""Optional boto3-backed S3 storage backend."""

from collections.abc import Iterator, Mapping
from datetime import datetime
from typing import Any

from pydantic_settings import SettingsConfigDict

from ..base import FileBackend, IterableBytes, normalize_key
from ..entities import StoredFile
from ..exc import (
    StorageAlreadyExistsError,
    StorageConfigurationError,
    StorageConnectionError,
    StorageNotFoundError,
    StorageOperationError,
    StorageValidationError,
)
from ..settings import StorageSettings


class S3StorageSettings(StorageSettings):
    """Settings for :class:`S3FileBackend`; credentials use boto3's provider chain."""

    model_config = SettingsConfigDict(env_prefix="STORAGE_S3_", extra="ignore")

    bucket: str = ""
    prefix: str = ""
    region_name: str | None = None
    endpoint_url: str | None = None
    allow_insecure_endpoint: bool = False


class S3FileBackend(FileBackend):
    """S3 adapter with conditional creation, metadata, and presigned downloads."""

    def __init__(self, settings: S3StorageSettings | None = None, *, client: Any | None = None) -> None:
        self._settings = settings or S3StorageSettings()
        if not self._settings.bucket:
            raise StorageConfigurationError("STORAGE_S3_BUCKET must be configured for the S3 backend.")
        if (
            self._settings.endpoint_url
            and not self._settings.endpoint_url.startswith("https://")
            and not self._settings.allow_insecure_endpoint
        ):
            raise StorageConfigurationError(
                "STORAGE_S3_ENDPOINT_URL must use https unless insecure endpoints are enabled."
            )
        self._client = client or self._create_client()
        self._closed = False

    @property
    def settings(self) -> S3StorageSettings:
        """Return the settings used by this backend."""
        return self._settings

    def _create_client(self) -> Any:
        try:
            import boto3
        except ImportError as exc:
            raise StorageConfigurationError(
                "S3 storage requires the optional dependency. Install with 'pip install bedrock-core[storage-s3]'."
            ) from exc
        return boto3.client("s3", region_name=self._settings.region_name, endpoint_url=self._settings.endpoint_url)

    def _provider_key(self, path: str) -> tuple[str, str]:
        key = normalize_key(path)
        prefix = self._settings.prefix.strip("/")
        return key, f"{prefix}/{key}" if prefix else key

    @staticmethod
    def _client_error(exc: Exception, *, key: str) -> StorageOperationError:
        try:
            code = str(exc.response["Error"]["Code"])
        except (AttributeError, KeyError, TypeError):
            return StorageOperationError(f"S3 operation failed for object: {key}")
        if code in {"NoSuchKey", "NoSuchBucket", "404", "NotFound"}:
            return StorageNotFoundError(f"Storage object not found: {key}")
        if code in {"PreconditionFailed", "412", "ConditionalRequestConflict"}:
            return StorageAlreadyExistsError(f"Storage object already exists: {key}")
        if code in {"RequestTimeout", "ServiceUnavailable", "SlowDown", "500", "502", "503", "504"}:
            return StorageConnectionError(f"S3 service is unavailable for object: {key}")
        return StorageOperationError(f"S3 operation failed for object: {key}")

    @staticmethod
    def _stored_file(key: str, response: Mapping[str, Any], *, fallback_size: int | None = None) -> StoredFile:
        last_modified = response.get("LastModified")
        return StoredFile(
            key=key,
            size=int(response.get("ContentLength", fallback_size or 0)),
            mime_type=response.get("ContentType"),
            etag=str(response["ETag"]).strip('"') if response.get("ETag") else None,
            checksum=response.get("ChecksumSHA256"),
            last_modified=last_modified if isinstance(last_modified, datetime) else None,
            metadata=dict(response.get("Metadata") or {}),
            provider_metadata={
                "backend": "s3",
                **{
                    field: response[field]
                    for field in ("VersionId", "StorageClass", "ServerSideEncryption", "Expiration", "Restore")
                    if response.get(field) is not None
                },
            },
        )

    def put(
        self,
        path: str,
        content: bytes,
        *,
        mime_type: str | None = None,
        metadata: Mapping[str, str] | None = None,
        overwrite: bool = False,
    ) -> StoredFile:
        """Put an object, conditionally refusing an existing key by default."""
        if not isinstance(content, bytes):
            raise StorageValidationError("Storage content must be bytes.")
        key, provider_key = self._provider_key(path)
        request: dict[str, Any] = {"Bucket": self._settings.bucket, "Key": provider_key, "Body": content}
        if mime_type:
            request["ContentType"] = mime_type
        if metadata:
            request["Metadata"] = dict(metadata)
        if not overwrite:
            request["IfNoneMatch"] = "*"
        try:
            response = self._client.put_object(**request)
        except Exception as exc:
            raise self._client_error(exc, key=key) from exc
        response = dict(response)
        response["ContentLength"] = len(content)
        response["ContentType"] = mime_type
        response["Metadata"] = dict(metadata or {})
        return self._stored_file(key, response, fallback_size=len(content))

    def head(self, path: str) -> StoredFile:
        """Read provider metadata without downloading content."""
        key, provider_key = self._provider_key(path)
        try:
            response = self._client.head_object(Bucket=self._settings.bucket, Key=provider_key)
        except Exception as exc:
            raise self._client_error(exc, key=key) from exc
        return self._stored_file(key, response)

    def download(self, path: str) -> bytes:
        """Get an object's complete bytes."""
        key, provider_key = self._provider_key(path)
        try:
            response = self._client.get_object(Bucket=self._settings.bucket, Key=provider_key)
            return response["Body"].read()
        except Exception as exc:
            raise self._client_error(exc, key=key) from exc

    def stream(self, path: str, *, chunk_size: int = 64 * 1024) -> IterableBytes:
        """Yield the S3 response body in bounded chunks."""
        if chunk_size <= 0:
            raise StorageValidationError("Storage stream chunk_size must be greater than zero.")
        key, provider_key = self._provider_key(path)

        def chunks() -> Iterator[bytes]:
            body: Any | None = None
            try:
                response = self._client.get_object(Bucket=self._settings.bucket, Key=provider_key)
                body = response["Body"]
                yield from body.iter_chunks(chunk_size=chunk_size)
            except Exception as exc:
                raise self._client_error(exc, key=key) from exc
            finally:
                if body is not None:
                    close = getattr(body, "close", None)
                    if close is not None:
                        close()

        return chunks()

    def delete(self, path: str) -> bool:
        """Delete an object, returning ``False`` when it does not exist."""
        key, provider_key = self._provider_key(path)
        try:
            self._client.head_object(Bucket=self._settings.bucket, Key=provider_key)
            self._client.delete_object(Bucket=self._settings.bucket, Key=provider_key)
            return True
        except Exception as exc:
            mapped = self._client_error(exc, key=key)
            if isinstance(mapped, StorageNotFoundError):
                return False
            raise mapped from exc

    def exists(self, path: str) -> bool:
        """Use a provider head request to test object existence."""
        try:
            self.head(path)
            return True
        except StorageNotFoundError:
            return False

    def copy(self, source: str, destination: str, *, overwrite: bool = False) -> StoredFile:
        """Copy an S3 object within this backend's configured bucket."""
        source_key, source_provider_key = self._provider_key(source)
        destination_key, destination_provider_key = self._provider_key(destination)
        if not overwrite and self.exists(destination_key):
            raise StorageAlreadyExistsError(f"Storage object already exists: {destination_key}")
        try:
            self._client.copy_object(
                Bucket=self._settings.bucket,
                Key=destination_provider_key,
                CopySource={"Bucket": self._settings.bucket, "Key": source_provider_key},
            )
        except Exception as exc:
            raise self._client_error(exc, key=source_key) from exc
        return self.head(destination_key)

    def mv(self, source: str, destination: str, *, overwrite: bool = False) -> StoredFile:
        """Move an S3 object by copying it and then deleting its source."""
        stored = self.copy(source, destination, overwrite=overwrite)
        self.delete(source)
        return stored

    def get_signed_url(self, path: str, *, expires_in: int = 3600) -> str:
        """Generate a temporary S3 GET URL without exposing credentials in logs."""
        if expires_in <= 0:
            raise StorageValidationError("Signed URL expiry must be greater than zero.")
        _, provider_key = self._provider_key(path)
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._settings.bucket, "Key": provider_key},
                ExpiresIn=expires_in,
            )
        except Exception as exc:
            raise self._client_error(exc, key=path) from exc

    def close(self) -> None:
        """Close the underlying HTTP client when it exposes a close method."""
        if self._closed:
            return
        self._closed = True
        close = getattr(self._client, "close", None)
        if close is not None:
            close()
