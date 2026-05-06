"""Coordinate interactive and non-interactive onboarding flows."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any

from opensquilla.onboarding.channel_specs import (
    get_channel_setup_spec,
    list_channel_setup_specs,
)
from opensquilla.onboarding.config_store import (
    PersistResult,
    default_config_path,
    load_config,
    persist_config,
)
from opensquilla.onboarding.mutations import (
    upsert_channel,
    upsert_llm_provider,
    upsert_search_provider,
)
from opensquilla.onboarding.provider_specs import (
    get_provider_setup_spec,
    list_provider_setup_specs,
)
from opensquilla.onboarding.search_specs import (
    get_search_provider_setup_spec,
    list_search_provider_setup_specs,
)
from opensquilla.onboarding.status import get_onboarding_status


@dataclass(frozen=True)
class OnboardOptions:
    skip_channels: bool = False
    skip_search: bool = False
    if_needed: bool = False
    provider_id: str | None = None
    model: str | None = None
    api_key: str | None = None
    api_key_env: str | None = None
    base_url: str | None = None
    router_mode: str = "recommended"
    minimal: bool = False


def _is_tty() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def run_noninteractive_provider_configure(
    provider_id: str, values: dict[str, Any]
) -> PersistResult:
    from opensquilla.onboarding.setup_engine import SetupEngine

    engine = SetupEngine()
    engine.apply(
        "provider",
        {
            "providerId": provider_id,
            "model": values.get("model", ""),
            "apiKey": values.get("api_key", ""),
            "apiKeyEnv": values.get("api_key_env", ""),
            "baseUrl": values.get("base_url", ""),
            "proxy": values.get("proxy", ""),
        },
    )
    router_mode = values.get("router", "")
    if router_mode:
        engine.apply("router", {"mode": router_mode})
    return engine.persist()


def run_noninteractive_channel_add(
    type_name: str, values: dict[str, Any]
) -> PersistResult:
    cfg = load_config()
    payload = {"type": type_name, **values}
    result = upsert_channel(cfg, entry_payload=payload)
    return persist_config(result.config, restart_required=True)


def run_noninteractive_search_configure(
    provider_id: str, values: dict[str, Any]
) -> PersistResult:
    cfg = load_config()
    result = upsert_search_provider(
        cfg,
        provider_id=provider_id,
        api_key=values.get("api_key", ""),
        max_results=int(values.get("max_results", 5)),
        proxy=values.get("proxy", ""),
        use_env_proxy=bool(values.get("use_env_proxy", False)),
        fallback_policy=values.get("fallback_policy", "off"),
        diagnostics=bool(values.get("diagnostics", False)),
    )
    return persist_config(result.config, restart_required=False)


def _print_noninteractive_hint() -> PersistResult:
    print(
        "Onboarding requires a TTY. Run a non-interactive equivalent, e.g.:\n"
        "  opensquilla onboard --provider openrouter "
        "--model deepseek/deepseek-v4-flash --api-key-env OPENROUTER_API_KEY "
        "--router recommended --minimal\n"
        "  opensquilla search configure brave --api-key $BRAVE_SEARCH_API_KEY\n"
        "  opensquilla channels add slack --name work --token $SLACK_TOKEN"
    )
    return PersistResult(
        path=default_config_path(),
        backup_path=None,
        restart_required=False,
        warnings=["tty_required"],
    )


def _ask_provider_choice(questionary, options: OnboardOptions):
    if options.provider_id:
        spec = get_provider_setup_spec(options.provider_id)
        return spec, spec.provider_id
    supported = [s for s in list_provider_setup_specs() if s.runtime_supported]
    pid = questionary.select(
        "LLM provider",
        choices=[f"{s.provider_id} ({s.label})" for s in supported],
    ).ask()
    pid_clean = pid.split(" ")[0]
    return get_provider_setup_spec(pid_clean), pid_clean


def _ask_provider_fields(
    questionary, spec, options: OnboardOptions
) -> dict[str, Any]:
    answers: dict[str, Any] = {}
    answers["model"] = options.model or (
        questionary.text("Model id").ask() or ""
    )
    if spec.requires_api_key:
        env_key = options.api_key_env or spec.env_key
        if options.api_key_env:
            answers["api_key"] = ""
            answers["api_key_env"] = options.api_key_env
        elif env_key and os.environ.get(env_key) and not options.api_key:
            use_env = questionary.confirm(
                f"Detected ${env_key}. Use it for this provider?", default=True
            ).ask()
            answers["api_key"] = ""
            answers["api_key_env"] = env_key if use_env else ""
        else:
            answers["api_key"] = options.api_key or (
                questionary.password("API key").ask() or ""
            )
            answers["api_key_env"] = ""
    else:
        answers["api_key"] = options.api_key or ""
        answers["api_key_env"] = ""
    if spec.requires_base_url:
        answers["base_url"] = options.base_url or (
            questionary.text("Base URL", default=spec.default_base_url).ask() or ""
        )
    else:
        answers["base_url"] = options.base_url or spec.default_base_url
    return answers


def _ask_search_choice(questionary):
    supported = [s for s in list_search_provider_setup_specs() if s.runtime_supported]
    provider_id = questionary.select(
        "Search provider",
        choices=[f"{s.provider_id} ({s.label})" for s in supported],
    ).ask()
    provider_id_clean = provider_id.split(" ")[0]
    return get_search_provider_setup_spec(provider_id_clean), provider_id_clean


def _ask_search_fields(questionary, spec) -> dict[str, Any]:
    answers: dict[str, Any] = {}
    if spec.requires_api_key:
        answers["api_key"] = questionary.password("Search API key").ask() or ""
    else:
        answers["api_key"] = ""
    max_results = questionary.text("Max search results", default="5").ask() or "5"
    answers["max_results"] = int(max_results)
    answers["proxy"] = questionary.text("Search HTTP proxy", default="").ask() or ""
    answers["use_env_proxy"] = questionary.confirm(
        "Use environment proxy for search?", default=False
    ).ask()
    answers["fallback_policy"] = questionary.select(
        "Search fallback policy", choices=["off", "network"], default="off"
    ).ask()
    answers["diagnostics"] = questionary.confirm(
        "Enable search diagnostics?", default=False
    ).ask()
    return answers


def run_interactive_search_configure() -> PersistResult:
    if not _is_tty():
        return _print_noninteractive_hint()

    import questionary

    spec, provider_id = _ask_search_choice(questionary)
    answers = _ask_search_fields(questionary, spec)
    cfg = load_config()
    result = upsert_search_provider(
        cfg,
        provider_id=provider_id,
        api_key=answers.get("api_key", ""),
        max_results=answers["max_results"],
        proxy=answers.get("proxy", ""),
        use_env_proxy=answers.get("use_env_proxy", False),
        fallback_policy=answers.get("fallback_policy", "off"),
        diagnostics=answers.get("diagnostics", False),
    )
    return persist_config(result.config, restart_required=False)


def run_interactive_onboard(options: OnboardOptions) -> PersistResult:
    cfg = load_config()
    if options.if_needed and get_onboarding_status(cfg).llm_configured:
        return persist_config(cfg, restart_required=False, backup=False)

    if not _is_tty():
        return _print_noninteractive_hint()

    import questionary

    spec, provider_id = _ask_provider_choice(questionary, options)
    answers = _ask_provider_fields(questionary, spec, options)
    res = upsert_llm_provider(
        cfg,
        provider_id=provider_id,
        model=answers["model"],
        api_key=answers.get("api_key", ""),
        api_key_env=answers.get("api_key_env", ""),
        base_url=answers.get("base_url", ""),
    )
    cfg_after_provider = res.config
    if options.router_mode:
        from opensquilla.onboarding.mutations import upsert_router

        router_res = upsert_router(cfg_after_provider, mode=options.router_mode)
        cfg_after_provider = router_res.config
    persist = persist_config(cfg_after_provider, restart_required=False)

    if options.minimal:
        return persist

    if not options.skip_channels and questionary.confirm(
        "Configure a messaging channel now?", default=False
    ).ask():
        run_interactive_channel_add(None)

    if not options.skip_search and questionary.confirm(
        "Configure web search now?", default=False
    ).ask():
        run_interactive_search_configure()

    return persist


def run_interactive_channel_add(type_name: str | None) -> PersistResult:
    if not _is_tty():
        return _print_noninteractive_hint()

    import questionary

    if type_name is None:
        type_name = questionary.select(
            "Channel type",
            choices=[s.type for s in list_channel_setup_specs()],
        ).ask()
    spec = get_channel_setup_spec(type_name)
    answers: dict[str, Any] = {"type": type_name}
    for f in spec.fields:
        if f.field_type == "select":
            select_default = f.default if isinstance(f.default, str) else None
            answers[f.name] = questionary.select(
                f.label, choices=list(f.choices), default=select_default
            ).ask()
        elif f.field_type == "bool":
            answers[f.name] = questionary.confirm(
                f.label, default=bool(f.default)
            ).ask()
        elif f.field_type == "password":
            answers[f.name] = questionary.password(f.label).ask() or ""
        elif f.field_type == "int":
            raw = questionary.text(
                f.label, default=str(f.default or 0)
            ).ask() or "0"
            answers[f.name] = int(raw)
        elif f.field_type == "float":
            raw = questionary.text(
                f.label, default=str(f.default or 0.0)
            ).ask() or "0"
            answers[f.name] = float(raw)
        else:
            answers[f.name] = questionary.text(
                f.label, default=str(f.default or "")
            ).ask() or ""

    cfg = load_config()
    res = upsert_channel(cfg, entry_payload=answers)
    return persist_config(res.config, restart_required=True)


def run_interactive_channel_edit(name: str | None = None) -> PersistResult:
    if not _is_tty():
        return _print_noninteractive_hint()

    import questionary

    cfg = load_config()
    existing_entries = [e.model_dump(mode="python") for e in cfg.channels.channels]
    if not existing_entries:
        print("No channels to edit. Use 'configure --section channels' to add one.")
        return persist_config(cfg, restart_required=False, backup=False)

    if name is None:
        name = questionary.select(
            "Channel to edit",
            choices=[e["name"] for e in existing_entries],
        ).ask()
    target_entry = next(e for e in existing_entries if e["name"] == name)
    type_name = target_entry["type"]
    spec = get_channel_setup_spec(type_name)

    answers: dict[str, Any] = {"type": type_name, "name": name}
    for f in spec.fields:
        if f.name == "name":
            continue
        current = target_entry.get(f.name)
        if f.field_type == "select":
            answers[f.name] = questionary.select(
                f.label,
                choices=list(f.choices),
                default=current if isinstance(current, str) else None,
            ).ask()
        elif f.field_type == "bool":
            answers[f.name] = questionary.confirm(
                f.label,
                default=bool(current) if current is not None else bool(f.default),
            ).ask()
        elif f.field_type == "password":
            answers[f.name] = questionary.password(
                f"{f.label} (blank = keep current)"
            ).ask() or ""
        elif f.field_type == "int":
            raw = questionary.text(
                f.label,
                default=str(current if current is not None else f.default or 0),
            ).ask() or "0"
            answers[f.name] = int(raw)
        elif f.field_type == "float":
            raw = questionary.text(
                f.label,
                default=str(current if current is not None else f.default or 0.0),
            ).ask() or "0"
            answers[f.name] = float(raw)
        else:
            answers[f.name] = questionary.text(
                f.label,
                default=str(current if current is not None else f.default or ""),
            ).ask() or ""

    res = upsert_channel(cfg, entry_payload=answers)
    return persist_config(res.config, restart_required=True)


def run_interactive_configure(section: str | None = None) -> PersistResult | None:
    if not _is_tty():
        _print_noninteractive_hint()
        return None

    import questionary

    section = section or questionary.select(
        "Section",
        choices=["providers", "channels", "search", "image-generation"],
    ).ask()
    if section == "providers":
        return run_interactive_onboard(
            OnboardOptions(skip_channels=True, skip_search=True)
        )
    if section == "channels":
        existing = load_config().channels.channels
        if existing:
            mode = questionary.select(
                "Channel action",
                choices=["add", "edit"],
                default="add",
            ).ask()
            if mode == "edit":
                return run_interactive_channel_edit(None)
        return run_interactive_channel_add(None)
    if section == "search":
        return run_interactive_search_configure()
    print(
        f"Section {section!r} is not yet supported in the wizard. "
        "Edit ~/.opensquilla/config.toml directly."
    )
    return None
