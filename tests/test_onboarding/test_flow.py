"""Tests for non-interactive onboarding flow halves."""

from __future__ import annotations


def test_interactive_provider_choice_offers_only_verified_supported_providers():
    from opensquilla.onboarding.flow import OnboardOptions, _ask_provider_choice

    captured: dict[str, list[str]] = {}

    class _Question:
        def ask(self) -> str:
            return "openrouter (OpenRouter)"

    class _Questionary:
        def select(self, _message: str, *, choices: list[str]) -> _Question:
            captured["choices"] = choices
            return _Question()

    _ask_provider_choice(_Questionary(), OnboardOptions())

    offered = {choice.split(" ")[0] for choice in captured["choices"]}
    assert offered == {
        "openrouter",
        "openai",
        "anthropic",
        "ollama",
        "deepseek",
        "gemini",
        "dashscope",
        "moonshot",
        "zhipu",
        "qianfan",
        "volcengine",
    }


def test_noninteractive_provider_configure_writes_config(tmp_path, monkeypatch):
    target = tmp_path / "c.toml"
    monkeypatch.setenv("OPENSQUILLA_GATEWAY_CONFIG_PATH", str(target))
    from opensquilla.onboarding.flow import run_noninteractive_provider_configure

    result = run_noninteractive_provider_configure(
        "openrouter",
        {"model": "deepseek/deepseek-v4-flash", "api_key": "sk"},
    )
    assert result.path == target
    assert "openrouter" in target.read_text()


def test_noninteractive_channel_add_writes_config(tmp_path, monkeypatch):
    target = tmp_path / "c.toml"
    monkeypatch.setenv("OPENSQUILLA_GATEWAY_CONFIG_PATH", str(target))
    from opensquilla.onboarding.flow import run_noninteractive_channel_add

    result = run_noninteractive_channel_add("slack", {"name": "w", "token": "x"})
    assert result.path == target
    assert "slack" in target.read_text()


def test_interactive_configure_without_tty_does_not_create_config(
    tmp_path, monkeypatch
):
    target = tmp_path / "c.toml"
    monkeypatch.setenv("OPENSQUILLA_GATEWAY_CONFIG_PATH", str(target))
    from opensquilla.onboarding import flow

    monkeypatch.setattr(flow, "_is_tty", lambda: False)
    result = flow.run_interactive_configure("providers")

    assert result is None
    assert not target.exists()
