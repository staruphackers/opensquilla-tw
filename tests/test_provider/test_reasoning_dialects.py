"""Consistency and unit tests for the reasoning-dialect registry.

Locks two properties of ``provider/reasoning_dialects.py``:

1. Every ``reasoning_format`` value the runtime can produce today resolves in
   ``DIALECTS`` (or is an explicit, deliberate skip), so a new capability
   ladder branch cannot silently serialize without a dialect entry.
2. Each dialect's enable/disable payload matches the exact literals the
   request-builder ladder produced before the extraction.
"""

from __future__ import annotations

from typing import Any

from opensquilla.engine.types import ThinkingLevel
from opensquilla.provider.compat_policy import compat_policy_for_kind, known_policy_kinds
from opensquilla.provider.reasoning_dialects import (
    DIALECTS,
    ReasoningDisableArgs,
    ReasoningEnableArgs,
    apply_reasoning_disable,
    apply_reasoning_enable,
)
from opensquilla.provider.registry import list_provider_specs

# Every reasoning_format value reachable today, with where each comes from:
#   "openrouter" — compat_policy: openrouter policy replay_reasoning_format;
#       model_catalog.get_capabilities catalog-info branch (an OpenRouter
#       /models row with reasoning support); provider/ensemble.py members.
#   "openai"     — get_capabilities api.openai.com + gpt-5/o1/o3/o4 prefix
#       branch (model_catalog.py).
#   "deepseek"   — compat_policy: deepseek policy default_reasoning_format;
#       get_capabilities deepseek-base-url branch and the
#       ProviderSpec(reasoning_shape="deepseek") branch (registry.py: deepseek).
#   "gemini"     — get_capabilities ProviderSpec(reasoning_shape="gemini")
#       branch, gemini-2.5 prefix ladder (registry.py: gemini).
#   "zai"        — get_capabilities ProviderSpec(reasoning_shape="zai")
#       branch, glm prefix ladder (registry.py: zhipu).
#   "dashscope"  — get_capabilities provider_id == "dashscope" branch, qwen/qwq
#       prefix ladder.
#   "moonshot"   — get_capabilities provider_id == "moonshot" branch, kimi
#       prefix ladder.
#   "volcengine" — get_capabilities provider_id == "volcengine" AND
#       provider_id == "byteplus" branches (two providers, one wire spelling).
#   "none"       — ModelCapabilities default plus every non-reasoning
#       fallthrough in get_capabilities and ProviderSpec.reasoning_shape.
REACHABLE_REASONING_FORMATS = frozenset(
    {
        "openrouter",
        "openai",
        "deepseek",
        "gemini",
        "zai",
        "dashscope",
        "moonshot",
        "volcengine",
        "none",
    }
)


def test_every_reachable_reasoning_format_has_a_dialect() -> None:
    missing = REACHABLE_REASONING_FORMATS - {"none"} - set(DIALECTS)
    assert not missing, (
        f"reasoning_format values reachable today without a DIALECTS entry: "
        f"{sorted(missing)} — a thinking request for them would silently "
        "serialize with no reasoning payload."
    )


def test_none_format_is_an_explicit_skip_not_an_entry() -> None:
    """Format "none" produced no payload in the ladder; the registry keeps
    that by omission, and both dispatch helpers must stay no-ops for it."""
    assert "none" not in DIALECTS
    payload: dict[str, Any] = {"model": "m"}
    apply_reasoning_enable(
        payload,
        "none",
        ReasoningEnableArgs(thinking_level=ThinkingLevel.HIGH, thinking_budget_tokens=5000),
    )
    apply_reasoning_disable(payload, "none", ReasoningDisableArgs(model="m"))
    assert payload == {"model": "m"}


def test_hardcoded_reachable_set_covers_policy_and_registry_sources() -> None:
    """Drift guard: any new format introduced through compat_policy or a
    ProviderSpec.reasoning_shape must be added to the hardcoded set above
    (and to DIALECTS) deliberately."""
    policy_formats = set()
    for kind in known_policy_kinds():
        policy = compat_policy_for_kind(kind)
        if policy.default_reasoning_format:
            policy_formats.add(policy.default_reasoning_format)
        if policy.replay_reasoning_format:
            policy_formats.add(policy.replay_reasoning_format)
    assert policy_formats <= REACHABLE_REASONING_FORMATS
    shape_formats = {spec.reasoning_shape for spec in list_provider_specs()}
    assert shape_formats <= REACHABLE_REASONING_FORMATS


def test_dialect_names_match_registry_keys() -> None:
    for key, dialect in DIALECTS.items():
        assert dialect.name == key


def test_moonshot_and_volcengine_are_two_entries_sharing_one_spelling() -> None:
    assert DIALECTS["moonshot"] is not DIALECTS["volcengine"]
    assert DIALECTS["moonshot"].enable is DIALECTS["volcengine"].enable
    assert DIALECTS["moonshot"].disable is DIALECTS["volcengine"].disable


def _enabled(reasoning_format: str, args: ReasoningEnableArgs) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    apply_reasoning_enable(payload, reasoning_format, args)
    return payload


def _disabled(reasoning_format: str, args: ReasoningDisableArgs) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    apply_reasoning_disable(payload, reasoning_format, args)
    return payload


_HIGH_ARGS = ReasoningEnableArgs(thinking_level=ThinkingLevel.HIGH, thinking_budget_tokens=5000)


def test_openrouter_enable_payload() -> None:
    assert _enabled("openrouter", _HIGH_ARGS) == {"reasoning": {"effort": "high"}}


def test_openrouter_disable_payload_is_gated_on_policy_model_set() -> None:
    disable_set = frozenset({"z-ai/glm-5"})
    listed = ReasoningDisableArgs(
        model="Z-AI/GLM-5 ", disable_reasoning_by_default_models=disable_set
    )
    assert _disabled("openrouter", listed) == {"reasoning": {"enabled": False}}
    unlisted = ReasoningDisableArgs(
        model="minimax/minimax-m2.5", disable_reasoning_by_default_models=disable_set
    )
    assert _disabled("openrouter", unlisted) == {}


def test_openai_enable_payload_and_no_disable_payload() -> None:
    assert _enabled("openai", _HIGH_ARGS) == {"reasoning_effort": "high"}
    assert DIALECTS["openai"].disable is None
    assert _disabled("openai", ReasoningDisableArgs(model="gpt-5.4")) == {}


def test_deepseek_enable_payload_maps_levels_to_documented_efforts() -> None:
    assert _enabled("deepseek", _HIGH_ARGS) == {
        "thinking": {"type": "enabled"},
        "reasoning_effort": "high",
    }
    xhigh = ReasoningEnableArgs(thinking_level=ThinkingLevel.XHIGH, thinking_budget_tokens=5000)
    assert _enabled("deepseek", xhigh) == {
        "thinking": {"type": "enabled"},
        "reasoning_effort": "max",
    }


def test_deepseek_disable_payload() -> None:
    assert _disabled("deepseek", ReasoningDisableArgs(model="deepseek-v4-flash")) == {
        "thinking": {"type": "disabled"}
    }


def test_gemini_enable_payload() -> None:
    assert _enabled("gemini", _HIGH_ARGS) == {"reasoning_effort": "high"}


def test_gemini_disable_payload_is_gated_on_documented_off_control() -> None:
    flash = ReasoningDisableArgs(model="gemini-2.5-flash")
    assert _disabled("gemini", flash) == {"reasoning_effort": "none"}
    pro = ReasoningDisableArgs(model="gemini-2.5-pro")
    assert _disabled("gemini", pro) == {}


def test_zai_enable_and_disable_payloads() -> None:
    assert _enabled("zai", _HIGH_ARGS) == {"thinking": {"type": "enabled"}}
    assert _disabled("zai", ReasoningDisableArgs(model="glm-5")) == {
        "thinking": {"type": "disabled"}
    }


def test_dashscope_enable_payload_carries_thinking_budget() -> None:
    args = ReasoningEnableArgs(thinking_level=ThinkingLevel.HIGH, thinking_budget_tokens=4096)
    assert _enabled("dashscope", args) == {"enable_thinking": True, "thinking_budget": 4096}


def test_dashscope_disable_payload() -> None:
    assert _disabled("dashscope", ReasoningDisableArgs(model="qwen3-coder-plus")) == {
        "enable_thinking": False
    }


def test_moonshot_enable_and_disable_payloads() -> None:
    assert _enabled("moonshot", _HIGH_ARGS) == {"thinking": {"type": "enabled"}}
    assert _disabled("moonshot", ReasoningDisableArgs(model="kimi-k2.5")) == {
        "thinking": {"type": "disabled"}
    }


def test_volcengine_enable_and_disable_payloads() -> None:
    assert _enabled("volcengine", _HIGH_ARGS) == {"thinking": {"type": "enabled"}}
    assert _disabled("volcengine", ReasoningDisableArgs(model="doubao-seed-1-6")) == {
        "thinking": {"type": "disabled"}
    }


def test_enable_effort_resolves_from_budget_when_level_is_absent() -> None:
    """The budget fallback ladder moved with the helper: pin its bands."""
    assert ReasoningEnableArgs(thinking_level=None, thinking_budget_tokens=1024).effort == "low"
    assert ReasoningEnableArgs(thinking_level=None, thinking_budget_tokens=5000).effort == "medium"
    assert ReasoningEnableArgs(thinking_level=None, thinking_budget_tokens=20000).effort == "high"


def test_unknown_format_produces_no_payload_in_either_direction() -> None:
    payload: dict[str, Any] = {}
    apply_reasoning_enable(payload, "think_tags", _HIGH_ARGS)
    apply_reasoning_disable(payload, "think_tags", ReasoningDisableArgs(model="m"))
    apply_reasoning_enable(payload, "", _HIGH_ARGS)
    apply_reasoning_disable(payload, "", ReasoningDisableArgs(model="m"))
    assert payload == {}
