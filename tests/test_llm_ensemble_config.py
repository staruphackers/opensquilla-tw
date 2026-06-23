from __future__ import annotations

import pytest

from opensquilla.gateway.config import GatewayConfig, LlmEnsembleConfig
from opensquilla.provider import EnsembleProvider, build_ensemble_provider_from_config
from opensquilla.provider.selector import ProviderConfig
from opensquilla.provider.types import DoneEvent, Message, TextDeltaEvent


class _FallbackProvider:
    provider_name = "fallback"

    async def chat(self, messages: list[Message], tools=None, config=None):  # noqa: ANN001
        yield TextDeltaEvent(text="fallback")
        yield DoneEvent(model="fallback")

    async def list_models(self) -> list:
        return []


def test_llm_ensemble_config_defaults_disabled_with_profiles() -> None:
    cfg = GatewayConfig()

    assert cfg.llm_ensemble.enabled is False
    assert cfg.llm_ensemble.active_profile == "g3_standard"
    assert "g3_standard" in cfg.llm_ensemble.profiles
    assert "g1_code" in cfg.llm_ensemble.profiles
    assert [ref.model for ref in cfg.llm_ensemble.profiles["g1_code"].proposers] == [
        "deepseek/deepseek-v4-pro",
        "z-ai/glm-5.2",
        "moonshotai/kimi-k2.7-code",
    ]
    assert [ref.model for ref in cfg.llm_ensemble.profiles["g3_standard"].proposers] == [
        "deepseek/deepseek-v4-pro",
        "z-ai/glm-5.2",
        "google/gemini-3-flash-preview",
    ]
    assert cfg.llm_ensemble.profiles["g3_standard"].aggregator.model == "z-ai/glm-5.2"
    assert (
        cfg.llm_ensemble.profiles["g4_gemini_aggregator"].aggregator.model
        == "google/gemini-3-flash-preview"
    )
    assert cfg.llm_ensemble.profiles["g3_standard"].record_candidates is False


def test_llm_ensemble_config_validates_enabled_profile() -> None:
    with pytest.raises(ValueError, match="active_profile"):
        LlmEnsembleConfig(enabled=True, active_profile="missing")


def test_build_ensemble_provider_from_gateway_config() -> None:
    cfg = GatewayConfig(
        llm_ensemble={
            "enabled": True,
            "active_profile": "custom",
            "profiles": {
                "custom": {
                    "proposers": [{"model": "p1"}, {"model": "p2", "k": 2}],
                    "aggregator": {"model": "agg"},
                    "candidate_max_chars": 123,
                }
            },
        }
    )
    inherited = ProviderConfig(
        provider="openrouter",
        model="base",
        api_key="sk-test",
        base_url="https://openrouter.ai/api",
    )

    provider = build_ensemble_provider_from_config(
        config=cfg,
        inherited_provider_config=inherited,
        fallback_provider=_FallbackProvider(),
    )

    assert isinstance(provider, EnsembleProvider)
    assert provider.profile_name == "custom"
    assert [member.provider_config.model for member in provider.proposers] == ["p1", "p2"]
    assert provider.proposers[1].k == 2
    assert provider.aggregator.provider_config.model == "agg"
    assert provider.candidate_max_chars == 123
