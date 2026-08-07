"""Settings for the Bedrock metrics service."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class MetricsSettings(BaseSettings):
    """Settings for the metrics service.

    Attributes:
        strict: When ``True``, provider failures raise
            :class:`~bedrock.contrib.metrics.exc.MetricsProviderError` instead of
            being logged and swallowed (fail-open). Defaults to ``False``.
        max_name_length: Maximum length of a metric name.
        max_tags: Maximum number of tags per metric call.
        max_tag_key_length: Maximum length of a tag key.
        max_tag_value_length: Maximum length of a tag value.
    """

    model_config = SettingsConfigDict(env_prefix="METRICS_", extra="ignore")

    strict: bool = False
    max_name_length: int = 128
    max_tags: int = 20
    max_tag_key_length: int = 64
    max_tag_value_length: int = 128
