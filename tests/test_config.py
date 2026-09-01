"""Tests for src.config — configuration loading from .env."""

import os
from unittest.mock import patch

import pytest

from src.config import Config, get_config, reset_config


@pytest.fixture(autouse=True)
def clear_config_cache():
    """Reset the cached config singleton before each test."""
    reset_config()
    yield
    reset_config()


class TestConfigDefaults:
    """Configuration should use sensible defaults when .env is absent."""

    def test_default_model_provider(self):
        cfg = Config()
        assert cfg.model_provider == "deepseek"

    def test_default_reasoning_effort(self, monkeypatch):
        monkeypatch.delenv("REASONING_EFFORT", raising=False)
        cfg = Config()
        assert cfg.reasoning_effort == "high"

    def test_default_api_keys_are_empty(self, monkeypatch):
        # Clear any keys set by the real .env file
        for var in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "CLAUDE_API_KEY", "GLM_API_KEY"):
            monkeypatch.delenv(var, raising=False)
        cfg = Config()
        assert cfg.deepseek_api_key == ""
        assert cfg.openai_api_key == ""
        assert cfg.claude_api_key == ""
        assert cfg.glm_api_key == ""

    def test_default_sagemath_settings(self):
        cfg = Config()
        assert cfg.sagemath_cmd == "sage"
        assert isinstance(cfg.sagemath_timeout, int)
        assert cfg.sagemath_timeout > 0
        assert cfg.sagemath_use_wsl is True

    def test_project_root_is_two_levels_above_config_file(self):
        cfg = Config()
        assert (cfg.project_root / "src" / "config.py").exists()


class TestConfigValidation:
    """Config.validate() should catch misconfigurations."""

    def test_valid_config_has_no_errors_when_key_set(self):
        cfg = Config()
        cfg.model_provider = "deepseek"
        cfg.deepseek_api_key = "sk-test"
        assert cfg.validate() == []

    def test_missing_api_key_for_active_provider(self):
        cfg = Config()
        cfg.model_provider = "deepseek"
        cfg.deepseek_api_key = ""
        errors = cfg.validate()
        assert len(errors) == 1
        assert "deepseek" in errors[0].lower()

    def test_unknown_provider(self):
        cfg = Config()
        cfg.model_provider = "unknown-llm"
        errors = cfg.validate()
        assert len(errors) >= 1
        assert "unknown" in errors[0].lower()

    def test_get_api_key_returns_correct_key(self):
        cfg = Config()
        cfg.deepseek_api_key = "sk-ds-1"
        cfg.openai_api_key = "sk-oai-2"
        assert cfg.get_api_key("deepseek") == "sk-ds-1"
        assert cfg.get_api_key("openai") == "sk-oai-2"

    def test_get_api_key_defaults_to_active_provider(self):
        cfg = Config()
        cfg.model_provider = "openai"
        cfg.openai_api_key = "sk-oai-test"
        assert cfg.get_api_key() == "sk-oai-test"


class TestConfigFromEnvironment:
    """Configuration values are read from environment variables."""

    def test_loads_from_env(self, monkeypatch):
        monkeypatch.setenv("MODEL_PROVIDER", "claude")
        monkeypatch.setenv("CLAUDE_API_KEY", "sk-ant-test")
        monkeypatch.setenv("SAGEMATH_TIMEOUT", "300")
        cfg = Config()
        assert cfg.model_provider == "claude"
        assert cfg.claude_api_key == "sk-ant-test"
        assert cfg.sagemath_timeout == 300

    def test_sagemath_use_wsl_false(self, monkeypatch):
        monkeypatch.setenv("SAGEMATH_USE_WSL", "false")
        cfg = Config()
        assert cfg.sagemath_use_wsl is False


class TestGetConfigSingleton:
    """get_config() returns a cached singleton."""

    def test_returns_same_instance(self):
        c1 = get_config()
        c2 = get_config()
        assert c1 is c2

    def test_reset_config_creates_new_instance(self):
        c1 = get_config()
        reset_config()
        c2 = get_config()
        assert c1 is not c2
