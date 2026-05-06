"""Tests for the shared onboarding setup engine."""

import tomllib

from opensquilla.onboarding.setup_engine import SetupEngine


def test_setup_engine_applies_provider_and_router_without_persisting_secret(tmp_path):
    target = tmp_path / "config.toml"
    engine = SetupEngine(path=target)

    engine.apply(
        "provider",
        {
            "providerId": "deepseek",
            "model": "deepseek-chat",
            "apiKeyEnv": "DEEPSEEK_API_KEY",
        },
    )
    engine.apply("router", {"mode": "recommended"})
    result = engine.persist()

    data = tomllib.loads(target.read_text())
    assert result.path == target
    assert data["llm"]["provider"] == "deepseek"
    assert data["llm"]["api_key_env"] == "DEEPSEEK_API_KEY"
    assert "api_key" not in data["llm"]
    assert data["squilla_router"]["tier_profile"] == "deepseek"
    assert "tiers" not in data["squilla_router"]


def test_setup_engine_next_steps_do_not_include_secret(tmp_path):
    engine = SetupEngine(path=tmp_path / "config.toml")
    engine.apply(
        "provider",
        {
            "providerId": "openrouter",
            "model": "deepseek/deepseek-v4-flash",
            "apiKey": "sk-secret",
        },
    )

    text = engine.preview_next_steps()

    assert "sk-secret" not in text
    assert "opensquilla gateway start" in text
    assert "openrouter" in text


def test_setup_engine_catalog_includes_memory_embedding():
    engine = SetupEngine()

    payload = engine.catalog("memory-embedding")

    provider_ids = {p["providerId"] for p in payload["memoryEmbeddingProviders"]}
    assert {"auto", "local", "openai", "ollama", "none"} <= provider_ids
