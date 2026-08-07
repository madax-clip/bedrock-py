# Bedrock Storage Module

Stable synchronous, provider-neutral object storage at `bedrock.contrib.storage`. Use the local backend by default; install `bedrock-core[storage-s3]` before configuring S3.

## Quick Start

```python
from bedrock.contrib.storage import storage

storage.configure("local")
stored = storage.put("avatars/42.png", image_bytes, mime_type="image/png")
metadata = storage.head(stored.key)
body = storage.download(stored.key)
```

Use `stream(path, chunk_size=64 * 1024)` for large reads. It returns a synchronous iterable of bounded byte chunks. Use `copy` and `mv` only within the currently configured backend.

## Key APIs

- `storage.put(path, content, *, mime_type=None, metadata=None, overwrite=False) -> StoredFile`
- `storage.head(path) -> StoredFile`
- `storage.download(path) -> bytes`
- `storage.stream(path, *, chunk_size=64 * 1024) -> Iterable[bytes]`
- `storage.delete(path) -> bool`, `storage.exists(path) -> bool`
- `storage.copy(source, destination, *, overwrite=False) -> StoredFile`
- `storage.mv(source, destination, *, overwrite=False) -> StoredFile`
- `storage.get_signed_url(path, *, expires_in=3600) -> str`

`StoredFile` contains provider-neutral metadata (`key`, `mime_type`, `size`, `etag`, `checksum`, `last_modified`, and user metadata) plus safe JSON-compatible provider metadata. It never includes credentials or content.

## Configuration

`storage.configure("local")` is the default and reads `STORAGE_LOCAL_ROOT`. `storage.configure("s3")` requires `STORAGE_S3_BUCKET`; optional values are `STORAGE_S3_PREFIX`, `STORAGE_S3_REGION_NAME`, and `STORAGE_S3_ENDPOINT_URL`. Boto3 uses its standard credential provider chain. Custom endpoints require HTTPS unless `STORAGE_S3_ALLOW_INSECURE_ENDPOINT=true` is set for local development.

## Safety and limitations

- Keys must be relative POSIX paths. Empty keys, absolute paths, backslashes, NUL bytes, and `.` or `..` segments are rejected.
- Local storage rejects signed URLs because `file://` URLs are not a portable or safe application API.
- S3 signed URLs and their signature parameters must not be logged.
- Storage does not provide multipart upload, directory listing, public URLs, version management, or cross-backend transfer.
- S3 conditional copy is a preflight check and can race. Use `put(..., overwrite=False)` for strict create-only writes.
