"""Provider-neutral storage entities."""

from datetime import datetime
from typing import Any

from pydantic import Field

from ...entities import BedrockEntity


class StoredFile(BedrockEntity):
    """Portable metadata for a stored object.

    ``provider_metadata`` contains JSON-compatible extension values supplied by
    the backend and never contains credentials, signed headers, or file bytes.
    """

    key: str
    size: int
    mime_type: str | None = None
    etag: str | None = None
    checksum: str | None = None
    last_modified: datetime | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
    provider_metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def content_type(self) -> str | None:
        """Return the legacy name for :attr:`mime_type`."""
        return self.mime_type
