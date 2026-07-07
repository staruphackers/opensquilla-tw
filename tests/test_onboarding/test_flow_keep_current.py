"""Wizard re-runs must seed prompts from the stored config, not factory
defaults, and channel edits must survive a rename with blank secrets.

Regression coverage for the destructive-re-save class: pressing Enter
through a search or image-generation wizard re-run used to persist factory
defaults over the operator's stored settings, and renaming a channel while
leaving a secret blank (as the wizard hint instructs) crashed with an
uncaught ValueError because the keep-current merge was keyed to the payload
name.
"""

from __future__ import annotations

import sys
import tomllib
import types
from typing import Any

from opensquilla.onboarding import flow
from opensquilla.onboarding.config_store import load_config
from opensquilla.onboarding.image_generation_specs import (
    get_image_generation_provider_setup_spec,
)
from opensquilla.onboarding.search_specs import get_search_provider_setup_spec


class _Answer:
    def __init__(self, value: Any) -> None:
        self.value = value

    def ask(self) -> Any:
        return self.value


class _RecordingConsole:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def print(self, message: str = "", *_a, **_kw) -> None:
        self.messages.append(str(message))

    def joined(self) -> str:
        return "\n".join(self.messages)


class _EnterThroughQuestionary(types.SimpleNamespace):
    """Answers every prompt with its default (a plain Enter), recording the
    defaults so tests can assert what the wizard offered."""

    def __init__(self, *, password_value: str = "sk-new") -> None:
        super().__init__()
        self.defaults: dict[str, Any] = {}
        self._password_value = password_value

    def select(self, message, **kwargs):
        self.defaults[message] = kwargs.get("default")
        choices = list(kwargs.get("choices") or [])
        return _Answer(kwargs.get("default") or (choices[0] if choices else None))

    def text(self, message, **kwargs):
        self.defaults[message] = kwargs.get("default")
        return _Answer(kwargs.get("default"))

    def confirm(self, message, **kwargs):
        self.defaults[message] = kwargs.get("default")
        return _Answer(kwargs.get("default"))

    def password(self, message, **kwargs):
        self.defaults[message] = None
        return _Answer(self._password_value)

    def checkbox(self, message, **kwargs):
        raise AssertionError(f"unexpected checkbox prompt: {message}")


# ---------------------------------------------------------------------------
# R7 — search wizard re-run seeds stored values.
# ---------------------------------------------------------------------------


_STORED_SEARCH_TOML = (
    'search_provider = "brave"\n'
    'search_api_key = "brave-stored-key"\n'
    "search_max_results = 10\n"
    'search_proxy = "http://127.0.0.1:7890"\n'
    "search_use_env_proxy = true\n"
    'search_fallback_policy = "network"\n'
    "search_diagnostics = true\n"
)


def test_search_fields_seed_defaults_from_stored_config(tmp_path, monkeypatch):
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    target = tmp_path / "c.toml"
    target.write_text(_STORED_SEARCH_TOML, encoding="utf-8")
    cfg = load_config(target)

    q = _EnterThroughQuestionary(password_value="brave-rotated-key")
    answers = flow._ask_search_fields(q, get_search_provider_setup_spec("brave"), cfg)

    # An Enter-through key rotation keeps every stored global setting.
    assert answers["api_key"] == "brave-rotated-key"
    assert answers["max_results"] == 10
    assert answers["proxy"] == "http://127.0.0.1:7890"
    assert answers["use_env_proxy"] is True
    assert answers["fallback_policy"] == "network"
    assert answers["diagnostics"] is True
    assert q.defaults["Max search results"] == "10"
    assert q.defaults["Search HTTP proxy"] == "http://127.0.0.1:7890"


def test_search_configure_rerun_enter_through_keeps_stored_settings(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    target = tmp_path / "c.toml"
    target.write_text(_STORED_SEARCH_TOML, encoding="utf-8")
    monkeypatch.setattr(flow, "_is_tty", lambda: True)
    monkeypatch.setattr(flow, "console", _RecordingConsole())

    class _Q(_EnterThroughQuestionary):
        def select(self, message, **kwargs):
            if message == "Search provider":
                return _Answer("brave (Brave Search)")
            return super().select(message, **kwargs)

    monkeypatch.setitem(
        sys.modules, "questionary", _Q(password_value="brave-rotated-key")
    )

    flow.run_interactive_search_configure(config_path=target)

    data = tomllib.loads(target.read_text())
    assert data["search_api_key"] == "brave-rotated-key"
    assert data["search_max_results"] == 10
    assert data["search_proxy"] == "http://127.0.0.1:7890"
    assert data["search_use_env_proxy"] is True
    assert data["search_fallback_policy"] == "network"
    assert data["search_diagnostics"] is True


# ---------------------------------------------------------------------------
# R7 — image-generation wizard re-run seeds stored values.
# ---------------------------------------------------------------------------


def test_image_generation_fields_seed_defaults_from_stored_config(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    target = tmp_path / "c.toml"
    target.write_text(
        "[image_generation]\n"
        "enabled = false\n"
        'primary = "openai/custom-image-model"\n'
        "[image_generation.providers.openai]\n"
        'api_key = "sk-image-old"\n'
        'base_url = "https://images.example.test/v1"\n',
        encoding="utf-8",
    )
    cfg = load_config(target)

    q = _EnterThroughQuestionary(password_value="sk-image-new")
    answers = flow._ask_image_generation_fields(
        q, get_image_generation_provider_setup_spec("openai"), cfg
    )

    # An Enter-through key rotation keeps the stored custom model, base URL,
    # and the deliberate enabled=false decision.
    assert answers["primary"] == "openai/custom-image-model"
    assert answers["base_url"] == "https://images.example.test/v1"
    assert answers["enabled"] is False
    assert q.defaults["Primary image model"] == "openai/custom-image-model"
    assert q.defaults["Image base URL"] == "https://images.example.test/v1"
    assert q.defaults["Image generation enabled?"] is False


def test_image_generation_fields_fresh_config_defaults_unchanged(monkeypatch):
    from opensquilla.gateway.config import GatewayConfig

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    spec = get_image_generation_provider_setup_spec("openai")

    q = _EnterThroughQuestionary(password_value="sk-image-first")
    answers = flow._ask_image_generation_fields(q, spec, GatewayConfig())

    assert answers["primary"] == spec.default_model
    assert answers["base_url"] == spec.default_base_url
    assert answers["enabled"] is True


# ---------------------------------------------------------------------------
# R8 — channel edit rename with a blank (keep-current) secret.
# ---------------------------------------------------------------------------


def test_channel_edit_rename_with_blank_secret_keeps_token(tmp_path, monkeypatch):
    """Following the wizard's own "leave blank to keep the stored value"
    hint while renaming the entry used to crash with an uncaught
    ValueError ("channel field 'token' requires a non-empty value") because
    the keep-current merge looked up the stored entry by the NEW name."""
    from opensquilla.onboarding.setup_engine import SetupEngine

    target = tmp_path / "c.toml"
    engine = SetupEngine(path=target)
    engine.apply(
        "channels",
        {"type": "telegram", "name": "t1", "token": "tg-stored-token"},
    )
    engine.persist()

    monkeypatch.setattr(flow, "_is_tty", lambda: True)
    monkeypatch.setattr(flow, "console", _RecordingConsole())

    class _Q(_EnterThroughQuestionary):
        def select(self, message, **kwargs):
            if message == "Channel to edit":
                return _Answer("t1")
            return super().select(message, **kwargs)

        def text(self, message, **kwargs):
            if message == "Channel name":
                return _Answer("t2")  # rename in the same edit
            return super().text(message, **kwargs)

        def password(self, message, **kwargs):
            return _Answer("")  # blank = keep stored value, per the hint

    monkeypatch.setitem(sys.modules, "questionary", _Q())

    flow.run_interactive_channel_edit(None, config_path=target)

    entries = {
        e.name: e for e in load_config(target).channels.channels
    }
    assert "t2" in entries
    assert entries["t2"].token == "tg-stored-token"
