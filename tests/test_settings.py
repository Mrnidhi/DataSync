"""Tests for datasight.config.settings"""

import os
from unittest.mock import patch

import pytest

from datasight.config.settings import (
    ApprovalChannel,
    DataSightSettings,
    LLMProvider,
    PatchMode,
    get_settings,
)


class TestDataSightSettings:
    """Test configuration loading and defaults."""

    def test_default_values(self):
        """All defaults should be sensible without any env vars."""
        settings = DataSightSettings()
        assert settings.enabled is True
        assert settings.llm_provider == LLMProvider.OLLAMA
        assert settings.llm_model == "llama3.2:8b"
        assert settings.airflow_api_url == "http://localhost:8080/api/v1"
        assert settings.airflow_username == "airflow"
        assert settings.airflow_password == "airflow"
        assert settings.dags_folder == "/opt/airflow/dags"
        assert settings.approval_required is True
        assert settings.git_enabled is False
        assert settings.patch_mode == PatchMode.DIRECT_WRITE
        assert ApprovalChannel.UI in settings.approval_channels

    def test_env_var_override(self):
        """Settings should be overridable via DATASIGHT_* env vars."""
        env = {
            "DATASIGHT_ENABLED": "false",
            "DATASIGHT_LLM_PROVIDER": "openai",
            "DATASIGHT_LLM_MODEL": "gpt-4o",
            "DATASIGHT_GIT_ENABLED": "true",
            "DATASIGHT_APPROVAL_REQUIRED": "false",
        }
        with patch.dict(os.environ, env, clear=False):
            settings = DataSightSettings()
            assert settings.enabled is False
            assert settings.llm_provider == LLMProvider.OPENAI
            assert settings.llm_model == "gpt-4o"
            assert settings.git_enabled is True
            assert settings.approval_required is False

    def test_enum_values(self):
        """All enum members should be valid string values."""
        assert LLMProvider.OLLAMA.value == "ollama"
        assert LLMProvider.OPENAI.value == "openai"
        assert ApprovalChannel.SLACK.value == "slack"
        assert ApprovalChannel.GITHUB_PR.value == "github_pr"
        assert PatchMode.GIT_PR.value == "git_pr"
        assert PatchMode.DIRECT_WRITE.value == "direct"

    def test_optional_fields_default_none(self):
        """Optional fields should default to None."""
        settings = DataSightSettings()
        assert settings.openai_api_key is None
        assert settings.git_repo_url is None
        assert settings.git_token is None
        assert settings.slack_webhook_url is None

    def test_get_settings_returns_instance(self):
        """get_settings() should return a DataSightSettings instance."""
        get_settings.cache_clear()
        settings = get_settings()
        assert isinstance(settings, DataSightSettings)
