"""Exception types for the Bedrock storage system."""

from ...exc import BedrockExc


class StorageError(BedrockExc):
    """Base exception for storage operations."""

    detail = "Storage operation failed."


class StorageConfigurationError(StorageError):
    """Raised when a storage backend has invalid configuration."""

    detail = "Storage backend configuration is invalid."


class StorageValidationError(StorageError):
    """Raised when a storage API argument is invalid."""

    detail = "Storage request is invalid."


class StorageNotFoundError(StorageError):
    """Raised when a stored object does not exist."""

    detail = "Stored object was not found."


class StorageAlreadyExistsError(StorageError):
    """Raised when a non-overwriting upload finds an existing object."""

    detail = "Stored object already exists."


class StorageConnectionError(StorageError):
    """Raised when a storage provider cannot be reached."""

    detail = "Failed to connect to the storage backend."


class StorageOperationError(StorageError):
    """Raised when a provider operation fails."""

    detail = "Storage provider operation failed."


class StorageUnsupportedOperationError(StorageError):
    """Raised when a backend cannot provide an optional storage operation."""

    detail = "Storage operation is not supported by this backend."
