"""
DataSight settings — Pydantic-Settings backed configuration.

All values can be overridden via DATASIGHT_* environment variables (case-insensitive).
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProvider(str, Enum):
    OLLAMA = "ollama"
    OPENAI = "openai"


class ApprovalChannel(str, Enum):
    UI = "ui"
    SLACK = "slack"
    GITHUB_PR = "github_pr"


class PatchMode(str, Enum):
    GIT_PR = "git_pr"
    DIRECT_WRITE = "direct"


class DataSightSettings(BaseSettings):
    """Runtime configuration for DataSight."""

    model_config = SettingsConfigDict(
        env_prefix="DATASIGHT_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Master switch
    enabled: bool = True

    # LLM
    llm_provider: LLMProvider = LLMProvider.OLLAMA
    llm_model: str = "llama3.2:8b"
    ollama_base_url: str = "http://localhost:11434"
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"

    # Airflow
    airflow_api_url: str = "http://localhost:8080/api/v1"
    airflow_username: str = "airflow"
    airflow_password: str = "airflow"
    dags_folder: str = "/opt/airflow/dags"

    # Approval workflow
    approval_required: bool = True
    approval_channels: List[ApprovalChannel] = Field(default_factory=lambda: [ApprovalChannel.UI])
    approval_timeout_minutes: int = 60

    # Git
    git_enabled: bool = False
    git_repo_url: Optional[str] = None
    git_token: Optional[str] = None
    git_branch_prefix: str = "datasight/fix"

    # Patch
    patch_mode: PatchMode = PatchMode.DIRECT_WRITE

    # Slack
    slack_webhook_url: Optional[str] = None
    slack_channel: str = "#datasight"

    @field_validator("approval_channels", mode="before")
    @classmethod
    def _split_channels(cls, value):
        """Allow comma-separated env var: DATASIGHT_APPROVAL_CHANNELS=ui,slack,github_pr."""
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        return value


@lru_cache(maxsize=1)
def get_settings() -> DataSightSettings:
    """Return a cached singleton of DataSightSettings."""
    return DataSightSettings()
