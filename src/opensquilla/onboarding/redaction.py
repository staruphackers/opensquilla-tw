"""Secret-aware redaction helpers used by mutations, RPC, and CLI output."""

from __future__ import annotations

from typing import Any

from opensquilla.onboarding.channel_specs import get_channel_setup_spec

REDACTED_PLACEHOLDER = "***"

_PROVIDER_SECRET_FIELDS = frozenset({"api_key"})


def redact_provider_payload(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    for key in _PROVIDER_SECRET_FIELDS:
        if key in out and out[key]:
            out[key] = REDACTED_PLACEHOLDER
    return out


_TIER_SECRET_FIELDS = frozenset({"api_key", "token", "secret"})


def redact_router_tiers_payload(tiers: dict[str, Any]) -> dict[str, Any]:
    """Redact secret-like fields hand-written into router tier dicts.

    Tiers are untyped dicts and carry no secrets by design (credentials live
    in ``[llm_profiles.<id>]``), but nothing stops an operator from pasting
    an ``api_key`` into one — the router-configure RPC response must not
    echo it back. (Adversarial-review finding salvaged from PR #406.)
    """
    out: dict[str, Any] = {}
    for tier_name, tier in tiers.items():
        if not isinstance(tier, dict):
            out[tier_name] = tier
            continue
        redacted = dict(tier)
        for key in _TIER_SECRET_FIELDS:
            if key in redacted and redacted[key]:
                redacted[key] = REDACTED_PLACEHOLDER
        out[tier_name] = redacted
    return out


def redact_search_payload(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    if out.get("api_key"):
        out["api_key"] = REDACTED_PLACEHOLDER
    return out


def redact_image_generation_payload(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    if out.get("api_key"):
        out["api_key"] = REDACTED_PLACEHOLDER
    return out


def redact_audio_payload(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    if out.get("api_key"):
        out["api_key"] = REDACTED_PLACEHOLDER
    return out


def redact_memory_embedding_payload(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    if out.get("api_key"):
        out["api_key"] = REDACTED_PLACEHOLDER
    remote = out.get("remote")
    if isinstance(remote, dict) and remote.get("api_key"):
        remote = dict(remote)
        remote["api_key"] = REDACTED_PLACEHOLDER
        out["remote"] = remote
    return out


def redact_channel_entry(type_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        spec = get_channel_setup_spec(type_name)
    except KeyError:
        return dict(payload)
    secret_names = {f.name for f in spec.fields if f.secret}
    out = dict(payload)
    for key in secret_names:
        if key in out and out[key]:
            out[key] = REDACTED_PLACEHOLDER
    return out
