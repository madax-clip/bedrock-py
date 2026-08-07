"""Shared settings helpers for the storage contrib module."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class StorageSettings(BaseSettings):
    """Common base for storage backend settings."""

    model_config = SettingsConfigDict(extra="ignore")
