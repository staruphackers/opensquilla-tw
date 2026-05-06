"""Tests for OnboardingStatus derivation."""

from opensquilla.gateway.config import GatewayConfig, LlmProviderConfig
from opensquilla.onboarding.mutations import upsert_channel
from opensquilla.onboarding.status import get_onboarding_status


def test_default_provider_with_no_key_needs_onboarding():
    cfg = GatewayConfig()
    cfg.llm = LlmProviderConfig(
        provider="openrouter",
        model="m",
        api_key="",
        base_url="https://openrouter.ai/api/v1",
    )
    s = get_onboarding_status(cfg)
    assert s.needs_onboarding is True


def test_provider_with_key_is_configured():
    cfg = GatewayConfig()
    cfg.llm = LlmProviderConfig(
        provider="openrouter",
        model="m",
        api_key="sk-x",
        base_url="https://openrouter.ai/api/v1",
    )
    s = get_onboarding_status(cfg)
    assert s.llm_configured is True
    assert s.llm_source == "explicit"
    assert s.needs_onboarding is False


def test_provider_with_env_key_is_configured(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-from-env")
    cfg = GatewayConfig()
    cfg.llm = LlmProviderConfig(
        provider="openrouter",
        model="m",
        api_key="",
        api_key_env="OPENROUTER_API_KEY",
        base_url="https://openrouter.ai/api/v1",
    )

    s = get_onboarding_status(cfg)

    assert s.llm_configured is True
    assert s.llm_source == "env"
    assert s.needs_onboarding is False


def test_runtime_secret_marker_keeps_env_source_after_resolution(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-from-env")
    from opensquilla.gateway.llm_runtime import resolve_llm_runtime_config

    cfg = GatewayConfig()
    cfg.llm = LlmProviderConfig(
        provider="openrouter",
        model="m",
        api_key="",
        api_key_env="OPENROUTER_API_KEY",
        base_url="https://openrouter.ai/api/v1",
    )
    resolve_llm_runtime_config(cfg)

    s = get_onboarding_status(cfg)

    assert cfg.llm.api_key == "sk-from-env"
    assert "llm.api_key" in cfg._runtime_secret_paths
    assert s.llm_configured is True
    assert s.llm_source == "env"


def test_provider_with_missing_env_key_needs_onboarding(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    cfg = GatewayConfig()
    cfg.llm = LlmProviderConfig(
        provider="openrouter",
        model="m",
        api_key="",
        api_key_env="OPENROUTER_API_KEY",
        base_url="https://openrouter.ai/api/v1",
    )

    s = get_onboarding_status(cfg)

    assert s.llm_configured is False
    assert s.llm_source == "missing_env"
    assert s.needs_onboarding is True


def test_matching_llm_key_does_not_configure_image_generation_until_enabled(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    cfg = GatewayConfig()
    cfg.llm = LlmProviderConfig(
        provider="openrouter",
        model="m",
        api_key="sk-or",
        base_url="https://openrouter.ai/api/v1",
    )
    s = get_onboarding_status(cfg)
    assert s.image_generation_configured is False
    assert s.image_generation_enabled is False
    assert s.image_generation_source == "none"
    assert s.image_generation_provider == ""


def test_enabled_image_generation_can_use_matching_llm_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    cfg = GatewayConfig()
    cfg.llm = LlmProviderConfig(
        provider="openrouter",
        model="m",
        api_key="sk-or",
        base_url="https://openrouter.ai/api/v1",
    )
    cfg.image_generation.enabled = True
    s = get_onboarding_status(cfg)
    assert s.image_generation_configured is True
    assert s.image_generation_enabled is True
    assert s.image_generation_source == "llm_fallback"
    assert s.image_generation_provider == "openrouter"


def test_image_generation_disabled_is_not_configured():
    cfg = GatewayConfig()
    cfg.image_generation.enabled = False
    cfg.image_generation.providers.openai.api_key = "sk-openai"
    s = get_onboarding_status(cfg)
    assert s.image_generation_configured is False
    assert s.image_generation_enabled is False


def test_ollama_without_key_is_configured():
    cfg = GatewayConfig()
    cfg.llm = LlmProviderConfig(
        provider="ollama",
        model="llama3",
        api_key="",
        base_url="http://localhost:11434",
    )
    s = get_onboarding_status(cfg)
    assert s.llm_configured is True


def test_zero_channels_means_not_messaging_configured():
    cfg = GatewayConfig()
    s = get_onboarding_status(cfg)
    assert s.channel_count == 0
    assert s.channels_configured is False


def test_channel_present_marks_configured():
    cfg = GatewayConfig()
    res = upsert_channel(cfg, entry_payload={"type": "slack", "name": "w", "token": "x"})
    s = get_onboarding_status(res.config)
    assert s.channel_count == 1
    assert s.channels_configured is True
