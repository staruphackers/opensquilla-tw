import ast
import asyncio
import base64
import contextlib
import copy
import json
import sys
import textwrap
import tomllib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from opensquilla.engine.types import (
    AgentEvent,
    AgentState,
    ArtifactEvent,
    CompactionEvent,
    DoneEvent,
    ErrorEvent,
    RouterControlReplayEvent,
    RouterDecisionEvent,
    RunHeartbeatEvent,
    StateChangeEvent,
    TextDeltaEvent,
    ToolResultEvent,
    ToolUseStartEvent,
)


def _without_state_changes(events: list[AgentEvent]) -> list[AgentEvent]:
    return [event for event in events if not isinstance(event, StateChangeEvent)]


def test_agent_kernel_default_is_existing_opensquilla_agent() -> None:
    from opensquilla.engine.agent_core import resolve_agent_kernel_id

    assert resolve_agent_kernel_id(None, config=None) == "opensquilla"


def test_agent_kernel_rejects_unknown_ids_before_turn_start() -> None:
    from opensquilla.engine.agent_core import resolve_agent_kernel_id

    with pytest.raises(ValueError, match="Unsupported agent kernel"):
        resolve_agent_kernel_id("unknown", config=None)


def test_agent_kernel_rejects_non_string_ids_without_coercion() -> None:
    from opensquilla.engine.agent_core import AgentCoreConfig, resolve_agent_kernel_id

    class PretendsToBePi:
        def __str__(self) -> str:
            return "pi"

    with pytest.raises(ValueError, match="agent kernel must be a string"):
        resolve_agent_kernel_id(PretendsToBePi(), config=None)

    with pytest.raises(ValueError, match="agent kernel must be a string"):
        AgentCoreConfig.from_runtime_config(
            SimpleNamespace(agent_core=SimpleNamespace(kernel=PretendsToBePi()))
        )


def test_agent_core_config_rejects_non_string_protocol_and_pi_command() -> None:
    from opensquilla.engine.agent_core import AgentCoreConfig

    class PretendsToBeString:
        def __str__(self) -> str:
            return "opensquilla.agent_core.v1"

    with pytest.raises(ValueError, match="agent_core_protocol_version must be a string"):
        AgentCoreConfig.from_runtime_config(
            SimpleNamespace(agent_core_protocol_version=PretendsToBeString())
        )

    with pytest.raises(ValueError, match="pi_rpc_command must be a string"):
        AgentCoreConfig.from_runtime_config(
            SimpleNamespace(agent_core=SimpleNamespace(pi_rpc_command=PretendsToBeString()))
        )


def test_agent_core_config_rejects_non_boolean_strict_host_flags() -> None:
    from opensquilla.engine.agent_core import AgentCoreConfig

    flag_fields = [
        "strict_host_provider",
        "strict_host_tools",
        "strict_host_sessions",
        "strict_host_orchestration",
        "strict_host_finalizer",
    ]

    for field in flag_fields:
        with pytest.raises(ValueError, match=f"{field} must be a boolean"):
            AgentCoreConfig.from_runtime_config(SimpleNamespace(**{field: object()}))

    with pytest.raises(ValueError, match="strict_host_sessions must be a boolean"):
        AgentCoreConfig.from_runtime_config(
            SimpleNamespace(agent_core=SimpleNamespace(strict_host_sessions=object()))
        )


def test_pi_direct_config_rejects_string_disabled_test_fixture_opt_ins() -> None:
    from opensquilla.engine.agent_core import AgentCoreConfig, _pi_rpc_client_from_config

    class FakePiRpcClient:
        async def stream_prompt(self, prompt: str, **kwargs: Any) -> Any:
            if False:
                yield {"protocol": "opensquilla.agent_core.v1", "kind": "event"}

    with pytest.raises(ValueError, match="test-only Pi RPC command"):
        _pi_rpc_client_from_config(
            AgentCoreConfig(
                kernel="pi",
                pi_rpc_command=f"{sys.executable} /tmp/fake_pi_rpc.py",
                allow_test_pi_rpc_command="false",
            )
        )

    with pytest.raises(ValueError, match="test-only Pi RPC client"):
        _pi_rpc_client_from_config(
            AgentCoreConfig(
                kernel="pi",
                pi_rpc_client=FakePiRpcClient(),
                allow_test_pi_rpc_client="false",
            )
        )


def test_pi_direct_config_rejects_conflicting_client_and_command() -> None:
    from opensquilla.engine.agent_core import AgentCoreConfig, _pi_rpc_client_from_config

    class FakePiRpcClient:
        async def stream_prompt(self, prompt: str, **kwargs: Any) -> Any:
            if False:
                yield {"protocol": "opensquilla.agent_core.v1", "kind": "event"}

    with pytest.raises(
        ValueError,
        match="pi_rpc_client and pi_agent_rpc_command cannot both be configured",
    ):
        _pi_rpc_client_from_config(
            AgentCoreConfig(
                kernel="pi",
                pi_rpc_client=FakePiRpcClient(),
                pi_rpc_command=f"{sys.executable} /tmp/fake_pi_rpc.py",
                allow_test_pi_rpc_client=True,
                allow_test_pi_rpc_command=True,
            )
        )


@pytest.mark.parametrize(
    ("field_name", "config_kwargs"),
    [
        (
            "allow_test_pi_rpc_command",
            {
                "pi_rpc_command": "node opensquilla-pi-sidecar.js",
                "allow_test_pi_rpc_command": object(),
            },
        ),
        (
            "allow_test_pi_rpc_client",
            {
                "pi_rpc_client": SimpleNamespace(stream_prompt=lambda prompt: iter(())),
                "allow_test_pi_rpc_client": object(),
            },
        ),
    ],
)
def test_pi_direct_config_rejects_non_boolean_test_fixture_opt_ins(
    field_name: str,
    config_kwargs: dict[str, Any],
) -> None:
    from opensquilla.engine.agent_core import AgentCoreConfig, _pi_rpc_client_from_config

    with pytest.raises(ValueError, match=f"{field_name} must be a boolean"):
        _pi_rpc_client_from_config(AgentCoreConfig(kernel="pi", **config_kwargs))


@pytest.mark.parametrize(
    ("field_name", "config_kwargs"),
    [
        ("pi_rpc_command", {"pi_rpc_command": object()}),
        (
            "pi_rpc_command_provenance",
            {
                "pi_rpc_command": "node opensquilla-pi-sidecar.js",
                "pi_rpc_command_provenance": object(),
            },
        ),
        (
            "pi_rpc_client_provenance",
            {
                "pi_rpc_client": SimpleNamespace(stream_prompt=lambda prompt: iter(())),
                "pi_rpc_client_provenance": object(),
            },
        ),
    ],
)
def test_pi_direct_config_rejects_non_string_pi_command_fields(
    field_name: str,
    config_kwargs: dict[str, Any],
) -> None:
    from opensquilla.engine.agent_core import AgentCoreConfig, _pi_rpc_client_from_config

    with pytest.raises(ValueError, match=f"{field_name} must be a string"):
        _pi_rpc_client_from_config(AgentCoreConfig(kernel="pi", **config_kwargs))


def test_agent_core_config_defaults_to_python_kernel_and_strict_host_ports() -> None:
    from opensquilla.engine.agent_core import AGENT_CORE_PROTOCOL_VERSION, AgentCoreConfig

    config = AgentCoreConfig.from_runtime_config(None)

    assert config.kernel == "opensquilla"
    assert config.protocol_version == AGENT_CORE_PROTOCOL_VERSION
    assert config.pi_rpc_client_provenance is None
    assert config.pi_rpc_command_provenance is None
    assert config.allow_test_pi_rpc_client is False
    assert config.allow_test_pi_rpc_command is False
    assert config.strict_host_provider is True
    assert config.strict_host_tools is True
    assert config.strict_host_sessions is True
    assert config.strict_host_orchestration is True
    assert config.strict_host_finalizer is True


def test_kernel_runtime_protocol_does_not_require_python_agent_config_shape() -> None:
    from opensquilla.engine.agent_core import KernelRuntime

    assert {"set_history", "refresh_system_prompt", "run_turn"} <= set(
        KernelRuntime.__dict__
    )
    assert "config" not in getattr(KernelRuntime, "__annotations__", {})


def test_agent_core_config_supports_nested_pi_sidecar_settings() -> None:
    from opensquilla.engine.agent_core import AgentCoreConfig

    config = AgentCoreConfig.from_runtime_config(
        SimpleNamespace(
            agent_core=SimpleNamespace(
                kernel="pi",
                pi_rpc_command="node sidecar.js",
            )
        )
    )

    assert config.kernel == "pi"
    assert config.pi_rpc_command == "node sidecar.js"


def test_agent_core_config_supports_top_level_compact_pi_sidecar_aliases() -> None:
    from opensquilla.engine.agent_core import AgentCoreConfig

    config = AgentCoreConfig.from_runtime_config(
        SimpleNamespace(
            agent_kernel="pi",
            pi_rpc_command="node sidecar.js",
            pi_rpc_command_provenance=(
                "thin opensquilla.agent_core.v1 sidecar around "
                "github.com/earendil-works/pi"
            ),
        )
    )

    assert config.kernel == "pi"
    assert config.pi_rpc_command == "node sidecar.js"
    assert (
        config.pi_rpc_command_provenance
        == "thin opensquilla.agent_core.v1 sidecar around github.com/earendil-works/pi"
    )


def test_gateway_config_loads_agent_core_pi_kernel_for_turn_runner(tmp_path) -> None:
    from opensquilla.engine.agent_core import AgentCoreConfig
    from opensquilla.gateway.config import GatewayConfig

    config_path = tmp_path / "gateway.toml"
    command = (
        "node src/opensquilla/engine/pi_sidecar_bridge.mjs "
        "--module-root /tmp/opensquilla-pi-wrapper.v7600e"
    )
    provenance = (
        "thin opensquilla.agent_core.v1 bridge around github.com/earendil-works/pi "
        "@earendil-works/pi-agent-core @earendil-works/pi-ai; "
        "upstream Pi owns agent loop"
    )
    config_path.write_text(
        f"""
[llm]
provider = "openrouter"
model = "openai/gpt-4o-mini"
api_key_env = "OPENROUTER_API_KEY"

[agent_core]
kernel = "pi"
pi_agent_rpc_command = "{command}"
pi_agent_rpc_command_provenance = "{provenance}"
""",
        encoding="utf-8",
    )

    gateway_config = GatewayConfig.load(config_path)
    agent_core_config = AgentCoreConfig.from_runtime_config(gateway_config)

    assert agent_core_config.kernel == "pi"
    assert agent_core_config.pi_rpc_command is not None
    assert "pi_sidecar_bridge.mjs" in agent_core_config.pi_rpc_command


def test_agent_core_config_rejects_conflicting_top_level_pi_sidecar_aliases() -> None:
    from opensquilla.engine.agent_core import AgentCoreConfig

    with pytest.raises(
        ValueError,
        match="conflicting config values.*pi_agent_rpc_command.*pi_rpc_command",
    ):
        AgentCoreConfig.from_runtime_config(
            SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command="node canonical-sidecar.js",
                pi_rpc_command="node compact-sidecar.js",
            )
        )


def test_agent_core_config_allows_whitespace_equivalent_pi_command_aliases() -> None:
    from opensquilla.engine.agent_core import AgentCoreConfig

    config = AgentCoreConfig.from_runtime_config(
        SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_command=" node sidecar.js ",
            pi_rpc_command="node sidecar.js",
        )
    )

    assert config.pi_rpc_command == "node sidecar.js"


def test_agent_core_config_rejects_distinct_equal_pi_rpc_client_aliases() -> None:
    from opensquilla.engine.agent_core import AgentCoreConfig

    class EqualPiRpcClient:
        async def stream_prompt(self, prompt: str, **kwargs: Any) -> Any:
            if False:
                yield {"protocol": "opensquilla.agent_core.v1", "kind": "event"}

        def __eq__(self, other: object) -> bool:
            return isinstance(other, EqualPiRpcClient)

    with pytest.raises(
        ValueError,
        match="conflicting config values.*pi_agent_rpc_client.*pi_rpc_client",
    ):
        AgentCoreConfig.from_runtime_config(
            SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_client=EqualPiRpcClient(),
                pi_rpc_client=EqualPiRpcClient(),
            )
        )


def test_agent_core_contract_declares_pi_direct_use_boundary_and_provenance() -> None:
    contract = Path("docs/agent-core-contract.md").read_text(encoding="utf-8")
    required_fragments = (
        "## Pi Direct-Use Boundary And Provenance",
        (
            "Production Pi kernels must connect to a real upstream Pi runtime, "
            "CLI, package, or equivalent RPC process"
        ),
        (
            "OpenSquilla adapter code owns only process launch/connection, "
            "JSONL/RPC bridge, protocol frame validation, host-port dispatch, "
            "event normalization, and process lifecycle cleanup."
        ),
        "session key and session id must be non-empty strings",
        "`session_id` defaults to the host-selected `session_key`",
        "Pi sidecars may map this field to Pi `sessionId` for provider-cache identity",
        "The derived `agent_id` and host-authored `turn_id` must be non-empty",
        "`extra_messages` must be a list or `None`; history passed through",
        "tool definitions must be a list; metadata must be an object",
        (
            "Top-level sidecar frame fields are limited to `protocol`, `kind`, "
            "`type`, and `payload`"
        ),
        "Pi sidecar frame `protocol`, `kind`, and `type` values must be non-empty strings",
        "intent frame `type` values are validated before host-port lookup",
        "including `payload`, must be JSON-compatible before dispatch",
        "Python-only sidecar-visible values must fail instead of falling back to `str()`",
            (
                "Outgoing JSONL `turn_start.payload.prompt`, "
                "`turn_start.payload.kwargs.session_key`, "
                "`turn_start.payload.kwargs.session_id`, `intent_result.type`, "
                "and `intent_result.session_key` must be non-empty strings"
            ),
        (
            "When `turn_snapshot.session_key` or `turn_snapshot.session_id` "
            "is present alongside the top-level turn kwarg"
        ),
        (
            "If `turn_start.payload.kwargs.turn_snapshot` is present, it must "
            "be a JSON object before the command process starts"
        ),
        (
            "If `turn_snapshot.session_key` or `turn_snapshot.session_id` is "
            "present, it must be a non-empty string before the command process starts"
        ),
        (
            "Outgoing JSONL `intent_result.payload` must be an object and "
            "`intent_result.events` must be a list"
        ),
        (
            "Outgoing JSONL `intent_result.payload` and `intent_result.events` "
            "must be"
        ),
        "Outgoing JSONL `intent_result.type` must be one of the allowed Pi intent types",
        (
            "Feedback serialization failures are protocol errors, while ordinary "
            "callback delivery failures remain best-effort"
        ),
        (
            "Provider API keys and Pi command/provenance variables must not be "
            "inherited by Pi JSONL sidecar processes"
        ),
        (
            "JSONL command clients must drain sidecar stderr concurrently so "
            "diagnostic logs cannot block stdout frames"
        ),
        "Sidecar stdout frames must be UTF-8 JSONL",
        "Sidecar stdout JSONL frames must remain within the command client's bounded",
        (
            "JSONL command clients must reject duplicate JSON object keys and "
            "non-finite"
        ),
        (
            "A non-error `sessions_yield` result returned by `yield.request` "
            "must be the final event in its host-port batch"
        ),
        (
            "The host orchestration batch for `yield.request` must contain "
            "exactly one `sessions_yield` `ToolResultEvent`"
        ),
        "present `payload.code` must be a non-empty string",
        "transcript `tool_call_id` must be a non-empty string",
        (
            "Successful `yield.request` settlement does not write an "
            "`intent_result` frame"
        ),
        (
            "FakePiRpcClient, fake/mock/dummy/stub/test/fixture/example/"
            "sample/demo-labeled "
            "sidecars, and Python script sidecars are contract-test fixtures "
            "only"
        ),
        "Commands under `tests/`, `examples/`, `samples/`, or `demos/` paths",
        (
            "`python -m tests.*`, `python -m examples.*`, "
            "`python -m samples.*`, or `python -m demos.*` sidecar commands"
        ),
        (
            "Commands whose `PYTHONPATH` points at a `tests`, `examples`, "
            "`samples`, or `demos` directory"
        ),
        "must not become a production runtime fallback",
        (
            "Pi production startup must fail fast when neither "
            "`pi_agent_rpc_command` nor `pi_agent_rpc_client` is configured"
        ),
        (
            "Command argv arguments that name an upstream Pi package do not "
            "count as provenance"
        ),
        (
            "Sidecar package wrapper commands may name upstream Pi packages "
            "as configuration arguments"
        ),
        (
            "Runtime-reference options such as `--runtime`, "
            "`--runtime-package`, `--runtime_package`, `--pi-runtime`, "
            "`--pi_runtime`, `--piRuntime`, `--agent-runtime`, "
            "`--agent_runtime`, `--agentRuntime`, and `--runtimepackage` may "
            "name an upstream Pi package as inert wrapper configuration"
        ),
        (
            "Wrapper module-resolution options such as `--module-root` may point "
            "to an external wrapper/package root used to resolve installed "
            "upstream Pi packages"
        ),
        (
            "they do not count as provenance and must not vendor or point "
            "OpenSquilla at copied Pi implementation files inside "
            "`src/opensquilla` or upstream Pi repository source paths"
        ),
        (
            "The sidecar bridge package name itself does not count as "
            "upstream Pi runtime provenance"
        ),
        (
            "Direct Node execution of an upstream Pi package path is treated "
            "as native Pi CLI/package invocation"
        ),
        (
            "Direct package-runner commands under the upstream "
            "`@earendil-works/pi-*` namespace are native Pi packages, "
            "not OpenSquilla sidecars"
        ),
        (
            "Environment or shell launch wrappers such as `env ...`, "
            "`bash -lc ...`, `bash -lc 'exec -- ...'`, "
            "`bash -lc 'command -- ...'`, `csh -c ...`, `fish -c ...`, "
            "`tcsh -c ...`, `cmd /c ...`, or `powershell -Command ...` "
            "do not change this boundary"
        ),
        (
            "`env -S` / `env --split-string` wrappers must be parsed as the "
            "actual command argv"
        ),
        (
            "Ordinary model configuration variables such as `MODEL=rpc` are "
            "not mode selectors"
        ),
        (
            "PowerShell encoded command wrappers such as "
            "`powershell -EncodedCommand ...`, `powershell -enc ...`, or "
            "`pwsh -e ...` must be decoded and checked"
        ),
        (
            "opaque or undecodable encoded payloads must fail fast instead of "
            "being accepted as sidecar wrappers"
        ),
        (
            "PowerShell file wrappers such as `powershell -File ...` or "
            "`pwsh -File ...` must parse the script path and arguments"
        ),
        (
            "Process launch wrappers such as `timeout ...`, `nohup ...`, "
            "`nohup -- ...`, `nice ...`, `setsid ...`, or `stdbuf ...` "
            "follow the same rule"
        ),
        (
            "`corepack pnpm` / `corepack yarn` / `corepack npm` launchers "
            "follow package-runner native Pi checks"
        ),
        (
            "Package-runner package injection options such as `--package` and "
            "`-p` must not inject upstream Pi packages"
        ),
        (
            "Package-runner shell command options such as `npm exec -c ...` "
            "and `npx -c ...` follow the same native Pi checks"
        ),
        (
            "Node script runners such as `node --run pi` and package-runner "
            "`yarn node ...` must not hide native Pi RPC mode"
        ),
        (
            "Package script runners such as `npm run pi`, `pnpm run pi`, "
            "`yarn pi`, and `bun run pi` must not hide native Pi RPC mode"
        ),
        (
            "Direct TypeScript/Deno executors such as `tsx`, `ts-node`, "
            "`jiti`, `esno`, or "
            "`deno run npm:@earendil-works/pi-*` must not launch upstream Pi"
        ),
        (
            "Package runners that target the short `pi` bin such as `npx pi`, "
            "`npx pi@latest`, `pnpm dlx pi`, or `bunx pi` are native Pi "
            "CLI/package invocation"
        ),
        (
            "Package creator/init runners such as `pnpm create`, "
            "`yarn create`, `npm init`, and `bun create` must not target "
            "upstream Pi packages"
        ),
        (
            "Production command/client provenance must not declare fake/mock/"
            "dummy/stub/test/fixture/example/sample/demo fixtures"
        ),
        (
            "Native upstream Pi RPC client identities must not be used as "
            "OpenSquilla sidecar clients"
        ),
        (
            "Native Pi module prefixes such as `pi.agent`, `pi.coding_agent`, "
            "`pi_agent_core`, or `pi_coding_agent`, and native Pi runtime class "
            "markers such as `PiAgentRuntimeClient`, remain native Pi client "
            "identities"
        ),
        (
            "Pi live command provenance must not declare fake/mock/dummy/stub/"
            "test/fixture/example/sample/demo fixtures"
        ),
        "Explicit live parity opt-in without provider credentials must fail instead of skip",
        (
            "when baseline write counts are non-zero and equal to the candidate "
            "count, baseline session write fingerprints are required before "
            "content parity can be claimed"
        ),
        "tool error count",
        "OpenSquilla must not vendor Pi source",
        "must not implement or rewrite Pi's agent loop",
            (
                "Pi-owned no-throw stream semantics, `prepareNextTurn`, safe-point "
                "queues, parallel tool scheduling/invocation scheduling/execution, "
                "`beforeToolCall` / `afterToolCall` and before/after tool hooks, "
                "`shouldStopAfterTurn`, `getSteeringMessages` / "
                "`getFollowUpMessages`, steering/follow-up queues, and Pi session "
                "lifecycle logic"
            ),
        (
            "JSONL command clients own exactly one active sidecar stream; "
            "concurrent Pi sidecar streams must use separate client instances"
        ),
        (
            "Pi kernel runtime instances own exactly one active turn; "
            "concurrent work must use host queueing or a separate runtime/session"
        ),
        "Pi is MIT-licensed",
    )

    normalized_contract = " ".join(contract.split())
    for fragment in required_fragments:
        assert " ".join(fragment.split()) in normalized_contract


def test_public_upper_surfaces_do_not_import_agent_core_internals() -> None:
    """Public/core surfaces stay on TurnRunner/AgentEvent contracts."""
    public_roots = (
        Path("src/opensquilla/cli"),
        Path("src/opensquilla/gateway"),
        Path("src/opensquilla/channels"),
        Path("src/opensquilla/scheduler"),
        Path("src/opensquilla/application"),
        Path("src/opensquilla/chat"),
        Path("src/opensquilla/mcp_server"),
        Path("src/opensquilla/squilla_router"),
        Path("src/opensquilla/skills/meta"),
        Path("src/opensquilla/skills/creator"),
        Path("src/opensquilla/skills/loader.py"),
    )
    forbidden_imports: list[str] = []

    for root in public_roots:
        if not root.exists():
            continue
        paths = [root] if root.is_file() else sorted(root.rglob("*.py"))
        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("opensquilla.engine.agent_core"):
                            forbidden_imports.append(f"{path}:{node.lineno}:{alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module.startswith("opensquilla.engine.agent_core"):
                        imported = ", ".join(alias.name for alias in node.names)
                        forbidden_imports.append(
                            f"{path}:{node.lineno}:from {module} import {imported}"
                        )
                    elif module == "opensquilla.engine":
                        for alias in node.names:
                            if alias.name.startswith("agent_core"):
                                forbidden_imports.append(
                                    f"{path}:{node.lineno}:from {module} import {alias.name}"
                                )

    assert forbidden_imports == []


def test_turn_runner_stages_do_not_import_concrete_kernel_implementations() -> None:
    """Stage slices consume KernelRuntime ports, not concrete Python/Pi kernels."""
    stage_paths = (
        Path("src/opensquilla/engine/turn_runner/agent_bootstrap_stage.py"),
        Path("src/opensquilla/engine/turn_runner/compaction_and_history_stage.py"),
        Path("src/opensquilla/engine/turn_runner/stream_consumer_stage.py"),
    )
    forbidden_agent_import_names = {"Agent"}
    forbidden_agent_core_import_names = {
        "OpenSquillaPythonKernelRuntime",
        "PiSidecarKernelRuntime",
        "PiJsonlCommandRpcClient",
        "build_agent_for_kernel",
    }
    forbidden_runtime_names = forbidden_agent_import_names | forbidden_agent_core_import_names
    violations: list[str] = []

    for path in stage_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in {
                        "opensquilla.engine.agent",
                        "opensquilla.engine.agent_core",
                    }:
                        violations.append(f"{path}:{node.lineno}:import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imported = {alias.name for alias in node.names}
                if module == "opensquilla.engine.agent":
                    forbidden = imported & forbidden_agent_import_names
                elif module == "opensquilla.engine.agent_core":
                    forbidden = imported & forbidden_agent_core_import_names
                elif module == "opensquilla.engine":
                    forbidden = imported & {"agent", "agent_core"}
                else:
                    forbidden = set()
                if forbidden:
                    violations.append(
                        f"{path}:{node.lineno}:from {module} import "
                        f"{', '.join(sorted(forbidden))}"
                    )
            elif isinstance(node, ast.Name) and node.id in forbidden_runtime_names:
                violations.append(f"{path}:{node.lineno}:name {node.id}")
            elif (
                isinstance(node, ast.Attribute)
                and node.attr in forbidden_runtime_names
            ):
                violations.append(f"{path}:{node.lineno}:attribute {node.attr}")

    assert violations == []


def test_third_party_notices_record_external_pi_runtime_provenance() -> None:
    notices = Path("THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    required_fragments = (
        "Pi agent runtime integration",
        "https://github.com/earendil-works/pi",
        "@earendil-works/pi-agent-core",
        "@earendil-works/pi-ai",
        "@earendil-works/pi-coding-agent",
        "MIT License",
        "not bundled with OpenSquilla",
        "`pi_agent_rpc_command`",
        "fake/test sidecars are not production Pi runtime substitutes",
    )

    normalized_notices = " ".join(notices.split())
    for fragment in required_fragments:
        assert " ".join(fragment.split()) in normalized_notices


def test_opensquilla_source_tree_does_not_vendor_pi_runtime_sources() -> None:
    src_root = Path("src/opensquilla")
    allowed_bridge_resources = {
        "src/opensquilla/engine/pi_sidecar_bridge.mjs",
    }
    forbidden_names = {
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "npm-shrinkwrap.json",
        "tsconfig.json",
        "vitest.config.ts",
        "vitest.harness.config.ts",
    }
    forbidden_suffixes = {".ts", ".tsx", ".mjs", ".cjs"}
    forbidden_path_parts = {"node_modules", "packages/agent", "packages/coding-agent"}

    vendored_paths = []
    for path in src_root.rglob("*"):
        if not path.is_file():
            continue
        normalized = path.as_posix()
        if normalized in allowed_bridge_resources:
            continue
        if path.name in forbidden_names or path.suffix in forbidden_suffixes:
            vendored_paths.append(normalized)
            continue
        if any(part in normalized for part in forbidden_path_parts):
            vendored_paths.append(normalized)

    assert vendored_paths == []


def test_packaged_pi_sidecar_bridge_invokes_upstream_pi_agent_without_loop_rewrite() -> None:
    from opensquilla.engine.agent_core import (
        AgentCoreConfig,
        PiJsonlCommandRpcClient,
        _pi_rpc_client_from_config,
        pi_sidecar_bridge_command,
        pi_sidecar_bridge_path,
    )

    bridge = Path("src/opensquilla/engine/pi_sidecar_bridge.mjs")
    assert bridge.is_file()
    assert pi_sidecar_bridge_path() == bridge.resolve()

    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    force_include = pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    assert (
        force_include["src/opensquilla/engine/pi_sidecar_bridge.mjs"]
        == "opensquilla/engine/pi_sidecar_bridge.mjs"
    )

    source = bridge.read_text(encoding="utf-8")
    assert "opensquilla.agent_core.v1" in source
    assert "@earendil-works/pi-agent-core" in source
    assert "new Agent(" in source
    assert "streamFn" in source
    assert "provider.request" in source
    assert "tool_use_end" in source
    assert "toolcall_end" in source
    assert "tool.call.prepare" in source
    assert "tool.call.execute" in source

    forbidden_markers = (
        "agentLoop(",
        "runAgentLoop",
        "runLoop(",
        "prepareNextTurn",
        "beforeToolCall",
        "afterToolCall",
        "shouldStopAfterTurn",
        "toolExecution",
        "steeringMode",
        "followUpMode",
        "safe-point queue",
        "safe_point_queue",
    )
    for marker in forbidden_markers:
        assert marker not in source

    command = pi_sidecar_bridge_command()
    assert str(bridge.resolve()) in command
    rpc_client = _pi_rpc_client_from_config(
        AgentCoreConfig(
            kernel="pi",
            pi_rpc_command=command,
            pi_rpc_command_provenance=(
                "thin opensquilla.agent_core.v1 IO bridge around "
                "@earendil-works/pi-agent-core"
            ),
        )
    )
    assert isinstance(rpc_client, PiJsonlCommandRpcClient)


def test_pi_intent_allowlists_match_contract_runtime_and_bridge() -> None:
    from opensquilla.engine.agent_core import _PI_INTENT_PAYLOAD_KEYS, _PI_INTENT_PORTS

    expected_intents = {
        "provider.request",
        "tool.call.prepare",
        "tool.call.execute",
        "session.write.enqueue",
        "queue.poll",
        "savepoint.request",
        "yield.request",
        "telemetry.emit",
    }
    fixed_schema_intents = expected_intents - {"telemetry.emit"}
    forbidden_host_owned_intents = {
        "provider.hook.before",
        "provider.hook.after",
        "queue.enqueue",
        "queue.drain",
        "session.write.direct",
        "subagent.wake",
        "parent.wake",
        "turn.finalize",
    }

    contract = Path("docs/agent-core-contract.md").read_text(encoding="utf-8")
    for intent in expected_intents:
        assert f"`{intent}`" in contract
    assert "Pi-style internal hook, queue, wake, or finalizer intents" in contract
    for intent in forbidden_host_owned_intents:
        assert f"`{intent}`" in contract

    bridge_source = Path("src/opensquilla/engine/pi_sidecar_bridge.mjs").read_text(
        encoding="utf-8"
    )
    bridge_intent_block = bridge_source.split(
        "const SUPPORTED_INTENT_RESULT_TYPES = new Set([", 1
    )[1].split("]);", 1)[0]
    bridge_intents = {
        line.strip().strip('",')
        for line in bridge_intent_block.splitlines()
        if line.strip().startswith('"')
    }

    assert set(_PI_INTENT_PORTS) == expected_intents
    assert set(_PI_INTENT_PAYLOAD_KEYS) == fixed_schema_intents
    assert bridge_intents == expected_intents
    assert forbidden_host_owned_intents.isdisjoint(_PI_INTENT_PORTS)
    assert forbidden_host_owned_intents.isdisjoint(_PI_INTENT_PAYLOAD_KEYS)
    assert forbidden_host_owned_intents.isdisjoint(bridge_intents)


def test_live_api_parity_markers_apply_only_to_real_provider_tests() -> None:
    module = ast.parse(
        Path("tests/functional/test_agent_core_live_parity.py").read_text(
            encoding="utf-8"
        )
    )
    module_level_pytestmark = [
        node
        for node in module.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "pytestmark"
            for target in node.targets
        )
    ]
    assert module_level_pytestmark == []

    expected_live_api_tests = {
        "test_live_opensquilla_kernel_not_weaker_than_direct_python_agent",
        "test_live_opensquilla_kernel_preserves_orchestration_shape",
        "test_live_pi_kernel_not_weaker_than_direct_python_agent",
        "test_live_pi_kernel_preserves_orchestration_shape",
    }
    expected_pi_live_api_tests = {
        "test_live_pi_kernel_not_weaker_than_direct_python_agent",
        "test_live_pi_kernel_preserves_orchestration_shape",
    }
    observed_live_api_tests: set[str] = set()

    for node in module.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in expected_live_api_tests:
            continue
        observed_live_api_tests.add(node.name)
        marker_names = {
            decorator.attr
            for decorator in node.decorator_list
            if isinstance(decorator, ast.Attribute)
            and isinstance(decorator.value, ast.Attribute)
            and isinstance(decorator.value.value, ast.Name)
            and decorator.value.value.id == "pytest"
            and decorator.value.attr == "mark"
        }
        assert {"llm", "llm_gateway", "llm_tools"} <= marker_names
        names = {
            child.id
            for child in ast.walk(node)
            if isinstance(child, ast.Name)
        }
        string_constants = {
            child.value
            for child in ast.walk(node)
            if isinstance(child, ast.Constant) and isinstance(child.value, str)
        }
        assert "_live_provider" in names
        assert "_assert_not_weaker" in names
        if node.name in expected_pi_live_api_tests:
            assert "_live_pi_rpc_command" in names
            assert "OPENSQUILLA_AGENT_CORE_PI_LIVE" in string_constants
        else:
            assert "OPENSQUILLA_AGENT_CORE_LIVE_PARITY" in string_constants

    assert observed_live_api_tests == expected_live_api_tests


@pytest.mark.asyncio
async def test_packaged_pi_sidecar_bridge_preserves_host_provider_error(
    tmp_path: Path,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    runtime = tmp_path / "fake_pi_agent_core.mjs"
    runtime.write_text(
        textwrap.dedent(
            """
            export class Agent {
              constructor(options) {
                this.options = options;
                this.listener = () => {};
              }

              subscribe(listener) {
                this.listener = listener;
              }

              async prompt(prompt) {
                const stream = this.options.streamFn(
                  { id: "fake-pi-model", api: "fake", provider: "fake" },
                  { messages: [{ role: "user", content: [{ type: "text", text: prompt }] }] },
                  {},
                );
                for await (const event of stream) {
                  if (event.type === "error") {
                    const message = event.error?.errorMessage ?? "";
                    this.listener({
                      assistantMessageEvent: { type: "text_delta", delta: message },
                    });
                    return;
                  }
                }
              }

              async waitForIdle() {}
            }
            """
        ).lstrip(),
        encoding="utf-8",
    )
    ai = tmp_path / "fake_pi_ai.mjs"
    ai.write_text(
        textwrap.dedent(
            """
            export class AssistantMessageEventStream {
              constructor() {
                this.items = [];
                this.waiters = [];
                this.closed = false;
              }

              push(event) {
                if (this.waiters.length > 0) {
                  this.waiters.shift()({ value: event, done: false });
                } else {
                  this.items.push(event);
                }
                if (event.type === "done" || event.type === "error") {
                  this.closed = true;
                }
              }

              [Symbol.asyncIterator]() {
                return this;
              }

              next() {
                if (this.items.length > 0) {
                  return Promise.resolve({ value: this.items.shift(), done: false });
                }
                if (this.closed) {
                  return Promise.resolve({ done: true });
                }
                return new Promise((resolve) => this.waiters.push(resolve));
              }
            }
            """
        ).lstrip(),
        encoding="utf-8",
    )

    client = PiJsonlCommandRpcClient(
        "node "
        f"{Path('src/opensquilla/engine/pi_sidecar_bridge.mjs').resolve()} "
        f"--runtime {runtime} --ai-package {ai}"
    )

    async def collect_text() -> list[str]:
        observed_text: list[str] = []
        async for frame in client.stream_prompt(
            "trigger provider error",
            session_key="agent:main:test",
            session_id="agent:main:test",
            turn_snapshot={
                "session_key": "agent:main:test",
                "session_id": "agent:main:test",
                "agent_id": "main",
                "turn_id": "agent:main:test:turn-1",
                "turn_input": "trigger provider error",
                "model_id": "fake-pi-model",
                "tool_definitions": [],
            },
        ):
            if frame["kind"] == "intent":
                assert frame["type"] == "provider.request"
                await client.receive_intent_result(
                    intent_type="provider.request",
                    payload=frame["payload"],
                    events=[
                        {
                            "kind": "error",
                            "message": "host provider boom",
                            "code": "provider_error",
                        }
                    ],
                    session_key="agent:main:test",
                )
                continue
            if frame["kind"] == "event" and frame["type"] == "text.delta":
                observed_text.append(frame["payload"]["text"])
        return observed_text

    observed_text = await asyncio.wait_for(collect_text(), timeout=5.0)

    assert observed_text == ["host provider boom"]


@pytest.mark.asyncio
async def test_packaged_pi_sidecar_bridge_chunks_large_provider_request_stdout(
    tmp_path: Path,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    runtime = tmp_path / "fake_pi_agent_core.mjs"
    runtime.write_text(
        textwrap.dedent(
            """
            export class Agent {
              constructor(options) {
                this.options = options;
                this.listener = () => {};
              }

              subscribe(listener) {
                this.listener = listener;
              }

              async prompt() {
                const stream = this.options.streamFn(
                  { id: "fake-pi-model", api: "fake", provider: "fake" },
                  {
                    messages: [
                      {
                        role: "user",
                        content: [{ type: "text", text: "x".repeat(100000) }],
                      },
                    ],
                    tools: [],
                  },
                  {},
                );
                for await (const event of stream) {
                  if (event.type === "done") {
                    const text = event.message?.content?.[0]?.text ?? "";
                    this.listener({
                      assistantMessageEvent: { type: "text_delta", delta: text },
                    });
                    return;
                  }
                }
              }

              async waitForIdle() {}
            }
            """
        ).lstrip(),
        encoding="utf-8",
    )
    ai = tmp_path / "fake_pi_ai.mjs"
    ai.write_text(
        textwrap.dedent(
            """
            export class AssistantMessageEventStream {
              constructor() {
                this.items = [];
                this.waiters = [];
                this.closed = false;
              }

              push(event) {
                if (this.waiters.length > 0) {
                  this.waiters.shift()({ value: event, done: false });
                } else {
                  this.items.push(event);
                }
                if (event.type === "done" || event.type === "error") {
                  this.closed = true;
                }
              }

              [Symbol.asyncIterator]() {
                return this;
              }

              next() {
                if (this.items.length > 0) {
                  return Promise.resolve({ value: this.items.shift(), done: false });
                }
                if (this.closed) {
                  return Promise.resolve({ done: true });
                }
                return new Promise((resolve) => this.waiters.push(resolve));
              }
            }
            """
        ).lstrip(),
        encoding="utf-8",
    )

    client = PiJsonlCommandRpcClient(
        "node "
        f"{Path('src/opensquilla/engine/pi_sidecar_bridge.mjs').resolve()} "
        f"--runtime {runtime} --ai-package {ai}"
    )

    observed_text: list[str] = []
    async for frame in client.stream_prompt(
        "large provider request",
        session_key="agent:main:test",
        session_id="agent:main:test",
        turn_snapshot={
            "session_key": "agent:main:test",
            "session_id": "agent:main:test",
            "agent_id": "main",
            "turn_id": "agent:main:test:turn-1",
            "turn_input": "large provider request",
            "model_id": "fake-pi-model",
            "tool_definitions": [],
        },
    ):
        if frame["kind"] == "intent":
            assert frame["type"] == "provider.request"
            assert frame["payload"]["messages"][0]["content"] == "x" * 100000
            await client.receive_intent_result(
                intent_type="provider.request",
                payload=frame["payload"],
                events=[
                    {"kind": "text_delta", "text": "large request accepted"},
                    {"kind": "done", "text": "large request accepted"},
                ],
                session_key="agent:main:test",
            )
            continue
        if frame["kind"] == "event" and frame["type"] == "text.delta":
            observed_text.append(frame["payload"]["text"])

    assert observed_text == ["large request accepted"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("host_events", "expected_message"),
    [
        (
            [{"kind": "run_heartbeat", "phase": "provider", "message": "ignored"}],
            "unsupported provider.request event kind run_heartbeat",
        ),
        (
            [{"kind": "text_delta", "text": {"bad": "text"}}],
            "text_delta text must be a string",
        ),
        (
            [{"kind": "done", "text": {"bad": "text"}}],
            "done text must be a string",
        ),
        (
            [{"kind": "error", "message": {"bad": "message"}}],
            "error message must be a string",
        ),
        (
            [
                {
                    "kind": "tool_use_start",
                    "tool_use_id": "call-1",
                    "tool_name": "echo",
                },
                {
                    "kind": "tool_use_start",
                    "tool_use_id": "call-1",
                    "tool_name": "echo",
                },
            ],
            "duplicate tool_use_start tool_use_id",
        ),
        (
            [
                {
                    "kind": "tool_use_end",
                    "tool_use_id": "call-1",
                    "tool_name": "echo",
                    "arguments": {"marker": "orphan"},
                },
            ],
            "tool_use_end requires matching tool_use_start",
        ),
        (
            [
                {
                    "kind": "tool_use_start",
                    "tool_use_id": "call-1",
                    "tool_name": "echo",
                },
                {
                    "kind": "tool_use_end",
                    "tool_use_id": "call-1",
                    "tool_name": "echo",
                    "arguments": ["bad"],
                },
            ],
            "tool_use_end arguments must be a JSON object",
        ),
        (
            [
                {
                    "kind": "tool_use_start",
                    "tool_use_id": "call-1",
                    "tool_name": "echo",
                },
                {
                    "kind": "tool_use_end",
                    "tool_use_id": "call-1",
                    "tool_name": "other",
                    "arguments": {"marker": "mismatch"},
                },
            ],
            "tool_use_end tool_name must match start tool_name",
        ),
        (
            [
                {
                    "kind": "tool_use_start",
                    "tool_use_id": "call-1",
                    "tool_name": "echo",
                },
                {
                    "kind": "tool_use_delta",
                    "tool_use_id": "call-1",
                    "json_fragment": '["not-an-object"]',
                },
                {
                    "kind": "tool_use_end",
                    "tool_use_id": "call-1",
                    "tool_name": "echo",
                },
            ],
            "provider.request provider tool-use arguments must decode to an object",
        ),
        (
            [
                {
                    "kind": "tool_use_start",
                    "tool_use_id": "call-1",
                    "tool_name": "echo",
                },
                {
                    "kind": "tool_use_end",
                    "tool_use_id": "call-1",
                    "tool_name": "echo",
                    "arguments": {"marker": "first"},
                },
                {
                    "kind": "tool_use_end",
                    "tool_use_id": "call-1",
                    "tool_name": "echo",
                    "arguments": {"marker": "duplicate"},
                },
            ],
            "tool_use_end requires matching tool_use_start",
        ),
        (
            [
                {
                    "kind": "tool_use_start",
                    "tool_use_id": "call-1",
                    "tool_name": "echo",
                },
                {"kind": "done", "text": "host done"},
            ],
            "provider.request ended with pending provider tool-use streams: call-1",
        ),
    ],
)
async def test_packaged_pi_sidecar_bridge_rejects_malformed_host_event_payloads(
    tmp_path: Path,
    host_events: Any,
    expected_message: str,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    runtime = tmp_path / "fake_pi_agent_core.mjs"
    runtime.write_text(
        textwrap.dedent(
            """
            export class Agent {
              constructor(options) {
                this.options = options;
                this.listener = () => {};
              }

              subscribe(listener) {
                this.listener = listener;
              }

              async prompt(prompt) {
                const stream = this.options.streamFn(
                  { id: "fake-pi-model", api: "fake", provider: "fake" },
                  { messages: [{ role: "user", content: [{ type: "text", text: prompt }] }] },
                  {},
                );
                for await (const event of stream) {
                  if (event.type === "error") {
                    const message = event.error?.errorMessage ?? "";
                    this.listener({
                      assistantMessageEvent: { type: "text_delta", delta: message },
                    });
                    return;
                  }
                }
              }

              async waitForIdle() {}
            }
            """
        ).lstrip(),
        encoding="utf-8",
    )
    ai = tmp_path / "fake_pi_ai.mjs"
    ai.write_text(
        textwrap.dedent(
            """
            export class AssistantMessageEventStream {
              constructor() {
                this.items = [];
                this.waiters = [];
                this.closed = false;
              }

              push(event) {
                if (this.waiters.length > 0) {
                  this.waiters.shift()({ value: event, done: false });
                } else {
                  this.items.push(event);
                }
                if (event.type === "done" || event.type === "error") {
                  this.closed = true;
                }
              }

              [Symbol.asyncIterator]() {
                return this;
              }

              next() {
                if (this.items.length > 0) {
                  return Promise.resolve({ value: this.items.shift(), done: false });
                }
                if (this.closed) {
                  return Promise.resolve({ done: true });
                }
                return new Promise((resolve) => this.waiters.push(resolve));
              }
            }
            """
        ).lstrip(),
        encoding="utf-8",
    )

    client = PiJsonlCommandRpcClient(
        "node "
        f"{Path('src/opensquilla/engine/pi_sidecar_bridge.mjs').resolve()} "
        f"--runtime {runtime} --ai-package {ai}"
    )

    async def collect_error_text() -> list[str]:
        observed_text: list[str] = []
        async for frame in client.stream_prompt(
            "trigger malformed host event",
            session_key="agent:main:test",
            session_id="agent:main:test",
            turn_snapshot={
                "session_key": "agent:main:test",
                "session_id": "agent:main:test",
                "agent_id": "main",
                "turn_id": "agent:main:test:turn-1",
                "turn_input": "trigger malformed host event",
                "model_id": "fake-pi-model",
                "tool_definitions": [],
            },
        ):
            if frame["kind"] == "intent":
                assert frame["type"] == "provider.request"
                await client.receive_intent_result(
                    intent_type="provider.request",
                    payload=frame["payload"],
                    events=host_events,
                    session_key="agent:main:test",
                )
                continue
            if frame["kind"] == "event" and frame["type"] == "text.delta":
                observed_text.append(frame["payload"]["text"])
        return observed_text

    observed_text = await asyncio.wait_for(collect_error_text(), timeout=5.0)

    assert observed_text == [expected_message]


@pytest.mark.asyncio
async def test_packaged_pi_sidecar_bridge_maps_tool_use_delta_fragments_to_arguments(
    tmp_path: Path,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    runtime = tmp_path / "fake_pi_agent_core.mjs"
    runtime.write_text(
        textwrap.dedent(
            """
            export class Agent {
              constructor(options) {
                this.options = options;
                this.listener = () => {};
              }

              subscribe(listener) {
                this.listener = listener;
              }

              async prompt(prompt) {
                const stream = this.options.streamFn(
                  { id: "fake-pi-model", api: "fake", provider: "fake" },
                  { messages: [{ role: "user", content: [{ type: "text", text: prompt }] }] },
                  {},
                );
                for await (const event of stream) {
                  if (event.type === "toolcall_end") {
                    this.listener({
                      assistantMessageEvent: {
                        type: "text_delta",
                        delta: JSON.stringify(event.toolCall.arguments),
                      },
                    });
                    return;
                  }
                  if (event.type === "error") {
                    this.listener({
                      assistantMessageEvent: {
                        type: "text_delta",
                        delta: event.error?.errorMessage ?? "",
                      },
                    });
                    return;
                  }
                }
              }

              async waitForIdle() {}
            }
            """
        ).lstrip(),
        encoding="utf-8",
    )
    ai = tmp_path / "fake_pi_ai.mjs"
    ai.write_text(
        textwrap.dedent(
            """
            export class AssistantMessageEventStream {
              constructor() {
                this.items = [];
                this.waiters = [];
                this.closed = false;
              }

              push(event) {
                if (this.waiters.length > 0) {
                  this.waiters.shift()({ value: event, done: false });
                } else {
                  this.items.push(event);
                }
                if (event.type === "done" || event.type === "error") {
                  this.closed = true;
                }
              }

              [Symbol.asyncIterator]() {
                return this;
              }

              next() {
                if (this.items.length > 0) {
                  return Promise.resolve({ value: this.items.shift(), done: false });
                }
                if (this.closed) {
                  return Promise.resolve({ done: true });
                }
                return new Promise((resolve) => this.waiters.push(resolve));
              }
            }
            """
        ).lstrip(),
        encoding="utf-8",
    )

    client = PiJsonlCommandRpcClient(
        "node "
        f"{Path('src/opensquilla/engine/pi_sidecar_bridge.mjs').resolve()} "
        f"--runtime {runtime} --ai-package {ai}"
    )

    async def collect_tool_arguments_text() -> list[str]:
        observed_text: list[str] = []
        async for frame in client.stream_prompt(
            "trigger streamed tool arguments",
            session_key="agent:main:test",
            session_id="agent:main:test",
            turn_snapshot={
                "session_key": "agent:main:test",
                "session_id": "agent:main:test",
                "agent_id": "main",
                "turn_id": "agent:main:test:turn-1",
                "turn_input": "trigger streamed tool arguments",
                "model_id": "fake-pi-model",
                "tool_definitions": [],
            },
        ):
            if frame["kind"] == "intent":
                assert frame["type"] == "provider.request"
                await client.receive_intent_result(
                    intent_type="provider.request",
                    payload=frame["payload"],
                    events=[
                        {
                            "kind": "tool_use_start",
                            "tool_use_id": "call-1",
                            "tool_name": "echo",
                        },
                        {
                            "kind": "tool_use_delta",
                            "tool_use_id": "call-1",
                            "json_fragment": '{"marker"',
                        },
                        {
                            "kind": "tool_use_delta",
                            "tool_use_id": "call-1",
                            "json_fragment": ':"delta"}',
                        },
                        {
                            "kind": "tool_use_end",
                            "tool_use_id": "call-1",
                            "tool_name": "echo",
                        },
                        {"kind": "done", "text": ""},
                    ],
                    session_key="agent:main:test",
                )
                continue
            if frame["kind"] == "event" and frame["type"] == "text.delta":
                observed_text.append(frame["payload"]["text"])
        return observed_text

    observed_text = await asyncio.wait_for(
        collect_tool_arguments_text(),
        timeout=5.0,
    )

    assert observed_text == ['{"marker":"delta"}']


@pytest.mark.asyncio
async def test_packaged_pi_sidecar_bridge_projects_pi_tool_transcript_to_host_provider(
    tmp_path: Path,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    runtime = tmp_path / "fake_pi_agent_core.mjs"
    runtime.write_text(
        textwrap.dedent(
            """
            export class Agent {
              constructor(options) {
                this.options = options;
                this.listener = () => {};
              }

              subscribe(listener) {
                this.listener = listener;
              }

              async prompt(prompt) {
                const stream = this.options.streamFn(
                  { id: "fake-pi-model", api: "fake", provider: "fake" },
                  {
                    messages: [
                      {
                        role: "user",
                        content: [{ type: "text", text: prompt }],
                      },
                      {
                        role: "assistant",
                        content: [
                          { type: "text", text: "calling echo" },
                          {
                            type: "toolCall",
                            id: "call-1",
                            name: "echo",
                            arguments: { marker: "from-pi" },
                          },
                        ],
                      },
                      {
                        role: "toolResult",
                        toolCallId: "call-1",
                        toolName: "echo",
                        content: [
                          { type: "text", text: "LIVE_AGENT_CORE_PARITY" },
                        ],
                        details: { ok: true },
                        isError: false,
                      },
                    ],
                  },
                  {},
                );
                for await (const event of stream) {
                  if (event.type === "done") {
                    this.listener({
                      assistantMessageEvent: {
                        type: "text_delta",
                        delta: "provider returned",
                      },
                    });
                    return;
                  }
                  if (event.type === "error") {
                    this.listener({
                      assistantMessageEvent: {
                        type: "text_delta",
                        delta: event.error?.errorMessage ?? "",
                      },
                    });
                    return;
                  }
                }
              }

              async waitForIdle() {}
            }
            """
        ).lstrip(),
        encoding="utf-8",
    )
    ai = tmp_path / "fake_pi_ai.mjs"
    ai.write_text(
        textwrap.dedent(
            """
            export class AssistantMessageEventStream {
              constructor() {
                this.items = [];
                this.waiters = [];
                this.closed = false;
              }

              push(event) {
                if (this.waiters.length > 0) {
                  this.waiters.shift()({ value: event, done: false });
                } else {
                  this.items.push(event);
                }
                if (event.type === "done" || event.type === "error") {
                  this.closed = true;
                }
              }

              [Symbol.asyncIterator]() {
                return this;
              }

              next() {
                if (this.items.length > 0) {
                  return Promise.resolve({ value: this.items.shift(), done: false });
                }
                if (this.closed) {
                  return Promise.resolve({ done: true });
                }
                return new Promise((resolve) => this.waiters.push(resolve));
              }
            }
            """
        ).lstrip(),
        encoding="utf-8",
    )

    client = PiJsonlCommandRpcClient(
        "node "
        f"{Path('src/opensquilla/engine/pi_sidecar_bridge.mjs').resolve()} "
        f"--runtime {runtime} --ai-package {ai}"
    )

    provider_payloads: list[dict[str, Any]] = []
    observed_text: list[str] = []
    async for frame in client.stream_prompt(
        "trigger transcript projection",
        session_key="agent:main:test",
        session_id="agent:main:test",
        turn_snapshot={
            "session_key": "agent:main:test",
            "session_id": "agent:main:test",
            "agent_id": "main",
            "turn_id": "agent:main:test:turn-1",
            "turn_input": "trigger transcript projection",
            "model_id": "fake-pi-model",
            "tool_definitions": [],
        },
    ):
        if frame["kind"] == "intent":
            assert frame["type"] == "provider.request"
            provider_payloads.append(frame["payload"])
            await client.receive_intent_result(
                intent_type="provider.request",
                payload=frame["payload"],
                events=[{"kind": "done", "text": "provider returned"}],
                session_key="agent:main:test",
            )
            continue
        if frame["kind"] == "event" and frame["type"] == "text.delta":
            observed_text.append(frame["payload"]["text"])

    assert observed_text == ["provider returned"]
    assert len(provider_payloads) == 1
    messages = provider_payloads[0]["messages"]
    assert messages[0] == {
        "role": "user",
        "content": "trigger transcript projection",
    }
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "calling echo"
    assert messages[1]["tool_calls"][0]["id"] == "call-1"
    assert messages[1]["tool_calls"][0]["function"]["name"] == "echo"
    assert json.loads(messages[1]["tool_calls"][0]["function"]["arguments"]) == {
        "marker": "from-pi"
    }
    assert messages[2] == {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": "call-1",
                "content": "LIVE_AGENT_CORE_PARITY",
                "is_error": False,
            }
        ],
    }


@pytest.mark.asyncio
async def test_packaged_pi_sidecar_bridge_resolves_external_upstream_module_root(
    tmp_path: Path,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    module_root = tmp_path / "external-wrapper"
    runtime_pkg = module_root / "node_modules" / "@earendil-works" / "pi-agent-core"
    ai_pkg = module_root / "node_modules" / "@earendil-works" / "pi-ai"
    runtime_pkg.mkdir(parents=True)
    ai_pkg.mkdir(parents=True)
    for package_dir, package_name in (
        (runtime_pkg, "@earendil-works/pi-agent-core"),
        (ai_pkg, "@earendil-works/pi-ai"),
    ):
        (package_dir / "package.json").write_text(
            json.dumps(
                    {
                        "name": package_name,
                        "type": "module",
                        "exports": {".": {"import": "./index.mjs"}},
                    }
                ),
                encoding="utf-8",
            )

    (runtime_pkg / "index.mjs").write_text(
        textwrap.dedent(
            """
            export class Agent {
              constructor(options) {
                this.listener = () => {};
              }

              subscribe(listener) {
                this.listener = listener;
              }

              async prompt(prompt) {
                this.listener({
                  assistantMessageEvent: {
                    type: "text_delta",
                    delta: `module-root:${prompt}`,
                  },
                });
              }

              async waitForIdle() {}
            }
            """
        ).lstrip(),
        encoding="utf-8",
    )
    (ai_pkg / "index.mjs").write_text(
        textwrap.dedent(
            """
            export class AssistantMessageEventStream {
              constructor() {
                this.items = [];
              }
            }
            """
        ).lstrip(),
        encoding="utf-8",
    )

    client = PiJsonlCommandRpcClient(
        "node "
        f"{Path('src/opensquilla/engine/pi_sidecar_bridge.mjs').resolve()} "
        f"--module-root {module_root}"
    )

    observed_text: list[str] = []
    async for frame in client.stream_prompt(
        "external package",
        session_key="agent:main:test",
        session_id="agent:main:test",
        turn_snapshot={
            "session_key": "agent:main:test",
            "session_id": "agent:main:test",
            "agent_id": "main",
            "turn_id": "agent:main:test:turn-1",
            "turn_input": "external package",
            "model_id": "fake-pi-model",
            "tool_definitions": [],
        },
    ):
        if frame["kind"] == "event" and frame["type"] == "text.delta":
            observed_text.append(frame["payload"]["text"])

    assert observed_text == ["module-root:external package"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("bad_usage", "expected_message"),
    [
        (
            {"input_tokens": -1},
            "done input_tokens must be a non-negative integer",
        ),
        (
            {"output_tokens": "3"},
            "done output_tokens must be a non-negative integer",
        ),
        (
            {"input_tokens": 3, "cached_tokens": 4},
            "done cached_tokens must be <= input_tokens",
        ),
        (
            {"billed_cost": -0.01},
            "done billed_cost must be a finite non-negative number",
        ),
    ],
)
async def test_packaged_pi_sidecar_bridge_rejects_malformed_host_usage_before_pi_done(
    tmp_path: Path,
    bad_usage: dict[str, Any],
    expected_message: str,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    runtime = tmp_path / "fake_pi_agent_core.mjs"
    runtime.write_text(
        textwrap.dedent(
            """
            export class Agent {
              constructor(options) {
                this.options = options;
                this.listener = () => {};
              }

              subscribe(listener) {
                this.listener = listener;
              }

              async prompt(prompt) {
                const stream = this.options.streamFn(
                  { id: "fake-pi-model", api: "fake", provider: "fake" },
                  { messages: [{ role: "user", content: [{ type: "text", text: prompt }] }] },
                  {},
                );
                for await (const event of stream) {
                  if (event.type === "error") {
                    const message = event.error?.errorMessage ?? "";
                    this.listener({
                      assistantMessageEvent: { type: "text_delta", delta: message },
                    });
                    return;
                  }
                }
              }

              async waitForIdle() {}
            }
            """
        ).lstrip(),
        encoding="utf-8",
    )
    ai = tmp_path / "fake_pi_ai.mjs"
    ai.write_text(
        textwrap.dedent(
            """
            export class AssistantMessageEventStream {
              constructor() {
                this.items = [];
                this.waiters = [];
                this.closed = false;
              }

              push(event) {
                if (this.waiters.length > 0) {
                  this.waiters.shift()({ value: event, done: false });
                } else {
                  this.items.push(event);
                }
                if (event.type === "done" || event.type === "error") {
                  this.closed = true;
                }
              }

              [Symbol.asyncIterator]() {
                return this;
              }

              next() {
                if (this.items.length > 0) {
                  return Promise.resolve({ value: this.items.shift(), done: false });
                }
                if (this.closed) {
                  return Promise.resolve({ done: true });
                }
                return new Promise((resolve) => this.waiters.push(resolve));
              }
            }
            """
        ).lstrip(),
        encoding="utf-8",
    )

    client = PiJsonlCommandRpcClient(
        "node "
        f"{Path('src/opensquilla/engine/pi_sidecar_bridge.mjs').resolve()} "
        f"--runtime {runtime} --ai-package {ai}"
    )

    async def collect_error_text() -> list[str]:
        observed_text: list[str] = []
        async for frame in client.stream_prompt(
            "trigger malformed usage",
            session_key="agent:main:test",
            session_id="agent:main:test",
            turn_snapshot={
                "session_key": "agent:main:test",
                "session_id": "agent:main:test",
                "agent_id": "main",
                "turn_id": "agent:main:test:turn-1",
                "turn_input": "trigger malformed usage",
                "model_id": "fake-pi-model",
                "tool_definitions": [],
            },
        ):
            if frame["kind"] == "intent":
                assert frame["type"] == "provider.request"
                await client.receive_intent_result(
                    intent_type="provider.request",
                    payload=frame["payload"],
                    events=[
                        {
                            "kind": "done",
                            "text": "bad usage",
                            **bad_usage,
                        }
                    ],
                    session_key="agent:main:test",
                )
                continue
            if frame["kind"] == "event" and frame["type"] == "text.delta":
                observed_text.append(frame["payload"]["text"])
        return observed_text

    observed_text = await asyncio.wait_for(collect_error_text(), timeout=5.0)

    assert observed_text == [expected_message]


@pytest.mark.asyncio
async def test_packaged_pi_sidecar_bridge_maps_host_usage_to_pi_usage_semantics(
    tmp_path: Path,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    runtime = tmp_path / "fake_pi_agent_core.mjs"
    runtime.write_text(
        textwrap.dedent(
            """
            export class Agent {
              constructor(options) {
                this.options = options;
                this.listener = () => {};
              }

              subscribe(listener) {
                this.listener = listener;
              }

              async prompt(prompt) {
                const stream = this.options.streamFn(
                  { id: "fake-pi-model", api: "fake", provider: "fake" },
                  { messages: [{ role: "user", content: [{ type: "text", text: prompt }] }] },
                  {},
                );
                for await (const event of stream) {
                  if (event.type === "done") {
                    this.listener({
                      assistantMessageEvent: {
                        type: "text_delta",
                        delta: JSON.stringify(event.message.usage),
                      },
                    });
                    return;
                  }
                }
              }

              async waitForIdle() {}
            }
            """
        ).lstrip(),
        encoding="utf-8",
    )
    ai = tmp_path / "fake_pi_ai.mjs"
    ai.write_text(
        textwrap.dedent(
            """
            export class AssistantMessageEventStream {
              constructor() {
                this.items = [];
                this.waiters = [];
                this.closed = false;
              }

              push(event) {
                if (this.waiters.length > 0) {
                  this.waiters.shift()({ value: event, done: false });
                } else {
                  this.items.push(event);
                }
                if (event.type === "done" || event.type === "error") {
                  this.closed = true;
                }
              }

              [Symbol.asyncIterator]() {
                return this;
              }

              next() {
                if (this.items.length > 0) {
                  return Promise.resolve({ value: this.items.shift(), done: false });
                }
                if (this.closed) {
                  return Promise.resolve({ done: true });
                }
                return new Promise((resolve) => this.waiters.push(resolve));
              }
            }
            """
        ).lstrip(),
        encoding="utf-8",
    )

    client = PiJsonlCommandRpcClient(
        "node "
        f"{Path('src/opensquilla/engine/pi_sidecar_bridge.mjs').resolve()} "
        f"--runtime {runtime} --ai-package {ai}"
    )

    async def collect_usage() -> dict[str, Any]:
        observed_usage: dict[str, Any] | None = None
        async for frame in client.stream_prompt(
            "trigger provider usage",
            session_key="agent:main:test",
            session_id="agent:main:test",
            turn_snapshot={
                "session_key": "agent:main:test",
                "session_id": "agent:main:test",
                "agent_id": "main",
                "turn_id": "agent:main:test:turn-1",
                "turn_input": "trigger provider usage",
                "model_id": "fake-pi-model",
                "tool_definitions": [],
            },
        ):
            if frame["kind"] == "intent":
                assert frame["type"] == "provider.request"
                await client.receive_intent_result(
                    intent_type="provider.request",
                    payload=frame["payload"],
                    events=[
                        {
                            "kind": "done",
                            "text": "ok",
                            "input_tokens": 10,
                            "output_tokens": 3,
                            "reasoning_tokens": 5,
                            "cached_tokens": 4,
                            "cache_write_tokens": 2,
                            "billed_cost": 0.25,
                        }
                    ],
                    session_key="agent:main:test",
                )
                continue
            if frame["kind"] == "event" and frame["type"] == "text.delta":
                observed_usage = json.loads(frame["payload"]["text"])
        assert observed_usage is not None
        return observed_usage

    usage = await asyncio.wait_for(collect_usage(), timeout=5.0)

    assert usage == {
        "input": 6,
        "output": 3,
        "cacheRead": 4,
        "cacheWrite": 2,
        "totalTokens": 20,
        "cost": {
            "input": 0,
            "output": 0,
            "cacheRead": 0,
            "cacheWrite": 0,
            "total": 0.25,
        },
    }


@pytest.mark.asyncio
async def test_packaged_pi_sidecar_bridge_preserves_sessions_yield_reason(
    tmp_path: Path,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    runtime = tmp_path / "fake_pi_agent_core.mjs"
    runtime.write_text(
        textwrap.dedent(
            """
            export class Agent {
              constructor(options) {
                this.options = options;
              }

              subscribe(listener) {}

              async prompt(prompt) {
                const tool = this.options.initialState.tools.find(
                  (candidate) => candidate.name === "sessions_yield",
                );
                if (!tool) throw new Error("missing sessions_yield tool");
                await tool.execute("yield-reason-1", { reason: "LIVE_AGENT_CORE_YIELD" });
              }

              async waitForIdle() {}
            }
            """
        ).lstrip(),
        encoding="utf-8",
    )
    ai = tmp_path / "fake_pi_ai.mjs"
    ai.write_text(
        "export class AssistantMessageEventStream {}\n",
        encoding="utf-8",
    )

    client = PiJsonlCommandRpcClient(
        "node "
        f"{Path('src/opensquilla/engine/pi_sidecar_bridge.mjs').resolve()} "
        f"--runtime {runtime} --ai-package {ai}"
    )
    stream = client.stream_prompt(
        "trigger yield",
        session_key="agent:main:test",
        session_id="agent:main:test",
        turn_snapshot={
            "session_key": "agent:main:test",
            "session_id": "agent:main:test",
            "agent_id": "main",
            "turn_id": "agent:main:test:turn-1",
            "turn_input": "trigger yield",
            "model_id": "fake-pi-model",
            "tool_definitions": [
                {
                    "name": "sessions_yield",
                    "description": "Yield to the host scheduler.",
                    "input_schema": {
                        "type": "object",
                        "properties": {"reason": {"type": "string"}},
                    },
                }
            ],
        },
    )

    try:
        frame = await asyncio.wait_for(anext(stream), timeout=5.0)
    finally:
        await stream.aclose()

    assert frame["kind"] == "intent"
    assert frame["type"] == "yield.request"
    assert frame["payload"] == {
        "session_key": "agent:main:test",
        "tool_call_id": "yield-reason-1",
        "reason": "LIVE_AGENT_CORE_YIELD",
    }


@pytest.mark.asyncio
async def test_packaged_pi_sidecar_bridge_delays_yield_until_host_tools_settle(
    tmp_path: Path,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    runtime = tmp_path / "fake_pi_agent_core.mjs"
    runtime.write_text(
        textwrap.dedent(
            """
            export class Agent {
              constructor(options) {
                this.options = options;
              }

              subscribe(listener) {}

              async prompt(prompt) {
                const send = this.options.initialState.tools.find(
                  (candidate) => candidate.name === "sessions_send",
                );
                const yieldTool = this.options.initialState.tools.find(
                  (candidate) => candidate.name === "sessions_yield",
                );
                if (!send) throw new Error("missing sessions_send tool");
                if (!yieldTool) throw new Error("missing sessions_yield tool");
                const sendPromise = send.execute("send-1", {
                  session_key: "agent:child:test",
                  message: "CHILD_PARITY_MESSAGE",
                });
                const yieldPromise = yieldTool.execute("yield-1", {
                  reason: "LIVE_AGENT_CORE_YIELD",
                });
                await Promise.all([sendPromise, yieldPromise]);
              }

              async waitForIdle() {}
            }
            """
        ).lstrip(),
        encoding="utf-8",
    )
    ai = tmp_path / "fake_pi_ai.mjs"
    ai.write_text(
        "export class AssistantMessageEventStream {}\n",
        encoding="utf-8",
    )

    client = PiJsonlCommandRpcClient(
        "node "
        f"{Path('src/opensquilla/engine/pi_sidecar_bridge.mjs').resolve()} "
        f"--runtime {runtime} --ai-package {ai}"
    )
    stream = client.stream_prompt(
        "trigger parallel yield",
        session_key="agent:main:test",
        session_id="agent:main:test",
        turn_snapshot={
            "session_key": "agent:main:test",
            "session_id": "agent:main:test",
            "agent_id": "main",
            "turn_id": "agent:main:test:turn-1",
            "turn_input": "trigger parallel yield",
            "model_id": "fake-pi-model",
            "tool_definitions": [
                {
                    "name": "sessions_send",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "session_key": {"type": "string"},
                            "message": {"type": "string"},
                        },
                    },
                },
                {"name": "sessions_yield"},
            ],
        },
    )

    try:
        prepare = await asyncio.wait_for(anext(stream), timeout=5.0)
        assert prepare["kind"] == "intent"
        assert prepare["type"] == "tool.call.prepare"
        assert prepare["payload"]["tool_call_id"] == "send-1"
        await client.receive_intent_result(
            intent_type="tool.call.prepare",
            payload=prepare["payload"],
            events=[
                {
                    "kind": "tool_use_start",
                    "tool_use_id": "send-1",
                    "tool_name": "sessions_send",
                }
            ],
            session_key="agent:main:test",
        )

        execute = await asyncio.wait_for(anext(stream), timeout=5.0)
        assert execute["kind"] == "intent"
        assert execute["type"] == "tool.call.execute"
        assert execute["payload"]["tool_call_id"] == "send-1"

        await client.receive_intent_result(
            intent_type="tool.call.execute",
            payload=execute["payload"],
            events=[
                {
                    "kind": "tool_result",
                    "tool_use_id": "send-1",
                    "tool_name": "sessions_send",
                    "result": '{"status":"sent"}',
                }
            ],
            session_key="agent:main:test",
        )

        yield_frame = await asyncio.wait_for(anext(stream), timeout=5.0)
    finally:
        await stream.aclose()

    assert yield_frame["kind"] == "intent"
    assert yield_frame["type"] == "yield.request"
    assert yield_frame["payload"] == {
        "session_key": "agent:main:test",
        "tool_call_id": "yield-1",
        "reason": "LIVE_AGENT_CORE_YIELD",
    }


@pytest.mark.asyncio
async def test_packaged_pi_sidecar_bridge_treats_stdin_close_as_yield_settled(
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "fake_pi_agent_core.mjs"
    runtime.write_text(
        textwrap.dedent(
            """
            export class Agent {
              constructor(options) {
                this.options = options;
              }

              subscribe(listener) {}

              async prompt(prompt) {
                const tool = this.options.initialState.tools.find(
                  (candidate) => candidate.name === "sessions_yield",
                );
                if (!tool) throw new Error("missing sessions_yield tool");
                await tool.execute("yield-settled-1", { message: "wait for child" });
              }

              async waitForIdle() {}
            }
            """
        ).lstrip(),
        encoding="utf-8",
    )
    ai = tmp_path / "fake_pi_ai.mjs"
    ai.write_text(
        "export class AssistantMessageEventStream {}\n",
        encoding="utf-8",
    )
    process = await asyncio.create_subprocess_exec(
        "node",
        str(Path("src/opensquilla/engine/pi_sidecar_bridge.mjs").resolve()),
        "--runtime",
        str(runtime),
        "--ai-package",
        str(ai),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None
    turn_start = {
        "protocol": "opensquilla.agent_core.v1",
        "kind": "turn_start",
        "payload": {
            "prompt": "trigger yield",
            "kwargs": {
                "session_key": "agent:main:test",
                "session_id": "agent:main:test",
                "turn_snapshot": {
                    "session_key": "agent:main:test",
                    "session_id": "agent:main:test",
                    "agent_id": "main",
                    "turn_id": "agent:main:test:turn-1",
                    "turn_input": "trigger yield",
                    "model_id": "fake-pi-model",
                    "tool_definitions": [{"name": "sessions_yield"}],
                },
            },
        },
    }
    process.stdin.write((json.dumps(turn_start) + "\n").encode("utf-8"))
    await process.stdin.drain()

    line = await asyncio.wait_for(process.stdout.readline(), timeout=5.0)
    frame = json.loads(line)
    assert frame["kind"] == "intent"
    assert frame["type"] == "yield.request"

    process.stdin.close()
    await process.stdin.wait_closed()
    stdout_tail, stderr_tail, returncode = await asyncio.wait_for(
        asyncio.gather(
            process.stdout.read(),
            process.stderr.read(),
            process.wait(),
        ),
        timeout=5.0,
    )

    assert returncode == 0
    assert stderr_tail == b""
    assert [
        json.loads(tail_line)
        for tail_line in stdout_tail.decode("utf-8").splitlines()
        if tail_line.strip()
    ] == []


@pytest.mark.parametrize(
    (
        "intent_result_type",
        "intent_result_session_key",
        "intent_result_payload",
        "events_payload",
        "expected_text",
    ),
    [
        (
            {"not": "a string"},
            "agent:main:test",
            {},
            [{"kind": "done", "text": "host done"}],
            "intent_result type must be a string",
        ),
        (
            "   ",
            "agent:main:test",
            {},
            [{"kind": "done", "text": "host done"}],
            "intent_result type must be non-empty",
        ),
        (
            " provider.request",
            "agent:main:test",
            {},
            [{"kind": "done", "text": "host done"}],
            "intent_result type must not contain surrounding whitespace",
        ),
        (
            "unknown.intent",
            "agent:main:test",
            {},
            [{"kind": "done", "text": "host done"}],
            "Unsupported Pi sidecar intent_result 'unknown.intent'",
        ),
        (
            "provider.request",
            {"not": "a string"},
            {},
            [{"kind": "done", "text": "host done"}],
            "intent_result session_key must be a string",
        ),
        (
            "provider.request",
            "",
            {},
            [{"kind": "done", "text": "host done"}],
            "intent_result session_key must be non-empty",
        ),
        (
            "provider.request",
            "   ",
            {},
            [{"kind": "done", "text": "host done"}],
            "intent_result session_key must be non-empty",
        ),
        (
            "provider.request",
            "agent:main:other",
            {},
            [{"kind": "done", "text": "host done"}],
            "intent_result session_key must match current turn session_key",
        ),
        (
            "provider.request",
            "agent:main:test",
            "not an object",
            [{"kind": "done", "text": "host done"}],
            "intent_result payload must be a JSON object",
        ),
        (
            "provider.request",
            "agent:main:test",
            {},
            {"bad": "events"},
            "provider.request events must be a JSON array",
        ),
        (
            "provider.request",
            "agent:main:test",
            {},
            [None],
            "provider.request events entries must be JSON objects",
        ),
        (
            "provider.request",
            "agent:main:test",
            {},
            ["bad"],
            "provider.request events entries must be JSON objects",
        ),
        (
            "provider.request",
            "agent:main:test",
            {},
            [[]],
            "provider.request events entries must be JSON objects",
        ),
        (
            "provider.request",
            "agent:main:test",
            {},
            [{}],
            "provider.request events entries must include string kind",
        ),
        (
            "provider.request",
            "agent:main:test",
            {},
            [{"kind": ""}],
            "provider.request events entries kind must be non-empty",
        ),
        (
            "provider.request",
            "agent:main:test",
            {},
            [{"kind": "   "}],
            "provider.request events entries kind must be non-empty",
        ),
        (
            "provider.request",
            "agent:main:test",
            {},
            [
                {"kind": "done", "text": "done"},
                {"kind": "text_delta", "text": "late"},
            ],
            "intent_result events returned events after terminal event",
        ),
        (
            "provider.request",
            "agent:main:test",
            {},
            [
                {"kind": "done", "text": "done"},
                {"kind": "error", "message": "failed"},
            ],
            "intent_result events returned multiple terminal events",
        ),
    ],
)
@pytest.mark.asyncio
async def test_packaged_pi_sidecar_bridge_rejects_malformed_provider_feedback_frame(
    tmp_path: Path,
    intent_result_type: object,
    intent_result_session_key: object,
    intent_result_payload: object,
    events_payload: object,
    expected_text: str,
) -> None:
    runtime = tmp_path / "fake_pi_agent_core.mjs"
    runtime.write_text(
        textwrap.dedent(
            """
            export class Agent {
              constructor(options) {
                this.options = options;
                this.listener = () => {};
              }

              subscribe(listener) {
                this.listener = listener;
              }

              async prompt(prompt) {
                const stream = this.options.streamFn(
                  { id: "fake-pi-model", api: "fake", provider: "fake" },
                  { messages: [{ role: "user", content: [{ type: "text", text: prompt }] }] },
                  {},
                );
                for await (const event of stream) {
                  if (event.type === "error") {
                    this.listener({
                      assistantMessageEvent: {
                        type: "text_delta",
                        delta: event.error?.errorMessage ?? "",
                      },
                    });
                    return;
                  }
                }
                this.listener({
                  assistantMessageEvent: {
                    type: "text_delta",
                    delta: "provider feedback accepted",
                  },
                });
              }

              async waitForIdle() {}
            }
            """
        ).lstrip(),
        encoding="utf-8",
    )
    ai = tmp_path / "fake_pi_ai.mjs"
    ai.write_text(
        textwrap.dedent(
            """
            export class AssistantMessageEventStream {
              constructor() {
                this.items = [];
                this.waiters = [];
                this.closed = false;
              }

              push(event) {
                if (this.waiters.length > 0) {
                  this.waiters.shift()({ value: event, done: false });
                } else {
                  this.items.push(event);
                }
                if (event.type === "done" || event.type === "error") {
                  this.closed = true;
                }
              }

              [Symbol.asyncIterator]() {
                return this;
              }

              next() {
                if (this.items.length > 0) {
                  return Promise.resolve({ value: this.items.shift(), done: false });
                }
                if (this.closed) {
                  return Promise.resolve({ done: true });
                }
                return new Promise((resolve) => this.waiters.push(resolve));
              }
            }
            """
        ).lstrip(),
        encoding="utf-8",
    )
    process = await asyncio.create_subprocess_exec(
        "node",
        str(Path("src/opensquilla/engine/pi_sidecar_bridge.mjs").resolve()),
        "--runtime",
        str(runtime),
        "--ai-package",
        str(ai),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None
    turn_start = {
        "protocol": "opensquilla.agent_core.v1",
        "kind": "turn_start",
        "payload": {
            "prompt": "trigger provider feedback",
            "kwargs": {
                "session_key": "agent:main:test",
                "session_id": "agent:main:test",
                "turn_snapshot": {
                    "session_key": "agent:main:test",
                    "session_id": "agent:main:test",
                    "agent_id": "main",
                    "turn_id": "agent:main:test:turn-1",
                    "turn_input": "trigger provider feedback",
                    "model_id": "fake-pi-model",
                    "tool_definitions": [],
                },
            },
        },
    }
    process.stdin.write((json.dumps(turn_start) + "\n").encode("utf-8"))
    await process.stdin.drain()

    line = await asyncio.wait_for(process.stdout.readline(), timeout=5.0)
    frame = json.loads(line)
    assert frame["kind"] == "intent"
    assert frame["type"] == "provider.request"

    process.stdin.write(
        (
            json.dumps(
                {
                    "protocol": "opensquilla.agent_core.v1",
                    "kind": "intent_result",
                    "type": intent_result_type,
                    "session_key": intent_result_session_key,
                    "payload": intent_result_payload,
                    "events": events_payload,
                }
            )
            + "\n"
        ).encode("utf-8")
    )
    await process.stdin.drain()
    process.stdin.close()
    await process.stdin.wait_closed()

    line = await asyncio.wait_for(process.stdout.readline(), timeout=5.0)
    frame = json.loads(line)

    _, stderr_tail, returncode = await asyncio.wait_for(
        asyncio.gather(
            process.stdout.read(),
            process.stderr.read(),
            process.wait(),
        ),
        timeout=5.0,
    )

    assert frame["kind"] == "event"
    assert frame["type"] == "text.delta"
    assert frame["payload"]["text"] == expected_text
    assert returncode == 0
    assert stderr_tail == b""


@pytest.mark.parametrize(
    ("events_payload", "expected_text"),
    [
        ({"bad": "events"}, "tool.call.execute events must be a JSON array"),
        ([None], "tool.call.execute events entries must be JSON objects"),
        ([{}], "tool.call.execute events entries must include string kind"),
        ([{"kind": ""}], "tool.call.execute events entries kind must be non-empty"),
        ([{"kind": "   "}], "tool.call.execute events entries kind must be non-empty"),
        (
            [
                {"kind": "unknown_event"},
                {
                    "kind": "tool_result",
                    "tool_use_id": "call-1",
                    "tool_name": "echo",
                    "result": "host handled",
                },
            ],
            "Unsupported Pi sidecar intent_result event kind 'unknown_event'",
        ),
        (
            [
                {"kind": "done", "text": "done"},
                {"kind": "run_heartbeat", "message": "late"},
                {
                    "kind": "tool_result",
                    "tool_use_id": "call-1",
                    "tool_name": "echo",
                    "result": "host handled",
                },
            ],
            "intent_result events returned events after terminal event",
        ),
        (
            [
                {"kind": "done", "text": "done"},
                {"kind": "error", "message": "failed"},
                {
                    "kind": "tool_result",
                    "tool_use_id": "call-1",
                    "tool_name": "echo",
                    "result": "host handled",
                },
            ],
            "intent_result events returned multiple terminal events",
        ),
        ([], "tool.call.execute must return matching tool_result"),
    ],
)
@pytest.mark.asyncio
async def test_packaged_pi_sidecar_bridge_rejects_malformed_tool_execute_feedback(
    tmp_path: Path,
    events_payload: object,
    expected_text: str,
) -> None:
    runtime = tmp_path / "fake_pi_agent_core.mjs"
    runtime.write_text(
        textwrap.dedent(
            """
            export class Agent {
              constructor(options) {
                this.options = options;
                this.listener = () => {};
              }

              subscribe(listener) {
                this.listener = listener;
              }

              async prompt() {
                const tool = this.options.initialState.tools[0];
                try {
                  await tool.execute("call-1", { marker: "from-pi" });
                  this.listener({
                    assistantMessageEvent: {
                      type: "text_delta",
                      delta: "tool feedback accepted",
                    },
                  });
                } catch (error) {
                  this.listener({
                    assistantMessageEvent: {
                      type: "text_delta",
                      delta: error?.message ?? String(error),
                    },
                  });
                }
              }

              async waitForIdle() {}
            }
            """
        ).lstrip(),
        encoding="utf-8",
    )
    ai = tmp_path / "fake_pi_ai.mjs"
    ai.write_text(
        textwrap.dedent(
            """
            export class AssistantMessageEventStream {}
            """
        ).lstrip(),
        encoding="utf-8",
    )
    process = await asyncio.create_subprocess_exec(
        "node",
        str(Path("src/opensquilla/engine/pi_sidecar_bridge.mjs").resolve()),
        "--runtime",
        str(runtime),
        "--ai-package",
        str(ai),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None
    turn_start = {
        "protocol": "opensquilla.agent_core.v1",
        "kind": "turn_start",
        "payload": {
            "prompt": "trigger tool feedback",
            "kwargs": {
                "session_key": "agent:main:test",
                "session_id": "agent:main:test",
                "turn_snapshot": {
                    "session_key": "agent:main:test",
                    "session_id": "agent:main:test",
                    "agent_id": "main",
                    "turn_id": "agent:main:test:turn-1",
                    "turn_input": "trigger tool feedback",
                    "model_id": "fake-pi-model",
                    "tool_definitions": [
                        {
                            "name": "echo",
                            "description": "Echo marker",
                            "input_schema": {"type": "object", "properties": {}},
                        }
                    ],
                },
            },
        },
    }
    process.stdin.write((json.dumps(turn_start) + "\n").encode("utf-8"))
    await process.stdin.drain()

    line = await asyncio.wait_for(process.stdout.readline(), timeout=5.0)
    frame = json.loads(line)
    assert frame["kind"] == "intent"
    assert frame["type"] == "tool.call.prepare"
    assert frame["payload"]["tool_call_id"] == "call-1"
    assert frame["payload"]["tool_name"] == "echo"
    process.stdin.write(
        (
            json.dumps(
                {
                    "protocol": "opensquilla.agent_core.v1",
                    "kind": "intent_result",
                    "type": "tool.call.prepare",
                    "session_key": "agent:main:test",
                    "payload": frame["payload"],
                    "events": [
                        {
                            "kind": "tool_use_start",
                            "tool_use_id": "call-1",
                            "tool_name": "echo",
                            "synthetic_from_text": False,
                        }
                    ],
                }
            )
            + "\n"
        ).encode("utf-8")
    )
    await process.stdin.drain()

    line = await asyncio.wait_for(process.stdout.readline(), timeout=5.0)
    frame = json.loads(line)
    assert frame["kind"] == "intent"
    assert frame["type"] == "tool.call.execute"
    assert frame["payload"]["tool_call_id"] == "call-1"
    assert frame["payload"]["tool_name"] == "echo"
    process.stdin.write(
        (
            json.dumps(
                {
                    "protocol": "opensquilla.agent_core.v1",
                    "kind": "intent_result",
                    "type": "tool.call.execute",
                    "session_key": "agent:main:test",
                    "payload": frame["payload"],
                    "events": events_payload,
                }
            )
            + "\n"
        ).encode("utf-8")
    )
    await process.stdin.drain()

    line = await asyncio.wait_for(process.stdout.readline(), timeout=5.0)
    frame = json.loads(line)

    process.stdin.close()
    await process.stdin.wait_closed()
    _, stderr_tail, returncode = await asyncio.wait_for(
        asyncio.gather(
            process.stdout.read(),
            process.stderr.read(),
            process.wait(),
        ),
        timeout=5.0,
    )

    assert frame["kind"] == "event"
    assert frame["type"] == "text.delta"
    assert frame["payload"]["text"] == expected_text
    assert returncode == 0
    assert stderr_tail == b""


def test_agent_core_adapter_source_does_not_rewrite_pi_agent_loop() -> None:
    source = Path("src/opensquilla/engine/agent_core.py").read_text(encoding="utf-8")
    forbidden_markers = (
        "FakePiRpcClient",
        "fake sidecar",
        "prepareNextTurn",
        "prepare_next_turn",
        "beforeToolCall",
        "afterToolCall",
        "shouldStopAfterTurn",
        "toolExecution",
        "steeringMode",
        "followUpMode",
        "safe-point queue",
        "safe_point_queue",
        "before_tool(",
        "after_tool(",
        "runPiAgentLoop",
        "tool scheduler",
    )

    for marker in forbidden_markers:
        assert marker not in source


def test_pi_production_kernel_requires_real_rpc_command_or_client() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(
        RuntimeError,
        match="no pi_agent_rpc_command or pi_agent_rpc_client",
    ):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(agent_kernel="pi"),
            provider=object(),
            config=AgentConfig(model_id="pi-requires-real-rpc"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_test_fixture_rpc_commands() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="test-only Pi RPC command"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=f"{sys.executable} /tmp/fake_pi_rpc.py",
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-test-fixture-rpc"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


@pytest.mark.parametrize(
    "command",
    [
        "python tests/fixtures/pi_sidecar.py",
        "python -m tests.fixtures.pi_sidecar",
        "python /tmp/test_agent_core_pi_sidecar.py",
        "env PYTHONPATH=tests python -m opensquilla_pi_bridge",
        "env PYTHONPATH=tests/fixtures python -m opensquilla_pi_bridge",
        r"env PYTHONPATH=tests\\fixtures python -m opensquilla_pi_bridge",
        r"env PYTHONPATH=.\tests python -m opensquilla_pi_bridge",
        "env PYTHONPATH=examples python -m opensquilla_pi_bridge",
        "env PYTHONPATH=samples python -m opensquilla_pi_bridge",
        "env PYTHONPATH=demos python -m opensquilla_pi_bridge",
        "env PYTHONPATH=examples/bridges python -m opensquilla_pi_bridge",
        "env PYTHONPATH=samples/bridges python -m opensquilla_pi_bridge",
        "env PYTHONPATH=demos/bridges python -m opensquilla_pi_bridge",
        "env -S 'PYTHONPATH=tests python -m opensquilla_pi_bridge'",
        "env --split-string='PYTHONPATH=tests python -m opensquilla_pi_bridge'",
        "python examples/pi_sidecar.py",
        "python samples/pi_sidecar.py",
        "python demos/pi_sidecar.py",
        "python -m examples.pi_sidecar",
        "python -m samples.pi_sidecar",
        "python -m demos.pi_sidecar",
    ],
)
def test_pi_production_kernel_rejects_tests_directory_python_sidecar_command(
    command: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="test-only Pi RPC command"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=command,
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-agent-core"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-tests-dir-sidecar-rpc"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_unprovenanced_custom_rpc_commands() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="upstream Pi runtime provenance"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command="python /opt/custom_pi_bridge.py",
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-unprovenanced-command"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_unprovenanced_wrapper_named_like_upstream_package() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="upstream Pi runtime provenance"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=f"{sys.executable} /opt/pi-agent-core-wrapper.py",
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-wrapper-package-name-spoof"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_unprovenanced_wrapper_arg_spoofing_upstream_package() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="upstream Pi runtime provenance"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=(
                    f"{sys.executable} /opt/opensquilla_pi_bridge.py "
                    "--runtime @earendil-works/pi-coding-agent"
                ),
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-wrapper-arg-spoof"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


@pytest.mark.parametrize(
    ("provenance", "model_id"),
    [
        (
            "thin opensquilla.agent_core.v1 IO bridge around "
            "github.com/earendil-works/pi @earendil-works/pi-coding-agent "
            "with prepareNextTurn safe-point queue beforeToolCall afterToolCall "
            "agent loop logic",
            "pi-rejects-provenance-prepare-next-turn-loop",
        ),
        (
            "thin opensquilla.agent_core.v1 IO bridge package invoking "
            "github.com/earendil-works/pi @earendil-works/pi-coding-agent "
            "and reimplements Pi tool scheduling session lifecycle",
            "pi-rejects-provenance-reimplemented-loop",
        ),
        (
            "thin opensquilla.agent_core.v1 IO bridge around "
            "github.com/earendil-works/pi @earendil-works/pi-coding-agent "
            "with before/after tool hook support",
            "pi-rejects-provenance-before-after-tool-hook",
        ),
        (
            "thin opensquilla.agent_core.v1 IO bridge around "
            "github.com/earendil-works/pi @earendil-works/pi-coding-agent "
            "that implements Pi no-throw stream semantics",
            "pi-rejects-provenance-no-throw-stream",
        ),
        (
            "thin opensquilla.agent_core.v1 IO bridge around "
            "github.com/earendil-works/pi @earendil-works/pi-coding-agent "
            "that implements Pi parallel tool execution",
            "pi-rejects-provenance-parallel-tool-execution",
        ),
        (
            "thin opensquilla.agent_core.v1 IO bridge around "
            "github.com/earendil-works/pi @earendil-works/pi-coding-agent "
            "with Pi parallel tool scheduling support",
            "pi-rejects-provenance-parallel-tool-scheduling",
        ),
        (
            "thin opensquilla.agent_core.v1 IO bridge around "
            "github.com/earendil-works/pi @earendil-works/pi-coding-agent "
            "with Pi parallel tool call scheduling support",
            "pi-rejects-provenance-parallel-tool-call-scheduling",
        ),
        (
            "thin opensquilla.agent_core.v1 IO bridge around "
            "github.com/earendil-works/pi @earendil-works/pi-coding-agent "
            "with Pi parallel tool invocation scheduling support",
            "pi-rejects-provenance-parallel-tool-invocation-scheduling",
        ),
        (
            "thin opensquilla.agent_core.v1 IO bridge around "
            "github.com/earendil-works/pi @earendil-works/pi-coding-agent "
            "that implements Pi safe point queue",
            "pi-rejects-provenance-safe-point-queue",
        ),
        (
            "thin opensquilla.agent_core.v1 IO bridge around "
            "github.com/earendil-works/pi @earendil-works/pi-coding-agent "
            "that implements getSteeringMessages and getFollowUpMessages",
            "pi-rejects-provenance-steering-follow-up-message-hooks",
        ),
        (
            "thin opensquilla.agent_core.v1 IO bridge around "
            "github.com/earendil-works/pi @earendil-works/pi-coding-agent "
            "that implements Pi steering/follow-up queues",
            "pi-rejects-provenance-steering-follow-up-queues",
        ),
    ],
)
def test_pi_production_kernel_rejects_provenance_declaring_pi_loop_rewrite(
    provenance: str,
    model_id: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="Pi agent loop"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=(
                    "npx @opensquilla/pi-agent-core-bridge "
                    "--runtime @earendil-works/pi-coding-agent"
                ),
                pi_agent_rpc_command_provenance=provenance,
            ),
            provider=object(),
            config=AgentConfig(model_id=model_id),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_native_pi_rpc_mode_as_host_sidecar() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command="pi --mode rpc",
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-native-rpc-mode"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_native_pi_rpc_mode_with_whitespace_value() -> (
    None
):
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command="pi --mode ' RPC '",
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-native-rpc-mode-whitespace"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_native_pi_rpc_mode_with_whitespace_equals_value() -> (
    None
):
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command="pi --mode=' RPC '",
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-native-rpc-mode-equals-whitespace"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_provenanced_native_pi_rpc_mode_as_host_sidecar() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command="pi --mode rpc",
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-provenanced-native-rpc-mode"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_legacy_native_pi_rpc_alias() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command="pi --rpc",
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-legacy-native-rpc-alias"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_provenanced_native_pi_json_mode_as_host_sidecar() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi CLI/package"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command="pi --mode json",
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-provenanced-native-json-mode"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


@pytest.mark.parametrize(
    "wrapped_command",
    [
        "cmd /c pi --mode rpc",
        "cmd.exe /C pi --mode rpc",
        'powershell -Command "pi --mode rpc"',
        'pwsh -Command "pi --mode rpc"',
        "cmd /c npx @earendil-works/pi-coding-agent --mode rpc",
        "cmd.exe /C npx @earendil-works/pi-coding-agent --mode rpc",
        'powershell -Command "npx @earendil-works/pi-coding-agent --mode rpc"',
        'pwsh -Command "npx @earendil-works/pi-coding-agent --mode rpc"',
    ],
)
def test_pi_production_kernel_rejects_native_pi_rpc_mode_behind_windows_shell(
    wrapped_command: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=wrapped_command,
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-windows-shell-native-rpc-mode"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


@pytest.mark.parametrize(
    "wrapped_command",
    [
        "cmd /c call pi --mode rpc",
        "cmd /c call npx @earendil-works/pi-coding-agent --mode rpc",
        "cmd /c start pi --mode rpc",
        'cmd /c start "" pi --mode rpc',
        'cmd /c start "Pi RPC" pi --mode rpc',
        'cmd /c start /wait "" npx @earendil-works/pi-coding-agent --mode rpc',
    ],
)
def test_pi_production_kernel_rejects_native_pi_rpc_mode_behind_cmd_builtins(
    wrapped_command: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=wrapped_command,
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-cmd-builtin-native-rpc-mode"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_allows_bridge_behind_cmd_start_builtin() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_command=(
                'cmd /c start "" /opt/opensquilla_pi_bridge.ps1 '
                "--runtime @earendil-works/pi-coding-agent"
            ),
            pi_agent_rpc_command_provenance=(
                "thin opensquilla.agent_core.v1 IO bridge around "
                "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
            ),
        ),
        provider=object(),
        config=AgentConfig(model_id="pi-allows-cmd-start-bridge"),
        tool_definitions=[],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )


@pytest.mark.parametrize(
    "shim_command",
    [
        "pi.cmd --mode rpc",
        r"C:\\Users\\weihe\\AppData\\Roaming\\npm\\pi.cmd --mode rpc",
        "pi.ps1 --mode rpc",
        "powershell -File pi.ps1 --mode rpc",
        "npx.cmd @earendil-works/pi-coding-agent --mode rpc",
        "npm.cmd exec @earendil-works/pi-coding-agent -- --mode rpc",
        "pnpm.cmd dlx @earendil-works/pi-coding-agent --mode rpc",
        "yarn.cmd dlx @earendil-works/pi-coding-agent --mode rpc",
        "bunx.exe @earendil-works/pi-coding-agent --mode rpc",
        "node.exe /opt/node_modules/@earendil-works/pi-coding-agent/bin/pi.js --mode rpc",
        "cmd /c call npx.cmd @earendil-works/pi-coding-agent --mode rpc",
        'cmd /c start "" pi.cmd --mode rpc',
    ],
)
def test_pi_production_kernel_rejects_native_pi_rpc_mode_behind_windows_shims(
    shim_command: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=shim_command,
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-windows-shim-native-rpc-mode"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_allows_bridge_behind_windows_cmd_shim() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_command=(
                'cmd /c start "" /opt/opensquilla_pi_bridge.cmd '
                "--runtime @earendil-works/pi-coding-agent"
            ),
            pi_agent_rpc_command_provenance=(
                "thin opensquilla.agent_core.v1 IO bridge around "
                "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
            ),
        ),
        provider=object(),
        config=AgentConfig(model_id="pi-allows-windows-cmd-shim-bridge"),
        tool_definitions=[],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )


@pytest.mark.parametrize(
    "wrapped_command",
    [
        "powershell -File /opt/node_modules/@earendil-works/pi-coding-agent/bin/pi.ps1 --mode rpc",
        "pwsh -File /opt/node_modules/@earendil-works/pi-coding-agent/bin/pi.ps1 --mode rpc",
        "powershell -f /opt/node_modules/@earendil-works/pi-agent-core/dist/index.ps1 --mode rpc",
        "pwsh -File pi --mode rpc",
    ],
)
def test_pi_production_kernel_rejects_native_pi_rpc_mode_behind_powershell_file(
    wrapped_command: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=wrapped_command,
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-powershell-file-native-rpc-mode"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )



@pytest.mark.parametrize(
    ("shell_command", "native_command"),
    [
        ("powershell -EncodedCommand", "pi --mode rpc"),
        ("pwsh -EncodedCommand", "pi --mode rpc"),
        (
            "powershell -enc",
            "npx @earendil-works/pi-coding-agent --mode rpc",
        ),
        ("pwsh -e", "npx @earendil-works/pi-coding-agent --mode rpc"),
    ],
)
def test_pi_production_kernel_rejects_native_pi_rpc_mode_behind_powershell_encoded_command(
    shell_command: str,
    native_command: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    encoded_command = base64.b64encode(native_command.encode("utf-16le")).decode("ascii")

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=f"{shell_command} {encoded_command}",
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(
                model_id="pi-rejects-powershell-encoded-native-rpc-mode"
            ),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


@pytest.mark.parametrize(
    "wrapped_command",
    [
        "powershell -EncodedCommand not-base64",
        "pwsh -enc not-base64",
        "powershell -EncodedCommand bm90LXV0ZjE2",
    ],
)
def test_pi_production_kernel_rejects_opaque_powershell_encoded_command(
    wrapped_command: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="PowerShell encoded command"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=wrapped_command,
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-opaque-powershell-encoded-command"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_native_coding_agent_rpc_package_as_host_sidecar() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command="npx @earendil-works/pi-coding-agent --mode rpc",
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-native-package-rpc-mode"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_encoded_native_rpc_package() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=(
                    "npx %40earendil%2Dworks%2Fpi%2Dcoding%2Dagent --mode rpc"
                ),
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-encoded-native-package-rpc-mode"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_provenanced_native_coding_agent_rpc_package() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command="npx @earendil-works/pi-coding-agent --mode rpc",
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(
                model_id="pi-rejects-provenanced-native-package-rpc-mode",
            ),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_provenanced_native_pi_namespace_package() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi CLI/package"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command="npx @earendil-works/pi-ai --help",
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-ai"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-native-namespace-package"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_env_wrapped_native_coding_agent_rpc_package() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=(
                    "env NODE_ENV=production "
                    "npx @earendil-works/pi-coding-agent --mode rpc"
                ),
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-env-native-package-rpc-mode"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_env_node_options_native_pi_preload() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi CLI/package"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=(
                    "env NODE_OPTIONS=--require=@earendil-works/pi-agent-core "
                    "node /opt/opensquilla_pi_bridge.js"
                ),
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-agent-core"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-env-node-options-native-preload"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_env_command_native_pi_rpc_injection() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=(
                    "env PI_AGENT_RPC_COMMAND='pi --mode rpc' "
                    "npx @opensquilla/pi-agent-core-bridge"
                ),
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(
                model_id="pi-rejects-env-command-native-rpc-injection"
            ),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_allows_env_runtime_package_reference() -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient, build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    wrapper_agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_command=(
                "env PI_AGENT_RUNTIME=@earendil-works/pi-coding-agent "
                "npx @opensquilla/pi-agent-core-bridge"
            ),
            pi_agent_rpc_command_provenance=(
                "thin opensquilla.agent_core.v1 IO bridge around "
                "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
            ),
        ),
        provider=object(),
        config=AgentConfig(model_id="pi-allows-env-runtime-package-reference"),
        tool_definitions=[],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )

    assert isinstance(wrapper_agent._rpc_client, PiJsonlCommandRpcClient)


def test_pi_production_kernel_allows_env_model_value_rpc_with_runtime_reference() -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient, build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    wrapper_agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_command=(
                "env PI_AGENT_RUNTIME=@earendil-works/pi-coding-agent "
                "MODEL=rpc npx @opensquilla/pi-agent-core-bridge"
            ),
            pi_agent_rpc_command_provenance=(
                "thin opensquilla.agent_core.v1 IO bridge around "
                "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
            ),
        ),
        provider=object(),
        config=AgentConfig(model_id="pi-allows-env-model-rpc-package-reference"),
        tool_definitions=[],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )

    assert isinstance(wrapper_agent._rpc_client, PiJsonlCommandRpcClient)


def test_pi_production_kernel_rejects_env_runtime_mode_native_pi_rpc_injection() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=(
                    "env PI_AGENT_RUNTIME=@earendil-works/pi-coding-agent "
                    "PI_AGENT_MODE=rpc npx @opensquilla/pi-agent-core-bridge"
                ),
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(
                model_id="pi-rejects-env-runtime-mode-native-rpc-injection"
            ),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_env_runtime_mode_rpc_injection_with_whitespace() -> (
    None
):
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=(
                    "env PI_AGENT_RUNTIME=@earendil-works/pi-coding-agent "
                    "PI_AGENT_MODE=' RPC ' npx @opensquilla/pi-agent-core-bridge"
                ),
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(
                model_id="pi-rejects-env-runtime-mode-native-rpc-injection-whitespace"
            ),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


@pytest.mark.parametrize(
    "command",
    [
        (
            "env BASH_ENV=/opt/node_modules/@earendil-works/pi-coding-agent/bootstrap.sh "
            "bash -c /opt/opensquilla_pi_bridge.sh"
        ),
        (
            "env ENV=/opt/node_modules/@earendil-works/pi-agent-core/profile.sh "
            "sh -c /opt/opensquilla_pi_bridge.sh"
        ),
        (
            "env ZDOTDIR=/opt/node_modules/@earendil-works/pi-coding-agent "
            "zsh -c /opt/opensquilla_pi_bridge.sh"
        ),
    ],
)
def test_pi_production_kernel_rejects_shell_startup_env_native_pi_injection(
    command: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi CLI/package"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=command,
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(
                model_id="pi-rejects-shell-startup-env-native-injection"
            ),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_allows_shell_startup_env_without_native_pi_marker() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_command=(
                "env BASH_ENV=/opt/opensquilla_bridge_env.sh "
                "bash -c /opt/opensquilla_pi_bridge.sh"
            ),
            pi_agent_rpc_command_provenance=(
                "thin opensquilla.agent_core.v1 IO bridge around "
                "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
            ),
        ),
        provider=object(),
        config=AgentConfig(model_id="pi-allows-shell-startup-env-bridge-wrapper"),
        tool_definitions=[],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )

    assert agent is not None


@pytest.mark.parametrize(
    "command",
    [
        "env -S 'npx @earendil-works/pi-coding-agent --mode rpc'",
        "env --split-string='npx @earendil-works/pi-coding-agent --mode rpc'",
        "env -S 'NODE_ENV=production npx @earendil-works/pi-coding-agent --mode rpc'",
    ],
)
def test_pi_production_kernel_rejects_env_split_string_native_coding_agent_rpc_package(
    command: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=command,
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(
                model_id="pi-rejects-env-split-string-native-package-rpc-mode"
            ),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_timeout_wrapped_native_coding_agent_rpc_package() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=(
                    "timeout 30 npx @earendil-works/pi-coding-agent --mode rpc"
                ),
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-timeout-native-package-rpc-mode"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


@pytest.mark.parametrize(
    "wrapped_command",
    [
        "nohup npx @earendil-works/pi-coding-agent --mode rpc",
        "nohup -- npx @earendil-works/pi-coding-agent --mode rpc",
        "nice -n 5 npx @earendil-works/pi-coding-agent --mode rpc",
        "setsid npx @earendil-works/pi-coding-agent --mode rpc",
        "stdbuf -oL npx @earendil-works/pi-coding-agent --mode rpc",
    ],
)
def test_pi_production_kernel_rejects_process_wrapped_native_coding_agent_rpc_package(
    wrapped_command: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=wrapped_command,
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-process-wrapper-native-package-rpc-mode"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


@pytest.mark.parametrize(
    "wrapped_command",
    [
        "corepack pnpm dlx @earendil-works/pi-coding-agent --mode rpc",
        "corepack yarn dlx @earendil-works/pi-coding-agent --mode rpc",
        "corepack npm exec @earendil-works/pi-coding-agent -- --mode rpc",
        "env -S 'corepack pnpm dlx @earendil-works/pi-coding-agent --mode rpc'",
        "bash -lc 'corepack pnpm dlx @earendil-works/pi-coding-agent --mode rpc'",
    ],
)
def test_pi_production_kernel_rejects_corepack_wrapped_native_coding_agent_package(
    wrapped_command: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=wrapped_command,
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-corepack-native-package-rpc-mode"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


@pytest.mark.parametrize(
    "wrapped_command",
    [
        "npm exec -c 'pi --mode rpc' --package @earendil-works/pi-coding-agent",
        "npx -c 'pi --mode rpc' --package @earendil-works/pi-coding-agent",
    ],
)
def test_pi_production_kernel_rejects_package_runner_shell_native_pi_rpc_package(
    wrapped_command: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=wrapped_command,
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(
                model_id="pi-rejects-package-runner-shell-native-rpc-mode"
            ),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


@pytest.mark.parametrize(
    "wrapped_command",
    [
        "npx --package @earendil-works/pi-agent-core node /opt/opensquilla_pi_bridge.js",
        "npx --package=@earendil-works/pi-agent-core node /opt/opensquilla_pi_bridge.js",
        "npm exec --package @earendil-works/pi-agent-core -- node /opt/opensquilla_pi_bridge.js",
    ],
)
def test_pi_production_kernel_rejects_package_runner_upstream_pi_package_injection(
    wrapped_command: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi CLI/package"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=wrapped_command,
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-agent-core"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-package-runner-pi-injection"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


@pytest.mark.parametrize(
    "wrapped_command",
    [
        "yarn node /opt/node_modules/@earendil-works/pi-coding-agent/bin/pi.js --mode rpc",
        "corepack yarn node /opt/node_modules/@earendil-works/pi-coding-agent/bin/pi.js --mode rpc",
    ],
)
def test_pi_production_kernel_rejects_yarn_node_native_pi_source_path(
    wrapped_command: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=wrapped_command,
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-yarn-node-native-source-path"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_node_run_native_pi_rpc_script() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command="node --run pi -- --mode rpc",
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-node-run-native-rpc-script"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


@pytest.mark.parametrize(
    "wrapped_command",
    [
        "npm run pi -- --mode rpc",
        "pnpm run pi -- --mode rpc",
        "yarn run pi --mode rpc",
        "yarn pi --mode rpc",
        "bun run pi --mode rpc",
        "corepack pnpm run pi -- --mode rpc",
        "corepack yarn run pi --mode rpc",
    ],
)
def test_pi_production_kernel_rejects_package_script_native_pi_rpc_script(
    wrapped_command: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=wrapped_command,
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-package-script-native-rpc"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_accepts_package_script_sidecar_bridge() -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient, build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    wrapper_agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_command=(
                "npm run opensquilla-pi-bridge -- "
                "--runtime @earendil-works/pi-coding-agent"
            ),
            pi_agent_rpc_command_provenance=(
                "thin opensquilla.agent_core.v1 IO bridge package invoking "
                "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
            ),
        ),
        provider=object(),
        config=AgentConfig(model_id="pi-accepts-package-script-sidecar-bridge"),
        tool_definitions=[],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )
    assert isinstance(wrapper_agent._rpc_client, PiJsonlCommandRpcClient)


@pytest.mark.parametrize(
    "wrapped_command",
    [
        "tsx /opt/pi/packages/coding-agent/src/cli.ts --mode rpc",
        "ts-node /opt/pi/packages/coding-agent/src/cli.ts --mode rpc",
        "ts-node-esm /opt/pi/packages/coding-agent/src/cli.ts --mode rpc",
        "jiti /opt/pi/packages/coding-agent/src/cli.ts --mode rpc",
        "esno /opt/pi/packages/coding-agent/src/cli.ts --mode rpc",
        "deno run -A npm:@earendil-works/pi-coding-agent --mode rpc",
        "deno run -A /opt/pi/packages/coding-agent/src/cli.ts --mode rpc",
    ],
)
def test_pi_production_kernel_rejects_direct_source_executor_native_pi_rpc(
    wrapped_command: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=wrapped_command,
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-direct-source-executor-rpc"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


@pytest.mark.parametrize(
    "wrapped_command",
    [
        "npx pi --mode rpc",
        "npx pi@latest --mode rpc",
        "npm exec pi -- --mode rpc",
        "npm exec pi@latest -- --mode rpc",
        "pnpm dlx pi --mode rpc",
        "pnpm dlx pi@latest --mode rpc",
        "yarn dlx pi --mode rpc",
        "yarn dlx pi@latest --mode rpc",
        "bunx pi --mode rpc",
        "bunx pi@latest --mode rpc",
    ],
)
def test_pi_production_kernel_rejects_package_runner_short_pi_bin_rpc(
    wrapped_command: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=wrapped_command,
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-package-runner-short-bin"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


@pytest.mark.parametrize(
    "wrapped_command",
    [
        "pnpm create @earendil-works/pi-coding-agent --mode rpc",
        "yarn create @earendil-works/pi-coding-agent --mode rpc",
        "npm init @earendil-works/pi-coding-agent -- --mode rpc",
        "corepack pnpm create @earendil-works/pi-coding-agent --mode rpc",
        "corepack yarn create @earendil-works/pi-coding-agent --mode rpc",
        "bun create @earendil-works/pi-coding-agent --mode rpc",
    ],
)
def test_pi_production_kernel_rejects_package_creator_native_pi_rpc_package(
    wrapped_command: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=wrapped_command,
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-package-creator-native-rpc"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


@pytest.mark.parametrize(
    "wrapped_command",
    [
        "bash -lc 'npx @earendil-works/pi-coding-agent --mode rpc'",
        "bash -lc 'exec -- npx @earendil-works/pi-coding-agent --mode rpc'",
        "bash -lc 'command -- npx @earendil-works/pi-coding-agent --mode rpc'",
        "csh -c 'npx @earendil-works/pi-coding-agent --mode rpc'",
        "fish -c 'npx @earendil-works/pi-coding-agent --mode rpc'",
        "tcsh -c 'npx @earendil-works/pi-coding-agent --mode rpc'",
    ],
)
def test_pi_production_kernel_rejects_shell_wrapped_native_coding_agent_rpc_package(
    wrapped_command: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=wrapped_command,
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-shell-native-package-rpc-mode"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


@pytest.mark.parametrize(
    "wrapped_command",
    [
        "bash -lc 'cd /tmp && npx @earendil-works/pi-ai --help'",
        "bash -lc 'echo prep; npx @earendil-works/pi-ai --help'",
    ],
)
def test_pi_production_kernel_rejects_shell_compound_native_pi_namespace_package(
    wrapped_command: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi CLI/package"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=wrapped_command,
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-ai"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-shell-compound-native-package"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_shell_compound_native_pi_rpc_cli() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command="bash -lc 'cd /tmp && pi --mode rpc'",
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-shell-compound-native-rpc"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_native_pi_profile_rpc_script() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=(
                    "node /opt/pi/scripts/profile-coding-agent-node.mjs --mode rpc"
                ),
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-native-profile-rpc-script"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_provenanced_native_coding_agent_json_package() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi CLI/package"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command="npx @earendil-works/pi-coding-agent --mode json",
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(
                model_id="pi-rejects-provenanced-native-package-json-mode",
            ),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_node_direct_native_coding_agent_package() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi CLI/package"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=(
                    "node /opt/node_modules/@earendil-works/pi-coding-agent/bin/pi.js "
                    "--mode json"
                ),
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(
                model_id="pi-rejects-node-direct-native-package",
            ),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_node_direct_native_agent_core_package() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi CLI/package"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=(
                    "node /opt/node_modules/@earendil-works/pi-agent-core/dist/index.js"
                ),
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-agent-core"
                ),
            ),
            provider=object(),
            config=AgentConfig(
                model_id="pi-rejects-node-direct-native-agent-core-package",
            ),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_node_direct_pi_checkout_coding_agent_cli() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=(
                    "node /opt/pi/packages/coding-agent/src/cli.ts --mode rpc"
                ),
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(
                model_id="pi-rejects-node-direct-checkout-coding-agent-cli",
            ),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


@pytest.mark.parametrize(
    "command",
    [
        "pnpm tsx /opt/pi/packages/coding-agent/src/cli.ts --mode rpc",
        "yarn tsx /opt/pi/packages/coding-agent/src/cli.ts --mode rpc",
        "bunx tsx /opt/pi/packages/coding-agent/src/cli.ts --mode rpc",
    ],
)
def test_pi_production_kernel_rejects_package_runner_direct_pi_checkout_cli(
    command: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=command,
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-runner-checkout-coding-agent-cli"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


@pytest.mark.parametrize(
    ("command", "model_id"),
    [
        (
            "node -e \"import('@earendil-works/pi-agent-core')\"",
            "pi-rejects-node-inline-native-agent-core-package",
        ),
        (
            "node --eval \"import('@earendil-works/pi-coding-agent')\"",
            "pi-rejects-node-inline-native-coding-agent-package",
        ),
        (
            "node -e \"import(decodeURIComponent("
            "'%40earendil%2Dworks%2Fpi%2Dagent%2Dcore'))\"",
            "pi-rejects-node-inline-percent-encoded-native-agent-core-package",
        ),
        (
            "node -e \"import(decodeURIComponent(decodeURIComponent("
            "'%2540earendil%252Dworks%252Fpi%252Dagent%252Dcore')))\"",
            "pi-rejects-node-inline-double-percent-encoded-native-agent-core-package",
        ),
    ],
)
def test_pi_production_kernel_rejects_node_inline_native_pi_package(
    command: str,
    model_id: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi CLI/package"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=command,
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-agent-core"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id=model_id),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


@pytest.mark.parametrize(
    ("command", "model_id"),
    [
        (
            "node --import @earendil-works/pi-agent-core /opt/opensquilla_pi_bridge.js",
            "pi-rejects-node-import-native-agent-core-package",
        ),
        (
            "node --require @earendil-works/pi-coding-agent/register /opt/opensquilla_pi_bridge.js",
            "pi-rejects-node-require-native-coding-agent-package",
        ),
        (
            "node --require "
            "%40earendil%2Dworks%2Fpi%2Dcoding%2Dagent/register "
            "/opt/opensquilla_pi_bridge.js",
            "pi-rejects-node-require-percent-encoded-native-coding-agent-package",
        ),
        (
            "node --experimental-loader=@earendil-works/pi-agent-core/loader "
            "/opt/opensquilla_pi_bridge.js",
            "pi-rejects-node-experimental-loader-native-agent-core-package",
        ),
        (
            "node --import "
            "data:text/javascript,import('@earendil-works/pi-agent-core') "
            "/opt/opensquilla_pi_bridge.js",
            "pi-rejects-node-import-data-url-native-agent-core-package",
        ),
        (
            "node --import "
            "data:text/javascript,import(decodeURIComponent("
            "'%40earendil%2Dworks%2Fpi%2Dagent%2Dcore')) "
            "/opt/opensquilla_pi_bridge.js",
            "pi-rejects-node-import-percent-encoded-data-url-native-agent-core-package",
        ),
        (
            "node --import "
            "data:text/javascript,import(decodeURIComponent(decodeURIComponent("
            "'%2540earendil%252Dworks%252Fpi%252Dagent%252Dcore'))) "
            "/opt/opensquilla_pi_bridge.js",
            (
                "pi-rejects-node-import-double-percent-encoded-data-url-"
                "native-agent-core-package"
            ),
        ),
    ],
)
def test_pi_production_kernel_rejects_node_preload_native_pi_package(
    command: str,
    model_id: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi CLI/package"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=command,
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-agent-core"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id=model_id),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_node_direct_native_package_after_node_option() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi CLI/package"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=(
                    "node --require ts-node/register "
                    "/opt/node_modules/@earendil-works/pi-coding-agent/bin/pi.ts "
                    "--mode json"
                ),
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(
                model_id="pi-rejects-node-direct-native-package-with-option",
            ),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_agent_core_package_as_direct_cli_command() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command="npx @earendil-works/pi-agent-core --mode rpc",
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-agent-core-package-command"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_accepts_provenanced_agent_core_bridge_command() -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient, build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    wrapper_agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_command="python /opt/opensquilla_pi_bridge.py",
            pi_agent_rpc_command_provenance=(
                "thin opensquilla.agent_core.v1 IO bridge around "
                "github.com/earendil-works/pi @earendil-works/pi-agent-core"
            ),
        ),
        provider=object(),
        config=AgentConfig(model_id="pi-provenanced-wrapper-command"),
        tool_definitions=[],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )
    assert isinstance(wrapper_agent._rpc_client, PiJsonlCommandRpcClient)


def test_pi_production_kernel_accepts_provenanced_sidecar_package_wrapper_command() -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient, build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    wrapper_agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_command=(
                "npx @opensquilla/pi-agent-core-bridge "
                "--runtime @earendil-works/pi-coding-agent"
            ),
            pi_agent_rpc_command_provenance=(
                "thin opensquilla.agent_core.v1 IO bridge package invoking "
                "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
            ),
        ),
        provider=object(),
        config=AgentConfig(model_id="pi-provenanced-package-wrapper-command"),
        tool_definitions=[],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )
    assert isinstance(wrapper_agent._rpc_client, PiJsonlCommandRpcClient)


def test_pi_production_kernel_rejects_module_root_inside_opensquilla_source() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="module root.*OpenSquilla source"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=(
                    "npx @opensquilla/pi-agent-core-bridge "
                    "--module-root /opt/opensquilla/src/opensquilla/_vendor/pi "
                    "--runtime @earendil-works/pi-coding-agent"
                ),
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge invoking "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-vendored-module-root"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_accepts_provenance_declaring_upstream_pi_owns_loop() -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient, build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    wrapper_agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_command=(
                "npx @opensquilla/pi-agent-core-bridge "
                "--runtime @earendil-works/pi-coding-agent"
            ),
            pi_agent_rpc_command_provenance=(
                "thin opensquilla.agent_core.v1 IO bridge around "
                "github.com/earendil-works/pi @earendil-works/pi-coding-agent; "
                "upstream Pi owns prepareNextTurn safe-point queue "
                "beforeToolCall afterToolCall; OpenSquilla wrapper only "
                "translates IO and protocol frames"
            ),
        ),
        provider=object(),
        config=AgentConfig(model_id="pi-accepts-upstream-owned-loop-provenance"),
        tool_definitions=[],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )
    assert isinstance(wrapper_agent._rpc_client, PiJsonlCommandRpcClient)


@pytest.mark.parametrize(
    ("runtime_package", "provenance"),
    [
        (
            "@mariozechner/pi-coding-agent",
            "github.com/badlogic/pi-mono @mariozechner/pi-coding-agent",
        ),
        (
            "@mariozechner/pi-agent-core",
            "github.com/badlogic/pi-mono @mariozechner/pi-agent-core",
        ),
    ],
)
def test_pi_production_kernel_accepts_legacy_pi_package_provenance_for_bridge_runtime(
    runtime_package: str,
    provenance: str,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient, build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    wrapper_agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_command=(
                "npx @opensquilla/pi-agent-core-bridge "
                f"--runtime {runtime_package}"
            ),
            pi_agent_rpc_command_provenance=(
                "thin opensquilla.agent_core.v1 IO bridge package invoking "
                f"{provenance}"
            ),
        ),
        provider=object(),
        config=AgentConfig(model_id="pi-legacy-provenanced-package-wrapper-command"),
        tool_definitions=[],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )
    assert isinstance(wrapper_agent._rpc_client, PiJsonlCommandRpcClient)


@pytest.mark.parametrize(
    ("runtime_arg", "model_id"),
    [
        (
            "--runtime "
            "data:text/javascript,import('@earendil-works/pi-agent-core')",
            "pi-rejects-wrapper-runtime-inline-code",
        ),
        (
            "--runtime="
            "data:text/javascript;charset=utf-8,import('@earendil-works/pi-agent-core')",
            "pi-rejects-wrapper-runtime-inline-code-with-charset",
        ),
        (
            "--runtime="
            "data:text/javascript,import(decodeURIComponent("
            "'%40earendil%2Dworks%2Fpi%2Dagent%2Dcore'))",
            "pi-rejects-wrapper-runtime-percent-encoded-inline-code",
        ),
        (
            "--runtime="
            "data:text/javascript,import(decodeURIComponent(decodeURIComponent("
            "'%2540earendil%252Dworks%252Fpi%252Dagent%252Dcore')))",
            "pi-rejects-wrapper-runtime-double-percent-encoded-inline-code",
        ),
        (
            "--runtime /opt/pi/packages/agent/src/index.ts",
            "pi-rejects-wrapper-runtime-upstream-source-path",
        ),
        (
            "--runtime=/opt/pi/packages/coding-agent/src/cli.ts",
            "pi-rejects-wrapper-runtime-upstream-coding-agent-source-path",
        ),
        (
            "--agentRuntime=/opt/pi/packages/ai/src/cli.ts",
            "pi-rejects-wrapper-agent-runtime-upstream-ai-source-path",
        ),
        (
            "--runtimepackage=/opt/pi/packages/tui/src/index.ts",
            "pi-rejects-wrapper-runtimepackage-upstream-tui-source-path",
        ),
    ],
)
def test_pi_production_kernel_rejects_wrapper_runtime_inline_upstream_code(
    runtime_arg: str,
    model_id: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi CLI/package"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=(
                    "npx @opensquilla/pi-agent-core-bridge "
                    f"{runtime_arg}"
                ),
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge package invoking "
                    "github.com/earendil-works/pi @earendil-works/pi-agent-core"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id=model_id),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


@pytest.mark.parametrize(
    ("mode_arg", "model_id"),
    [
        (
            "--runtime @earendil-works/pi-coding-agent --mode rpc",
            "pi-rejects-wrapper-split-runtime-mode-native-rpc",
        ),
        (
            "--runtime @earendil-works/pi-coding-agent --rpc",
            "pi-rejects-wrapper-split-runtime-rpc-flag-native-rpc",
        ),
        (
            "--runtime @earendil-works/pi-coding-agent --mode=' RPC '",
            "pi-rejects-wrapper-runtime-equals-mode-whitespace-native-rpc",
        ),
        (
            "--runtime @earendil-works/pi-coding-agent --mode='rpc '",
            "pi-rejects-wrapper-runtime-equals-mode-trailing-space-native-rpc",
        ),
        (
            "--pi-runtime @earendil-works/pi-coding-agent --mode rpc",
            "pi-rejects-wrapper-split-pi-runtime-mode-native-rpc",
        ),
        (
            "--piRuntime @earendil-works/pi-coding-agent --mode rpc",
            "pi-rejects-wrapper-split-pi-runtime-camel-native-rpc",
        ),
        (
            "--agent-runtime @earendil-works/pi-coding-agent --mode rpc",
            "pi-rejects-wrapper-split-agent-runtime-native-rpc",
        ),
        (
            "--runtime-package @earendil-works/pi-coding-agent --mode rpc",
            "pi-rejects-wrapper-split-runtime-package-native-rpc",
        ),
        (
            "--runtime_package @earendil-works/pi-coding-agent --mode rpc",
            "pi-rejects-wrapper-split-runtime-package-underscore-native-rpc",
        ),
        (
            "--pi_runtime @earendil-works/pi-coding-agent --mode rpc",
            "pi-rejects-wrapper-split-pi-runtime-underscore-native-rpc",
        ),
        (
            "--agent_runtime @earendil-works/pi-coding-agent --mode rpc",
            "pi-rejects-wrapper-split-agent-runtime-underscore-native-rpc",
        ),
    ],
)
def test_pi_production_kernel_rejects_wrapper_split_runtime_rpc_mode_options(
    mode_arg: str,
    model_id: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=(
                    "npx @opensquilla/pi-agent-core-bridge "
                    f"{mode_arg}"
                ),
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge package invoking "
                    "github.com/earendil-works/pi @earendil-works/pi-agent-core"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id=model_id),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_sidecar_wrapper_native_pi_command_tail() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=(
                    "pnpm dlx @opensquilla/pi-agent-core-bridge -- "
                    "@earendil-works/pi-coding-agent --mode rpc"
                ),
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge package invoking "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-wrapper-native-command-tail"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


@pytest.mark.parametrize(
    ("command_arg", "model_id"),
    [
        (
            "--runtime-command 'npx @earendil-works/pi-coding-agent --mode rpc'",
            "pi-rejects-wrapper-runtime-command-native-rpc",
        ),
        (
            "--command 'pi --mode rpc'",
            "pi-rejects-wrapper-command-native-rpc",
        ),
        (
            "--exec 'node /opt/node_modules/@earendil-works/pi-coding-agent/bin/pi.js --rpc'",
            "pi-rejects-wrapper-exec-native-rpc",
        ),
        (
            "--runtimeCommand 'pi --mode rpc'",
            "pi-rejects-wrapper-runtime-command-camel-native-rpc",
        ),
        (
            "--runtimeCmd 'pi --mode rpc'",
            "pi-rejects-wrapper-runtime-cmd-camel-native-rpc",
        ),
        (
            "--runtime_cmd 'pi --mode rpc'",
            "pi-rejects-wrapper-runtime-cmd-snake-native-rpc",
        ),
        (
            "--runtime_command 'pi --mode rpc'",
            "pi-rejects-wrapper-runtime-command-snake-native-rpc",
        ),
        (
            "--agent-command 'pi --mode rpc'",
            "pi-rejects-wrapper-agent-command-native-rpc",
        ),
        (
            "--agentCmd 'pi --mode rpc'",
            "pi-rejects-wrapper-agent-cmd-camel-native-rpc",
        ),
        (
            "--spawnCommand 'pi --mode rpc'",
            "pi-rejects-wrapper-spawn-command-camel-native-rpc",
        ),
        (
            "--spawnCmd 'pi --mode rpc'",
            "pi-rejects-wrapper-spawn-cmd-camel-native-rpc",
        ),
        (
            "--spawn_command 'pi --mode rpc'",
            "pi-rejects-wrapper-spawn-command-snake-native-rpc",
        ),
    ],
)
def test_pi_production_kernel_rejects_sidecar_wrapper_native_pi_command_options(
    command_arg: str,
    model_id: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="native Pi RPC mode"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=(
                    "npx @opensquilla/pi-agent-core-bridge "
                    f"{command_arg}"
                ),
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 IO bridge package invoking "
                    "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id=model_id),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_bridge_package_name_as_upstream_provenance() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="upstream Pi runtime provenance"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command="python /opt/opensquilla_pi_bridge.py",
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 sidecar package "
                    "@opensquilla/pi-agent-core-bridge"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-bridge-only-provenance"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_accepts_shell_wrapped_sidecar_package_wrapper() -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient, build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    wrapper_agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_command=(
                "bash -lc 'exec npx @opensquilla/pi-agent-core-bridge "
                "--runtime @earendil-works/pi-coding-agent'"
            ),
            pi_agent_rpc_command_provenance=(
                "thin opensquilla.agent_core.v1 IO bridge package invoking "
                "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
            ),
        ),
        provider=object(),
        config=AgentConfig(model_id="pi-accepts-shell-wrapper-package-command"),
        tool_definitions=[],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )
    assert isinstance(wrapper_agent._rpc_client, PiJsonlCommandRpcClient)


@pytest.mark.parametrize(
    ("module_name", "class_name"),
    [
        ("pi.agent.runtime", "OpenSquillaBridgeClient"),
        ("pi.coding_agent.client", "OpenSquillaBridgeClient"),
        ("opensquilla_pi_bridge.client", "PiAgentRuntimeClient"),
    ],
)
def test_pi_production_kernel_rejects_native_pi_runtime_rpc_client_identity(
    module_name: str,
    class_name: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    def stream_prompt(self: object, message: str, **kwargs: Any):
        _ = self, message, kwargs
        raise AssertionError("production build should reject native Pi runtime client")

    native_client_type = type(
        class_name,
        (),
        {
            "__module__": module_name,
            "stream_prompt": stream_prompt,
        },
    )

    with pytest.raises(ValueError, match="native Pi RPC client"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_client=native_client_type(),
                pi_agent_rpc_client_provenance=(
                    "thin opensquilla.agent_core.v1 client for "
                    "github.com/earendil-works/pi @earendil-works/pi-agent-core"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-native-pi-runtime-client"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_accepts_env_wrapped_sidecar_package_wrapper() -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient, build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    wrapper_agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_command=(
                "env NODE_ENV=production npx @opensquilla/pi-agent-core-bridge "
                "--runtime @earendil-works/pi-coding-agent"
            ),
            pi_agent_rpc_command_provenance=(
                "thin opensquilla.agent_core.v1 IO bridge package invoking "
                "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
            ),
        ),
        provider=object(),
        config=AgentConfig(model_id="pi-accepts-env-wrapper-package-command"),
        tool_definitions=[],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )
    assert isinstance(wrapper_agent._rpc_client, PiJsonlCommandRpcClient)


def test_pi_production_kernel_accepts_corepack_wrapped_sidecar_package_wrapper() -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient, build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    wrapper_agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_command=(
                "corepack pnpm dlx @opensquilla/pi-agent-core-bridge "
                "--runtime @earendil-works/pi-coding-agent"
            ),
            pi_agent_rpc_command_provenance=(
                "thin opensquilla.agent_core.v1 IO bridge package invoking "
                "github.com/earendil-works/pi @earendil-works/pi-coding-agent"
            ),
        ),
        provider=object(),
        config=AgentConfig(model_id="pi-accepts-corepack-wrapper-package-command"),
        tool_definitions=[],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )
    assert isinstance(wrapper_agent._rpc_client, PiJsonlCommandRpcClient)


def test_pi_production_kernel_rejects_unprovenanced_custom_rpc_clients() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    def stream_prompt(self: object, message: str, **kwargs: Any):
        _ = self, message, kwargs
        raise AssertionError("production build should reject custom client")

    custom_rpc_client_type = type(
        "AcmeRpcClient",
        (),
        {"__module__": "acme.pi_bridge", "stream_prompt": stream_prompt},
    )

    with pytest.raises(ValueError, match="upstream Pi runtime provenance"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_client=custom_rpc_client_type(),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-unprovenanced-client"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_non_pi_earendil_rpc_client_identity() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    def stream_prompt(self: object, message: str, **kwargs: Any):
        _ = self, message, kwargs
        raise AssertionError("production build should reject non-Pi identity")

    non_pi_rpc_client_type = type(
        "AcmeRpcClient",
        (),
        {"__module__": "earendil.tools", "stream_prompt": stream_prompt},
    )

    with pytest.raises(ValueError, match="upstream Pi runtime provenance"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_client=non_pi_rpc_client_type(),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-broad-earendil-client"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_bridge_client_identity_as_upstream_runtime() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    def stream_prompt(self: object, message: str, **kwargs: Any):
        _ = self, message, kwargs
        raise AssertionError("production build should reject bridge-only client")

    bridge_client_type = type(
        "Client",
        (),
        {
            "__module__": "opensquilla.pi_agent_core_bridge",
            "stream_prompt": stream_prompt,
        },
    )

    with pytest.raises(ValueError, match="upstream Pi runtime provenance"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_client=bridge_client_type(),
                pi_agent_rpc_client_provenance=(
                    "thin opensquilla.agent_core.v1 sidecar package "
                    "@opensquilla/pi-agent-core-bridge"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-bridge-only-client"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_rpc_client_without_stream_prompt() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    client_type = type(
        "BridgeWithoutStreamPrompt",
        (),
        {"__module__": "acme.pi_bridge"},
    )

    with pytest.raises(ValueError, match="stream_prompt"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_client=client_type(),
                pi_agent_rpc_client_provenance=(
                    "thin opensquilla.agent_core.v1 client for "
                    "github.com/earendil-works/pi @earendil-works/pi-agent-core"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-client-without-stream"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_rpc_client_with_non_callable_stream_prompt() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    client_type = type(
        "BridgeWithNonCallableStreamPrompt",
        (),
        {"__module__": "acme.pi_bridge", "stream_prompt": "not-callable"},
    )

    with pytest.raises(ValueError, match="stream_prompt"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_client=client_type(),
                pi_agent_rpc_client_provenance=(
                    "thin opensquilla.agent_core.v1 client for "
                    "github.com/earendil-works/pi @earendil-works/pi-agent-core"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-non-callable-stream"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_native_upstream_rpc_client_identity() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    def stream_prompt(self: object, message: str, **kwargs: Any):
        _ = self, message, kwargs
        raise AssertionError("production build should reject native Pi client")

    native_client_type = type(
        "Client",
        (),
        {
            "__module__": "pi_agent_core.client",
            "stream_prompt": stream_prompt,
        },
    )

    with pytest.raises(ValueError, match="native Pi RPC client"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_client=native_client_type(),
                pi_agent_rpc_client_provenance=(
                    "thin opensquilla.agent_core.v1 client for "
                    "github.com/earendil-works/pi @earendil-works/pi-agent-core"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-native-upstream-client"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_rejects_rpc_client_provenance_declaring_pi_loop_rewrite() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    def stream_prompt(self: object, message: str, **kwargs: Any):
        _ = self, message, kwargs
        raise AssertionError("production build should reject loop-rewrite provenance")

    client_type = type(
        "AcmeRpcClient",
        (),
        {"__module__": "acme.pi_bridge", "stream_prompt": stream_prompt},
    )

    with pytest.raises(ValueError, match="Pi agent loop"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_client=client_type(),
                pi_agent_rpc_client_provenance=(
                    "thin opensquilla.agent_core.v1 client for "
                    "github.com/earendil-works/pi @earendil-works/pi-agent-core "
                    "with prepareNextTurn safe-point queue beforeToolCall "
                    "afterToolCall agent loop logic"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-client-provenance-loop-rewrite"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_production_kernel_accepts_provenanced_custom_rpc_clients() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    def stream_prompt(self: object, message: str, **kwargs: Any):
        _ = self, message, kwargs
        raise AssertionError("production build should not invoke client at construction")

    custom_rpc_client_type = type(
        "AcmeRpcClient",
        (),
        {"__module__": "acme.pi_bridge", "stream_prompt": stream_prompt},
    )
    client = custom_rpc_client_type()

    agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_client=client,
            pi_agent_rpc_client_provenance=(
                "thin opensquilla.agent_core.v1 client for "
                "github.com/earendil-works/pi @earendil-works/pi-agent-core"
            ),
        ),
        provider=object(),
        config=AgentConfig(model_id="pi-accepts-provenanced-client"),
        tool_definitions=[],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )

    assert agent._rpc_client is client


def test_pi_production_kernel_accepts_client_provenance_for_upstream_owned_loop() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    def stream_prompt(self: object, message: str, **kwargs: Any):
        _ = self, message, kwargs
        raise AssertionError("production build should not invoke client at construction")

    custom_rpc_client_type = type(
        "AcmeRpcClient",
        (),
        {"__module__": "acme.pi_bridge", "stream_prompt": stream_prompt},
    )
    client = custom_rpc_client_type()

    agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_client=client,
            pi_agent_rpc_client_provenance=(
                "thin opensquilla.agent_core.v1 client for "
                "github.com/earendil-works/pi @earendil-works/pi-agent-core; "
                "upstream Pi owns prepareNextTurn safe-point queue "
                "beforeToolCall afterToolCall; OpenSquilla client only "
                "translates IO and protocol frames"
            ),
        ),
        provider=object(),
        config=AgentConfig(model_id="pi-accepts-client-upstream-owned-loop"),
        tool_definitions=[],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )

    assert agent._rpc_client is client


@pytest.mark.parametrize(
    "client_type_name",
    [
        "FakePiRpcClient",
        "MockPiRpcClient",
        "DummyPiRpcClient",
        "PiStubSidecarClient",
        "FixturePiRpcClient",
        "TestPiRpcClient",
        "ExamplePiRpcClient",
        "SamplePiRpcClient",
        "DemoPiRpcClient",
    ],
)
def test_pi_production_kernel_rejects_test_fixture_rpc_clients(
    client_type_name: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    def stream_prompt(self: object, message: str, **kwargs: Any):
        _ = self, message, kwargs
        raise AssertionError("production build should reject fixture client")

    client_type = type(
        client_type_name,
        (),
        {"__module__": "acme.pi_bridge", "stream_prompt": stream_prompt},
    )

    with pytest.raises(ValueError, match="test-only Pi RPC client"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_client=client_type(),
                pi_agent_rpc_client_provenance=(
                    "thin opensquilla.agent_core.v1 bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-agent-core"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-test-fixture-client"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


@pytest.mark.parametrize(
    "provenance",
    [
        "fake/test fixture around opensquilla.agent_core.v1 and "
        "github.com/earendil-works/pi @earendil-works/pi-agent-core",
        "dummy wrapper around opensquilla.agent_core.v1 and "
        "github.com/earendil-works/pi @earendil-works/pi-agent-core",
        "stub wrapper around opensquilla.agent_core.v1 and "
        "github.com/earendil-works/pi @earendil-works/pi-agent-core",
        "example wrapper around opensquilla.agent_core.v1 and "
        "github.com/earendil-works/pi @earendil-works/pi-agent-core",
        "sample sidecar around opensquilla.agent_core.v1 and "
        "github.com/earendil-works/pi @earendil-works/pi-agent-core",
        "demo sidecar around opensquilla.agent_core.v1 and "
        "github.com/earendil-works/pi @earendil-works/pi-agent-core",
    ],
)
def test_pi_production_kernel_rejects_fake_or_test_rpc_client_provenance(
    provenance: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    def stream_prompt(self: object, message: str, **kwargs: Any):
        _ = self, message, kwargs
        raise AssertionError("production build should reject fake client provenance")

    custom_rpc_client_type = type(
        "AcmeRpcClient",
        (),
        {"__module__": "acme.pi_bridge", "stream_prompt": stream_prompt},
    )

    with pytest.raises(ValueError, match="test-only Pi RPC client provenance"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_client=custom_rpc_client_type(),
                pi_agent_rpc_client_provenance=provenance,
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-fake-provenance-client"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


@pytest.mark.parametrize(
    "provenance",
    [
        "contract-test fixture around opensquilla.agent_core.v1 and "
        "github.com/earendil-works/pi @earendil-works/pi-agent-core",
        "fixture wrapper around opensquilla.agent_core.v1 and "
        "github.com/earendil-works/pi @earendil-works/pi-agent-core",
        "dummy wrapper around opensquilla.agent_core.v1 and "
        "github.com/earendil-works/pi @earendil-works/pi-agent-core",
        "stub wrapper around opensquilla.agent_core.v1 and "
        "github.com/earendil-works/pi @earendil-works/pi-agent-core",
        "example wrapper around opensquilla.agent_core.v1 and "
        "github.com/earendil-works/pi @earendil-works/pi-agent-core",
        "sample sidecar around opensquilla.agent_core.v1 and "
        "github.com/earendil-works/pi @earendil-works/pi-agent-core",
        "demo sidecar around opensquilla.agent_core.v1 and "
        "github.com/earendil-works/pi @earendil-works/pi-agent-core",
    ],
)
def test_pi_production_kernel_rejects_fake_or_test_rpc_command_provenance(
    provenance: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="test-only Pi RPC command provenance"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command="python /opt/custom_pi_bridge.py",
                pi_agent_rpc_command_provenance=provenance,
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-fake-provenance-command"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


@pytest.mark.parametrize(
    "command",
    [
        "python /opt/fake-pi-rpc.py",
        "python /opt/fake_sidecar.py",
        "python /opt/fake-sidecar.py",
        "python /opt/mock_pi_rpc.py",
        "python /opt/contract_test_pi_rpc.py",
        "python /opt/pi_fixture_sidecar.py",
        "python /opt/test_fixture_pi_rpc.py",
        "python /opt/dummy_pi_rpc.py",
        "python /opt/pi_stub_sidecar.py",
        "python /opt/example_pi_rpc.py",
        "python /opt/sample_sidecar.py",
        "python /opt/demo_pi_sidecar.py",
    ],
)
def test_pi_production_kernel_rejects_mock_or_contract_fixture_rpc_commands(
    command: str,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    with pytest.raises(ValueError, match="test-only Pi RPC command"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=command,
                pi_agent_rpc_command_provenance=(
                    "thin opensquilla.agent_core.v1 bridge around "
                    "github.com/earendil-works/pi @earendil-works/pi-agent-core"
                ),
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-rejects-mock-fixture-command"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_test_fixture_rpc_command_opt_in_requires_pytest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    with pytest.raises(ValueError, match="requires pytest"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=f"{sys.executable} /tmp/fake_pi_rpc.py",
                allow_test_pi_rpc_command=True,
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-command-opt-in-requires-pytest"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("pi --mode rpc", "native Pi RPC mode"),
        (
            "npx @earendil-works/pi-coding-agent --mode rpc",
            "native Pi RPC mode",
        ),
        (
            "node /opt/@earendil-works/pi-coding-agent/dist/cli.js",
            "native Pi CLI/package",
        ),
    ],
)
def test_pi_test_fixture_rpc_command_opt_in_does_not_allow_native_pi_runtime(
    command: str,
    expected: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test")

    with pytest.raises(ValueError, match=expected):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_command=command,
                allow_test_pi_rpc_command=True,
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-opt-in-native-still-rejected"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_test_fixture_rpc_client_opt_in_requires_pytest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    class FakePiRpcClient:
        def stream_prompt(self, message: str, **kwargs: Any):
            _ = message, kwargs
            raise AssertionError("production build should reject fake client")

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    with pytest.raises(ValueError, match="requires pytest"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_client=FakePiRpcClient(),
                allow_test_pi_rpc_client=True,
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-client-opt-in-requires-pytest"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_test_fixture_rpc_client_opt_in_still_requires_stream_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test")

    with pytest.raises(ValueError, match="stream_prompt"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_client=object(),
                allow_test_pi_rpc_client=True,
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-client-opt-in-shape-required"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_pi_test_fixture_rpc_client_opt_in_does_not_allow_native_pi_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    def stream_prompt(self: object, message: str, **kwargs: Any):
        _ = self, message, kwargs
        raise AssertionError("test opt-in should reject native Pi client")

    native_client_type = type(
        "Client",
        (),
        {
            "__module__": "pi_agent_core.client",
            "stream_prompt": stream_prompt,
        },
    )

    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test")

    with pytest.raises(ValueError, match="native Pi RPC client"):
        build_agent_for_kernel(
            runtime_config=SimpleNamespace(
                agent_kernel="pi",
                pi_agent_rpc_client=native_client_type(),
                allow_test_pi_rpc_client=True,
            ),
            provider=object(),
            config=AgentConfig(model_id="pi-client-opt-in-native-still-rejected"),
            tool_definitions=[],
            tool_handler=None,
            usage_tracker=None,
            session_key="agent:main:test",
            turn_call_logger=None,
            memory_sync_manager=None,
            session_flush_service=None,
            tool_registry=None,
            tool_context=None,
        )


def test_agent_core_config_parses_string_booleans_for_strict_host_flags() -> None:
    from opensquilla.engine.agent_core import AgentCoreConfig

    config = AgentCoreConfig.from_runtime_config(
        SimpleNamespace(
            strict_host_provider="false",
            strict_host_tools="0",
            agent_core=SimpleNamespace(
                kernel="pi",
                strict_host_sessions="off",
                strict_host_orchestration="no",
                strict_host_finalizer="true",
            ),
        )
    )

    assert config.strict_host_provider is False
    assert config.strict_host_tools is False
    assert config.strict_host_sessions is False
    assert config.strict_host_orchestration is False
    assert config.strict_host_finalizer is True


def test_kernel_turn_snapshot_names_host_owned_turn_inputs() -> None:
    from opensquilla.engine.agent_core import KernelTurnSnapshot

    snapshot = KernelTurnSnapshot(
        session_key="agent:main:test",
        agent_id="main",
        turn_id="turn-1",
        turn_input="hello",
        system_prompt="system",
        request_context_prompt="ctx",
        model_id="gpt-test",
        tool_definitions=[{"name": "read"}],
        extra_messages=[],
        semantic_message="semantic hello",
        metadata={"route": "default"},
    )

    assert snapshot.session_key == "agent:main:test"
    assert snapshot.session_id == "agent:main:test"
    assert snapshot.tool_definitions == [{"name": "read"}]
    assert snapshot.metadata == {"route": "default"}


@pytest.mark.parametrize("session_key", ["", "   "])
def test_kernel_turn_snapshot_rejects_blank_session_key(session_key: str) -> None:
    from opensquilla.engine.agent_core import KernelTurnSnapshot

    with pytest.raises(RuntimeError, match="KernelTurnSnapshot session_key must be non-empty"):
        KernelTurnSnapshot(
            session_key=session_key,
            agent_id="main",
            turn_id="turn-1",
            turn_input="hello",
            system_prompt="system",
            request_context_prompt="ctx",
            model_id="gpt-test",
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("agent_id", "", "KernelTurnSnapshot agent_id must be non-empty"),
        ("agent_id", "   ", "KernelTurnSnapshot agent_id must be non-empty"),
        ("turn_id", "", "KernelTurnSnapshot turn_id must be non-empty"),
        ("turn_id", "   ", "KernelTurnSnapshot turn_id must be non-empty"),
        ("session_id", "", "KernelTurnSnapshot session_id must be non-empty"),
        ("session_id", "   ", "KernelTurnSnapshot session_id must be non-empty"),
        ("agent_id", {"agent": "main"}, "KernelTurnSnapshot agent_id must be a string"),
        ("turn_id", ["turn-1"], "KernelTurnSnapshot turn_id must be a string"),
        ("session_id", {"session": "main"}, "KernelTurnSnapshot session_id must be a string"),
    ],
)
def test_kernel_turn_snapshot_rejects_invalid_identity_fields(
    field: str,
    value: object,
    message: str,
) -> None:
    from opensquilla.engine.agent_core import KernelTurnSnapshot

    kwargs: dict[str, object] = {
        "session_key": "agent:main:test",
        "agent_id": "main",
        "turn_id": "turn-1",
        "turn_input": "hello",
        "system_prompt": "system",
        "request_context_prompt": "ctx",
        "model_id": "gpt-test",
    }
    kwargs[field] = value

    with pytest.raises(RuntimeError, match=message):
        KernelTurnSnapshot(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("turn_input", {"text": "hello"}, "KernelTurnSnapshot turn_input must be a string"),
        ("system_prompt", ["system"], "KernelTurnSnapshot system_prompt must be a string"),
        (
            "request_context_prompt",
            {"ctx": "request"},
            "KernelTurnSnapshot request_context_prompt must be a string",
        ),
        ("model_id", 123, "KernelTurnSnapshot model_id must be a string"),
    ],
)
def test_kernel_turn_snapshot_rejects_non_string_prompt_fields(
    field: str,
    value: object,
    message: str,
) -> None:
    from opensquilla.engine.agent_core import KernelTurnSnapshot

    kwargs: dict[str, object] = {
        "session_key": "agent:main:test",
        "agent_id": "main",
        "turn_id": "turn-1",
        "turn_input": "hello",
        "system_prompt": "system",
        "request_context_prompt": "ctx",
        "model_id": "gpt-test",
    }
    kwargs[field] = value

    with pytest.raises(RuntimeError, match=message):
        KernelTurnSnapshot(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "tool_definitions",
            {"name": "read"},
            "KernelTurnSnapshot tool_definitions must be a list",
        ),
        (
            "extra_messages",
            {"role": "user"},
            "KernelTurnSnapshot extra_messages must be a list or None",
        ),
        (
            "semantic_message",
            {"text": "semantic"},
            "KernelTurnSnapshot semantic_message must be a string or None",
        ),
        ("metadata", ["route"], "KernelTurnSnapshot metadata must be an object"),
    ],
)
def test_kernel_turn_snapshot_rejects_invalid_collection_fields(
    field: str,
    value: object,
    message: str,
) -> None:
    from opensquilla.engine.agent_core import KernelTurnSnapshot

    kwargs: dict[str, object] = {
        "session_key": "agent:main:test",
        "agent_id": "main",
        "turn_id": "turn-1",
        "turn_input": "hello",
        "system_prompt": "system",
        "request_context_prompt": "ctx",
        "model_id": "gpt-test",
    }
    kwargs[field] = value

    with pytest.raises(RuntimeError, match=message):
        KernelTurnSnapshot(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tool_definitions", [{"name": "read", "weight": float("nan")}]),
        ("extra_messages", [{"role": "user", "content": float("inf")}]),
        ("metadata", {"route": "default", 1: "numeric key"}),
    ],
)
def test_kernel_turn_snapshot_rejects_non_json_safe_sidecar_visible_fields(
    field: str,
    value: object,
) -> None:
    from opensquilla.engine.agent_core import KernelTurnSnapshot

    kwargs: dict[str, object] = {
        "session_key": "agent:main:test",
        "agent_id": "main",
        "turn_id": "turn-1",
        "turn_input": "hello",
        "system_prompt": "system",
        "request_context_prompt": "ctx",
        "model_id": "gpt-test",
    }
    kwargs[field] = value

    with pytest.raises(RuntimeError, match="Pi sidecar JSON"):
        KernelTurnSnapshot(**kwargs)  # type: ignore[arg-type]


def test_kernel_turn_snapshot_rejects_bad_cache_hit_rate_metadata() -> None:
    from opensquilla.engine.agent_core import KernelTurnSnapshot

    with pytest.raises(
        RuntimeError,
        match="KernelTurnSnapshot metadata cache_hit_rate must be a probability",
    ):
        KernelTurnSnapshot(
            session_key="agent:main:test",
            agent_id="main",
            turn_id="turn-1",
            turn_input="hello",
            system_prompt="system",
            request_context_prompt="ctx",
            model_id="gpt-test",
            metadata={"cache_hit_rate": 1.5},
        )


def test_kernel_turn_snapshot_owns_sidecar_visible_collections() -> None:
    from opensquilla.engine.agent_core import KernelTurnSnapshot

    tool_definitions = [{"name": "read", "input_schema": {"properties": {}}}]
    extra_messages = [{"role": "user", "content": {"text": "extra"}}]
    metadata = {"route": {"kernel": "pi"}}

    snapshot = KernelTurnSnapshot(
        session_key="agent:main:test",
        agent_id="main",
        turn_id="turn-1",
        turn_input="hello",
        system_prompt="system",
        request_context_prompt="ctx",
        model_id="gpt-test",
        tool_definitions=tool_definitions,
        extra_messages=extra_messages,
        metadata=metadata,
    )

    tool_definitions[0]["input_schema"]["properties"]["mutated"] = {
        "type": "string"
    }
    extra_messages[0]["content"]["text"] = "mutated extra"
    metadata["route"]["kernel"] = "mutated"

    assert snapshot.tool_definitions == [
        {"name": "read", "input_schema": {"properties": {}}}
    ]
    assert snapshot.extra_messages == [{"role": "user", "content": {"text": "extra"}}]
    assert snapshot.metadata == {"route": {"kernel": "pi"}}


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_accepts_only_protocol_text_delta_events() -> None:
    from opensquilla.engine.agent_core import AGENT_CORE_PROTOCOL_VERSION, PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            assert message == "hello"
            assert kwargs["extra_messages"] == []
            assert kwargs["semantic_message"] == "semantic hello"
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "hi"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(),
        session_key="agent:main:test",
    )

    events = [
        event
        async for event in agent.run_turn(
            "hello",
            extra_messages=[],
            semantic_message="semantic hello",
        )
    ]

    assert events == [
        TextDeltaEvent(text="hi"),
        DoneEvent(text="hi", model="", cost_source="unavailable"),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_host_finalizes_text_only_stream() -> None:
    from opensquilla.engine.agent_core import AGENT_CORE_PROTOCOL_VERSION, PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "hello "},
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "world"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-test"),
        session_key="agent:main:test",
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="hello "),
        TextDeltaEvent(text="world"),
        DoneEvent(text="hello world", model="pi-test", cost_source="unavailable"),
    ]


@pytest.mark.asyncio
async def test_pi_finalizer_rejects_non_string_text_before_done_event() -> None:
    from opensquilla.engine.agent_core import OpenSquillaFinalizerHostPort

    finalizer = OpenSquillaFinalizerHostPort(config=SimpleNamespace(model_id="pi-test"))

    with pytest.raises(RuntimeError, match="turn.finalize text must be a string"):
        await finalizer.handle_intent(
            intent_type="turn.finalize",
            payload={"text": {"nested": "object"}},
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_finalizer_rejects_non_string_model_before_done_event() -> None:
    from opensquilla.engine.agent_core import OpenSquillaFinalizerHostPort

    finalizer = OpenSquillaFinalizerHostPort(config=SimpleNamespace())

    with pytest.raises(RuntimeError, match="turn.finalize model must be a string"):
        await finalizer.handle_intent(
            intent_type="turn.finalize",
            payload={"text": "ok", "model": {"nested": "object"}},
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_finalizer_preserves_host_runtime_context_metadata() -> None:
    from opensquilla.engine.agent_core import OpenSquillaFinalizerHostPort

    finalizer = OpenSquillaFinalizerHostPort(config=SimpleNamespace(model_id="pi-test"))

    events = await finalizer.handle_intent(
        intent_type="turn.finalize",
        payload={
            "text": "ok",
            "runtime_context_hash": "abc123",
            "runtime_context_chars": 42,
        },
        session_key="agent:main:test",
    )

    assert events == [
        DoneEvent(
            text="ok",
            model="pi-test",
            cost_source="unavailable",
            runtime_context_hash="abc123",
            runtime_context_chars=42,
        )
    ]


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("text", "turn.finalize text must be a string"),
        ("model", "turn.finalize model must be a string"),
    ],
)
@pytest.mark.asyncio
async def test_pi_finalizer_rejects_explicit_null_payload_fields_before_done_event(
    field: str,
    message: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaFinalizerHostPort

    finalizer = OpenSquillaFinalizerHostPort(config=SimpleNamespace(model_id="pi-test"))
    payload = {"text": "ok", "model": "pi-sidecar", field: None}

    with pytest.raises(RuntimeError, match=message):
        await finalizer.handle_intent(
            intent_type="turn.finalize",
            payload=payload,
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("cache_field", ["cached_tokens", "cache_write_tokens"])
async def test_pi_sidecar_kernel_rejects_host_done_cache_tokens_above_input(
    cache_field: str,
) -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "bad cache counters"},
            }

    class BadDoneFinalizer:
        async def handle_intent(self, *, intent_type: str, payload: dict, session_key: str):
            _ = intent_type, payload, session_key
            done = DoneEvent(text="final", model="host-final", input_tokens=1)
            setattr(done, cache_field, 2)
            return [done]

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-side"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(finalizer=BadDoneFinalizer()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="bad cache counters"),
        ErrorEvent(
            message=(
                "KernelHostPorts returned malformed DoneEvent: "
                f"{cache_field} must be <= input_tokens"
            ),
            code="pi_sidecar_error",
        ),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("cache_field", ["cache_read_tokens", "cache_write_tokens"])
async def test_pi_sidecar_kernel_rejects_host_done_session_cache_tokens_above_input(
    cache_field: str,
) -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )
    from opensquilla.engine.usage import SessionTotalsSnapshot

    session_totals = SessionTotalsSnapshot(input_tokens=1)
    setattr(session_totals, cache_field, 2)

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "bad session cache counters"},
            }

    class BadDoneFinalizer:
        async def handle_intent(self, *, intent_type: str, payload: dict, session_key: str):
            _ = intent_type, payload, session_key
            return [
                DoneEvent(
                    text="final",
                    model="host-final",
                    session_totals=session_totals,
                )
            ]

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-side"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(finalizer=BadDoneFinalizer()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="bad session cache counters"),
        ErrorEvent(
            message=(
                "KernelHostPorts returned malformed DoneEvent: "
                f"session_totals.{cache_field} must be <= session_totals.input_tokens"
            ),
            code="pi_sidecar_error",
        ),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "bad_value", "match"),
    [
        ("input_tokens", "3", "finalizer usage input_tokens must be an integer"),
        (
            "input_tokens",
            -1,
            "finalizer usage input_tokens must be a non-negative integer",
        ),
        (
            "cache_write_tokens",
            -1,
            "finalizer usage cache_write_tokens must be a non-negative integer",
        ),
        ("provider_done_count", "1", "finalizer usage provider_done_count must be an integer"),
        (
            "provider_done_count",
            -1,
            "finalizer usage provider_done_count must be a non-negative integer",
        ),
        ("billed_cost", "0.01", "finalizer usage billed_cost must be a number"),
        ("cost_source", {"bad": "source"}, "finalizer usage cost_source must be a string"),
        ("model", {"bad": "model"}, "finalizer usage model must be a string"),
        (
            "reasoning_content",
            {"bad": "reasoning"},
            "finalizer usage reasoning_content must be a string or None",
        ),
    ],
)
async def test_pi_finalizer_rejects_invalid_provider_usage_summary_fields(
    field: str,
    bad_value: Any,
    match: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaFinalizerHostPort

    class FakeProviderUsage:
        def drain(self) -> dict[str, Any]:
            usage: dict[str, Any] = {
                "input_tokens": 3,
                "output_tokens": 2,
                "reasoning_tokens": 1,
                "cached_tokens": 1,
                "cache_write_tokens": 1,
                "billed_cost": 0.01,
                "provider_done_count": 1,
                "cost_source": "provider_billed",
                "model": "provider-model",
                "reasoning_content": "reasoning",
            }
            usage[field] = bad_value
            return usage

        def reset(self) -> None:
            pass

    finalizer = OpenSquillaFinalizerHostPort(
        config=SimpleNamespace(model_id="config-model"),
        provider_usage=FakeProviderUsage(),
    )

    with pytest.raises(RuntimeError, match=match):
        await finalizer.handle_intent(
            intent_type="turn.finalize",
            payload={"text": "ok"},
            session_key="agent:main:test",
        )


@pytest.mark.parametrize("cache_field", ["cached_tokens", "cache_write_tokens"])
@pytest.mark.asyncio
async def test_pi_finalizer_rejects_cache_tokens_above_input_before_done_event(
    cache_field: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaFinalizerHostPort

    class FakeProviderUsage:
        def drain(self) -> dict[str, Any]:
            usage: dict[str, Any] = {
                "input_tokens": 2,
                "output_tokens": 1,
                "reasoning_tokens": 0,
                "cached_tokens": 0,
                "cache_write_tokens": 0,
                "billed_cost": 0.01,
                "provider_done_count": 1,
                "cost_source": "provider_billed",
                "model": "provider-model",
                "reasoning_content": None,
            }
            usage[cache_field] = 3
            return usage

        def reset(self) -> None:
            pass

    finalizer = OpenSquillaFinalizerHostPort(
        config=SimpleNamespace(model_id="config-model"),
        provider_usage=FakeProviderUsage(),
    )

    with pytest.raises(
        RuntimeError,
        match=f"finalizer usage {cache_field} must be <= input_tokens",
    ):
        await finalizer.handle_intent(
            intent_type="turn.finalize",
            payload={"text": "ok"},
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "match"),
    [
        ("input_tokens", "finalizer usage input_tokens must be an integer"),
        ("billed_cost", "finalizer usage billed_cost must be a number"),
        ("cost_source", "finalizer usage cost_source must be a string"),
        ("model", "finalizer usage model must be a string"),
    ],
)
async def test_pi_finalizer_rejects_null_provider_usage_summary_fields_before_defaults(
    field: str,
    match: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaFinalizerHostPort

    class FakeProviderUsage:
        def drain(self) -> dict[str, Any]:
            usage: dict[str, Any] = {
                "input_tokens": 3,
                "output_tokens": 2,
                "reasoning_tokens": 1,
                "cached_tokens": 1,
                "cache_write_tokens": 1,
                "billed_cost": 0.01,
                "provider_done_count": 1,
                "cost_source": "provider_billed",
                "model": "provider-model",
                "reasoning_content": None,
            }
            usage[field] = None
            return usage

        def reset(self) -> None:
            pass

    finalizer = OpenSquillaFinalizerHostPort(
        config=SimpleNamespace(model_id="config-model"),
        provider_usage=FakeProviderUsage(),
    )

    with pytest.raises(RuntimeError, match=match):
        await finalizer.handle_intent(
            intent_type="turn.finalize",
            payload={"text": "ok"},
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_finalizer_rejects_non_object_provider_usage_summary_before_done_event() -> None:
    from opensquilla.engine.agent_core import OpenSquillaFinalizerHostPort

    class FakeProviderUsage:
        def drain(self) -> list[str]:
            return ["not", "a", "usage", "object"]

        def reset(self) -> None:
            pass

    finalizer = OpenSquillaFinalizerHostPort(
        config=SimpleNamespace(model_id="config-model"),
        provider_usage=FakeProviderUsage(),
    )

    with pytest.raises(RuntimeError, match="finalizer usage summary must be an object"):
        await finalizer.handle_intent(
            intent_type="turn.finalize",
            payload={"text": "ok"},
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_finalizer_rejects_non_finite_usage_cost_before_done_event() -> None:
    from opensquilla.engine.agent_core import OpenSquillaFinalizerHostPort

    class FakeProviderUsage:
        def drain(self) -> dict[str, Any]:
            return {"billed_cost": float("nan")}

        def reset(self) -> None:
            pass

    finalizer = OpenSquillaFinalizerHostPort(
        config=SimpleNamespace(model_id="config-model"),
        provider_usage=FakeProviderUsage(),
    )

    with pytest.raises(RuntimeError, match="finalizer usage billed_cost must be finite"):
        await finalizer.handle_intent(
            intent_type="turn.finalize",
            payload={"text": "ok"},
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_finalizer_rejects_negative_usage_cost_before_done_event() -> None:
    from opensquilla.engine.agent_core import OpenSquillaFinalizerHostPort

    class FakeProviderUsage:
        def drain(self) -> dict[str, Any]:
            return {"billed_cost": -0.01}

        def reset(self) -> None:
            pass

    finalizer = OpenSquillaFinalizerHostPort(
        config=SimpleNamespace(model_id="config-model"),
        provider_usage=FakeProviderUsage(),
    )

    with pytest.raises(
        RuntimeError,
        match="finalizer usage billed_cost must be a non-negative number",
    ):
        await finalizer.handle_intent(
            intent_type="turn.finalize",
            payload={"text": "ok"},
            session_key="agent:main:test",
        )


@pytest.mark.parametrize(
    "strict_flag",
    [
        "strict_host_provider",
        "strict_host_tools",
        "strict_host_sessions",
        "strict_host_orchestration",
        "strict_host_finalizer",
    ],
)
def test_pi_sidecar_kernel_rejects_disabled_strict_host_flags(
    strict_flag: str,
) -> None:
    from opensquilla.engine.agent_core import AgentCoreConfig, PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            if False:
                yield {}

    agent_core_config = AgentCoreConfig(kernel="pi", **{strict_flag: False})

    with pytest.raises(ValueError, match="requires strict host-owned ports"):
        PiSidecarKernelRuntime(
            rpc_client=FakePiRpcClient(),
            config=SimpleNamespace(model_id="pi-strict"),
            session_key="agent:main:test",
            agent_core_config=agent_core_config,
        )


@pytest.mark.parametrize(
    "strict_flag",
    [
        "strict_host_provider",
        "strict_host_tools",
        "strict_host_sessions",
        "strict_host_orchestration",
        "strict_host_finalizer",
    ],
)
def test_pi_sidecar_kernel_rejects_direct_string_disabled_strict_host_flags(
    strict_flag: str,
) -> None:
    from opensquilla.engine.agent_core import AgentCoreConfig, PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            if False:
                yield {}

    agent_core_config = AgentCoreConfig(kernel="pi", **{strict_flag: "false"})

    with pytest.raises(ValueError, match="requires strict host-owned ports"):
        PiSidecarKernelRuntime(
            rpc_client=FakePiRpcClient(),
            config=SimpleNamespace(model_id="pi-strict-string"),
            session_key="agent:main:test",
            agent_core_config=agent_core_config,
        )


def test_pi_sidecar_kernel_rejects_direct_non_boolean_strict_host_flags() -> None:
    from opensquilla.engine.agent_core import AgentCoreConfig, PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            if False:
                yield {}

    agent_core_config = AgentCoreConfig(kernel="pi", strict_host_provider=object())

    with pytest.raises(ValueError, match="strict_host_provider must be a boolean"):
        PiSidecarKernelRuntime(
            rpc_client=FakePiRpcClient(),
            config=SimpleNamespace(model_id="pi-strict-object"),
            session_key="agent:main:test",
            agent_core_config=agent_core_config,
        )


@pytest.mark.parametrize(
    ("kernel", "message"),
    [
        ("opensquilla", "Pi sidecar kernel requires pi agent kernel"),
        (object(), "agent kernel must be a string"),
    ],
)
def test_pi_sidecar_kernel_rejects_direct_non_pi_kernel_config(
    kernel: object,
    message: str,
) -> None:
    from opensquilla.engine.agent_core import AgentCoreConfig, PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            if False:
                yield {}

    with pytest.raises(ValueError, match=message):
        PiSidecarKernelRuntime(
            rpc_client=FakePiRpcClient(),
            config=SimpleNamespace(model_id="pi-kernel-boundary"),
            session_key="agent:main:test",
            agent_core_config=AgentCoreConfig(kernel=kernel),
        )


@pytest.mark.parametrize(
    "rpc_client",
    [
        object(),
        SimpleNamespace(stream_prompt="not-callable"),
    ],
)
def test_pi_sidecar_kernel_rejects_direct_rpc_client_without_callable_stream_prompt(
    rpc_client: object,
) -> None:
    from opensquilla.engine.agent_core import PiSidecarKernelRuntime

    with pytest.raises(
        ValueError,
        match="Pi RPC client must provide callable stream_prompt",
    ):
        PiSidecarKernelRuntime(
            rpc_client=rpc_client,
            config=SimpleNamespace(model_id="pi-rpc-client-shape"),
            session_key="agent:main:test",
        )


def test_pi_sidecar_kernel_rejects_unsupported_protocol_version() -> None:
    from opensquilla.engine.agent_core import AgentCoreConfig, PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            if False:
                yield {}

    with pytest.raises(ValueError, match="Unsupported Pi sidecar protocol"):
        PiSidecarKernelRuntime(
            rpc_client=FakePiRpcClient(),
            config=SimpleNamespace(model_id="pi-protocol"),
            session_key="agent:main:test",
            agent_core_config=AgentCoreConfig(
                kernel="pi",
                protocol_version="opensquilla.agent_core.v2",
            ),
        )


def test_pi_sidecar_kernel_rejects_direct_non_string_protocol_version() -> None:
    from opensquilla.engine.agent_core import AgentCoreConfig, PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            if False:
                yield {}

    with pytest.raises(ValueError, match="agent_core_protocol_version must be a string"):
        PiSidecarKernelRuntime(
            rpc_client=FakePiRpcClient(),
            config=SimpleNamespace(model_id="pi-protocol-object"),
            session_key="agent:main:test",
            agent_core_config=AgentCoreConfig(
                kernel="pi",
                protocol_version=object(),
            ),
        )


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_uses_host_finalizer_port_for_terminal_success() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    calls: list[dict[str, object]] = []

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "host finalize me"},
            }

    class FakeFinalizer:
        async def handle_intent(self, *, intent_type: str, payload: dict, session_key: str):
            calls.append(
                {
                    "intent_type": intent_type,
                    "payload": payload,
                    "session_key": session_key,
                }
            )
            return [DoneEvent(text=f"final:{payload['text']}", model="host-final")]

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-side"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(finalizer=FakeFinalizer()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="host finalize me"),
        DoneEvent(text="final:host finalize me", model="host-final"),
    ]
    assert calls == [
        {
            "intent_type": "turn.finalize",
            "payload": {"text": "host finalize me", "model": "pi-side"},
            "session_key": "agent:main:test",
        }
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_accepts_sync_iterable_host_port_events() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "iterable"},
            }

    class IterableFinalizer:
        async def handle_intent(self, *, intent_type: str, payload: dict, session_key: str):
            def events():
                yield DoneEvent(text=f"final:{payload['text']}", model="host-final")

            return events()

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-side"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(finalizer=IterableFinalizer()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="iterable"),
        DoneEvent(text="final:iterable", model="host-final"),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_non_agent_event_host_port_output() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "bad host output"},
            }

    class BadFinalizer:
        async def handle_intent(self, *, intent_type: str, payload: dict, session_key: str):
            return [{"kind": "done", "text": payload["text"]}]

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-side"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(finalizer=BadFinalizer()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="bad host output"),
        ErrorEvent(
            message="KernelHostPorts returned non-AgentEvent: dict",
            code="pi_sidecar_error",
        ),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_malformed_host_port_done_event_fields() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "bad done"},
            }

    class BadDoneFinalizer:
        async def handle_intent(self, *, intent_type: str, payload: dict, session_key: str):
            _ = intent_type, payload, session_key
            return [DoneEvent(text={"bad": "text"}, model="host-final")]

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-side"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(finalizer=BadDoneFinalizer()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="bad done"),
        ErrorEvent(
            message="KernelHostPorts returned malformed DoneEvent: text must be a string",
            code="pi_sidecar_error",
        ),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_non_finite_host_port_done_event_numbers() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "bad done cost"},
            }

    class BadDoneFinalizer:
        async def handle_intent(self, *, intent_type: str, payload: dict, session_key: str):
            _ = intent_type, payload, session_key
            return [
                DoneEvent(
                    text="bad done cost",
                    model="host-final",
                    billed_cost=float("nan"),
                )
            ]

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-side"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(finalizer=BadDoneFinalizer()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="bad done cost"),
        ErrorEvent(
            message="KernelHostPorts returned malformed DoneEvent: billed_cost must be finite",
            code="pi_sidecar_error",
        ),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_negative_host_port_heartbeat_timing() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "bad heartbeat"},
            }

    class BadHeartbeatFinalizer:
        async def handle_intent(self, *, intent_type: str, payload: dict, session_key: str):
            _ = intent_type, payload, session_key
            return [
                RunHeartbeatEvent(
                    phase="finalizer",
                    message="invalid timing",
                    elapsed_ms=-1,
                ),
                DoneEvent(text="bad heartbeat", model="host-final"),
            ]

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-side"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(finalizer=BadHeartbeatFinalizer()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="bad heartbeat"),
        ErrorEvent(
            message=(
                "KernelHostPorts returned malformed RunHeartbeatEvent: "
                "elapsed_ms must be a non-negative integer"
            ),
            code="pi_sidecar_error",
        ),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_malformed_host_port_event_kind() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "bad kind"},
            }

    class BadDoneFinalizer:
        async def handle_intent(self, *, intent_type: str, payload: dict, session_key: str):
            _ = intent_type, payload, session_key
            done = DoneEvent(text="final", model="host-final")
            setattr(done, "kind", {"bad": "kind"})
            return [done]

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-side"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(finalizer=BadDoneFinalizer()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="bad kind"),
        ErrorEvent(
            message="KernelHostPorts returned malformed DoneEvent: kind must be 'done'",
            code="pi_sidecar_error",
        ),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_malformed_host_port_state_change_fields() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "bad state"},
            }

    class BadStateFinalizer:
        async def handle_intent(self, *, intent_type: str, payload: dict, session_key: str):
            _ = intent_type, payload, session_key
            return [
                StateChangeEvent(from_state={"bad": "state"}),
                DoneEvent(text="final", model="host-final"),
            ]

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-side"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(finalizer=BadStateFinalizer()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="bad state"),
        ErrorEvent(
            message=(
                "KernelHostPorts returned malformed StateChangeEvent: "
                "from_state must be an AgentState"
            ),
            code="pi_sidecar_error",
        ),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_negative_host_port_artifact_size() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "bad artifact"},
            }

    class BadArtifactFinalizer:
        async def handle_intent(self, *, intent_type: str, payload: dict, session_key: str):
            _ = intent_type, payload, session_key
            return [
                ArtifactEvent(
                    id="artifact-1",
                    sha256="abc123",
                    name="bad.txt",
                    mime="text/plain",
                    size=-1,
                    session_id="main",
                    session_key="agent:main:test",
                    source="host-port",
                    created_at="2026-06-03T00:00:00Z",
                    download_url="/artifacts/bad.txt",
                ),
                DoneEvent(text="bad artifact", model="host-final"),
            ]

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-side"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(finalizer=BadArtifactFinalizer()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="bad artifact"),
        ErrorEvent(
            message=(
                "KernelHostPorts returned malformed ArtifactEvent: "
                "size must be a non-negative integer"
            ),
            code="pi_sidecar_error",
        ),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_negative_host_port_router_replay_depth() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "bad router replay"},
            }

    class BadRouterReplayFinalizer:
        async def handle_intent(self, *, intent_type: str, payload: dict, session_key: str):
            _ = intent_type, payload, session_key
            return [
                RouterControlReplayEvent(
                    action="retry",
                    target_tier="standard",
                    target_model="model-a",
                    target_provider="openrouter",
                    target_id="candidate-1",
                    replay_depth=-1,
                ),
                DoneEvent(text="bad router replay", model="host-final"),
            ]

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-side"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(finalizer=BadRouterReplayFinalizer()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="bad router replay"),
        ErrorEvent(
            message=(
                "KernelHostPorts returned malformed RouterControlReplayEvent: "
                "replay_depth must be a non-negative integer"
            ),
            code="pi_sidecar_error",
        ),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_out_of_range_host_router_probs() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "bad router probs"},
            }

    class BadRouterDecisionFinalizer:
        async def handle_intent(self, *, intent_type: str, payload: dict, session_key: str):
            _ = intent_type, payload, session_key
            return [
                RouterDecisionEvent(
                    tier="t1",
                    tier_index=1,
                    model="model-a",
                    probs=[-0.1, 0.5, 1.1],
                ),
                DoneEvent(text="bad router probs", model="host-final"),
            ]

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-side"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(finalizer=BadRouterDecisionFinalizer()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="bad router probs"),
        ErrorEvent(
            message=(
                "KernelHostPorts returned malformed RouterDecisionEvent: "
                "probs must be a list of probabilities"
            ),
            code="pi_sidecar_error",
        ),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_out_of_range_host_router_confidence() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "bad router confidence"},
            }

    class BadRouterDecisionFinalizer:
        async def handle_intent(self, *, intent_type: str, payload: dict, session_key: str):
            _ = intent_type, payload, session_key
            return [
                RouterDecisionEvent(
                    tier="t1",
                    tier_index=1,
                    model="model-a",
                    confidence=1.5,
                    probs=[0.2, 0.8],
                ),
                DoneEvent(text="bad router confidence", model="host-final"),
            ]

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-side"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(finalizer=BadRouterDecisionFinalizer()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="bad router confidence"),
        ErrorEvent(
            message=(
                "KernelHostPorts returned malformed RouterDecisionEvent: "
                "confidence must be a probability"
            ),
            code="pi_sidecar_error",
        ),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field_name", "field_value", "message"),
    [
        (
            "arguments",
            {"opaque": object()},
            "KernelHostPorts returned malformed ToolResultEvent: "
            "arguments must be JSON-safe",
        ),
        (
            "execution_status",
            {"tokens": float("nan")},
            "KernelHostPorts returned malformed ToolResultEvent: "
            "execution_status must be JSON-safe",
        ),
    ],
)
async def test_pi_sidecar_kernel_rejects_python_only_host_tool_result_metadata(
    field_name: str,
    field_value: dict[str, object],
    message: str,
) -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "bad tool metadata"},
            }

    class BadToolResultFinalizer:
        async def handle_intent(self, *, intent_type: str, payload: dict, session_key: str):
            _ = intent_type, payload, session_key
            tool_result = ToolResultEvent(
                tool_use_id="call-1",
                tool_name="read",
                result="host result",
            )
            setattr(tool_result, field_name, field_value)
            return [tool_result, DoneEvent(text="final", model="host-final")]

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-side"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(finalizer=BadToolResultFinalizer()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="bad tool metadata"),
        ErrorEvent(message=message, code="pi_sidecar_error"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event_factory", "message"),
    [
        (
            lambda: ToolUseStartEvent(
                tool_use_id="   ",
                tool_name="read",
            ),
            "KernelHostPorts returned malformed ToolUseStartEvent: "
            "tool_use_id must be a non-empty string",
        ),
        (
            lambda: ToolUseStartEvent(
                tool_use_id="call-1",
                tool_name="   ",
            ),
            "KernelHostPorts returned malformed ToolUseStartEvent: "
            "tool_name must be a non-empty string",
        ),
        (
            lambda: ToolResultEvent(
                tool_use_id="   ",
                tool_name="read",
                result="host result",
            ),
            "KernelHostPorts returned malformed ToolResultEvent: "
            "tool_use_id must be a non-empty string",
        ),
        (
            lambda: ToolResultEvent(
                tool_use_id="call-1",
                tool_name="   ",
                result="host result",
            ),
            "KernelHostPorts returned malformed ToolResultEvent: "
            "tool_name must be a non-empty string",
        ),
    ],
)
async def test_pi_sidecar_kernel_rejects_blank_host_tool_event_identity(
    event_factory,
    message: str,
) -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "bad tool identity"},
            }

    class BadToolEventFinalizer:
        async def handle_intent(self, *, intent_type: str, payload: dict, session_key: str):
            _ = intent_type, payload, session_key
            return [event_factory(), DoneEvent(text="final", model="host-final")]

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-side"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(finalizer=BadToolEventFinalizer()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="bad tool identity"),
        ErrorEvent(message=message, code="pi_sidecar_error"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("session_totals", "message"),
    [
        (
            {"input_tokens": object()},
            "KernelHostPorts returned malformed DoneEvent: "
            "session_totals must be a SessionTotalsSnapshot or None",
        ),
        (
            lambda snapshot_cls: snapshot_cls(
                input_tokens=1,
                billed_cost=float("nan"),
            ),
            "KernelHostPorts returned malformed DoneEvent: "
            "session_totals must be JSON-safe",
        ),
    ],
)
async def test_pi_sidecar_kernel_rejects_python_only_host_done_session_totals(
    session_totals,
    message: str,
) -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )
    from opensquilla.engine.usage import SessionTotalsSnapshot

    if callable(session_totals):
        session_totals = session_totals(SessionTotalsSnapshot)

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "bad totals"},
            }

    class BadDoneFinalizer:
        async def handle_intent(self, *, intent_type: str, payload: dict, session_key: str):
            _ = intent_type, payload, session_key
            return [
                DoneEvent(
                    text="final",
                    model="host-final",
                    session_totals=session_totals,
                )
            ]

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-side"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(finalizer=BadDoneFinalizer()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="bad totals"),
        ErrorEvent(message=message, code="pi_sidecar_error"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field_name", "field_value", "message"),
    [
        (
            "input_tokens",
            -1,
            "KernelHostPorts returned malformed DoneEvent: "
            "session_totals.input_tokens must be a non-negative integer",
        ),
        (
            "cache_read_tokens",
            -1,
            "KernelHostPorts returned malformed DoneEvent: "
            "session_totals.cache_read_tokens must be a non-negative integer",
        ),
        (
            "cost_usd",
            -0.01,
            "KernelHostPorts returned malformed DoneEvent: "
            "session_totals.cost_usd must be a non-negative number",
        ),
        (
            "billed_cost",
            -0.01,
            "KernelHostPorts returned malformed DoneEvent: "
            "session_totals.billed_cost must be a non-negative number",
        ),
    ],
)
async def test_pi_sidecar_kernel_rejects_negative_host_done_session_totals(
    field_name: str,
    field_value: int | float,
    message: str,
) -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )
    from opensquilla.engine.usage import SessionTotalsSnapshot

    session_totals = SessionTotalsSnapshot()
    setattr(session_totals, field_name, field_value)

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "bad totals"},
            }

    class BadDoneFinalizer:
        async def handle_intent(self, *, intent_type: str, payload: dict, session_key: str):
            _ = intent_type, payload, session_key
            return [
                DoneEvent(
                    text="final",
                    model="host-final",
                    session_totals=session_totals,
                )
            ]

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-side"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(finalizer=BadDoneFinalizer()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="bad totals"),
        ErrorEvent(message=message, code="pi_sidecar_error"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field_name", "field_value", "message"),
    [
        (
            "input_tokens",
            -1,
            "KernelHostPorts returned malformed DoneEvent: "
            "input_tokens must be a non-negative integer",
        ),
        (
            "cache_write_tokens",
            -1,
            "KernelHostPorts returned malformed DoneEvent: "
            "cache_write_tokens must be a non-negative integer",
        ),
        (
            "cost_usd",
            -0.01,
            "KernelHostPorts returned malformed DoneEvent: "
            "cost_usd must be a non-negative number",
        ),
        (
            "billed_cost",
            -0.01,
            "KernelHostPorts returned malformed DoneEvent: "
            "billed_cost must be a non-negative number",
        ),
        (
            "routing_confidence",
            -0.01,
            "KernelHostPorts returned malformed DoneEvent: "
            "routing_confidence must be a non-negative number",
        ),
        (
            "routing_confidence",
            1.5,
            "KernelHostPorts returned malformed DoneEvent: "
            "routing_confidence must be a probability",
        ),
        (
            "savings_pct",
            -0.01,
            "KernelHostPorts returned malformed DoneEvent: "
            "savings_pct must be a non-negative number",
        ),
        (
            "savings_usd",
            -0.01,
            "KernelHostPorts returned malformed DoneEvent: "
            "savings_usd must be a non-negative number",
        ),
        (
            "total_savings_pct",
            -0.01,
            "KernelHostPorts returned malformed DoneEvent: "
            "total_savings_pct must be a non-negative number",
        ),
        (
            "total_savings_usd",
            -0.01,
            "KernelHostPorts returned malformed DoneEvent: "
            "total_savings_usd must be a non-negative number",
        ),
    ],
)
async def test_pi_sidecar_kernel_rejects_negative_host_done_counters(
    field_name: str,
    field_value: int | float,
    message: str,
) -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "bad counters"},
            }

    class BadDoneFinalizer:
        async def handle_intent(self, *, intent_type: str, payload: dict, session_key: str):
            _ = intent_type, payload, session_key
            done = DoneEvent(text="final", model="host-final")
            setattr(done, field_name, field_value)
            return [done]

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-side"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(finalizer=BadDoneFinalizer()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="bad counters"),
        ErrorEvent(message=message, code="pi_sidecar_error"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kept_entries", "message"),
    [
        (
            [object()],
            "KernelHostPorts returned malformed CompactionEvent: "
            "kept_entries must be a list of JSON-safe objects",
        ),
        (
            [{"tokens": float("nan")}],
            "KernelHostPorts returned malformed CompactionEvent: "
            "kept_entries must be a list of JSON-safe objects",
        ),
    ],
)
async def test_pi_sidecar_kernel_rejects_python_only_host_compaction_entries(
    kept_entries: list[object],
    message: str,
) -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "bad compaction"},
            }

    class BadCompactionFinalizer:
        async def handle_intent(self, *, intent_type: str, payload: dict, session_key: str):
            _ = intent_type, payload, session_key
            return [
                CompactionEvent(
                    compaction_id="compact-1",
                    summary="summary",
                    kept_entries=kept_entries,
                    kept_count=1,
                    removed_count=0,
                ),
                DoneEvent(text="final", model="host-final"),
            ]

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-side"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(finalizer=BadCompactionFinalizer()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="bad compaction"),
        ErrorEvent(message=message, code="pi_sidecar_error"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field_name", "message"),
    [
        (
            "kept_count",
            "KernelHostPorts returned malformed CompactionEvent: "
            "kept_count must be a non-negative integer",
        ),
        (
            "removed_count",
            "KernelHostPorts returned malformed CompactionEvent: "
            "removed_count must be a non-negative integer",
        ),
    ],
)
async def test_pi_sidecar_kernel_rejects_negative_host_compaction_counts(
    field_name: str,
    message: str,
) -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "bad compaction count"},
            }

    class BadCompactionFinalizer:
        async def handle_intent(self, *, intent_type: str, payload: dict, session_key: str):
            _ = intent_type, payload, session_key
            compaction = CompactionEvent(
                compaction_id="compact-1",
                summary="summary",
                kept_entries=[],
                kept_count=1,
                removed_count=0,
            )
            setattr(compaction, field_name, -1)
            return [compaction, DoneEvent(text="final", model="host-final")]

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-side"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(finalizer=BadCompactionFinalizer()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="bad compaction count"),
        ErrorEvent(message=message, code="pi_sidecar_error"),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_requires_finalizer_done_event() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "needs final done"},
            }

    class EmptyFinalizer:
        async def handle_intent(self, *, intent_type: str, payload: dict, session_key: str):
            return []

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-side"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(finalizer=EmptyFinalizer()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="needs final done"),
        ErrorEvent(
            message=(
                "KernelHostPorts.finalizer must return a terminal "
                "DoneEvent or ErrorEvent"
            ),
            code="pi_sidecar_error",
        ),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_preserves_finalizer_error_without_duplicate() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "cannot finalize"},
            }

    class ErrorFinalizer:
        async def handle_intent(self, *, intent_type: str, payload: dict, session_key: str):
            return [ErrorEvent(message="finalizer denied turn", code="finalizer_error")]

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-side"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(finalizer=ErrorFinalizer()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="cannot finalize"),
        ErrorEvent(message="finalizer denied turn", code="finalizer_error"),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_finalizer_events_after_terminal() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "terminal"},
            }

    class NoisyFinalizer:
        async def handle_intent(self, *, intent_type: str, payload: dict, session_key: str):
            return [
                DoneEvent(text=payload["text"], model="host-final"),
                TextDeltaEvent(text="must not leak"),
            ]

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-side"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(finalizer=NoisyFinalizer()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="terminal"),
        ErrorEvent(
            message="KernelHostPorts.finalizer returned events after terminal event",
            code="pi_sidecar_error",
        ),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_multiple_finalizer_terminal_events() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "terminal"},
            }

    class DoubleDoneFinalizer:
        async def handle_intent(self, *, intent_type: str, payload: dict, session_key: str):
            return [
                DoneEvent(text=payload["text"], model="host-final"),
                DoneEvent(text="second terminal", model="host-final"),
            ]

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-side"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(finalizer=DoubleDoneFinalizer()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="terminal"),
        ErrorEvent(
            message="KernelHostPorts.finalizer returned multiple terminal events",
            code="pi_sidecar_error",
        ),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_converts_finalizer_runtime_failure_to_error_event() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakePiRpcClient:
        def __init__(self) -> None:
            self.calls = 0

        async def stream_prompt(self, message: str, **kwargs):
            self.calls += 1
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": f"text-{self.calls}"},
            }

    class FlakyFinalizer:
        def __init__(self) -> None:
            self.calls = 0

        async def handle_intent(self, *, intent_type: str, payload: dict, session_key: str):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("finalizer unavailable")
            return [DoneEvent(text=f"final:{payload['text']}", model="host-final")]

    rpc_client = FakePiRpcClient()
    agent = PiSidecarKernelRuntime(
        rpc_client=rpc_client,
        config=SimpleNamespace(model_id="pi-side"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(finalizer=FlakyFinalizer()),
    )

    first_events = [event async for event in agent.run_turn("hello")]
    second_events = [event async for event in agent.run_turn("hello again")]

    assert first_events == [
        TextDeltaEvent(text="text-1"),
        ErrorEvent(message="finalizer unavailable", code="pi_sidecar_error"),
    ]
    assert second_events == [
        TextDeltaEvent(text="text-2"),
        DoneEvent(text="final:text-2", model="host-final"),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_converts_stream_creation_exception_to_error_event() -> None:
    from opensquilla.engine.agent_core import PiSidecarKernelRuntime
    from opensquilla.engine.types import ErrorEvent

    class FakePiRpcClient:
        def stream_prompt(self, message: str, **kwargs):
            _ = message, kwargs
            raise OSError("sidecar failed before stream")

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-test"),
        session_key="agent:main:test",
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        ErrorEvent(message="sidecar failed before stream", code="pi_sidecar_error")
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_converts_runtime_exception_to_error_event() -> None:
    from opensquilla.engine.agent_core import AGENT_CORE_PROTOCOL_VERSION, PiSidecarKernelRuntime
    from opensquilla.engine.types import ErrorEvent

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "partial"},
            }
            raise OSError("sidecar transport closed")

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-test"),
        session_key="agent:main:test",
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="partial"),
        ErrorEvent(message="sidecar transport closed", code="pi_sidecar_error"),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_clears_pending_tool_calls_after_runtime_error() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )
    from opensquilla.engine.types import ErrorEvent

    class FailingToolBridge:
        async def handle_intent(self, **kwargs):
            if kwargs["intent_type"] == "tool.call.execute":
                raise OSError("tool bridge failed")
            return []

    class FakePiRpcClient:
        def __init__(self) -> None:
            self.turns = 0

        async def stream_prompt(self, message: str, **kwargs):
            self.turns += 1
            if self.turns == 1:
                yield {
                    "protocol": AGENT_CORE_PROTOCOL_VERSION,
                    "kind": "intent",
                    "type": "tool.call.prepare",
                    "payload": {"tool_call_id": "call-1", "tool_name": "read"},
                }
                yield {
                    "protocol": AGENT_CORE_PROTOCOL_VERSION,
                    "kind": "intent",
                    "type": "tool.call.execute",
                    "payload": {"tool_call_id": "call-1", "tool_name": "read"},
                }
                return
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "recovered"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-recovery"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(tool_bridge=FailingToolBridge()),
    )

    first_events = [event async for event in agent.run_turn("first")]
    second_events = [event async for event in agent.run_turn("second")]

    assert first_events == [ErrorEvent(message="tool bridge failed", code="pi_sidecar_error")]
    assert second_events == [
        TextDeltaEvent(text="recovered"),
        DoneEvent(text="recovered", model="pi-recovery", cost_source="unavailable"),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_settles_pending_tool_after_host_tool_error_result() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    calls: list[tuple[str, str]] = []

    class ErrorToolBridge:
        async def handle_intent(self, **kwargs):
            tool_call_id = kwargs["payload"].get("tool_call_id")
            calls.append((kwargs["intent_type"], tool_call_id))
            if kwargs["intent_type"] == "tool.call.execute":
                return [
                    ToolResultEvent(
                        tool_use_id=tool_call_id,
                        tool_name="read",
                        result="tool failed but host handled it",
                        is_error=True,
                    )
                ]
            return []

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "tool.call.prepare",
                "payload": {"tool_call_id": "call-1", "tool_name": "read"},
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "tool.call.execute",
                "payload": {"tool_call_id": "call-1", "tool_name": "read"},
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "recovered after tool error"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-tool-error"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(tool_bridge=ErrorToolBridge()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        ToolResultEvent(
            tool_use_id="call-1",
            tool_name="read",
            result="tool failed but host handled it",
            is_error=True,
        ),
        TextDeltaEvent(text="recovered after tool error"),
        DoneEvent(
            text="recovered after tool error",
            model="pi-tool-error",
            cost_source="unavailable",
        ),
    ]
    assert calls == [
        ("tool.call.prepare", "call-1"),
        ("tool.call.execute", "call-1"),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_error_event_settles_pending_tool_calls() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )
    from opensquilla.engine.types import ErrorEvent

    class RecordingToolBridge:
        async def handle_intent(self, **kwargs):
            return []

    class FakePiRpcClient:
        def __init__(self) -> None:
            self.turns = 0

        async def stream_prompt(self, message: str, **kwargs):
            self.turns += 1
            if self.turns == 1:
                yield {
                    "protocol": AGENT_CORE_PROTOCOL_VERSION,
                    "kind": "intent",
                    "type": "tool.call.prepare",
                    "payload": {"tool_call_id": "call-1", "tool_name": "read"},
                }
                yield {
                    "protocol": AGENT_CORE_PROTOCOL_VERSION,
                    "kind": "event",
                    "type": "error",
                    "payload": {"message": "sidecar failed", "code": "sidecar_failed"},
                }
                return
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "next turn"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-error"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(tool_bridge=RecordingToolBridge()),
    )

    first_events = [event async for event in agent.run_turn("first")]
    second_events = [event async for event in agent.run_turn("second")]

    assert first_events == [ErrorEvent(message="sidecar failed", code="sidecar_failed")]
    assert second_events == [
        TextDeltaEvent(text="next turn"),
        DoneEvent(text="next turn", model="pi-error", cost_source="unavailable"),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_receives_host_loaded_history() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelTurnSnapshot,
        PiSidecarKernelRuntime,
    )

    history = [{"role": "user", "content": "previous"}]

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            assert kwargs["history"] == history
            snapshot = kwargs["turn_snapshot"]
            assert isinstance(snapshot, KernelTurnSnapshot)
            assert snapshot.session_key == "agent:main:test"
            assert snapshot.agent_id == "main"
            assert snapshot.turn_id == "agent:main:test:turn-1"
            assert snapshot.turn_input == "hello"
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "with history"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(),
        session_key="agent:main:test",
    )
    agent.set_history(history)

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="with history"),
        DoneEvent(text="with history", model="", cost_source="unavailable"),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_turn_snapshot_agent_id_is_never_blank() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelTurnSnapshot,
        PiSidecarKernelRuntime,
    )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            _ = message
            snapshot = kwargs["turn_snapshot"]
            assert isinstance(snapshot, KernelTurnSnapshot)
            assert snapshot.session_key == "agent::test"
            assert snapshot.agent_id == "agent::test"
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "nonblank agent id"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-agent-id"),
        session_key="agent::test",
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="nonblank agent id"),
        DoneEvent(
            text="nonblank agent id",
            model="pi-agent-id",
            cost_source="unavailable",
        ),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_passes_host_authored_turn_snapshot() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelTurnSnapshot,
        PiSidecarKernelRuntime,
    )

    seen: list[KernelTurnSnapshot] = []
    seen_session_ids: list[str] = []

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            seen.append(kwargs["turn_snapshot"])
            seen_session_ids.append(kwargs["session_id"])
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "snapshot"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(
            model_id="pi-model",
            system_prompt="system",
            request_context_prompt="host request context",
        ),
        session_key="agent:worker:test",
        tool_definitions=[{"name": "read"}],
        metadata={"route": "pi"},
    )

    events = [
        event
        async for event in agent.run_turn(
            "hello",
            extra_messages=[{"role": "user", "content": "extra"}],
            semantic_message="semantic hello",
        )
    ]

    assert events == [
        TextDeltaEvent(text="snapshot"),
        DoneEvent(text="snapshot", model="pi-model", cost_source="unavailable"),
    ]
    assert seen == [
        KernelTurnSnapshot(
            session_key="agent:worker:test",
            session_id="agent:worker:test",
            agent_id="worker",
            turn_id="agent:worker:test:turn-1",
            turn_input="hello",
            system_prompt="system",
            request_context_prompt="host request context",
            model_id="pi-model",
            tool_definitions=[{"name": "read"}],
            extra_messages=[{"role": "user", "content": "extra"}],
            semantic_message="semantic hello",
            metadata={"route": "pi"},
        )
    ]
    assert seen_session_ids == ["agent:worker:test"]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_exposes_host_runtime_policy_snapshot_metadata() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelTurnSnapshot,
        PiSidecarKernelRuntime,
    )

    seen: list[KernelTurnSnapshot] = []

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            _ = message
            seen.append(kwargs["turn_snapshot"])
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "policy snapshot"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(
            model_id="pi-policy",
            flush_enabled=False,
            flush_triggers=["pre_compaction", "manual"],
            flush_pre_compaction=True,
            flush_timeout_seconds=2.5,
            flush_compaction_requires_safe_receipt=True,
            flush_compaction_safety_mode="block",
            compaction_profile="coding",
            compaction_protected_recent_messages=4,
        ),
        session_key="agent:worker:test",
        metadata={
            "route": "pi",
            "host_runtime_policy": {"flush_enabled": True},
        },
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="policy snapshot"),
        DoneEvent(text="policy snapshot", model="pi-policy", cost_source="unavailable"),
    ]
    assert len(seen) == 1
    assert seen[0].metadata == {
        "route": "pi",
        "host_runtime_policy": {
            "flush_enabled": False,
            "flush_triggers": ["pre_compaction", "manual"],
            "flush_pre_compaction": True,
            "flush_timeout_seconds": 2.5,
            "flush_compaction_requires_safe_receipt": True,
            "flush_compaction_safety_mode": "block",
            "compaction_profile": "coding",
            "compaction_protected_recent_messages": 4,
        },
    }


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_passes_normalized_protocol_version_to_sidecar() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        AgentCoreConfig,
        PiSidecarKernelRuntime,
    )

    seen_protocol_versions: list[str] = []

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            _ = message
            seen_protocol_versions.append(kwargs["protocol_version"])
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "protocol"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-protocol"),
        session_key="agent:main:test",
        agent_core_config=AgentCoreConfig(kernel="pi", protocol_version="  "),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert seen_protocol_versions == [AGENT_CORE_PROTOCOL_VERSION]
    assert events == [
        TextDeltaEvent(text="protocol"),
        DoneEvent(text="protocol", model="pi-protocol", cost_source="unavailable"),
    ]


def test_pi_sidecar_kernel_rejects_non_string_refresh_system_prompt_before_ports() -> None:
    from opensquilla.engine.agent_core import KernelHostPorts, PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            raise AssertionError("not used")
            yield  # pragma: no cover

    class FakeProviderPort:
        def refresh_system_prompt(self, system_prompt: str) -> None:
            _ = system_prompt
            raise AssertionError("non-string system prompt reached host port")

    config = SimpleNamespace(
        model_id="pi-refresh",
        system_prompt="stable",
        request_context_prompt="host request context",
    )
    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=config,
        session_key="agent:main:test",
        host_ports=KernelHostPorts(provider=FakeProviderPort()),
    )

    with pytest.raises(
        RuntimeError,
        match="KernelTurnSnapshot system_prompt must be a string",
    ):
        agent.refresh_system_prompt(["not", "a", "string"])

    assert agent._system_prompt == "stable"
    assert config.system_prompt == "stable"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field_name", "expected_message"),
    [
        ("system_prompt", "KernelTurnSnapshot system_prompt must be a string"),
        (
            "request_context_prompt",
            "KernelTurnSnapshot request_context_prompt must be a string",
        ),
        ("model_id", "KernelTurnSnapshot model_id must be a string"),
    ],
)
async def test_pi_sidecar_kernel_rejects_structured_snapshot_config_before_rpc(
    field_name: str,
    expected_message: str,
) -> None:
    from opensquilla.engine.agent_core import PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            raise AssertionError("structured snapshot config reached Pi RPC client")
            yield  # pragma: no cover

    config = SimpleNamespace(
        model_id="pi-model",
        system_prompt="system",
        request_context_prompt="host request context",
    )
    setattr(config, field_name, {"not": "a string"})
    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=config,
        session_key="agent:worker:test",
    )

    with pytest.raises(RuntimeError, match=expected_message):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_structured_semantic_message_before_rpc() -> None:
    from opensquilla.engine.agent_core import PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            raise AssertionError("structured semantic_message reached Pi RPC client")
            yield  # pragma: no cover

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(
            model_id="pi-model",
            system_prompt="system",
            request_context_prompt="host request context",
        ),
        session_key="agent:worker:test",
    )

    with pytest.raises(
        RuntimeError,
        match="KernelTurnSnapshot semantic_message must be a string or None",
    ):
        _ = [
            event
            async for event in agent.run_turn(
                "hello",
                semantic_message={"not": "a string"},
            )
        ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_structured_turn_input_before_rpc() -> None:
    from opensquilla.engine.agent_core import PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            raise AssertionError("structured turn_input reached Pi RPC client")
            yield  # pragma: no cover

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(
            model_id="pi-model",
            system_prompt="system",
            request_context_prompt="host request context",
        ),
        session_key="agent:worker:test",
    )

    with pytest.raises(
        RuntimeError,
        match="KernelTurnSnapshot turn_input must be a string",
    ):
        _ = [event async for event in agent.run_turn({"not": "a string"})]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_missing_turn_input_before_rpc() -> None:
    from opensquilla.engine.agent_core import PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            raise AssertionError("missing turn_input reached Pi RPC client")
            yield  # pragma: no cover

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(
            model_id="pi-model",
            system_prompt="system",
            request_context_prompt="host request context",
        ),
        session_key="agent:worker:test",
    )

    with pytest.raises(
        RuntimeError,
        match="KernelTurnSnapshot turn_input must be a string",
    ):
        _ = [event async for event in agent.run_turn(None)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extra_messages",
    [
        {"role": "user", "content": "not a list"},
        ({"role": "user", "content": "tuple coerces to list"},),
    ],
)
async def test_pi_sidecar_kernel_rejects_non_list_extra_messages_before_rpc(
    extra_messages: object,
) -> None:
    from opensquilla.engine.agent_core import PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            raise AssertionError("non-list extra_messages reached Pi RPC client")
            yield  # pragma: no cover

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(
            model_id="pi-model",
            system_prompt="system",
            request_context_prompt="host request context",
        ),
        session_key="agent:worker:test",
    )

    with pytest.raises(
        RuntimeError,
        match="KernelTurnSnapshot extra_messages must be a list or None",
    ):
        _ = [
            event
            async for event in agent.run_turn(
                "hello",
                extra_messages=extra_messages,
            )
        ]


def test_pi_sidecar_kernel_rejects_non_list_history_before_rpc() -> None:
    from opensquilla.engine.agent_core import PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            raise AssertionError("non-list history reached Pi RPC client")
            yield  # pragma: no cover

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(
            model_id="pi-model",
            system_prompt="system",
            request_context_prompt="host request context",
        ),
        session_key="agent:worker:test",
    )

    with pytest.raises(RuntimeError, match="Pi sidecar history must be a list"):
        agent.set_history({"role": "user", "content": "not a list"})


def test_pi_sidecar_kernel_rejects_non_string_history_keys_before_runtime_state() -> None:
    from opensquilla.engine.agent_core import PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            raise AssertionError("history with non-string key reached Pi RPC client")
            yield  # pragma: no cover

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(
            model_id="pi-model",
            system_prompt="system",
            request_context_prompt="host request context",
        ),
        session_key="agent:worker:test",
    )

    with pytest.raises(
        RuntimeError,
        match="Pi sidecar JSON object keys must be strings",
    ):
        agent.set_history([{1: "numeric key"}])


@pytest.mark.parametrize(
    "tool_definitions",
    [
        {"name": "not a list"},
        ({"name": "tuple coerces to list"},),
    ],
)
def test_pi_sidecar_kernel_rejects_non_list_tool_definitions_before_rpc(
    tool_definitions: object,
) -> None:
    from opensquilla.engine.agent_core import PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            raise AssertionError("non-list tool_definitions reached Pi RPC client")
            yield  # pragma: no cover

    with pytest.raises(
        RuntimeError,
        match="Pi sidecar tool_definitions must be a list",
    ):
        PiSidecarKernelRuntime(
            rpc_client=FakePiRpcClient(),
            config=SimpleNamespace(
                model_id="pi-model",
                system_prompt="system",
                request_context_prompt="host request context",
            ),
            session_key="agent:worker:test",
            tool_definitions=tool_definitions,
        )


def test_pi_sidecar_kernel_rejects_non_object_metadata_before_rpc() -> None:
    from opensquilla.engine.agent_core import PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            raise AssertionError("non-object metadata reached Pi RPC client")
            yield  # pragma: no cover

    with pytest.raises(RuntimeError, match="Pi sidecar metadata must be an object"):
        PiSidecarKernelRuntime(
            rpc_client=FakePiRpcClient(),
            config=SimpleNamespace(
                model_id="pi-model",
                system_prompt="system",
                request_context_prompt="host request context",
            ),
            session_key="agent:worker:test",
            metadata=["not", "an", "object"],
        )


def test_pi_sidecar_kernel_rejects_non_string_metadata_keys_before_rpc() -> None:
    from opensquilla.engine.agent_core import PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            raise AssertionError("metadata with non-string key reached Pi RPC client")
            yield  # pragma: no cover

    with pytest.raises(
        RuntimeError,
        match="Pi sidecar JSON object keys must be strings",
    ):
        PiSidecarKernelRuntime(
            rpc_client=FakePiRpcClient(),
            config=SimpleNamespace(
                model_id="pi-model",
                system_prompt="system",
                request_context_prompt="host request context",
            ),
            session_key="agent:worker:test",
            metadata={1: "numeric key"},
        )


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_non_string_extra_message_keys_before_rpc() -> None:
    from opensquilla.engine.agent_core import PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            raise AssertionError("extra_messages with non-string key reached Pi RPC client")
            yield  # pragma: no cover

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(
            model_id="pi-model",
            system_prompt="system",
            request_context_prompt="host request context",
        ),
        session_key="agent:worker:test",
    )

    with pytest.raises(
        RuntimeError,
        match="Pi sidecar JSON object keys must be strings",
    ):
        _ = [
            event
            async for event in agent.run_turn(
                "hello",
                extra_messages=[{1: "numeric key"}],
            )
        ]


def test_pi_sidecar_kernel_rejects_non_string_session_key_before_runtime() -> None:
    from opensquilla.engine.agent_core import PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            raise AssertionError("non-string session_key reached Pi RPC client")
            yield  # pragma: no cover

    with pytest.raises(RuntimeError, match="Pi sidecar session_key must be a string"):
        PiSidecarKernelRuntime(
            rpc_client=FakePiRpcClient(),
            config=SimpleNamespace(
                model_id="pi-model",
                system_prompt="system",
                request_context_prompt="host request context",
            ),
            session_key={"not": "a string"},
        )


@pytest.mark.parametrize("session_key", ["", "   "])
def test_pi_sidecar_kernel_rejects_blank_session_key_before_runtime(session_key: str) -> None:
    from opensquilla.engine.agent_core import PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            raise AssertionError("blank session_key reached Pi RPC client")
            yield  # pragma: no cover

    with pytest.raises(RuntimeError, match="Pi sidecar session_key must be non-empty"):
        PiSidecarKernelRuntime(
            rpc_client=FakePiRpcClient(),
            config=SimpleNamespace(
                model_id="pi-model",
                system_prompt="system",
                request_context_prompt="host request context",
            ),
            session_key=session_key,
        )


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_isolates_host_authored_turn_inputs() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        PiSidecarKernelRuntime,
    )

    history = [{"role": "user", "content": {"text": "previous"}}]
    extra_messages = [{"role": "user", "content": {"text": "extra"}}]
    tool_definitions = [{"name": "read", "input_schema": {"properties": {}}}]
    seen_history: list[list[dict[str, str]]] = []

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            seen_history.append(copy.deepcopy(kwargs["history"]))
            kwargs["history"][0]["content"]["text"] = "mutated nested history"
            kwargs["history"].append({"role": "assistant", "content": "mutated history"})
            kwargs["extra_messages"][0]["content"]["text"] = "mutated nested extra"
            kwargs["extra_messages"].append(
                {"role": "assistant", "content": "mutated extra"}
            )
            kwargs["turn_snapshot"].tool_definitions[0]["input_schema"][
                "properties"
            ]["mutated"] = {"type": "string"}
            kwargs["turn_snapshot"].extra_messages.append(
                {"role": "assistant", "content": "mutated snapshot extra"}
            )
            kwargs["turn_snapshot"].tool_definitions.append({"name": "mutated_tool"})
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "isolated"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-isolated"),
        session_key="agent:worker:test",
        tool_definitions=tool_definitions,
    )
    agent.set_history(history)

    first_events = [
        event async for event in agent.run_turn("first", extra_messages=extra_messages)
    ]
    second_events = [
        event async for event in agent.run_turn("second", extra_messages=extra_messages)
    ]

    assert first_events == [
        TextDeltaEvent(text="isolated"),
        DoneEvent(text="isolated", model="pi-isolated", cost_source="unavailable"),
    ]
    assert second_events == [
        TextDeltaEvent(text="isolated"),
        DoneEvent(text="isolated", model="pi-isolated", cost_source="unavailable"),
    ]
    assert seen_history == [history, history]
    assert extra_messages == [{"role": "user", "content": {"text": "extra"}}]
    assert tool_definitions == [{"name": "read", "input_schema": {"properties": {}}}]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_sets_host_agent_current_turn_message() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        PiSidecarKernelRuntime,
    )
    from opensquilla.engine.types import AgentConfig, ErrorEvent

    host_config = AgentConfig(metadata={"user_message": "stale prompt"})

    class FakeHostAgent:
        config = host_config

    host_agent = FakeHostAgent()

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            _ = kwargs
            assert message == "fresh meta request"
            assert getattr(host_agent, "_current_turn_message") == "fresh meta request"
            assert host_agent.config.metadata["user_message"] == "fresh meta request"
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "error",
                "payload": {"message": "stop after assertion", "code": "test_stop"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-model"),
        session_key="agent:main:test",
        host_agent=host_agent,
    )

    events = [event async for event in agent.run_turn("fresh meta request")]

    assert ErrorEvent(message="stop after assertion", code="test_stop") in events


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_owns_constructor_tool_definitions_and_metadata() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        PiSidecarKernelRuntime,
    )

    tool_definitions = [{"name": "read", "input_schema": {"properties": {}}}]
    metadata = {"route": {"kernel": "pi"}}
    seen: list[tuple[list[dict[str, object]], dict[str, object]]] = []

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            _ = message
            snapshot = kwargs["turn_snapshot"]
            seen.append(
                (
                    copy.deepcopy(snapshot.tool_definitions),
                    copy.deepcopy(snapshot.metadata),
                )
            )
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "owned inputs"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-owned-inputs"),
        session_key="agent:worker:test",
        tool_definitions=tool_definitions,
        metadata=metadata,
    )
    tool_definitions[0]["input_schema"]["properties"]["mutated"] = {
        "type": "string"
    }
    metadata["route"]["kernel"] = "mutated"

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="owned inputs"),
        DoneEvent(text="owned inputs", model="pi-owned-inputs", cost_source="unavailable"),
    ]
    assert seen == [
        (
            [{"name": "read", "input_schema": {"properties": {}}}],
            {"route": {"kernel": "pi"}},
        )
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_opaque_snapshot_metadata_before_rpc() -> None:
    from opensquilla.engine.agent_core import PiSidecarKernelRuntime

    class OpaqueMetadata:
        def __str__(self) -> str:
            return "opaque-json-safe"

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            _ = message, kwargs
            raise AssertionError("opaque snapshot metadata reached Pi RPC client")
            yield  # pragma: no cover

    with pytest.raises(RuntimeError, match="JSON value"):
        PiSidecarKernelRuntime(
            rpc_client=FakePiRpcClient(),
            config=SimpleNamespace(model_id="pi-json-safe-snapshot"),
            session_key="agent:worker:test",
            metadata={"opaque": OpaqueMetadata()},
        )


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_non_finite_snapshot_metadata_before_rpc() -> None:
    from opensquilla.engine.agent_core import PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            _ = message, kwargs
            raise AssertionError("non-finite snapshot metadata reached Pi RPC client")
            yield  # pragma: no cover

    with pytest.raises(RuntimeError, match="non-finite"):
        agent = PiSidecarKernelRuntime(
            rpc_client=FakePiRpcClient(),
            config=SimpleNamespace(model_id="pi-json-safe-snapshot"),
            session_key="agent:worker:test",
            metadata={"cache_hit_rate": float("nan")},
        )
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_host_owned_done_frames() -> None:
    from opensquilla.engine.agent_core import AGENT_CORE_PROTOCOL_VERSION, PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "turn_end",
                "payload": {"text": "should not become DoneEvent"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(),
        session_key="agent:main:test",
    )

    with pytest.raises(RuntimeError, match="host-owned event"):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event_type",
    [
        "agent_start",
        "turn_start",
        "message_start",
        "message_update",
        "message_end",
        "tool_execution_start",
        "tool_execution_update",
        "tool_execution_end",
        "queue_update",
        "compaction_start",
        "compaction_end",
        "auto_retry_start",
        "auto_retry_end",
        "provider.done",
        "provider_done",
        "provider.request",
        "provider_request",
        "tool.call.prepare",
        "tool.call.execute",
        "session.write.enqueue",
        "queue.poll",
        "savepoint.request",
        "yield.request",
        "telemetry.emit",
        "turn_end",
        "agent_end",
    ],
)
async def test_pi_sidecar_kernel_rejects_pi_native_loop_frames(
    event_type: str,
) -> None:
    from opensquilla.engine.agent_core import AGENT_CORE_PROTOCOL_VERSION, PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": event_type,
                "payload": {"text": "pi native frame"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(),
        session_key="agent:main:test",
    )

    with pytest.raises(RuntimeError, match="host-owned event"):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_direct_artifact_events_as_host_owned() -> None:
    from opensquilla.engine.agent_core import AGENT_CORE_PROTOCOL_VERSION, PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "artifact",
                "payload": {
                    "id": "artifact-1",
                    "sha256": "abc",
                    "name": "report.txt",
                    "mime": "text/plain",
                    "size": 42,
                },
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(),
        session_key="agent:main:test",
    )

    with pytest.raises(RuntimeError, match="host-owned event"):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event_type",
    ["router_decision", "router_control_replay"],
)
async def test_pi_sidecar_kernel_rejects_direct_router_events_as_host_owned(
    event_type: str,
) -> None:
    from opensquilla.engine.agent_core import AGENT_CORE_PROTOCOL_VERSION, PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": event_type,
                "payload": {"model": "pi-direct-router"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(),
        session_key="agent:main:test",
    )

    with pytest.raises(RuntimeError, match="host-owned event"):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event_type",
    [
        "done",
        "text_delta",
        "tool.result",
        "tool_result",
        "tool_use_start",
        "tool_use_delta",
        "tool_use_end",
        "session.write",
        "yield",
        "thinking",
        "run_heartbeat",
        "state_change",
        "warning",
        "compaction",
    ],
)
async def test_pi_sidecar_kernel_rejects_direct_host_side_effect_events(
    event_type: str,
) -> None:
    from opensquilla.engine.agent_core import AGENT_CORE_PROTOCOL_VERSION, PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": event_type,
                "payload": {"marker": event_type},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(),
        session_key="agent:main:test",
    )

    with pytest.raises(RuntimeError, match="host-owned event"):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.parametrize(
    ("frame", "message"),
    [
        (
            {
                "protocol": "opensquilla.agent_core.v0",
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "old"},
            },
            "missing protocol",
        ),
        (
            {
                "protocol": "opensquilla.agent_core.v0",
                "kind": "event",
                "type": "done",
                "payload": {"text": "wrong version"},
            },
            "missing protocol",
        ),
        (
            {
                "protocol": ["opensquilla.agent_core.v1"],
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "ambiguous protocol"},
            },
            "frame protocol must be a string",
        ),
        (
            {
                "protocol": "   ",
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "blank protocol"},
            },
            "frame protocol must be non-empty",
        ),
        (
            {
                "protocol": " opensquilla.agent_core.v1 ",
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "protocol with whitespace"},
            },
            "frame protocol must not contain surrounding whitespace",
        ),
        (
            {
                "protocol": "opensquilla.agent_core.v1",
                "kind": "side_effect",
                "type": "text.delta",
                "payload": {"text": "unknown kind"},
            },
            "Unsupported Pi sidecar frame kind",
        ),
        (
            {
                "protocol": "opensquilla.agent_core.v1",
                "kind": "side_effect",
                "type": "done",
                "payload": {"text": "host-owned type with unknown kind"},
            },
            "Unsupported Pi sidecar frame kind",
        ),
        (
            {
                "protocol": "opensquilla.agent_core.v1",
                "kind": "intent",
                "type": "done",
                "payload": {"text": "host-owned type as intent"},
            },
            "Unsupported Pi sidecar intent",
        ),
        (
            {
                "protocol": "opensquilla.agent_core.v1",
                "kind": "event",
                "type": "thinking.delta",
                "payload": {"text": "unknown event"},
            },
            "Unsupported Pi sidecar event type",
        ),
        (
            {
                "protocol": "opensquilla.agent_core.v1",
                "kind": "event",
                "type": ["text.delta"],
                "payload": {"text": "ambiguous type"},
            },
            "frame type must be a string",
        ),
        (
            {
                "protocol": "opensquilla.agent_core.v1",
                "kind": "event",
                "type": "   ",
                "payload": {"text": "blank type"},
            },
            "frame type must be non-empty",
        ),
        (
            {
                "protocol": "opensquilla.agent_core.v1",
                "kind": "event",
                "type": " done ",
                "payload": {"text": "host-owned type with whitespace"},
            },
            "frame type must not contain surrounding whitespace",
        ),
        (
            {
                "protocol": "opensquilla.agent_core.v1",
                "kind": ["event"],
                "type": "done",
                "payload": {"text": "ambiguous kind"},
            },
            "frame kind must be a string",
        ),
        (
            {
                "protocol": "opensquilla.agent_core.v1",
                "kind": "   ",
                "type": "text.delta",
                "payload": {"text": "blank kind"},
            },
            "frame kind must be non-empty",
        ),
        (
            {
                "protocol": "opensquilla.agent_core.v1",
                "kind": " event ",
                "type": "text.delta",
                "payload": {"text": "kind with whitespace"},
            },
            "frame kind must not contain surrounding whitespace",
        ),
        (
            ["not", "an", "object"],
            "frame must be a JSON object",
        ),
        (
            {
                1: "non-json-key",
                "protocol": "opensquilla.agent_core.v1",
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "looks valid"},
            },
            "non-JSON object key at frame",
        ),
        (
            {
                "protocol": "opensquilla.agent_core.v1",
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "looks valid"},
                "debug": "shadow control",
            },
            "unsupported top-level field",
        ),
        (
            {
                "protocol": "opensquilla.agent_core.v1",
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "looks valid"},
                "debug": object(),
            },
            "unsupported top-level field",
        ),
        (
            {
                "protocol": "opensquilla.agent_core.v1",
                "kind": "event",
                "type": "done",
                "payload": ["not", "an", "object"],
            },
            "payload must be a JSON object",
        ),
        (
            {
                "protocol": "opensquilla.agent_core.v1",
                "kind": "event",
                "type": "done",
                "payload": {"python_only": object()},
            },
            "frame contains non-JSON value",
        ),
    ],
)
@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_unknown_or_mismatched_protocol_frames(
    frame,
    message: str,
) -> None:
    from opensquilla.engine.agent_core import PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield frame

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(),
        session_key="agent:main:test",
    )

    with pytest.raises(RuntimeError, match=message):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_non_object_event_payload_before_agent_event() -> None:
    from opensquilla.engine.agent_core import AGENT_CORE_PROTOCOL_VERSION, PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": ["not", "an", "object"],
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-event-payload"),
        session_key="agent:main:test",
    )

    with pytest.raises(RuntimeError, match="payload must be a JSON object"):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_non_string_text_delta_text() -> None:
    from opensquilla.engine.agent_core import AGENT_CORE_PROTOCOL_VERSION, PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": {"nested": "object"}},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-text-payload"),
        session_key="agent:main:test",
    )

    with pytest.raises(RuntimeError, match="text.delta text must be a string"):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event_type", "payload", "message"),
    [
        (
            "text.delta",
            {"text": "ok", "model": "sidecar-model"},
            "event 'text.delta' unsupported payload field: model",
        ),
        (
            "error",
            {"message": "failed", "code": "pi_error", "details": {"debug": True}},
            "event 'error' unsupported payload field: details",
        ),
    ],
)
async def test_pi_sidecar_kernel_rejects_unknown_event_payload_fields(
    event_type: str,
    payload: dict[str, Any],
    message: str,
) -> None:
    from opensquilla.engine.agent_core import AGENT_CORE_PROTOCOL_VERSION, PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": event_type,
                "payload": payload,
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-event-payload"),
        session_key="agent:main:test",
    )

    with pytest.raises(RuntimeError, match=message):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"message": {"nested": "object"}, "code": "pi_error"}, "error message must be a string"),
        ({"message": "failed", "code": {"nested": "object"}}, "error code must be a string"),
        ({"message": "failed", "code": "   "}, "error code must be non-empty"),
    ],
)
async def test_pi_sidecar_kernel_rejects_non_string_error_event_fields(
    payload: dict[str, Any],
    message: str,
) -> None:
    from opensquilla.engine.agent_core import AGENT_CORE_PROTOCOL_VERSION, PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "error",
                "payload": payload,
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-error-payload"),
        session_key="agent:main:test",
    )

    with pytest.raises(RuntimeError, match=message):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "intent_type",
    [
        "tool.hook.before",
        "tool.hook.after",
        "provider.hook.before",
        "provider.hook.after",
        "queue.enqueue",
        "queue.drain",
        "session.write.direct",
        "subagent.wake",
        "parent.wake",
        "turn.finalize",
    ],
)
async def test_pi_sidecar_kernel_rejects_pi_private_runtime_intents(
    intent_type: str,
) -> None:
    from opensquilla.engine.agent_core import AGENT_CORE_PROTOCOL_VERSION, PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": intent_type,
                "payload": {"marker": intent_type},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(),
        session_key="agent:main:test",
    )

    with pytest.raises(RuntimeError, match="Unsupported Pi sidecar intent"):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("intent_type", "message"),
    [
        (["provider.request"], "Pi sidecar intent type must be a string"),
        ({"type": "provider.request"}, "Pi sidecar intent type must be a string"),
        ("", "Pi sidecar intent type must be non-empty"),
        ("   ", "Pi sidecar intent type must be non-empty"),
    ],
)
async def test_pi_sidecar_kernel_rejects_structured_or_blank_intent_type_before_host_port(
    intent_type: object,
    message: str,
) -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": intent_type,
                "payload": {"messages": []},
            }

    class FakeProviderPort:
        async def handle_intent(self, **kwargs):
            _ = kwargs
            raise AssertionError("invalid intent type must not reach host port")

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(provider=FakeProviderPort()),
    )

    with pytest.raises(RuntimeError, match=message):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_non_object_intent_payload_before_host_port() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "provider.request",
                "payload": ["not", "an", "object"],
            }

    class FakeProviderPort:
        async def handle_intent(self, **kwargs):
            _ = kwargs
            raise AssertionError("invalid intent payload must not reach host port")

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(provider=FakeProviderPort()),
    )

    with pytest.raises(RuntimeError, match="payload must be a JSON object"):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_non_json_intent_payload_values_before_host_port() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class NonJsonPayloadValue:
        pass

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "provider.request",
                "payload": {"messages": [NonJsonPayloadValue()]},
            }

    class FakeProviderPort:
        async def handle_intent(self, **kwargs):
            _ = kwargs
            raise AssertionError("non-JSON intent payload must not reach host port")

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(provider=FakeProviderPort()),
    )

    with pytest.raises(RuntimeError, match="frame contains non-JSON value"):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_requires_host_provider_port_for_provider_intent() -> None:
    from opensquilla.engine.agent_core import AGENT_CORE_PROTOCOL_VERSION, PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "provider.request",
                "payload": {"messages": []},
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "host provider"},
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "host provider"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(),
        session_key="agent:main:test",
    )

    with pytest.raises(RuntimeError, match="KernelHostPorts.provider"):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_unknown_provider_fields_before_custom_port() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            _ = message, kwargs
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "provider.request",
                "payload": {
                    "messages": [{"role": "user", "content": "hello"}],
                    "provider_override": {"model": "sidecar-owned"},
                },
            }

    class FakeProviderPort:
        async def handle_intent(self, **kwargs):
            if "provider_override" in kwargs["payload"]:
                raise AssertionError(
                    "unknown provider intent field reached custom provider port"
                )
            return []

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-custom-provider-port"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(provider=FakeProviderPort()),
    )

    with pytest.raises(RuntimeError, match="provider.request unsupported payload field"):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.parametrize(
    ("intent_type", "payload", "host_port_name", "message"),
    [
        (
            "session.write.enqueue",
            {"content": "state", "sidecar_policy": {"write": "force"}},
            "session_writes",
            "session.write.enqueue unsupported payload field",
        ),
        (
            "queue.poll",
            {"task_id": "task-1", "sidecar_policy": {"wake": "force"}},
            "queue",
            "queue.poll unsupported payload field",
        ),
        (
            "savepoint.request",
            {"turn_id": "turn-1", "sidecar_policy": {"source": "force"}},
            "savepoints",
            "savepoint.request unsupported payload field",
        ),
        (
            "yield.request",
            {"message": "wait", "sidecar_policy": {"settle": "force"}},
            "orchestration",
            "yield.request unsupported payload field",
        ),
    ],
)
@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_unknown_host_port_intent_fields_before_custom_port(
    intent_type: str,
    payload: dict[str, Any],
    host_port_name: str,
    message: str,
) -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            _ = message, kwargs
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": intent_type,
                "payload": payload,
            }

    class FakeHostPort:
        async def handle_intent(self, **kwargs):
            if "sidecar_policy" in kwargs["payload"]:
                raise AssertionError(
                    "unknown host-port intent field reached custom host port"
                )
            return []

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-custom-host-port"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(**{host_port_name: FakeHostPort()}),
    )

    with pytest.raises(RuntimeError, match=message):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.parametrize(
    ("intent_type", "payload", "missing_port"),
    [
        (
            "tool.call.prepare",
            {"tool_call_id": "call-1", "tool_name": "read"},
            "tool_bridge",
        ),
        ("session.write.enqueue", {"role": "assistant", "content": "state"}, "session_writes"),
        ("queue.poll", {"task_id": "task-1"}, "queue"),
        ("savepoint.request", {"turn_id": "turn-1"}, "savepoints"),
        ("yield.request", {"message": "wait"}, "orchestration"),
    ],
)
@pytest.mark.asyncio
async def test_pi_sidecar_kernel_requires_required_host_ports(
    intent_type: str,
    payload: dict,
    missing_port: str,
) -> None:
    from opensquilla.engine.agent_core import AGENT_CORE_PROTOCOL_VERSION, PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": intent_type,
                "payload": payload,
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(),
        session_key="agent:main:test",
    )

    with pytest.raises(RuntimeError, match=f"KernelHostPorts.{missing_port}"):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_routes_provider_intent_to_host_port() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    calls: list[dict] = []

    class FakeProviderPort:
        async def handle_intent(self, **kwargs):
            calls.append(kwargs)
            return [TextDeltaEvent(text="host provider")]

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "provider.request",
                "payload": {"messages": []},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(provider=FakeProviderPort()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert _without_state_changes(events) == [
        TextDeltaEvent(text="host provider"),
        DoneEvent(text="host provider", model="", cost_source="unavailable"),
    ]
    assert calls == [
        {
            "intent_type": "provider.request",
            "payload": {"messages": []},
            "session_key": "agent:main:test",
        }
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_reports_host_intent_results_back_to_rpc_client() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakeProviderPort:
        async def handle_intent(self, **kwargs):
            _ = kwargs
            return [
                TextDeltaEvent(text="host provider"),
                DoneEvent(text="host provider", model="provider-model"),
            ]

    class FakePiRpcClient:
        def __init__(self) -> None:
            self.intent_results: list[dict[str, Any]] = []

        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "provider.request",
                "payload": {"messages": []},
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "host provider"},
            }

        async def receive_intent_result(
            self,
            *,
            intent_type: str,
            payload: dict[str, Any],
            events: list[Any],
            session_key: str,
        ) -> None:
            self.intent_results.append(
                {
                    "intent_type": intent_type,
                    "payload": payload,
                    "events": events,
                    "session_key": session_key,
                }
            )

    rpc_client = FakePiRpcClient()
    agent = PiSidecarKernelRuntime(
        rpc_client=rpc_client,
        config=SimpleNamespace(model_id="pi-intent-feedback"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(provider=FakeProviderPort()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert _without_state_changes(events) == [
        TextDeltaEvent(text="host provider"),
        DoneEvent(
            text="host provider",
            model="pi-intent-feedback",
            cost_source="unavailable",
        ),
    ]
    assert rpc_client.intent_results == [
        {
            "intent_type": "provider.request",
            "payload": {"messages": []},
            "events": [
                {"kind": "text_delta", "text": "host provider"},
                {
                    "baseline_model": "",
                    "billed_cost": 0.0,
                    "cache_hit_active": False,
                    "cache_write_tokens": 0,
                    "cached_tokens": 0,
                    "cost_source": "none",
                    "cost_usd": 0.0,
                    "input_tokens": 0,
                    "iterations": 0,
                    "kind": "done",
                    "model": "provider-model",
                    "output_tokens": 0,
                    "reasoning_content": None,
                    "reasoning_tokens": 0,
                    "routed_model": "",
                    "routed_tier": None,
                    "routing_applied": True,
                    "routing_confidence": 0.0,
                    "routing_source": "none",
                    "rollout_phase": "full",
                    "runtime_context_chars": 0,
                    "runtime_context_hash": None,
                    "savings_pct": 0.0,
                    "savings_usd": 0.0,
                    "session_totals": None,
                    "text": "host provider",
                    "total_savings_pct": 0.0,
                    "total_savings_usd": 0.0,
                },
            ],
            "session_key": "agent:main:test",
        }
    ]


@pytest.mark.asyncio
async def test_pi_provider_request_text_is_visible_only_after_sidecar_streams_it() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakeProviderPort:
        async def handle_intent(self, **kwargs):
            _ = kwargs
            return [TextDeltaEvent(text="host provider")]

    class FakePiRpcClient:
        def __init__(self) -> None:
            self.intent_results: list[dict[str, Any]] = []

        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "provider.request",
                "payload": {"messages": []},
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "host provider"},
            }

        async def receive_intent_result(
            self,
            *,
            intent_type: str,
            payload: dict[str, Any],
            events: list[Any],
            session_key: str,
        ) -> None:
            self.intent_results.append(
                {
                    "intent_type": intent_type,
                    "payload": payload,
                    "events": events,
                    "session_key": session_key,
                }
            )

    rpc_client = FakePiRpcClient()
    agent = PiSidecarKernelRuntime(
        rpc_client=rpc_client,
        config=SimpleNamespace(model_id="pi-provider-feedback-visibility"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(provider=FakeProviderPort()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert _without_state_changes(events) == [
        TextDeltaEvent(text="host provider"),
        DoneEvent(
            text="host provider",
            model="pi-provider-feedback-visibility",
            cost_source="unavailable",
        ),
    ]
    assert rpc_client.intent_results[0]["events"] == [
        {"kind": "text_delta", "text": "host provider"}
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_intent_feedback_cannot_mutate_host_events() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakeProviderPort:
        async def handle_intent(self, **kwargs):
            _ = kwargs
            return [TextDeltaEvent(text="host-owned text")]

    class FakePiRpcClient:
        def __init__(self) -> None:
            self.feedback_events: list[list[dict[str, Any]]] = []

        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "provider.request",
                "payload": {"messages": []},
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "sidecar text"},
            }

        async def receive_intent_result(
            self,
            *,
            intent_type: str,
            payload: dict[str, Any],
            events: list[Any],
            session_key: str,
        ) -> None:
            _ = intent_type, payload, session_key
            self.feedback_events.append(copy.deepcopy(events))
            events[0]["text"] = "sidecar-mutated"

    rpc_client = FakePiRpcClient()
    agent = PiSidecarKernelRuntime(
        rpc_client=rpc_client,
        config=SimpleNamespace(model_id="pi-intent-feedback-copy"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(provider=FakeProviderPort()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert _without_state_changes(events) == [
        TextDeltaEvent(text="sidecar text"),
        DoneEvent(
            text="sidecar text",
            model="pi-intent-feedback-copy",
            cost_source="unavailable",
        ),
    ]
    assert rpc_client.feedback_events == [
        [{"kind": "text_delta", "text": "host-owned text"}]
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_intent_feedback_failure_cannot_replace_host_events() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakeProviderPort:
        async def handle_intent(self, **kwargs):
            _ = kwargs
            return [TextDeltaEvent(text="host-owned text")]

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "provider.request",
                "payload": {"messages": []},
            }

        async def receive_intent_result(
            self,
            *,
            intent_type: str,
            payload: dict[str, Any],
            events: list[Any],
            session_key: str,
        ) -> None:
            _ = intent_type, payload, events, session_key
            raise OSError("feedback channel closed")

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-intent-feedback-failure"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(provider=FakeProviderPort()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert _without_state_changes(events) == [
        TextDeltaEvent(text="host-owned text"),
        DoneEvent(
            text="host-owned text",
            model="pi-intent-feedback-failure",
            cost_source="unavailable",
        ),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_emits_host_state_transitions_around_pi_intents() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakeProviderPort:
        async def handle_intent(self, **kwargs):
            _ = kwargs
            return []

    class FakeToolPort:
        async def handle_intent(self, **kwargs):
            payload = kwargs["payload"]
            if kwargs["intent_type"] == "tool.call.prepare":
                return [
                    ToolUseStartEvent(
                        tool_use_id=payload["tool_call_id"],
                        tool_name=payload["tool_name"],
                    )
                ]
            return [
                ToolResultEvent(
                    tool_use_id=payload["tool_call_id"],
                    tool_name=payload["tool_name"],
                    result="tool ok",
                )
            ]

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "provider.request",
                "payload": {"messages": [{"role": "user", "content": message}]},
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "tool.call.prepare",
                "payload": {"tool_call_id": "call-1", "tool_name": "echo_marker"},
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "tool.call.execute",
                "payload": {"tool_call_id": "call-1", "tool_name": "echo_marker"},
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "provider.request",
                "payload": {"messages": [{"role": "user", "content": message}]},
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "done"},
            }

        async def receive_intent_result(self, **kwargs) -> None:
            _ = kwargs

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-state"),
        session_key="agent:main:test",
        emit_state_events=True,
        host_ports=KernelHostPorts(
            provider=FakeProviderPort(),
            tool_bridge=FakeToolPort(),
        ),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        StateChangeEvent(from_state=AgentState.IDLE, to_state=AgentState.THINKING),
        StateChangeEvent(from_state=AgentState.THINKING, to_state=AgentState.STREAMING),
        ToolUseStartEvent(tool_use_id="call-1", tool_name="echo_marker"),
        StateChangeEvent(
            from_state=AgentState.STREAMING,
            to_state=AgentState.TOOL_CALLING,
        ),
        ToolResultEvent(
            tool_use_id="call-1",
            tool_name="echo_marker",
            result="tool ok",
        ),
        StateChangeEvent(
            from_state=AgentState.TOOL_CALLING,
            to_state=AgentState.THINKING,
        ),
        StateChangeEvent(from_state=AgentState.THINKING, to_state=AgentState.STREAMING),
        TextDeltaEvent(text="done"),
        StateChangeEvent(from_state=AgentState.STREAMING, to_state=AgentState.DONE),
        DoneEvent(text="done", model="pi-state", cost_source="unavailable"),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_can_coalesce_parallel_tool_state_transitions() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakeProviderPort:
        async def handle_intent(self, **kwargs):
            _ = kwargs
            return []

    class FakeToolPort:
        async def handle_intent(self, **kwargs):
            payload = kwargs["payload"]
            if kwargs["intent_type"] == "tool.call.prepare":
                return [
                    ToolUseStartEvent(
                        tool_use_id=payload["tool_call_id"],
                        tool_name=payload["tool_name"],
                    )
                ]
            return [
                ToolResultEvent(
                    tool_use_id=payload["tool_call_id"],
                    tool_name=payload["tool_name"],
                    result="tool ok",
                )
            ]

    class FakeOrchestrationPort:
        async def handle_intent(self, **kwargs):
            payload = kwargs["payload"]
            return [
                ToolResultEvent(
                    tool_use_id=payload["tool_call_id"],
                    tool_name="sessions_yield",
                    result='{"status":"yielded"}',
                    arguments={"reason": payload["reason"]},
                )
            ]

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            _ = kwargs
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "provider.request",
                "payload": {"messages": [{"role": "user", "content": message}]},
            }
            for tool_call_id, tool_name in (
                ("call-1", "sessions_spawn"),
                ("call-2", "sessions_send"),
            ):
                yield {
                    "protocol": AGENT_CORE_PROTOCOL_VERSION,
                    "kind": "intent",
                    "type": "tool.call.prepare",
                    "payload": {
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                    },
                }
            for tool_call_id, tool_name in (
                ("call-1", "sessions_spawn"),
                ("call-2", "sessions_send"),
            ):
                yield {
                    "protocol": AGENT_CORE_PROTOCOL_VERSION,
                    "kind": "intent",
                    "type": "tool.call.execute",
                    "payload": {
                        "tool_call_id": tool_call_id,
                        "tool_name": tool_name,
                    },
                }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "yield.request",
                "payload": {
                    "tool_call_id": "call-3",
                    "session_key": "agent:main:test",
                    "reason": "LIVE_AGENT_CORE_YIELD",
                },
            }

        async def receive_intent_result(self, **kwargs) -> None:
            _ = kwargs

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-state"),
        session_key="agent:main:test",
        emit_state_events=True,
        coalesce_tool_state_events=True,
        emit_yield_tool_start_events=True,
        host_ports=KernelHostPorts(
            provider=FakeProviderPort(),
            tool_bridge=FakeToolPort(),
            orchestration=FakeOrchestrationPort(),
        ),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        StateChangeEvent(from_state=AgentState.IDLE, to_state=AgentState.THINKING),
        StateChangeEvent(from_state=AgentState.THINKING, to_state=AgentState.STREAMING),
        ToolUseStartEvent(tool_use_id="call-1", tool_name="sessions_spawn"),
        ToolUseStartEvent(tool_use_id="call-2", tool_name="sessions_send"),
        StateChangeEvent(
            from_state=AgentState.STREAMING,
            to_state=AgentState.TOOL_CALLING,
        ),
        ToolResultEvent(
            tool_use_id="call-1",
            tool_name="sessions_spawn",
            result="tool ok",
        ),
        ToolResultEvent(
            tool_use_id="call-2",
            tool_name="sessions_send",
            result="tool ok",
        ),
        ToolUseStartEvent(tool_use_id="call-3", tool_name="sessions_yield"),
        ToolResultEvent(
            tool_use_id="call-3",
            tool_name="sessions_yield",
            result='{"status":"yielded"}',
            arguments={"reason": "LIVE_AGENT_CORE_YIELD"},
        ),
        StateChangeEvent(
            from_state=AgentState.TOOL_CALLING,
            to_state=AgentState.DONE,
        ),
        DoneEvent(text="", model="pi-state", cost_source="unavailable"),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_malformed_host_tool_result_is_rejected_before_feedback() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class PythonOnlyValue:
        pass

    class FakeToolPort:
        async def handle_intent(self, **kwargs):
            return [
                ToolResultEvent(
                    tool_use_id=kwargs["payload"]["tool_call_id"],
                    tool_name=kwargs["payload"]["tool_name"],
                    result="host result",
                    arguments={"value": PythonOnlyValue()},
                )
            ]

    class FakePiRpcClient:
        def __init__(self) -> None:
            self.feedback_calls = 0

        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "tool.call.prepare",
                "payload": {"tool_call_id": "call-1", "tool_name": "echo"},
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "tool.call.execute",
                "payload": {"tool_call_id": "call-1", "tool_name": "echo"},
            }

        async def receive_intent_result(self, **kwargs) -> None:
            _ = kwargs
            self.feedback_calls += 1

    rpc_client = FakePiRpcClient()
    agent = PiSidecarKernelRuntime(
        rpc_client=rpc_client,
        config=SimpleNamespace(model_id="pi-feedback-json-failure"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(tool_bridge=FakeToolPort()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        ErrorEvent(
            message=(
                "KernelHostPorts returned malformed ToolResultEvent: "
                "arguments must be JSON-safe"
            ),
            code="pi_sidecar_error",
        )
    ]
    assert rpc_client.feedback_calls == 0


@pytest.mark.asyncio
async def test_pi_sidecar_tool_arguments_are_copied_before_host_execution() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class MutatingToolBridge:
        async def handle_intent(self, **kwargs):
            if kwargs["intent_type"] == "tool.call.execute":
                arguments = kwargs["payload"]["arguments"]
                arguments["nested"]["value"] = "mutated"
                return [
                    ToolResultEvent(
                        tool_use_id=kwargs["payload"]["tool_call_id"],
                        tool_name=kwargs["payload"]["tool_name"],
                        result="host result",
                    )
                ]
            return []

    class FakePiRpcClient:
        def __init__(self) -> None:
            self.intent_results: list[dict[str, Any]] = []

        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "tool.call.prepare",
                "payload": {"tool_call_id": "call-1", "tool_name": "read"},
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "tool.call.execute",
                "payload": {
                    "tool_call_id": "call-1",
                    "tool_name": "read",
                    "arguments": {"nested": {"value": "original"}},
                },
            }

        async def receive_intent_result(
            self,
            *,
            intent_type: str,
            payload: dict[str, Any],
            events: list[Any],
            session_key: str,
        ) -> None:
            _ = events, session_key
            self.intent_results.append({"intent_type": intent_type, "payload": payload})

    rpc_client = FakePiRpcClient()
    agent = PiSidecarKernelRuntime(
        rpc_client=rpc_client,
        config=SimpleNamespace(model_id="pi-copy"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(tool_bridge=MutatingToolBridge()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        ToolResultEvent(
            tool_use_id="call-1",
            tool_name="read",
            result="host result",
        ),
        DoneEvent(text="", model="pi-copy", cost_source="unavailable"),
    ]
    assert rpc_client.intent_results[-1]["payload"] == {
        "tool_call_id": "call-1",
        "tool_name": "read",
        "arguments": {"nested": {"value": "original"}},
    }


@pytest.mark.asyncio
async def test_pi_provider_request_rejects_unknown_payload_fields_before_provider_call() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools, config
            raise AssertionError("unknown provider.request field must not reach provider")

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="host-model"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    with pytest.raises(
        RuntimeError,
        match="provider.request unsupported payload field",
    ):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={
                "messages": [{"role": "user", "content": "hello"}],
                "provider_override": {"model": "sidecar-owned"},
            },
        )


@pytest.mark.asyncio
async def test_pi_provider_request_injects_host_runtime_context_before_provider_chat() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.provider import DoneEvent as ProviderDoneEvent

    captured_messages: list[Any] = []

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = tools, config
            captured_messages.extend(messages)
            yield ProviderDoneEvent(model="provider-model")

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="host-model"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    await port.handle_intent(
        intent_type="provider.request",
        session_key="agent:main:test",
        payload={
            "messages": [{"role": "user", "content": "hello"}],
            "_host_runtime_context": "[Runtime context for this turn]\nfixed",
            "_host_runtime_context_hash": "ctx-hash",
            "_host_runtime_context_chars": 37,
        },
    )

    assert len(captured_messages) == 1
    assert captured_messages[0].role == "user"
    assert (
        captured_messages[0].content
        == "hello\n\n[Runtime context for this turn]\nfixed"
    )


@pytest.mark.parametrize(
    ("bad_tools", "message"),
    [
        ({"name": "not-a-list"}, "provider.request tools must be a list"),
        ([{"name": object()}], "Pi sidecar JSON"),
    ],
)
@pytest.mark.asyncio
async def test_pi_provider_request_rejects_malformed_sidecar_tools_before_provider_call(
    bad_tools: object,
    message: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.provider import DoneEvent as ProviderDoneEvent

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools, config
            yield ProviderDoneEvent(model="provider-model")

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="host-model"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    with pytest.raises(RuntimeError, match=message):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={
                "messages": [{"role": "user", "content": "hello"}],
                "tools": bad_tools,
            },
        )


@pytest.mark.parametrize(
    ("bad_config", "message"),
    [
        (["not", "an", "object"], "provider.request config must be an object"),
        ({"opaque": object()}, "Pi sidecar JSON"),
    ],
)
@pytest.mark.asyncio
async def test_pi_provider_request_rejects_malformed_sidecar_config_before_provider_call(
    bad_config: object,
    message: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.provider import DoneEvent as ProviderDoneEvent

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools, config
            yield ProviderDoneEvent(model="provider-model")

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="host-model"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    with pytest.raises(RuntimeError, match=message):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={
                "messages": [{"role": "user", "content": "hello"}],
                "config": bad_config,
            },
        )


@pytest.mark.asyncio
async def test_pi_provider_host_port_uses_host_owned_chat_config() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.provider import DoneEvent as ProviderDoneEvent
    from opensquilla.provider.types import ModelCapabilities

    seen_configs: list[Any] = []
    seen_tools: list[Any] = []
    host_capabilities = ModelCapabilities(supports_vision=True)
    host_tools = [{"name": "host_tool"}]

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages
            seen_tools.append(tools)
            seen_configs.append(config)
            yield ProviderDoneEvent(model="provider-model")

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tools=[],
        tool_definitions=host_tools,
        config=SimpleNamespace(
            model_id="host-model",
            max_tokens=128,
            temperature=0.2,
            system_prompt="host system",
            request_timeout=9.0,
            cache_breakpoints=[{"type": "ephemeral"}],
            cache_mode="on",
            model_capabilities=host_capabilities,
            provider_request_proof_max_chars=1234,
        ),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    events = await port.handle_intent(
        intent_type="provider.request",
        session_key="agent:main:test",
        payload={
            "messages": [{"role": "user", "content": "hello"}],
            "tools": [{"name": "sidecar_tool"}],
            "config": {
                "max_tokens": 999,
                "temperature": 0.9,
                "system": "sidecar system",
                "timeout": 99.0,
                "cache_breakpoints": [{"type": "sidecar"}],
                "cache_mode": "off",
                "model_capabilities": ModelCapabilities(supports_reasoning=True),
                "provider_request_max_chars": 0,
            },
        },
    )

    assert events == [
        DoneEvent(
            text="",
            model="provider-model",
            iterations=1,
            cost_source="unavailable",
        )
    ]
    assert seen_configs[0] is not None
    assert len(seen_configs) == 1
    assert seen_tools == [host_tools]
    config = seen_configs[0]
    assert config.max_tokens == 128
    assert config.temperature == 0.2
    assert config.system == "host system"
    assert config.timeout == 9.0
    assert config.cache_breakpoints == [{"type": "ephemeral"}]
    assert config.cache_mode == "on"
    assert config.model_capabilities == host_capabilities
    assert config.provider_request_max_chars == 1234


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model_id",
    [{"not": "a string"}, 0],
    ids=["structured", "falsy-non-string"],
)
async def test_pi_provider_host_port_rejects_structured_fallback_model_id(
    model_id: Any,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.provider import DoneEvent as ProviderDoneEvent

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools, config
            yield ProviderDoneEvent(model="")

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id=model_id),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    with pytest.raises(RuntimeError, match="provider config model_id must be a string"):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={"messages": [{"role": "user", "content": "hello"}]},
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("thinking_name", "prompt"),
    [
        ("high", "hello"),
        ("adaptive", "adaptive thinking prompt " * 1000),
    ],
    ids=["high", "adaptive"],
)
async def test_pi_provider_host_port_preserves_host_thinking_level(
    thinking_name: str,
    prompt: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.engine.types import AgentConfig, ThinkingLevel
    from opensquilla.provider import DoneEvent as ProviderDoneEvent

    thinking = ThinkingLevel(thinking_name)
    seen_configs: list[Any] = []

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools
            seen_configs.append(config)
            yield ProviderDoneEvent(model="provider-model")

    host_config = AgentConfig(
        model_id="host-model",
        thinking=thinking,
    )
    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=host_config,
    )
    port = OpenSquillaProviderHostPort(host_agent)

    await port.handle_intent(
        intent_type="provider.request",
        session_key="agent:main:test",
        payload={"messages": [{"role": "user", "content": prompt}]},
    )

    expected_thinking, expected_budget = host_config.resolve_thinking(prompt=prompt)
    assert len(seen_configs) == 1
    config = seen_configs[0]
    assert config.thinking is expected_thinking
    assert config.thinking_level == thinking
    assert config.thinking_budget_tokens == expected_budget


@pytest.mark.asyncio
async def test_pi_provider_request_copies_host_tool_definitions_for_provider() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.provider import DoneEvent as ProviderDoneEvent

    host_tools = [{"name": "host_tool", "parameters": {"path": "README.md"}}]

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, config
            tools[0]["parameters"]["path"] = "mutated"
            yield ProviderDoneEvent(model="provider-model")

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=host_tools,
        config=SimpleNamespace(model_id="host-model"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    await port.handle_intent(
        intent_type="provider.request",
        session_key="agent:main:test",
        payload={
            "messages": [{"role": "user", "content": "hello"}],
            "tools": [{"name": "sidecar_tool"}],
        },
    )

    assert host_tools == [{"name": "host_tool", "parameters": {"path": "README.md"}}]


@pytest.mark.asyncio
async def test_pi_provider_request_copies_mutable_host_chat_config_fields() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.provider import DoneEvent as ProviderDoneEvent

    cache_breakpoints = [{"type": "ephemeral"}]

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools
            config.cache_breakpoints[0]["type"] = "mutated"
            yield ProviderDoneEvent(model="provider-model")

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(
            model_id="host-model",
            cache_breakpoints=cache_breakpoints,
        ),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    await port.handle_intent(
        intent_type="provider.request",
        session_key="agent:main:test",
        payload={"messages": [{"role": "user", "content": "hello"}]},
    )

    assert cache_breakpoints == [{"type": "ephemeral"}]


@pytest.mark.asyncio
async def test_pi_provider_request_preserves_host_stop_sequences() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.provider import DoneEvent as ProviderDoneEvent

    stop_sequences = ["END"]
    seen_stop_sequences: list[list[str]] = []

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools
            seen_stop_sequences.append(list(config.stop_sequences))
            config.stop_sequences.append("MUTATED")
            yield ProviderDoneEvent(model="provider-model")

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(
            model_id="host-model",
            stop_sequences=stop_sequences,
        ),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    await port.handle_intent(
        intent_type="provider.request",
        session_key="agent:main:test",
        payload={"messages": [{"role": "user", "content": "hello"}]},
    )

    assert seen_stop_sequences == [["END"]]
    assert stop_sequences == ["END"]


@pytest.mark.asyncio
async def test_pi_kernel_preserves_lightweight_host_provider_config_fields() -> None:
    from opensquilla.engine.agent_core import AGENT_CORE_PROTOCOL_VERSION, build_agent_for_kernel
    from opensquilla.provider import DoneEvent as ProviderDoneEvent

    seen_configs: list[Any] = []
    cache_breakpoints = [{"type": "ephemeral"}]

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            _ = message, kwargs
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "provider.request",
                "payload": {"messages": [{"role": "user", "content": "hello"}]},
            }

    class FakeProvider:
        async def chat(self, messages, *, tools=None, config=None):
            _ = messages, tools
            seen_configs.append(config)
            yield ProviderDoneEvent(model="provider-model")

    agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_client=FakePiRpcClient(),
            allow_test_pi_rpc_client=True,
        ),
        provider=FakeProvider(),
        config=SimpleNamespace(
            model_id="pi-light-config",
            system_prompt="light system",
            max_tokens=321,
            temperature=0.4,
            request_timeout=7.0,
            cache_breakpoints=cache_breakpoints,
            cache_mode="on",
            provider_request_proof_max_chars=777,
            thinking=True,
            thinking_budget_tokens=12345,
            stop_sequences=["DONE"],
        ),
        tool_definitions=[],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:pi-light-config",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )

    _ = [event async for event in agent.run_turn("hello")]

    assert len(seen_configs) == 1
    config = seen_configs[0]
    assert config.max_tokens == 321
    assert config.temperature == 0.4
    assert config.system == "light system"
    assert config.timeout == 7.0
    assert config.cache_breakpoints == [{"type": "ephemeral"}]
    assert config.cache_mode == "on"
    assert config.provider_request_max_chars == 777
    assert config.thinking is True
    assert config.thinking_budget_tokens == 12345
    assert config.stop_sequences == ["DONE"]


@pytest.mark.asyncio
async def test_pi_kernel_provider_request_uses_refreshed_host_system_prompt() -> None:
    from opensquilla.engine.agent_core import AGENT_CORE_PROTOCOL_VERSION, build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig
    from opensquilla.provider import DoneEvent as ProviderDoneEvent

    seen_system_prompts: list[str | None] = []

    class FakePiRpcClient:
        def stream_prompt(self, message: str, **kwargs: Any):
            _ = message, kwargs
            return self._stream()

        async def _stream(self):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "provider.request",
                "payload": {"messages": [{"role": "user", "content": "hello"}]},
            }

    class FakeProvider:
        async def chat(self, messages, *, tools=None, config=None):
            _ = messages, tools
            seen_system_prompts.append(config.system if config is not None else None)
            yield ProviderDoneEvent(model="provider-model")

    agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_client=FakePiRpcClient(),
            allow_test_pi_rpc_client=True,
        ),
        provider=FakeProvider(),
        config=AgentConfig(
            model_id="pi-refreshed-system",
            system_prompt="initial system",
        ),
        tool_definitions=[],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:pi-refreshed-system",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )

    agent.refresh_system_prompt("refreshed system")
    events = [event async for event in agent.run_turn("hello", extra_messages=None)]

    assert seen_system_prompts == ["refreshed system"]
    assert events == [
        DoneEvent(
            text="",
            model="provider-model",
            iterations=1,
            cost_source="unavailable",
        )
    ]


def test_pi_kernel_refreshes_shared_host_agent_once() -> None:
    from opensquilla.engine.agent_core import (
        KernelHostPorts,
        OpenSquillaProviderHostPort,
        OpenSquillaToolBridgeHostPort,
        PiSidecarKernelRuntime,
    )

    class FakePiRpcClient:
        def stream_prompt(self, message: str, **kwargs: Any):
            raise AssertionError("refresh should not start sidecar stream")

    class FakeHostAgent:
        def __init__(self) -> None:
            self.config = SimpleNamespace(model_id="pi-refresh-once")
            self.tool_definitions: list[Any] = []
            self.refresh_count = 0
            self.system_prompts: list[str] = []

        def refresh_system_prompt(self, system_prompt: str) -> None:
            self.refresh_count += 1
            self.system_prompts.append(system_prompt)

    host_agent = FakeHostAgent()
    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-refresh-once"),
        session_key="agent:main:pi-refresh-once",
        tool_definitions=[],
        host_ports=KernelHostPorts(
            provider=OpenSquillaProviderHostPort(host_agent),
            tool_bridge=OpenSquillaToolBridgeHostPort(host_agent),
        ),
    )

    agent.refresh_system_prompt("refreshed once")

    assert host_agent.refresh_count == 1
    assert host_agent.system_prompts == ["refreshed once"]


@pytest.mark.asyncio
async def test_pi_provider_request_copies_message_objects_before_provider_chat() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.provider import DoneEvent as ProviderDoneEvent
    from opensquilla.provider import Message

    message = Message(role="user", content="original")

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = tools, config
            messages[0].content = "mutated"
            yield ProviderDoneEvent(model="provider-model")

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="pi-provider-message-copy"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    await port.handle_intent(
        intent_type="provider.request",
        session_key="agent:main:test",
        payload={"messages": [message]},
    )

    assert message.content == "original"


@pytest.mark.asyncio
@pytest.mark.parametrize("message_shape", ["dict", "model"])
async def test_pi_provider_request_rejects_python_only_message_values_before_provider_chat(
    message_shape: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.provider import ContentBlockToolUse, Message

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools, config
            raise AssertionError("Python-only provider message must not reach provider")
            yield

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="pi-provider-message-json"),
    )
    port = OpenSquillaProviderHostPort(host_agent)
    if message_shape == "dict":
        message: object = {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "call-1",
                    "name": "read",
                    "input": {"opaque": object()},
                }
            ],
        }
    else:
        message = Message(
            role="assistant",
            content=[
                ContentBlockToolUse(
                    id="call-1",
                    name="read",
                    input={"opaque": object()},
                )
            ],
        )

    with pytest.raises(RuntimeError, match="Pi sidecar JSON"):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={"messages": [message]},
        )


@pytest.mark.asyncio
async def test_pi_sidecar_provider_request_rejects_invalid_message_payloads() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools, config
            raise AssertionError("invalid provider messages must not reach provider")

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="pi-provider-validation"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    with pytest.raises(ValueError, match="Invalid provider.request message"):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={
                "messages": [
                    {"role": "user", "content": "ok"},
                    {"role": "system", "content": "sidecar-owned system"},
                ],
            },
        )


@pytest.mark.asyncio
async def test_pi_provider_request_repairs_orphaned_tool_use_before_provider_chat() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.provider import DoneEvent as ProviderDoneEvent

    captured_messages: list[Any] = []

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = tools, config
            captured_messages.extend(messages)
            yield ProviderDoneEvent(model="provider-model")

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="pi-provider-tool-pairing"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    await port.handle_intent(
        intent_type="provider.request",
        session_key="agent:main:test",
        payload={
            "messages": [
                {"role": "user", "content": "please calculate"},
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "orphan-call-1",
                            "name": "calculate",
                            "input": {"expression": "25 * 18"},
                        }
                    ],
                },
                {"role": "user", "content": "never mind, answer 2+2"},
            ],
        },
    )

    assert [(message.role, message.content) for message in captured_messages] == [
        ("user", "please calculate"),
        ("user", "never mind, answer 2+2"),
    ]


@pytest.mark.asyncio
async def test_pi_provider_request_normalizes_openai_tool_calls_before_provider_chat() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.provider import DoneEvent as ProviderDoneEvent

    captured_messages: list[Any] = []

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = tools, config
            captured_messages.extend(messages)
            yield ProviderDoneEvent(model="provider-model")

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="pi-provider-tool-call-normalize"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    await port.handle_intent(
        intent_type="provider.request",
        session_key="agent:main:test",
        payload={
            "messages": [
                {"role": "user", "content": "please calculate"},
                {
                    "role": "assistant",
                    "content": "calling tool",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "calculate",
                                "arguments": '{"expression":"25 * 18"}',
                            },
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "call-1",
                            "content": "450",
                        }
                    ],
                },
                {"role": "user", "content": "continue"},
            ],
        },
    )

    assistant = captured_messages[1]
    assert assistant.role == "assistant"
    assert [block.type for block in assistant.content] == ["text", "tool_use"]
    tool_use = assistant.content[1]
    assert tool_use.id == "call-1"
    assert tool_use.name == "calculate"
    assert tool_use.input == {"expression": "25 * 18"}


@pytest.mark.parametrize("bad_tool_call", ["read", ["read"]])
@pytest.mark.asyncio
async def test_pi_provider_request_rejects_non_object_message_tool_call_entries(
    bad_tool_call: object,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools, config
            raise AssertionError(
                "malformed provider message tool_call must not reach provider"
            )
            yield

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="pi-provider-validation"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    with pytest.raises(
        ValueError,
        match="provider.request message at index 0 tool_calls entries must be objects",
    ):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={
                "messages": [
                    {
                        "role": "assistant",
                        "content": "state",
                        "tool_calls": [bad_tool_call],
                    }
                ],
            },
        )


@pytest.mark.asyncio
async def test_pi_provider_request_rejects_non_object_openai_tool_call_arguments() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools, config
            raise AssertionError("malformed provider message tool arguments reached provider")
            yield

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="pi-provider-validation"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    with pytest.raises(ValueError, match="function.arguments must be an object"):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={
                "messages": [
                    {
                        "role": "assistant",
                        "content": "calling",
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "type": "function",
                                "function": {
                                    "name": "calculate",
                                    "arguments": "[1, 2]",
                                },
                            }
                        ],
                    }
                ],
            },
        )


@pytest.mark.asyncio
async def test_pi_provider_request_rejects_unsupported_openai_tool_call_type() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools, config
            raise AssertionError("unsupported provider message tool call reached provider")
            yield

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="pi-provider-validation"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    with pytest.raises(ValueError, match="tool_calls\\[0\\].type must be 'function'"):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={
                "messages": [
                    {
                        "role": "assistant",
                        "content": "calling",
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "type": "custom",
                                "function": {
                                    "name": "calculate",
                                    "arguments": "{}",
                                },
                            }
                        ],
                    }
                ],
            },
        )


@pytest.mark.asyncio
async def test_pi_provider_request_rejects_empty_messages_after_tool_pairing_repair() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools, config
            raise AssertionError("empty repaired provider messages reached provider")
            yield

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="pi-provider-validation"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    with pytest.raises(ValueError, match="provider.request messages are empty after repair"):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={
                "messages": [
                    {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "orphan-call-1",
                                "name": "calculate",
                                "input": {"expression": "25 * 18"},
                            }
                        ],
                    }
                ],
            },
        )


@pytest.mark.asyncio
async def test_pi_provider_request_rejects_sidecar_owned_compaction_blocks() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools, config
            raise AssertionError("sidecar compaction blocks must not reach provider")
            yield

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="pi-provider-validation"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    with pytest.raises(ValueError, match="host-owned compaction"):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "compaction",
                                "content": "sidecar state",
                                "cache_control": {"type": "ephemeral"},
                            }
                        ],
                    }
                ],
            },
        )


@pytest.mark.asyncio
async def test_pi_provider_request_allows_host_authored_compaction_blocks() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.provider import (
        ContentBlockCompaction,
        Message,
    )
    from opensquilla.provider import (
        DoneEvent as ProviderDoneEvent,
    )

    captured: dict[str, object] = {}

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = tools, config
            captured["messages"] = messages
            yield ProviderDoneEvent(model="provider-model")

    host_compaction = ContentBlockCompaction(
        content="host state",
        cache_control={"type": "ephemeral"},
    )
    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="pi-provider-validation"),
        _history=[
            Message(
                role="assistant",
                content=[host_compaction],
            )
        ],
    )
    port = OpenSquillaProviderHostPort(host_agent)

    await port.handle_intent(
        intent_type="provider.request",
        session_key="agent:main:test",
        payload={
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "compaction",
                            "content": "host state",
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                }
            ],
        },
    )

    messages = captured["messages"]
    assert isinstance(messages, list)
    block = messages[0].content[0]
    assert isinstance(block, ContentBlockCompaction)
    assert block.content == "host state"
    assert block.cache_control == {"type": "ephemeral"}


@pytest.mark.asyncio
async def test_pi_provider_request_rejects_sidecar_owned_reasoning_controls() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools, config
            raise AssertionError("sidecar reasoning controls must not reach provider")
            yield

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="pi-provider-validation"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    with pytest.raises(ValueError, match="host-owned reasoning_content"):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={
                "messages": [
                    {
                        "role": "assistant",
                        "content": "assistant text",
                        "reasoning_content": "sidecar reasoning",
                    }
                ],
            },
        )

    with pytest.raises(ValueError, match="host-owned thinking block"):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={
                "messages": [
                    {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "thinking",
                                "thinking": "sidecar reasoning",
                                "signature": "sidecar-signature",
                            }
                        ],
                    }
                ],
            },
        )


@pytest.mark.asyncio
async def test_pi_provider_request_allows_host_authored_reasoning_controls() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.provider import ContentBlockThinking, Message
    from opensquilla.provider import DoneEvent as ProviderDoneEvent

    captured: dict[str, object] = {}

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = tools, config
            captured["messages"] = messages
            yield ProviderDoneEvent(model="provider-model")

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="pi-provider-validation"),
        _history=[
            Message(
                role="assistant",
                content=[
                    ContentBlockThinking(
                        thinking="host reasoning",
                        signature="host-signature",
                    )
                ],
                reasoning_content="host reasoning",
            )
        ],
    )
    port = OpenSquillaProviderHostPort(host_agent)

    await port.handle_intent(
        intent_type="provider.request",
        session_key="agent:main:test",
        payload={
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "thinking",
                            "thinking": "host reasoning",
                            "signature": "host-signature",
                        }
                    ],
                    "reasoning_content": "host reasoning",
                }
            ],
        },
    )

    messages = captured["messages"]
    assert isinstance(messages, list)
    assert messages[0].reasoning_content == "host reasoning"
    block = messages[0].content[0]
    assert isinstance(block, ContentBlockThinking)
    assert block.thinking == "host reasoning"
    assert block.signature == "host-signature"


@pytest.mark.asyncio
async def test_pi_provider_request_rejects_non_list_messages_before_provider_call() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools, config
            raise AssertionError("non-list provider messages must not reach provider")
            yield

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="pi-provider-validation"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    with pytest.raises(ValueError, match="provider.request messages must be a list"):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={"messages": {"role": "user", "content": "not a list"}},
        )


@pytest.mark.parametrize("field", ["prompt", "message"])
@pytest.mark.asyncio
async def test_pi_provider_request_rejects_non_string_prompt_fallback_before_provider(
    field: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools, config
            raise AssertionError("non-string provider prompt must not reach provider")
            yield

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="host-model"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    with pytest.raises(ValueError, match=f"provider.request {field} must be a string"):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={field: {"nested": "object"}},
        )


@pytest.mark.parametrize("field", ["prompt", "message"])
@pytest.mark.asyncio
async def test_pi_provider_request_rejects_explicit_null_prompt_fallback_before_provider(
    field: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools, config
            raise AssertionError("null provider prompt must not reach provider")
            yield

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="host-model"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    with pytest.raises(ValueError, match=f"provider.request {field} must be a string"):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={field: None},
        )


@pytest.mark.parametrize(("field", "value"), [("prompt", ""), ("message", " \n\t")])
@pytest.mark.asyncio
async def test_pi_provider_request_rejects_blank_prompt_fallback_before_provider(
    field: str,
    value: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools, config
            raise AssertionError("blank provider prompt must not reach provider")
            yield

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="host-model"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    with pytest.raises(ValueError, match=f"provider.request {field} must be non-empty"):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={field: value},
        )


@pytest.mark.asyncio
async def test_pi_provider_request_requires_user_input_before_provider_call() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools, config
            raise AssertionError("empty provider.request payload must not reach provider")
            yield

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="host-model"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    with pytest.raises(
        ValueError,
        match="provider.request requires messages, prompt, or message",
    ):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={},
        )


@pytest.mark.asyncio
async def test_pi_provider_request_rejects_cross_session_target() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools, config
            raise AssertionError("provider.request must reject before provider call")
            yield

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="host-model"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    with pytest.raises(
        RuntimeError,
        match="Pi sidecar provider.request cannot target a different session_key",
    ):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={
                "session_key": "agent:other:test",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )


@pytest.mark.asyncio
async def test_pi_host_owned_intents_reject_non_string_session_key_before_host_call() -> None:
    from opensquilla.engine.agent_core import (
        OpenSquillaOrchestrationHostPort,
        OpenSquillaProviderHostPort,
        OpenSquillaSavepointHostPort,
        OpenSquillaSessionWritesHostPort,
    )
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools, config
            raise AssertionError("invalid provider.request session_key must not reach provider")
            yield

    class FakeSessionManager:
        async def append_message(self, session_key: str, **kwargs):
            _ = session_key, kwargs
            raise AssertionError(
                "invalid session.write.enqueue session_key must not reach SessionManager"
            )

        async def record_memory_checkpoint(self, session_key, transcript, **kwargs):
            _ = session_key, transcript, kwargs
            raise AssertionError(
                "invalid savepoint.request session_key must not reach SessionManager"
            )

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("invalid yield.request session_key must not reach host tool")

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            _ = tool_call
            return result

    provider_port = OpenSquillaProviderHostPort(
        SimpleNamespace(
            provider=FakeProvider(),
            tool_definitions=[],
            config=SimpleNamespace(model_id="host-model"),
        )
    )
    session_manager = FakeSessionManager()
    cases = [
        (
            provider_port,
            "provider.request",
            {"session_key": {"nested": "object"}, "prompt": "hello"},
        ),
        (
            OpenSquillaSessionWritesHostPort(session_manager=session_manager),
            "session.write.enqueue",
            {
                "session_key": {"nested": "object"},
                "role": "assistant",
                "content": "state",
            },
        ),
        (
            OpenSquillaOrchestrationHostPort(FakeHostAgent()),
            "yield.request",
            {"session_key": {"nested": "object"}, "message": "yield"},
        ),
        (
            OpenSquillaSavepointHostPort(session_manager=session_manager),
            "savepoint.request",
            {
                "session_key": {"nested": "object"},
                "transcript": [{"role": "assistant", "content": "state"}],
            },
        ),
    ]

    for port, intent_type, payload in cases:
        with pytest.raises(RuntimeError, match=f"{intent_type} session_key must be a string"):
            await port.handle_intent(
                intent_type=intent_type,
                payload=payload,
                session_key="agent:main:test",
            )


@pytest.mark.asyncio
async def test_pi_host_owned_intents_reject_explicit_null_session_key_before_host_call() -> None:
    from opensquilla.engine.agent_core import (
        OpenSquillaOrchestrationHostPort,
        OpenSquillaProviderHostPort,
        OpenSquillaSavepointHostPort,
        OpenSquillaSessionWritesHostPort,
    )
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools, config
            raise AssertionError("null provider.request session_key must not reach provider")
            yield

    class FakeSessionManager:
        async def append_message(self, session_key: str, **kwargs):
            _ = session_key, kwargs
            raise AssertionError(
                "null session.write.enqueue session_key must not reach SessionManager"
            )

        async def record_memory_checkpoint(self, session_key, transcript, **kwargs):
            _ = session_key, transcript, kwargs
            raise AssertionError(
                "null savepoint.request session_key must not reach SessionManager"
            )

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("null yield.request session_key must not reach host tool")

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            _ = tool_call
            return result

    provider_port = OpenSquillaProviderHostPort(
        SimpleNamespace(
            provider=FakeProvider(),
            tool_definitions=[],
            config=SimpleNamespace(model_id="host-model"),
        )
    )
    session_manager = FakeSessionManager()
    cases = [
        (
            provider_port,
            "provider.request",
            {"session_key": None, "prompt": "hello"},
        ),
        (
            OpenSquillaSessionWritesHostPort(session_manager=session_manager),
            "session.write.enqueue",
            {
                "session_key": None,
                "role": "assistant",
                "content": "state",
            },
        ),
        (
            OpenSquillaOrchestrationHostPort(FakeHostAgent()),
            "yield.request",
            {"session_key": None, "message": "yield"},
        ),
        (
            OpenSquillaSavepointHostPort(session_manager=session_manager),
            "savepoint.request",
            {
                "session_key": None,
                "transcript": [{"role": "assistant", "content": "state"}],
            },
        ),
    ]

    for port, intent_type, payload in cases:
        with pytest.raises(RuntimeError, match=f"{intent_type} session_key must be a string"):
            await port.handle_intent(
                intent_type=intent_type,
                payload=payload,
                session_key="agent:main:test",
            )


@pytest.mark.asyncio
async def test_pi_provider_host_port_preserves_provider_heartbeats() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.provider import DoneEvent as ProviderDoneEvent
    from opensquilla.provider import ProviderHeartbeatEvent
    from opensquilla.provider import TextDeltaEvent as ProviderTextDeltaEvent

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools, config
            yield ProviderHeartbeatEvent(phase="llm_fallback", message="retrying")
            yield ProviderTextDeltaEvent(text="after heartbeat")
            yield ProviderDoneEvent(model="provider-model")

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="host-model"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    events = await port.handle_intent(
        intent_type="provider.request",
        session_key="agent:main:test",
        payload={"messages": [{"role": "user", "content": "hello"}]},
    )

    assert events == [
        RunHeartbeatEvent(phase="llm_fallback", message="retrying"),
        TextDeltaEvent(text="after heartbeat"),
        DoneEvent(
            text="after heartbeat",
            model="provider-model",
            iterations=1,
            cost_source="unavailable",
        ),
    ]



@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_event", "match"),
    [
        (
            "text",
            "provider text.delta text must be a string",
        ),
        (
            "error",
            "provider error message must be a string",
        ),
        (
            "heartbeat",
            "provider heartbeat phase must be a string",
        ),
        (
            "error_code",
            "provider error code must be a string",
        ),
        (
            "heartbeat_message",
            "provider heartbeat message must be a string",
        ),
    ],
)
async def test_pi_provider_host_port_rejects_non_string_public_provider_event_fields(
    provider_event: str,
    match: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.provider import ErrorEvent as ProviderErrorEvent
    from opensquilla.provider import ProviderHeartbeatEvent
    from opensquilla.provider import TextDeltaEvent as ProviderTextDeltaEvent

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools, config
            if provider_event == "text":
                yield ProviderTextDeltaEvent(text={"bad": "text"})
            elif provider_event == "error":
                yield ProviderErrorEvent(message={"bad": "message"}, code="bad")
            elif provider_event == "error_code":
                yield ProviderErrorEvent(message="bad", code={"bad": "code"})
            elif provider_event == "heartbeat_message":
                yield ProviderHeartbeatEvent(phase="provider", message={"bad": "message"})
            else:
                yield ProviderHeartbeatEvent(phase={"bad": "phase"}, message="retrying")

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="host-model"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    with pytest.raises(RuntimeError, match=match):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={"messages": [{"role": "user", "content": "hello"}]},
        )


def test_pi_kernel_exposes_read_only_provider_identity_for_history_context() -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    class FakeProvider:
        provider_name = "anthropic"
        provider_kind = "anthropic"

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            raise AssertionError("not used")

    agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_client=FakePiRpcClient(),
            allow_test_pi_rpc_client=True,
        ),
        provider=FakeProvider(),
        config=AgentConfig(model_id="pi-provider-identity"),
        tool_definitions=[],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )

    assert agent.provider.provider_name == "anthropic"
    assert agent.provider.provider_kind == "anthropic"
    assert not hasattr(agent.provider, "chat")


@pytest.mark.asyncio
async def test_pi_provider_host_port_returns_complete_provider_tool_use_to_sidecar() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.engine.types import ToolCall, ToolResult, ToolUseEndEvent, ToolUseStartEvent
    from opensquilla.provider import DoneEvent as ProviderDoneEvent
    from opensquilla.provider import ToolUseDeltaEvent as ProviderToolUseDeltaEvent
    from opensquilla.provider import ToolUseEndEvent as ProviderToolUseEndEvent
    from opensquilla.provider import ToolUseStartEvent as ProviderToolUseStartEvent

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools, config
            yield ProviderToolUseStartEvent(tool_use_id="call-1", tool_name="read")
            yield ProviderToolUseDeltaEvent(
                tool_use_id="call-1",
                json_fragment='{"path": "README.md"}',
            )
            yield ProviderToolUseEndEvent(
                tool_use_id="call-1",
                tool_name="read",
                arguments={"path": "README.md"},
            )
            yield ProviderDoneEvent(stop_reason="tool_use", model="provider-model")

    executed_calls: list[ToolCall] = []

    class FakeHostAgent:
        provider = FakeProvider()
        tool_definitions = [{"name": "read"}]
        config = SimpleNamespace(model_id="host-model")

        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("Pi provider.request must not execute host tools")

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            _ = tool_call
            return result

        def _approval_wait_timeout(self) -> float:
            return 0.0

    host_agent = FakeHostAgent()
    port = OpenSquillaProviderHostPort(host_agent)

    events = await port.handle_intent(
        intent_type="provider.request",
        session_key="agent:main:test",
        payload={"messages": [{"role": "user", "content": "read README"}]},
    )

    assert executed_calls == []
    assert events == [
        ToolUseStartEvent(tool_use_id="call-1", tool_name="read"),
        ToolUseEndEvent(
            tool_use_id="call-1",
            tool_name="read",
            arguments={"path": "README.md"},
        ),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_event", "match"),
    [
        ("start_id", "provider tool-use start tool_use_id must be a string"),
        ("start_name", "provider tool-use start tool_name must be a string"),
        (
            "start_id_blank",
            "provider tool-use start tool_use_id must be a non-empty string",
        ),
        (
            "start_name_blank",
            "provider tool-use start tool_name must be a non-empty string",
        ),
        (
            "start_synthetic",
            "provider tool-use start synthetic_from_text must be a boolean",
        ),
        ("delta_id", "provider tool-use delta tool_use_id must be a string"),
        (
            "delta_id_blank",
            "provider tool-use delta tool_use_id must be a non-empty string",
        ),
        ("delta_fragment", "provider tool-use delta json_fragment must be a string"),
        ("end_id", "provider tool-use end tool_use_id must be a string"),
        ("end_name", "provider tool-use end tool_name must be a string"),
        (
            "end_id_blank",
            "provider tool-use end tool_use_id must be a non-empty string",
        ),
        (
            "end_name_blank",
            "provider tool-use end tool_name must be a non-empty string",
        ),
        (
            "end_name_mismatch",
            "provider tool-use end tool_name must match start tool_name",
        ),
        (
            "end_synthetic",
            "provider tool-use end synthetic_from_text must be a boolean",
        ),
    ],
)
async def test_pi_provider_tool_use_rejects_malformed_identity_and_provenance_fields(
    provider_event: str,
    match: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.engine.types import ToolCall, ToolResult
    from opensquilla.provider import ToolUseDeltaEvent as ProviderToolUseDeltaEvent
    from opensquilla.provider import ToolUseEndEvent as ProviderToolUseEndEvent
    from opensquilla.provider import ToolUseStartEvent as ProviderToolUseStartEvent

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools, config
            if provider_event == "start_id":
                yield ProviderToolUseStartEvent(tool_use_id={"bad": "id"}, tool_name="read")
            elif provider_event == "start_name":
                yield ProviderToolUseStartEvent(tool_use_id="call-1", tool_name={"bad": "name"})
            elif provider_event == "start_id_blank":
                yield ProviderToolUseStartEvent(tool_use_id="   ", tool_name="read")
            elif provider_event == "start_name_blank":
                yield ProviderToolUseStartEvent(tool_use_id="call-1", tool_name="   ")
            elif provider_event == "start_synthetic":
                yield ProviderToolUseStartEvent(
                    tool_use_id="call-1",
                    tool_name="read",
                    synthetic_from_text="yes",
                )
            else:
                yield ProviderToolUseStartEvent(tool_use_id="call-1", tool_name="read")
                if provider_event == "delta_id":
                    yield ProviderToolUseDeltaEvent(
                        tool_use_id={"bad": "id"},
                        json_fragment="{}",
                    )
                elif provider_event == "delta_id_blank":
                    yield ProviderToolUseDeltaEvent(
                        tool_use_id="   ",
                        json_fragment="{}",
                    )
                elif provider_event == "delta_fragment":
                    yield ProviderToolUseDeltaEvent(
                        tool_use_id="call-1",
                        json_fragment={"bad": "fragment"},
                    )
                elif provider_event == "end_id":
                    yield ProviderToolUseEndEvent(
                        tool_use_id={"bad": "id"},
                        tool_name="read",
                        arguments={},
                    )
                elif provider_event == "end_name":
                    yield ProviderToolUseEndEvent(
                        tool_use_id="call-1",
                        tool_name={"bad": "name"},
                        arguments={},
                    )
                elif provider_event == "end_id_blank":
                    yield ProviderToolUseEndEvent(
                        tool_use_id="   ",
                        tool_name="read",
                        arguments={},
                    )
                elif provider_event == "end_name_blank":
                    yield ProviderToolUseEndEvent(
                        tool_use_id="call-1",
                        tool_name="   ",
                        arguments={},
                    )
                elif provider_event == "end_name_mismatch":
                    yield ProviderToolUseEndEvent(
                        tool_use_id="call-1",
                        tool_name="write",
                        arguments={},
                    )
                else:
                    yield ProviderToolUseEndEvent(
                        tool_use_id="call-1",
                        tool_name="read",
                        arguments={},
                        synthetic_from_text="yes",
                    )

    class FakeHostAgent:
        provider = FakeProvider()
        tool_definitions = [{"name": "read"}]
        config = SimpleNamespace(model_id="host-model")

        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("invalid provider tool-use must not reach host tool")

    port = OpenSquillaProviderHostPort(FakeHostAgent())

    with pytest.raises(RuntimeError, match=match):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={"messages": [{"role": "user", "content": "read README"}]},
        )


@pytest.mark.asyncio
async def test_pi_provider_tool_use_rejects_direct_non_object_arguments() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.engine.types import ToolCall, ToolResult
    from opensquilla.provider import ToolUseEndEvent as ProviderToolUseEndEvent
    from opensquilla.provider import ToolUseStartEvent as ProviderToolUseStartEvent

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools, config
            yield ProviderToolUseStartEvent(tool_use_id="call-1", tool_name="read")
            yield ProviderToolUseEndEvent(
                tool_use_id="call-1",
                tool_name="read",
                arguments=["not", "an", "object"],
            )

    class FakeHostAgent:
        provider = FakeProvider()
        tool_definitions = [{"name": "read"}]
        config = SimpleNamespace(model_id="host-model")

        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("invalid provider arguments must not reach host tool")

    port = OpenSquillaProviderHostPort(FakeHostAgent())

    with pytest.raises(RuntimeError, match="provider tool-use arguments must be an object"):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={"messages": [{"role": "user", "content": "read README"}]},
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_arguments",
    [
        {1: "numeric key"},
        {"tokens": float("nan")},
        {"opaque": object()},
    ],
)
async def test_pi_provider_tool_use_rejects_python_only_arguments_before_host_tool(
    bad_arguments: dict[object, object],
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.engine.types import ToolCall, ToolResult
    from opensquilla.provider import ToolUseEndEvent as ProviderToolUseEndEvent
    from opensquilla.provider import ToolUseStartEvent as ProviderToolUseStartEvent

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools, config
            yield ProviderToolUseStartEvent(tool_use_id="call-1", tool_name="read")
            yield ProviderToolUseEndEvent(
                tool_use_id="call-1",
                tool_name="read",
                arguments=bad_arguments,
            )

    class FakeHostAgent:
        provider = FakeProvider()
        tool_definitions = [{"name": "read"}]
        config = SimpleNamespace(model_id="host-model")

        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError(
                "Python-only provider arguments must not reach host tool"
            )

    port = OpenSquillaProviderHostPort(FakeHostAgent())

    with pytest.raises(RuntimeError, match="Pi sidecar JSON"):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={"messages": [{"role": "user", "content": "read README"}]},
        )


@pytest.mark.asyncio
async def test_pi_provider_tool_use_rejects_invalid_fragment_json_before_host_tool() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.engine.types import ToolCall, ToolResult
    from opensquilla.provider import ToolUseDeltaEvent as ProviderToolUseDeltaEvent
    from opensquilla.provider import ToolUseEndEvent as ProviderToolUseEndEvent
    from opensquilla.provider import ToolUseStartEvent as ProviderToolUseStartEvent

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools, config
            yield ProviderToolUseStartEvent(tool_use_id="call-1", tool_name="read")
            yield ProviderToolUseDeltaEvent(
                tool_use_id="call-1",
                json_fragment='{"path": ',
            )
            yield ProviderToolUseEndEvent(
                tool_use_id="call-1",
                tool_name="read",
                arguments={},
            )

    class FakeHostAgent:
        provider = FakeProvider()
        tool_definitions = [{"name": "read"}]
        config = SimpleNamespace(model_id="host-model")

        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("invalid provider argument fragments must not reach host tool")

    port = OpenSquillaProviderHostPort(FakeHostAgent())

    with pytest.raises(RuntimeError, match="provider tool-use arguments must decode to an object"):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={"messages": [{"role": "user", "content": "read README"}]},
        )


@pytest.mark.asyncio
async def test_pi_provider_request_returns_tool_call_end_without_executing_host_tool() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.engine.types import ToolCall, ToolResult, ToolUseEndEvent, ToolUseStartEvent
    from opensquilla.provider import ToolUseDeltaEvent as ProviderToolUseDeltaEvent
    from opensquilla.provider import ToolUseEndEvent as ProviderToolUseEndEvent
    from opensquilla.provider import ToolUseStartEvent as ProviderToolUseStartEvent

    provider_arguments = {"path": {"value": "README.md"}}

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools, config
            yield ProviderToolUseStartEvent(tool_use_id="call-1", tool_name="read")
            yield ProviderToolUseDeltaEvent(
                tool_use_id="call-1",
                json_fragment='{"path":{"value":"README.md"}}',
            )
            yield ProviderToolUseEndEvent(
                tool_use_id="call-1",
                tool_name="read",
                arguments=provider_arguments,
            )

    class FakeHostAgent:
        provider = FakeProvider()
        tool_definitions = [{"name": "read"}]
        config = SimpleNamespace(model_id="host-model")

        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("Pi provider.request must not execute host tools")

    port = OpenSquillaProviderHostPort(FakeHostAgent())

    events = await port.handle_intent(
        intent_type="provider.request",
        session_key="agent:main:test",
        payload={"messages": [{"role": "user", "content": "read README"}]},
    )

    assert events == [
        ToolUseStartEvent(tool_use_id="call-1", tool_name="read"),
        ToolUseEndEvent(
            tool_use_id="call-1",
            tool_name="read",
            arguments={"path": {"value": "README.md"}},
        ),
    ]
    assert provider_arguments == {"path": {"value": "README.md"}}


@pytest.mark.asyncio
async def test_pi_provider_tool_use_copies_arguments_before_sidecar_event() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.engine.types import ToolCall, ToolResult, ToolUseEndEvent, ToolUseStartEvent
    from opensquilla.provider import ToolUseEndEvent as ProviderToolUseEndEvent
    from opensquilla.provider import ToolUseStartEvent as ProviderToolUseStartEvent

    provider_arguments = {"path": {"value": "README.md"}}

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools, config
            yield ProviderToolUseStartEvent(tool_use_id="call-1", tool_name="read")
            yield ProviderToolUseEndEvent(
                tool_use_id="call-1",
                tool_name="read",
                arguments=provider_arguments,
            )

    class FakeHostAgent:
        provider = FakeProvider()
        tool_definitions = [{"name": "read"}]
        config = SimpleNamespace(model_id="host-model")

        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("Pi provider.request must not execute host tools")

    port = OpenSquillaProviderHostPort(FakeHostAgent())

    events = await port.handle_intent(
        intent_type="provider.request",
        session_key="agent:main:test",
        payload={"messages": [{"role": "user", "content": "read README"}]},
    )

    assert events == [
        ToolUseStartEvent(tool_use_id="call-1", tool_name="read"),
        ToolUseEndEvent(
            tool_use_id="call-1",
            tool_name="read",
            arguments={"path": {"value": "README.md"}},
        ),
    ]
    assert provider_arguments == {"path": {"value": "README.md"}}


@pytest.mark.asyncio
async def test_pi_provider_request_allows_provider_sessions_yield_tool_use_feedback() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.engine.types import ToolCall, ToolResult, ToolUseEndEvent, ToolUseStartEvent
    from opensquilla.provider import ToolUseEndEvent as ProviderToolUseEndEvent
    from opensquilla.provider import ToolUseStartEvent as ProviderToolUseStartEvent

    class FakeProvider:
        async def chat(self, messages, *, tools, config):
            _ = messages, tools, config
            yield ProviderToolUseStartEvent(
                tool_use_id="yield-1",
                tool_name="sessions_yield",
            )
            yield ProviderToolUseEndEvent(
                tool_use_id="yield-1",
                tool_name="sessions_yield",
                arguments={"session_key": "agent:other:test"},
            )

    class FakeHostAgent:
        provider = FakeProvider()
        tool_definitions = [{"name": "sessions_yield"}]
        config = SimpleNamespace(model_id="host-model")

        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("sessions_yield must go through yield.request")

    port = OpenSquillaProviderHostPort(FakeHostAgent())

    events = await port.handle_intent(
        intent_type="provider.request",
        session_key="agent:main:test",
        payload={"messages": [{"role": "user", "content": "yield"}]},
    )

    assert events == [
        ToolUseStartEvent(tool_use_id="yield-1", tool_name="sessions_yield"),
        ToolUseEndEvent(
            tool_use_id="yield-1",
            tool_name="sessions_yield",
            arguments={"session_key": "agent:other:test"},
        ),
    ]


@pytest.mark.asyncio
async def test_pi_tool_bridge_keeps_host_tool_outputs() -> None:
    from opensquilla.engine.agent_core import OpenSquillaToolBridgeHostPort
    from opensquilla.engine.types import (
        ArtifactEvent,
        RouterControlReplayEvent,
        ToolCall,
        ToolResult,
    )

    router_payload = (
        '{"status":"router_control","accepted":true,"action":"switch",'
        '"target_tier":"t3","target_model":"strong-model",'
        '"target_provider":"openrouter","target_id":"tier:t3",'
        '"replay_required":true,"evidence":"needs stronger model"}'
    )

    executed_calls: list[ToolCall] = []
    projected_calls: list[tuple[ToolResult, ToolCall]] = []

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            executed_calls.append(tool_call)
            return ToolResult(
                tool_use_id=tool_call.tool_use_id,
                tool_name=tool_call.tool_name,
                content=router_payload,
                artifacts=[
                    {
                        "id": "art-provider-router",
                        "sha256": "abc123",
                        "name": "router.txt",
                        "mime": "text/plain",
                        "size": 42,
                    }
                ],
            )

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            projected_calls.append((result, tool_call))
            return ToolResult(
                tool_use_id=result.tool_use_id,
                tool_name=result.tool_name,
                content="projected router result",
                artifacts=result.artifacts,
            )

        def _approval_wait_timeout(self) -> float:
            return 0.0

    host_agent = FakeHostAgent()
    port = OpenSquillaToolBridgeHostPort(host_agent)

    events = await port.handle_intent(
        intent_type="tool.call.execute",
        session_key="agent:main:test",
        payload={
            "tool_call_id": "call-1",
            "tool_name": "router_control",
            "arguments": {"target_id": "tier:t3", "reason": "hard task"},
        },
    )

    expected_call = ToolCall(
        tool_use_id="call-1",
        tool_name="router_control",
        arguments={"target_id": "tier:t3", "reason": "hard task"},
    )
    assert executed_calls == [expected_call]
    assert projected_calls == [(projected_calls[0][0], expected_call)]
    assert projected_calls[0][0].content == router_payload
    assert events == [
        ArtifactEvent(
            id="art-provider-router",
            sha256="abc123",
            name="router.txt",
            mime="text/plain",
            size=42,
            download_url="/api/v1/artifacts/art-provider-router",
        ),
        ToolResultEvent(
            tool_use_id="call-1",
            tool_name="router_control",
            result="projected router result",
            arguments={"target_id": "tier:t3", "reason": "hard task"},
        ),
        RouterControlReplayEvent(
            action="switch",
            target_tier="t3",
            target_model="strong-model",
            target_provider="openrouter",
            target_id="tier:t3",
        ),
    ]


@pytest.mark.asyncio
async def test_pi_tool_bridge_routes_meta_invoke_through_host_meta_stream() -> None:
    from opensquilla.engine.agent_core import OpenSquillaToolBridgeHostPort
    from opensquilla.engine.types import (
        TextDeltaEvent,
        ToolCall,
        ToolResult,
        ToolResultEvent,
        ToolUseStartEvent,
    )
    from opensquilla.tools.types import ToolContext

    executed_calls: list[ToolCall] = []
    streamed_calls: list[tuple[ToolCall, object]] = []
    projected_calls: list[tuple[ToolResult, ToolCall]] = []
    host_context = ToolContext(workspace_dir="/tmp/meta-workspace")

    class FakeHostAgent:
        _tool_context = host_context

        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            executed_calls.append(tool_call)
            raise AssertionError("meta_invoke must not use ordinary tool execution")

        async def _run_one_streaming(self, tool_call: ToolCall, tool_context: object):
            streamed_calls.append((tool_call, tool_context))
            yield ToolUseStartEvent(
                tool_use_id="nested-step",
                tool_name="meta-step:research",
            )
            yield ToolResultEvent(
                tool_use_id="nested-step",
                tool_name="meta-step:research",
                result="nested meta scheduler card",
            )
            yield TextDeltaEvent(text="meta final text")
            yield ToolResult(
                tool_use_id=tool_call.tool_use_id,
                tool_name=tool_call.tool_name,
                content="meta-skill 'research-plot-pipeline' completed.",
                is_error=False,
                terminates_turn=True,
            )

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            projected_calls.append((result, tool_call))
            return result

        def _approval_wait_timeout(self) -> float:
            return 0.0

    port = OpenSquillaToolBridgeHostPort(FakeHostAgent())

    events = await port.handle_intent(
        intent_type="tool.call.execute",
        session_key="agent:main:test",
        payload={
            "tool_call_id": "call-meta",
            "tool_name": "meta_invoke",
            "arguments": {"name": "research-plot-pipeline"},
        },
    )

    expected_call = ToolCall(
        tool_use_id="call-meta",
        tool_name="meta_invoke",
        arguments={"name": "research-plot-pipeline"},
    )
    assert executed_calls == []
    assert streamed_calls == [(expected_call, host_context)]
    assert projected_calls == [(projected_calls[0][0], expected_call)]
    assert events == [
        ToolUseStartEvent(
            tool_use_id="nested-step",
            tool_name="meta-step:research",
        ),
        ToolResultEvent(
            tool_use_id="nested-step",
            tool_name="meta-step:research",
            result="nested meta scheduler card",
        ),
        TextDeltaEvent(text="meta final text"),
        ToolResultEvent(
            tool_use_id="call-meta",
            tool_name="meta_invoke",
            result="meta-skill 'research-plot-pipeline' completed.",
            is_error=False,
            arguments={"name": "research-plot-pipeline"},
        ),
    ]


@pytest.mark.asyncio
async def test_pi_tool_bridge_normalizes_artifact_ref_payload_kind_for_runtime_event() -> None:
    from opensquilla.engine.agent_core import OpenSquillaToolBridgeHostPort
    from opensquilla.engine.types import ArtifactEvent, ToolCall, ToolResult, ToolResultEvent

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            return ToolResult(
                tool_use_id=tool_call.tool_use_id,
                tool_name=tool_call.tool_name,
                content="host result",
                artifacts=[
                    {
                        "id": "art-ref",
                        "kind": "artifact_ref",
                        "sha256": "abc123",
                        "name": "ref.txt",
                        "mime": "text/plain",
                        "size": 42,
                    }
                ],
            )

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            _ = tool_call
            return result

        def _approval_wait_timeout(self) -> float:
            return 0.0

    port = OpenSquillaToolBridgeHostPort(FakeHostAgent())

    events = await port.handle_intent(
        intent_type="tool.call.execute",
        session_key="agent:main:test",
        payload={
            "tool_call_id": "call-1",
            "tool_name": "file_write",
            "arguments": {"path": "ref.txt"},
        },
    )

    assert events == [
        ArtifactEvent(
            id="art-ref",
            sha256="abc123",
            name="ref.txt",
            mime="text/plain",
            size=42,
            download_url="/api/v1/artifacts/art-ref",
        ),
        ToolResultEvent(
            tool_use_id="call-1",
            tool_name="file_write",
            result="host result",
            arguments={"path": "ref.txt"},
        ),
    ]


@pytest.mark.asyncio
async def test_pi_tool_bridge_rejects_non_list_tool_result_artifacts() -> None:
    from opensquilla.engine.agent_core import OpenSquillaToolBridgeHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            return ToolResult(
                tool_use_id=tool_call.tool_use_id,
                tool_name=tool_call.tool_name,
                content="host result",
                artifacts="not-a-list",
            )

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            _ = tool_call
            return result

    port = OpenSquillaToolBridgeHostPort(FakeHostAgent())

    with pytest.raises(RuntimeError, match="tool result artifacts must be a list"):
        await port.handle_intent(
            intent_type="tool.call.execute",
            session_key="agent:main:test",
            payload={"tool_call_id": "call-1", "tool_name": "read"},
        )


@pytest.mark.asyncio
async def test_pi_tool_bridge_rejects_null_tool_result_artifacts() -> None:
    from opensquilla.engine.agent_core import OpenSquillaToolBridgeHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            return ToolResult(
                tool_use_id=tool_call.tool_use_id,
                tool_name=tool_call.tool_name,
                content="host result",
                artifacts=None,  # type: ignore[arg-type]
            )

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            _ = tool_call
            return result

    port = OpenSquillaToolBridgeHostPort(FakeHostAgent())

    with pytest.raises(RuntimeError, match="tool result artifacts must be a list"):
        await port.handle_intent(
            intent_type="tool.call.execute",
            session_key="agent:main:test",
            payload={"tool_call_id": "call-1", "tool_name": "read"},
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "bad_value", "match"),
    [
        ("sha256", {"bad": "sha"}, "tool artifact sha256 must be a string"),
        ("name", {"bad": "name"}, "tool artifact name must be a string"),
        ("mime", {"bad": "mime"}, "tool artifact mime must be a string"),
        ("size", "42", "tool artifact size must be an integer"),
        ("size", -1, "tool artifact size must be a non-negative integer"),
    ],
)
async def test_pi_tool_bridge_rejects_invalid_tool_artifact_event_fields(
    field: str,
    bad_value: Any,
    match: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaToolBridgeHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    artifact = {
        "id": "art-bad",
        "sha256": "abc123",
        "name": "artifact.txt",
        "mime": "text/plain",
        "size": 42,
    }
    artifact[field] = bad_value

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            return ToolResult(
                tool_use_id=tool_call.tool_use_id,
                tool_name=tool_call.tool_name,
                content="host result",
                artifacts=[artifact],
            )

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            _ = tool_call
            return result

    port = OpenSquillaToolBridgeHostPort(FakeHostAgent())

    with pytest.raises(RuntimeError, match=match):
        await port.handle_intent(
            intent_type="tool.call.execute",
            session_key="agent:main:test",
            payload={"tool_call_id": "call-1", "tool_name": "read"},
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "bad_value", "match"),
    [
        ("target_tier", {"bad": "tier"}, "router replay target_tier must be a string or None"),
        ("target_model", {"bad": "model"}, "router replay target_model must be a string or None"),
        (
            "target_provider",
            {"bad": "provider"},
            "router replay target_provider must be a string or None",
        ),
        ("target_id", {"bad": "id"}, "router replay target_id must be a string or None"),
    ],
)
async def test_pi_tool_bridge_rejects_invalid_router_replay_public_event_fields(
    field: str,
    bad_value: Any,
    match: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaToolBridgeHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    router_payload = {
        "status": "router_control",
        "accepted": True,
        "action": "switch",
        "target_tier": "t3",
        "target_model": "strong-model",
        "target_provider": "openrouter",
        "target_id": "tier:t3",
        "replay_required": True,
    }
    router_payload[field] = bad_value

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            return ToolResult(
                tool_use_id="call-1",
                tool_name="router_control",
                content=json.dumps(router_payload),
            )

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            _ = tool_call
            return result

    port = OpenSquillaToolBridgeHostPort(FakeHostAgent())

    with pytest.raises(RuntimeError, match=match):
        await port.handle_intent(
            intent_type="tool.call.execute",
            session_key="agent:main:test",
            payload={"tool_call_id": "call-1", "tool_name": "router_control"},
        )


@pytest.mark.asyncio
async def test_pi_tool_bridge_rejects_negative_host_router_replay_depth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaToolBridgeHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    def fake_replay_event_from_payload(content: object, *, replay_depth: int = 0):
        _ = content, replay_depth
        return RouterControlReplayEvent(
            action="switch",
            target_tier="t3",
            target_model="strong-model",
            target_provider="openrouter",
            target_id="tier:t3",
            replay_depth=-1,
        )

    monkeypatch.setattr(
        "opensquilla.router_control.router_control_replay_event_from_payload",
        fake_replay_event_from_payload,
    )

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            return ToolResult(
                tool_use_id="call-1",
                tool_name="router_control",
                content='{"status": "router_control"}',
            )

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            _ = tool_call
            return result

    port = OpenSquillaToolBridgeHostPort(FakeHostAgent())

    with pytest.raises(
        RuntimeError,
        match="router replay replay_depth must be a non-negative integer",
    ):
        await port.handle_intent(
            intent_type="tool.call.execute",
            session_key="agent:main:test",
            payload={"tool_call_id": "call-1", "tool_name": "router_control"},
        )


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_stops_after_host_terminal_done_event() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class TerminalProviderPort:
        async def handle_intent(self, **kwargs):
            return [DoneEvent(text="host terminal", model="host-model")]

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "provider.request",
                "payload": {"messages": [{"role": "user", "content": "host"}]},
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "must not append"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-terminal"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(provider=TerminalProviderPort()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [DoneEvent(text="host terminal", model="host-model")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("host_events", "expected_message"),
    [
        (
            [DoneEvent(text="host terminal", model="host-model"), TextDeltaEvent(text="late")],
            "KernelHostPorts.provider returned events after terminal event",
        ),
        (
            [
                DoneEvent(text="first terminal", model="host-model"),
                ErrorEvent(message="second", code="late"),
            ],
            "KernelHostPorts.provider returned multiple terminal events",
        ),
    ],
)
async def test_pi_sidecar_kernel_rejects_host_port_events_after_terminal(
    host_events: list[Any],
    expected_message: str,
) -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class TerminalProviderPort:
        async def handle_intent(self, **kwargs):
            return host_events

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "provider.request",
                "payload": {"messages": [{"role": "user", "content": "host"}]},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-terminal-order"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(provider=TerminalProviderPort()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        ErrorEvent(
            message=expected_message,
            code="pi_sidecar_error",
        )
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_host_terminal_error_with_pending_tool_call() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class TerminalToolBridge:
        async def handle_intent(self, **kwargs):
            return [ErrorEvent(message="host terminal", code="host_terminal")]

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "tool.call.prepare",
                "payload": {"tool_call_id": "call-1", "tool_name": "read"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-terminal-error"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(tool_bridge=TerminalToolBridge()),
    )

    with pytest.raises(RuntimeError, match="terminal host event rejected"):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_tool_bridge_terminal_on_execute() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class TerminalToolBridge:
        async def handle_intent(self, **kwargs):
            if kwargs["intent_type"] == "tool.call.execute":
                return [DoneEvent(text="tool bridge terminal", model="tool-model")]
            return []

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "tool.call.prepare",
                "payload": {"tool_call_id": "call-1", "tool_name": "read"},
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "tool.call.execute",
                "payload": {"tool_call_id": "call-1", "tool_name": "read"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-tool-terminal"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(tool_bridge=TerminalToolBridge()),
    )

    with pytest.raises(RuntimeError, match="tool_bridge must not return terminal"):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_routes_tool_execute_intent_to_host_tool_bridge() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    calls: list[tuple[str, dict]] = []

    class FakeToolBridge:
        async def handle_intent(self, **kwargs):
            calls.append((kwargs["intent_type"], kwargs["payload"]))
            if kwargs["intent_type"] == "tool.call.execute":
                return [
                    ToolResultEvent(
                        tool_use_id=kwargs["payload"]["tool_call_id"],
                        tool_name=kwargs["payload"]["tool_name"],
                        result="projected by host",
                    )
                ]
            return []

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "tool.call.prepare",
                "payload": {"tool_call_id": "call-1", "tool_name": "read"},
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "tool.call.execute",
                "payload": {"tool_call_id": "call-1", "tool_name": "read"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(tool_bridge=FakeToolBridge()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert calls == [
        ("tool.call.prepare", {"tool_call_id": "call-1", "tool_name": "read"}),
        ("tool.call.execute", {"tool_call_id": "call-1", "tool_name": "read"}),
    ]
    assert events == [
        ToolResultEvent(
            tool_use_id="call-1",
            tool_name="read",
            result="projected by host",
        ),
        DoneEvent(text="", model="", cost_source="unavailable"),
    ]


@pytest.mark.parametrize(
    ("returned_event", "expected_message"),
    [
        (
            ToolUseStartEvent(tool_use_id="call-2", tool_name="read"),
            "KernelHostPorts.tool_bridge returned ToolUseStartEvent "
            "for a different tool_use_id",
        ),
        (
            ToolUseStartEvent(tool_use_id="call-1", tool_name="write"),
            "KernelHostPorts.tool_bridge returned ToolUseStartEvent "
            "for a different tool_name",
        ),
        (
            ToolResultEvent(tool_use_id="call-2", tool_name="read", result="wrong id"),
            "KernelHostPorts.tool_bridge returned ToolResultEvent "
            "for a different tool_use_id",
        ),
        (
            ToolResultEvent(tool_use_id="call-1", tool_name="write", result="wrong name"),
            "KernelHostPorts.tool_bridge returned ToolResultEvent "
            "for a different tool_name",
        ),
    ],
)
@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_tool_bridge_result_identity_mismatch(
    returned_event: AgentEvent,
    expected_message: str,
) -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakeToolBridge:
        async def handle_intent(self, **kwargs):
            if kwargs["intent_type"] == "tool.call.execute":
                return [returned_event]
            return []

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            _ = message, kwargs
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "tool.call.prepare",
                "payload": {"tool_call_id": "call-1", "tool_name": "read"},
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "tool.call.execute",
                "payload": {"tool_call_id": "call-1", "tool_name": "read"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(tool_bridge=FakeToolBridge()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [ErrorEvent(message=expected_message, code="pi_sidecar_error")]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_non_string_tool_call_id_for_tool_intents() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakeToolBridge:
        async def handle_intent(self, **kwargs):
            _ = kwargs
            raise AssertionError("tool intent with structured id must not reach host bridge")

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "tool.call.prepare",
                "payload": {"tool_call_id": {"nested": "object"}, "tool_name": "read"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-tool-call-id"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(tool_bridge=FakeToolBridge()),
    )

    with pytest.raises(RuntimeError, match="requires string tool_call_id"):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.parametrize("intent_type", ["tool.call.prepare", "tool.call.execute"])
@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_cross_session_tool_intent_before_host_tool(
    intent_type: str,
) -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakeToolBridge:
        async def handle_intent(self, **kwargs):
            if kwargs["payload"].get("session_key") == "agent:main:other":
                raise AssertionError("cross-session tool intent must not reach host bridge")
            return []

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            if intent_type == "tool.call.execute":
                yield {
                    "protocol": AGENT_CORE_PROTOCOL_VERSION,
                    "kind": "intent",
                    "type": "tool.call.prepare",
                    "payload": {"tool_call_id": "call-1", "tool_name": "read"},
                }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": intent_type,
                "payload": {
                    "session_key": "agent:main:other",
                    "tool_call_id": "call-1",
                    "tool_name": "read",
                },
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-tool-session"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(tool_bridge=FakeToolBridge()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        ErrorEvent(
            message="Pi sidecar tool intent cannot target a different session_key",
            code="pi_sidecar_error",
        )
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_non_string_tool_call_id_even_with_alias() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakeToolBridge:
        async def handle_intent(self, **kwargs):
            _ = kwargs
            raise AssertionError("invalid primary tool_call_id must not fall back to alias")

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "tool.call.prepare",
                "payload": {
                    "tool_call_id": [],
                    "toolCallId": "call-1",
                    "tool_name": "read",
                },
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-tool-call-id-alias"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(tool_bridge=FakeToolBridge()),
    )

    with pytest.raises(RuntimeError, match="requires string tool_call_id"):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_non_string_tool_name_for_tool_intents() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakeToolBridge:
        async def handle_intent(self, **kwargs):
            _ = kwargs
            raise AssertionError("tool intent with structured name must not reach host bridge")

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "tool.call.prepare",
                "payload": {"tool_call_id": "call-1", "tool_name": {"nested": "object"}},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-tool-name"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(tool_bridge=FakeToolBridge()),
    )

    with pytest.raises(RuntimeError, match="requires string tool_name"):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_requires_tool_name_for_tool_intents() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakeToolBridge:
        async def handle_intent(self, **kwargs):
            _ = kwargs
            raise AssertionError("tool intent without tool_name must not reach host bridge")

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "tool.call.prepare",
                "payload": {"tool_call_id": "call-1"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-tool-name"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(tool_bridge=FakeToolBridge()),
    )

    with pytest.raises(RuntimeError, match="requires tool_name"):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_direct_sessions_yield_tool_intent() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakeToolBridge:
        async def handle_intent(self, **kwargs):
            raise AssertionError("sessions_yield must go through yield.request")

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "tool.call.prepare",
                "payload": {
                    "tool_call_id": "yield-1",
                    "tool_name": "sessions_yield",
                },
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "tool.call.execute",
                "payload": {
                    "tool_call_id": "yield-1",
                    "tool_name": "sessions_yield",
                    "arguments": {"session_key": "agent:other:test"},
                },
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-yield"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(tool_bridge=FakeToolBridge()),
    )

    with pytest.raises(
        RuntimeError,
        match="Pi sidecar must use yield.request for sessions_yield",
    ):
        [event async for event in agent.run_turn("hello")]


@pytest.mark.parametrize(
    ("intent_type", "payload", "host_port_name"),
    [
        (
            "provider.request",
            {"messages": [{"role": "user", "content": "hello"}]},
            "provider",
        ),
        (
            "tool.call.execute",
            {"tool_call_id": "call-1", "tool_name": "read"},
            "tool_bridge",
        ),
        (
            "session.write.enqueue",
            {"role": "assistant", "content": "state"},
            "session_writes",
        ),
        ("queue.poll", {"task_id": "task-1"}, "queue"),
        (
            "savepoint.request",
            {"transcript": [{"role": "assistant", "content": "state"}]},
            "savepoints",
        ),
    ],
)
@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_sessions_yield_from_non_yield_host_ports(
    intent_type: str,
    payload: dict[str, Any],
    host_port_name: str,
) -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakeHostPort:
        async def handle_intent(self, *, intent_type: str, **kwargs):
            _ = kwargs
            if intent_type == "tool.call.prepare":
                return []
            return [
                ToolResultEvent(
                    tool_use_id="yield-request",
                    tool_name="sessions_yield",
                    result='{"status":"ok"}',
                    is_error=False,
                )
            ]

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            _ = message, kwargs
            if intent_type == "tool.call.execute":
                yield {
                    "protocol": AGENT_CORE_PROTOCOL_VERSION,
                    "kind": "intent",
                    "type": "tool.call.prepare",
                    "payload": {"tool_call_id": "call-1", "tool_name": "read"},
                }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": intent_type,
                "payload": payload,
            }

    port = FakeHostPort()
    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-yield-boundary"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(**{host_port_name: port}),
    )

    with pytest.raises(
        RuntimeError,
        match=(
            f"KernelHostPorts.{host_port_name} must not return "
            "sessions_yield outside yield.request"
        ),
    ):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.parametrize(
    ("intent_type", "payload", "host_port_name", "terminal_events"),
    [
        (
            "provider.request",
            {"messages": [{"role": "user", "content": "hello"}]},
            "provider",
            [],
        ),
        (
            "tool.call.execute",
            {"tool_call_id": "call-1", "tool_name": "read"},
            "tool_bridge",
            [],
        ),
        ("queue.poll", {"task_id": "task-1"}, "queue", []),
        (
            "turn.finalize",
            {"text": "done", "model": "pi-artifact-boundary"},
            "finalizer",
            [DoneEvent(text="done", model="host-final")],
        ),
    ],
)
@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_cross_session_artifacts_from_host_ports(
    intent_type: str,
    payload: dict[str, Any],
    host_port_name: str,
    terminal_events: list[DoneEvent],
) -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakeHostPort:
        async def handle_intent(self, *, intent_type: str, **kwargs):
            _ = intent_type, kwargs
            return [
                ArtifactEvent(
                    id="artifact-1",
                    sha256="0" * 64,
                    name="result.txt",
                    mime="text/plain",
                    size=4,
                    session_id="other-session",
                    session_key="agent:main:other",
                    source="tool",
                    created_at="2026-06-04T00:00:00Z",
                    download_url="/artifacts/artifact-1",
                    store="local",
                ),
                *terminal_events,
            ]

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            _ = message, kwargs
            if intent_type == "tool.call.execute":
                yield {
                    "protocol": AGENT_CORE_PROTOCOL_VERSION,
                    "kind": "intent",
                    "type": "tool.call.prepare",
                    "payload": {"tool_call_id": "call-1", "tool_name": "read"},
                }
            if intent_type != "turn.finalize":
                yield {
                    "protocol": AGENT_CORE_PROTOCOL_VERSION,
                    "kind": "intent",
                    "type": intent_type,
                    "payload": payload,
                }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-artifact-boundary"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(**{host_port_name: FakeHostPort()}),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        ErrorEvent(
            message=(
                f"KernelHostPorts.{host_port_name} returned ArtifactEvent "
                "for a different session_key"
            ),
            code="pi_sidecar_error",
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("intent_type", ["tool.call.prepare", "tool.call.execute"])
async def test_pi_tool_bridge_rejects_reserved_sessions_yield_tool(
    intent_type: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaToolBridgeHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("sessions_yield must go through orchestration port")

    port = OpenSquillaToolBridgeHostPort(FakeHostAgent())

    with pytest.raises(
        RuntimeError,
        match="KernelHostPorts.tool_bridge must not execute sessions_yield",
    ):
        await port.handle_intent(
            intent_type=intent_type,
            session_key="agent:main:test",
            payload={
                "tool_call_id": "yield-1",
                "tool_name": "sessions_yield",
            },
        )


@pytest.mark.asyncio
async def test_pi_tool_bridge_rejects_unknown_intent_before_payload_parsing() -> None:
    from opensquilla.engine.agent_core import OpenSquillaToolBridgeHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("unknown tool intent must not reach host execution")

    port = OpenSquillaToolBridgeHostPort(FakeHostAgent())

    with pytest.raises(RuntimeError, match="Unsupported tool bridge intent"):
        await port.handle_intent(
            intent_type="tool.call.cancel",
            session_key="agent:main:test",
            payload={"tool_call_id": {"nested": "object"}, "tool_name": "read"},
        )


@pytest.mark.parametrize("intent_type", ["tool.call.prepare", "tool.call.execute"])
@pytest.mark.asyncio
async def test_pi_tool_bridge_rejects_unknown_payload_fields_before_host_tool(
    intent_type: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaToolBridgeHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("unknown tool intent field must not reach host tool")

    port = OpenSquillaToolBridgeHostPort(FakeHostAgent())

    with pytest.raises(
        RuntimeError,
        match="tool intent unsupported payload field",
    ):
        await port.handle_intent(
            intent_type=intent_type,
            session_key="agent:main:test",
            payload={
                "tool_call_id": "call-1",
                "tool_name": "read",
                "host_tool_policy": {"approval": "sidecar-owned"},
            },
        )


@pytest.mark.parametrize("intent_type", ["tool.call.prepare", "tool.call.execute"])
@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_unknown_tool_intent_fields_before_custom_port(
    intent_type: str,
) -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )
    from opensquilla.engine.types import ToolResultEvent, ToolUseStartEvent

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            _ = message, kwargs
            if intent_type == "tool.call.execute":
                yield {
                    "protocol": AGENT_CORE_PROTOCOL_VERSION,
                    "kind": "intent",
                    "type": "tool.call.prepare",
                    "payload": {
                        "tool_call_id": "call-1",
                        "tool_name": "read",
                    },
                }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": intent_type,
                "payload": {
                    "tool_call_id": "call-1",
                    "tool_name": "read",
                    "host_tool_policy": {"approval": "sidecar-owned"},
                },
            }

    class FakeToolBridge:
        async def handle_intent(self, *, intent_type: str, payload: dict, session_key: str):
            _ = session_key
            if "host_tool_policy" in payload:
                raise AssertionError(
                    "unknown tool intent field reached custom tool port"
                )
            if intent_type == "tool.call.prepare":
                return [
                    ToolUseStartEvent(
                        tool_use_id=payload["tool_call_id"],
                        tool_name=payload["tool_name"],
                    )
                ]
            return [
                ToolResultEvent(
                    tool_use_id=payload["tool_call_id"],
                    tool_name=payload["tool_name"],
                    result="host result",
                )
            ]

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-custom-tool-port"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(tool_bridge=FakeToolBridge()),
    )

    with pytest.raises(RuntimeError, match="tool intent unsupported payload field"):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.parametrize("intent_type", ["tool.call.prepare", "tool.call.execute"])
@pytest.mark.asyncio
async def test_pi_tool_bridge_rejects_cross_session_target_before_host_tool(
    intent_type: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaToolBridgeHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("cross-session tool intent must not reach host tool")

    port = OpenSquillaToolBridgeHostPort(FakeHostAgent())

    with pytest.raises(
        RuntimeError,
        match="Pi sidecar tool intent cannot target a different session_key",
    ):
        await port.handle_intent(
            intent_type=intent_type,
            session_key="agent:main:test",
            payload={
                "session_key": "agent:main:other",
                "tool_call_id": "call-1",
                "tool_name": "read",
            },
        )


@pytest.mark.parametrize("intent_type", ["tool.call.prepare", "tool.call.execute"])
@pytest.mark.asyncio
async def test_pi_tool_bridge_rejects_non_string_payload_session_key_before_host_tool(
    intent_type: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaToolBridgeHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("malformed tool intent session_key must not reach host tool")

    port = OpenSquillaToolBridgeHostPort(FakeHostAgent())

    with pytest.raises(RuntimeError, match=f"{intent_type} session_key must be a string"):
        await port.handle_intent(
            intent_type=intent_type,
            session_key="agent:main:test",
            payload={
                "session_key": {"nested": "session"},
                "tool_call_id": "call-1",
                "tool_name": "read",
            },
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"tool_call_id": {"nested": "object"}, "tool_name": "read"},
        {"tool_call_id": [], "toolCallId": "call-1", "tool_name": "read"},
        {"toolCallId": [], "id": "call-1", "tool_name": "read"},
        {"tool_call_id": "call-1", "tool_name": {"nested": "object"}},
    ],
)
async def test_pi_tool_bridge_rejects_structured_tool_identity_before_host_tool(
    payload: dict[str, Any],
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaToolBridgeHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("structured tool identity must not reach host tool")

    port = OpenSquillaToolBridgeHostPort(FakeHostAgent())

    with pytest.raises(RuntimeError, match="requires string tool"):
        await port.handle_intent(
            intent_type="tool.call.prepare",
            session_key="agent:main:test",
            payload=payload,
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"tool_call_id": "   ", "tool_name": "read"},
        {"tool_call_id": "   ", "toolCallId": "call-1", "tool_name": "read"},
        {"toolCallId": "   ", "id": "call-1", "tool_name": "read"},
    ],
)
@pytest.mark.asyncio
async def test_pi_tool_bridge_rejects_blank_tool_call_id_before_host_tool(
    payload: dict[str, Any],
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaToolBridgeHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("blank tool_call_id must not reach host tool")

    port = OpenSquillaToolBridgeHostPort(FakeHostAgent())

    with pytest.raises(RuntimeError, match="requires tool_call_id"):
        await port.handle_intent(
            intent_type="tool.call.execute",
            session_key="agent:main:test",
            payload=payload,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["arguments", "input"])
async def test_pi_tool_bridge_rejects_non_object_arguments_before_host_tool(
    field: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaToolBridgeHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("non-object tool arguments must not reach host tool")

    port = OpenSquillaToolBridgeHostPort(FakeHostAgent())

    with pytest.raises(RuntimeError, match="Pi sidecar intent arguments must be an object"):
        await port.handle_intent(
            intent_type="tool.call.execute",
            session_key="agent:main:test",
            payload={
                "tool_call_id": "call-1",
                "tool_name": "read",
                field: ["not", "an", "object"],
            },
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("intent_type", ["tool.call.prepare", "tool.call.execute"])
@pytest.mark.parametrize(
    ("bad_input", "message"),
    [
        (["not", "an", "object"], "Pi sidecar intent arguments must be an object"),
        ({1: "numeric key"}, "Pi sidecar JSON"),
        ({"tokens": float("nan")}, "Pi sidecar JSON"),
        ({"opaque": object()}, "Pi sidecar JSON"),
    ],
)
async def test_pi_tool_bridge_rejects_malformed_fallback_input_even_with_arguments(
    intent_type: str,
    bad_input: object,
    message: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaToolBridgeHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("malformed fallback input must not reach host tool")

    port = OpenSquillaToolBridgeHostPort(FakeHostAgent())

    with pytest.raises(RuntimeError, match=message):
        await port.handle_intent(
            intent_type=intent_type,
            session_key="agent:main:test",
            payload={
                "tool_call_id": "call-1",
                "tool_name": "read",
                "arguments": {"path": "README.md"},
                "input": bad_input,
            },
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_arguments",
    [
        {1: "numeric key"},
        {"tokens": float("nan")},
        {"opaque": object()},
    ],
)
async def test_pi_tool_bridge_rejects_python_only_arguments_before_host_tool(
    bad_arguments: dict[object, object],
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaToolBridgeHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("Python-only tool arguments must not reach host tool")

    port = OpenSquillaToolBridgeHostPort(FakeHostAgent())

    with pytest.raises(RuntimeError, match="Pi sidecar JSON"):
        await port.handle_intent(
            intent_type="tool.call.execute",
            session_key="agent:main:test",
            payload={
                "tool_call_id": "call-1",
                "tool_name": "read",
                "arguments": bad_arguments,
            },
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("raw_synthetic_from_text", ["false", 1, []])
async def test_pi_tool_bridge_rejects_non_bool_synthetic_from_text_before_host_tool(
    raw_synthetic_from_text: Any,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaToolBridgeHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("invalid synthetic_from_text must not reach host tool")

    port = OpenSquillaToolBridgeHostPort(FakeHostAgent())

    with pytest.raises(RuntimeError, match="synthetic_from_text must be a boolean"):
        await port.handle_intent(
            intent_type="tool.call.execute",
            session_key="agent:main:test",
            payload={
                "tool_call_id": "call-1",
                "tool_name": "read",
                "synthetic_from_text": raw_synthetic_from_text,
            },
        )


@pytest.mark.asyncio
async def test_pi_tool_bridge_rejects_non_string_origin_trace_before_host_tool() -> None:
    from opensquilla.engine.agent_core import OpenSquillaToolBridgeHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("structured origin_trace must not reach host tool")

    port = OpenSquillaToolBridgeHostPort(FakeHostAgent())

    with pytest.raises(RuntimeError, match="origin_trace must be a string"):
        await port.handle_intent(
            intent_type="tool.call.execute",
            session_key="agent:main:test",
            payload={
                "tool_call_id": "call-1",
                "tool_name": "read",
                "origin_trace": {"nested": "object"},
            },
        )


@pytest.mark.asyncio
async def test_pi_tool_bridge_rejects_explicit_null_origin_trace_before_host_tool() -> None:
    from opensquilla.engine.agent_core import OpenSquillaToolBridgeHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("null origin_trace must not reach host tool")

    port = OpenSquillaToolBridgeHostPort(FakeHostAgent())

    with pytest.raises(RuntimeError, match="origin_trace must be a string"):
        await port.handle_intent(
            intent_type="tool.call.execute",
            session_key="agent:main:test",
            payload={
                "tool_call_id": "call-1",
                "tool_name": "read",
                "origin_trace": None,
            },
        )


@pytest.mark.asyncio
async def test_pi_tool_bridge_copies_payload_arguments_before_host_tool() -> None:
    from opensquilla.engine.agent_core import OpenSquillaToolBridgeHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            tool_call.arguments["nested"]["value"] = "mutated"
            return ToolResult(
                tool_use_id=tool_call.tool_use_id,
                tool_name=tool_call.tool_name,
                content="host result",
            )

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            _ = tool_call
            return result

    port = OpenSquillaToolBridgeHostPort(FakeHostAgent())
    payload = {
        "tool_call_id": "call-1",
        "tool_name": "read",
        "arguments": {"nested": {"value": "original"}},
    }

    events = await port.handle_intent(
        intent_type="tool.call.execute",
        session_key="agent:main:test",
        payload=payload,
    )

    assert events == [
        ToolResultEvent(
            tool_use_id="call-1",
            tool_name="read",
            result="host result",
            arguments={"nested": {"value": "mutated"}},
        )
    ]
    assert payload == {
        "tool_call_id": "call-1",
        "tool_name": "read",
        "arguments": {"nested": {"value": "original"}},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "bad_value", "match"),
    [
        ("tool_use_id", {"bad": "id"}, "projected tool result tool_use_id must be a string"),
        ("tool_name", {"bad": "name"}, "projected tool result tool_name must be a string"),
        ("content", {"bad": "content"}, "projected tool result content must be a string"),
        ("is_error", "yes", "projected tool result is_error must be a boolean"),
        (
            "execution_status",
            "bad-status",
            "projected tool result execution_status must be an object or None",
        ),
        ("execution_status", {1: "numeric key"}, "Pi sidecar JSON"),
        ("execution_status", {"tokens": float("nan")}, "Pi sidecar JSON"),
        ("execution_status", {"opaque": object()}, "Pi sidecar JSON"),
        (
            "arguments",
            ["not", "an", "object"],
            "projected tool result arguments must be an object or None",
        ),
        ("arguments", {1: "numeric key"}, "Pi sidecar JSON"),
        ("arguments", {"tokens": float("nan")}, "Pi sidecar JSON"),
        ("arguments", {"opaque": object()}, "Pi sidecar JSON"),
    ],
)
async def test_pi_tool_bridge_rejects_invalid_projected_tool_result_fields(
    field: str,
    bad_value: Any,
    match: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaToolBridgeHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            return ToolResult(
                tool_use_id=tool_call.tool_use_id,
                tool_name=tool_call.tool_name,
                content="host result",
            )

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            _ = tool_call
            setattr(result, field, bad_value)
            return result

    port = OpenSquillaToolBridgeHostPort(FakeHostAgent())

    with pytest.raises(RuntimeError, match=match):
        await port.handle_intent(
            intent_type="tool.call.execute",
            session_key="agent:main:test",
            payload={
                "tool_call_id": "call-1",
                "tool_name": "read",
                "arguments": {"path": "README.md"},
            },
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "bad_value", "match"),
    [
        (
            "tool_use_id",
            "",
            "projected tool result tool_use_id must be non-empty",
        ),
        (
            "tool_use_id",
            "call-2",
            "projected tool result tool_use_id must match tool call",
        ),
        (
            "tool_name",
            "",
            "projected tool result tool_name must be non-empty",
        ),
        (
            "tool_name",
            "write",
            "projected tool result tool_name must match tool call",
        ),
    ],
)
async def test_pi_tool_bridge_rejects_mismatched_projected_tool_result_identity(
    field: str,
    bad_value: str,
    match: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaToolBridgeHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            return ToolResult(
                tool_use_id=tool_call.tool_use_id,
                tool_name=tool_call.tool_name,
                content="host result",
            )

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            _ = tool_call
            setattr(result, field, bad_value)
            return result

    port = OpenSquillaToolBridgeHostPort(FakeHostAgent())

    with pytest.raises(RuntimeError, match=match):
        await port.handle_intent(
            intent_type="tool.call.execute",
            session_key="agent:main:test",
            payload={"tool_call_id": "call-1", "tool_name": "read"},
        )


@pytest.mark.asyncio
async def test_pi_tool_bridge_rejects_missing_projected_tool_result_content() -> None:
    from opensquilla.engine.agent_core import OpenSquillaToolBridgeHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            return ToolResult(
                tool_use_id=tool_call.tool_use_id,
                tool_name=tool_call.tool_name,
                content="host result",
            )

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> Any:
            _ = result
            return SimpleNamespace(
                tool_use_id=tool_call.tool_use_id,
                tool_name=tool_call.tool_name,
                is_error=False,
            )

    port = OpenSquillaToolBridgeHostPort(FakeHostAgent())

    with pytest.raises(RuntimeError, match="projected tool result content is required"):
        await port.handle_intent(
            intent_type="tool.call.execute",
            session_key="agent:main:test",
            payload={"tool_call_id": "call-1", "tool_name": "read"},
        )


@pytest.mark.asyncio
async def test_pi_tool_bridge_waits_and_retries_pending_approval(monkeypatch) -> None:
    import opensquilla.engine.agent as agent_module
    from opensquilla.engine.agent_core import OpenSquillaToolBridgeHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    waited: list[tuple[str, float]] = []

    async def fake_wait_for_pending_approval_resolution(
        payload: dict[str, Any],
        *,
        timeout: float,
    ) -> None:
        waited.append((payload["approval_id"], timeout))

    monkeypatch.setattr(
        agent_module,
        "_wait_for_pending_approval_resolution",
        fake_wait_for_pending_approval_resolution,
    )

    calls: list[ToolCall] = []
    projected: list[ToolCall] = []

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            calls.append(tool_call)
            if "approval_id" not in tool_call.arguments:
                return ToolResult(
                    tool_use_id=tool_call.tool_use_id,
                    tool_name=tool_call.tool_name,
                    content=(
                        '{"status":"approval_required",'
                        '"approval_id":"approve-1",'
                        '"warning":"command requires approval"}'
                    ),
                )
            return ToolResult(
                tool_use_id=tool_call.tool_use_id,
                tool_name=tool_call.tool_name,
                content="approved command result",
            )

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            _ = result
            projected.append(tool_call)
            return result

        def _approval_wait_timeout(self) -> float:
            return 7.0

    port = OpenSquillaToolBridgeHostPort(FakeHostAgent())

    events = await port.handle_intent(
        intent_type="tool.call.execute",
        session_key="agent:main:test",
        payload={
            "tool_call_id": "call-1",
            "tool_name": "exec_command",
            "arguments": {"command": "pip install demo"},
        },
    )

    assert waited == [("approve-1", 7.0)]
    assert [call.arguments for call in calls] == [
        {"command": "pip install demo"},
        {"command": "pip install demo", "approval_id": "approve-1"},
    ]
    assert [call.arguments for call in projected] == [
        {"command": "pip install demo"},
        {"command": "pip install demo", "approval_id": "approve-1"},
    ]
    assert events == [
        ToolResultEvent(
            tool_use_id="call-1",
            tool_name="exec_command",
            result=(
                '{"status":"approval_required",'
                '"approval_id":"approve-1",'
                '"warning":"command requires approval"}'
            ),
            arguments={"command": "pip install demo"},
        ),
        ToolResultEvent(
            tool_use_id="call-1",
            tool_name="exec_command",
            result="approved command result",
            arguments={"command": "pip install demo", "approval_id": "approve-1"},
        ),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("approval_field_name", ["approval_id", "approvalId"])
async def test_pi_tool_bridge_rejects_sidecar_supplied_approval_id_before_tool(
    approval_field_name: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaToolBridgeHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("sidecar-owned approval_id reached host tool")

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            _ = result, tool_call
            raise AssertionError("sidecar-owned approval_id reached projection")

        def _approval_wait_timeout(self) -> float:
            return 7.0

    port = OpenSquillaToolBridgeHostPort(FakeHostAgent())

    with pytest.raises(RuntimeError, match="approval_id"):
        await port.handle_intent(
            intent_type="tool.call.execute",
            session_key="agent:main:test",
            payload={
                "tool_call_id": "call-1",
                "tool_name": "exec_command",
                "arguments": {
                    "command": "pip install demo",
                    approval_field_name: "sidecar-forged",
                },
            },
        )


@pytest.mark.asyncio
async def test_pi_tool_bridge_applies_host_tool_execution_timeout() -> None:
    from opensquilla.engine.agent_core import OpenSquillaToolBridgeHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            await asyncio.sleep(0.5)
            return ToolResult(
                tool_use_id=tool_call.tool_use_id,
                tool_name=tool_call.tool_name,
                content="late",
            )

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            _ = tool_call
            return result

        def _tool_execution_timeout(self, tool_call: ToolCall) -> float:
            _ = tool_call
            return 0.01

    port = OpenSquillaToolBridgeHostPort(FakeHostAgent())

    events = await asyncio.wait_for(
        port.handle_intent(
            intent_type="tool.call.execute",
            session_key="agent:main:test",
            payload={
                "tool_call_id": "call-1",
                "tool_name": "slow",
                "arguments": {},
            },
        ),
        timeout=0.2,
    )

    assert events == [
        ToolResultEvent(
            tool_use_id="call-1",
            tool_name="slow",
            result="Tool 'slow' timed out after 0.01s",
            arguments={},
            is_error=True,
            execution_status={
                "version": 1,
                "status": "timeout",
                "exit_code": None,
                "timed_out": True,
                "truncated": False,
                "reason": "runtime_timeout",
                "source": "tool_runtime",
                "preservation_class": "diagnostic",
            },
        )
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_supports_parallel_prepared_tool_calls() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    calls: list[tuple[str, str]] = []

    class FakeToolBridge:
        async def handle_intent(self, **kwargs):
            tool_call_id = kwargs["payload"]["tool_call_id"]
            calls.append((kwargs["intent_type"], tool_call_id))
            if kwargs["intent_type"] == "tool.call.execute":
                return [
                    ToolResultEvent(
                        tool_use_id=tool_call_id,
                        tool_name=kwargs["payload"]["tool_name"],
                        result=f"host result {tool_call_id}",
                    )
                ]
            return []

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            for frame in (
                ("tool.call.prepare", "call-1"),
                ("tool.call.prepare", "call-2"),
                ("tool.call.execute", "call-2"),
                ("tool.call.execute", "call-1"),
            ):
                yield {
                    "protocol": AGENT_CORE_PROTOCOL_VERSION,
                    "kind": "intent",
                    "type": frame[0],
                    "payload": {"tool_call_id": frame[1], "tool_name": "read"},
                }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-parallel"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(tool_bridge=FakeToolBridge()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert calls == [
        ("tool.call.prepare", "call-1"),
        ("tool.call.prepare", "call-2"),
        ("tool.call.execute", "call-2"),
        ("tool.call.execute", "call-1"),
    ]
    assert events == [
        ToolResultEvent(tool_use_id="call-2", tool_name="read", result="host result call-2"),
        ToolResultEvent(tool_use_id="call-1", tool_name="read", result="host result call-1"),
        DoneEvent(text="", model="pi-parallel", cost_source="unavailable"),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_duplicate_tool_prepare() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    calls: list[tuple[str, str]] = []

    class FakeToolBridge:
        async def handle_intent(self, **kwargs):
            calls.append((kwargs["intent_type"], kwargs["payload"]["tool_call_id"]))
            return []

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            for _ in range(2):
                yield {
                    "protocol": AGENT_CORE_PROTOCOL_VERSION,
                    "kind": "intent",
                    "type": "tool.call.prepare",
                    "payload": {"tool_call_id": "call-1", "tool_name": "read"},
                }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(tool_bridge=FakeToolBridge()),
    )

    with pytest.raises(RuntimeError, match="duplicate tool.call.prepare"):
        [event async for event in agent.run_turn("hello")]
    assert calls == [("tool.call.prepare", "call-1")]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_tool_execute_without_prepare() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    calls: list[dict] = []

    class FakeToolBridge:
        async def handle_intent(self, **kwargs):
            calls.append(kwargs)
            return []

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "tool.call.execute",
                "payload": {"tool_call_id": "call-1", "tool_name": "read"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(tool_bridge=FakeToolBridge()),
    )

    with pytest.raises(RuntimeError, match="without matching prepare"):
        [event async for event in agent.run_turn("hello")]
    assert calls == []


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_routes_lifecycle_intents_to_host_ports() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    calls: list[tuple[str, dict]] = []

    class RecordingPort:
        async def handle_intent(self, **kwargs):
            calls.append((kwargs["intent_type"], kwargs["payload"]))
            if kwargs["intent_type"] == "yield.request":
                return [
                    ToolResultEvent(
                        tool_use_id="yield-request",
                        tool_name="sessions_yield",
                        result='{"status":"error","message":"no child sessions"}',
                        is_error=True,
                    )
                ]
            return []

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            payloads = {
                "session.write.enqueue": {"content": "state"},
                "queue.poll": {"task_id": "task-1"},
                "savepoint.request": {"turn_id": "turn-1"},
                "telemetry.emit": {"marker": "telemetry.emit"},
                "yield.request": {"message": "wait"},
            }
            for intent_type in (
                "session.write.enqueue",
                "queue.poll",
                "savepoint.request",
                "telemetry.emit",
                "yield.request",
            ):
                yield {
                    "protocol": AGENT_CORE_PROTOCOL_VERSION,
                    "kind": "intent",
                    "type": intent_type,
                    "payload": payloads[intent_type],
                }

    port = RecordingPort()
    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(
            session_writes=port,
            queue=port,
            savepoints=port,
            orchestration=port,
            telemetry=port,
        ),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        ToolResultEvent(
            tool_use_id="yield-request",
            tool_name="sessions_yield",
            result='{"status":"error","message":"no child sessions"}',
            is_error=True,
        ),
        DoneEvent(text="", model="", cost_source="unavailable"),
    ]
    assert calls == [
        ("session.write.enqueue", {"content": "state"}),
        ("queue.poll", {"task_id": "task-1"}),
        ("savepoint.request", {"turn_id": "turn-1"}),
        ("telemetry.emit", {"marker": "telemetry.emit"}),
        ("yield.request", {"message": "wait"}),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("intent_type", "payload", "port_name"),
    [
        ("session.write.enqueue", {"role": "assistant", "content": "state"}, "session_writes"),
        ("queue.poll", {"task_id": "task-1"}, "queue"),
        ("savepoint.request", {"turn_id": "turn-1"}, "savepoints"),
        ("yield.request", {"message": "wait"}, "orchestration"),
    ],
)
async def test_pi_sidecar_kernel_rejects_non_terminal_host_port_terminal_events(
    intent_type: str,
    payload: dict[str, Any],
    port_name: str,
) -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class TerminalPort:
        async def handle_intent(self, **kwargs):
            _ = kwargs
            return [DoneEvent(text="terminal from lifecycle port", model="host-model")]

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": intent_type,
                "payload": payload,
            }

    port = TerminalPort()
    host_ports = KernelHostPorts(
        session_writes=port if port_name == "session_writes" else None,
        queue=port if port_name == "queue" else None,
        savepoints=port if port_name == "savepoints" else None,
        orchestration=port if port_name == "orchestration" else None,
    )
    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-non-terminal-port"),
        session_key="agent:main:test",
        host_ports=host_ports,
    )

    with pytest.raises(
        RuntimeError,
        match=f"KernelHostPorts.{port_name} must not return terminal events",
    ):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_allows_default_noop_telemetry_port() -> None:
    from opensquilla.engine.agent_core import AGENT_CORE_PROTOCOL_VERSION, PiSidecarKernelRuntime

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "telemetry.emit",
                "payload": {"phase": "prepare-next-turn"},
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "ok"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-telemetry"),
        session_key="agent:main:test",
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="ok"),
        DoneEvent(text="ok", model="pi-telemetry", cost_source="unavailable"),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_allows_direct_callable_telemetry_port() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    telemetry_payloads: list[dict[str, Any]] = []
    feedback_payloads: list[dict[str, Any]] = []

    def telemetry_sink(payload: dict[str, Any]) -> None:
        telemetry_payloads.append(payload)
        payload["details"]["phase"] = "mutated"

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "telemetry.emit",
                "payload": {"details": {"phase": "prepare-next-turn"}},
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "ok"},
            }

        def receive_intent_result(self, *, intent_type, payload, events, session_key):
            _ = intent_type, events, session_key
            feedback_payloads.append(payload)

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-callable-telemetry"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(telemetry=telemetry_sink),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="ok"),
        DoneEvent(text="ok", model="pi-callable-telemetry", cost_source="unavailable"),
    ]
    assert telemetry_payloads == [{"details": {"phase": "mutated"}}]
    assert feedback_payloads == [{"details": {"phase": "prepare-next-turn"}}]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_cross_session_telemetry_before_sink() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    def telemetry_sink(payload: dict[str, Any]) -> None:
        _ = payload
        raise AssertionError("cross-session telemetry must not reach sink")

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            _ = message, kwargs
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "telemetry.emit",
                "payload": {
                    "session_key": "agent:main:other",
                    "details": {"phase": "prepare-next-turn"},
                },
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-telemetry-session"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(telemetry=telemetry_sink),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        ErrorEvent(
            message="Pi sidecar telemetry.emit cannot target a different session_key",
            code="pi_sidecar_error",
        )
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_ignores_direct_callable_telemetry_failure() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    def failing_telemetry_sink(payload: dict[str, Any]) -> None:
        _ = payload
        raise OSError("telemetry sink closed")

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "telemetry.emit",
                "payload": {"phase": "prepare-next-turn"},
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "ok"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-callable-telemetry-failure"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(telemetry=failing_telemetry_sink),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="ok"),
        DoneEvent(text="ok", model="pi-callable-telemetry-failure", cost_source="unavailable"),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_ignores_default_telemetry_sink_failure() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        OpenSquillaTelemetryHostPort,
        PiSidecarKernelRuntime,
    )

    class FailingSink:
        def emit(self, payload: dict[str, Any]) -> None:
            _ = payload
            raise OSError("telemetry sink closed")

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "telemetry.emit",
                "payload": {"phase": "prepare-next-turn"},
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "ok"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-telemetry-failure"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(
            telemetry=OpenSquillaTelemetryHostPort(sink=FailingSink())
        ),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="ok"),
        DoneEvent(text="ok", model="pi-telemetry-failure", cost_source="unavailable"),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_public_events_from_telemetry_port() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class LeakyTelemetry:
        async def handle_intent(self, *, intent_type: str, payload: dict, session_key: str):
            return [TextDeltaEvent(text="must not leak")]

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "telemetry.emit",
                "payload": {"phase": "prepare-next-turn"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-telemetry"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(telemetry=LeakyTelemetry()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        ErrorEvent(
            message="KernelHostPorts.telemetry must not return AgentEvents",
            code="pi_sidecar_error",
        )
    ]


@pytest.mark.asyncio
async def test_pi_telemetry_host_port_rejects_public_events_from_sink() -> None:
    from opensquilla.engine.agent_core import OpenSquillaTelemetryHostPort

    class LeakySink:
        def emit(self, payload: dict[str, Any]) -> list[TextDeltaEvent]:
            _ = payload
            return [TextDeltaEvent(text="must not leak")]

    port = OpenSquillaTelemetryHostPort(sink=LeakySink())

    with pytest.raises(RuntimeError, match="telemetry sink must not return AgentEvents"):
        await port.handle_intent(
            intent_type="telemetry.emit",
            payload={"phase": "prepare-next-turn"},
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_telemetry_host_port_rejects_async_public_events_from_sink() -> None:
    from opensquilla.engine.agent_core import OpenSquillaTelemetryHostPort

    class LeakyAsyncSink:
        def emit(self, payload: dict[str, Any]):
            _ = payload

            async def events():
                yield TextDeltaEvent(text="must not leak")

            return events()

    port = OpenSquillaTelemetryHostPort(sink=LeakyAsyncSink())

    with pytest.raises(RuntimeError, match="telemetry sink must not return AgentEvents"):
        await port.handle_intent(
            intent_type="telemetry.emit",
            payload={"phase": "prepare-next-turn"},
            session_key="agent:main:test",
        )


@pytest.mark.parametrize(
    "bad_payload",
    [
        {1: "numeric key"},
        {"tokens": float("nan")},
        {"opaque": object()},
    ],
)
@pytest.mark.asyncio
async def test_pi_telemetry_host_port_rejects_python_only_payload_before_sink_call(
    bad_payload: dict[object, object],
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaTelemetryHostPort

    class RecordingSink:
        def emit(self, payload: dict[str, Any]) -> None:
            _ = payload
            raise AssertionError("Python-only telemetry payload must not reach sink")

    port = OpenSquillaTelemetryHostPort(sink=RecordingSink())

    with pytest.raises(RuntimeError, match="Pi sidecar JSON"):
        await port.handle_intent(
            intent_type="telemetry.emit",
            payload=bad_payload,
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_telemetry_host_port_rejects_non_object_payload_before_sink_call() -> None:
    from opensquilla.engine.agent_core import OpenSquillaTelemetryHostPort

    class RecordingSink:
        def emit(self, payload: dict[str, Any]) -> None:
            _ = payload
            raise AssertionError("non-object telemetry payload must not reach sink")

    port = OpenSquillaTelemetryHostPort(sink=RecordingSink())

    with pytest.raises(RuntimeError, match="telemetry.emit payload must be an object"):
        await port.handle_intent(
            intent_type="telemetry.emit",
            payload=["not", "an", "object"],
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_telemetry_host_port_copies_payload_before_sink_call() -> None:
    from opensquilla.engine.agent_core import OpenSquillaTelemetryHostPort

    class MutatingSink:
        def emit(self, payload: dict[str, Any]) -> None:
            payload["details"]["phase"] = "mutated"

    port = OpenSquillaTelemetryHostPort(sink=MutatingSink())
    payload = {"details": {"phase": "prepare-next-turn"}}

    await port.handle_intent(
        intent_type="telemetry.emit",
        payload=payload,
        session_key="agent:main:test",
    )

    assert payload == {"details": {"phase": "prepare-next-turn"}}


@pytest.mark.asyncio
async def test_pi_telemetry_host_port_rejects_cross_session_target_before_sink_call() -> None:
    from opensquilla.engine.agent_core import OpenSquillaTelemetryHostPort

    calls: list[dict[str, Any]] = []

    class RecordingSink:
        def emit(self, payload: dict[str, Any]) -> None:
            calls.append(payload)

    port = OpenSquillaTelemetryHostPort(sink=RecordingSink())

    with pytest.raises(
        RuntimeError,
        match="Pi sidecar telemetry.emit cannot target a different session_key",
    ):
        await port.handle_intent(
            intent_type="telemetry.emit",
            payload={
                "session_key": "agent:main:other",
                "details": {"phase": "prepare-next-turn"},
            },
            session_key="agent:main:test",
        )

    assert calls == []


@pytest.mark.asyncio
async def test_pi_telemetry_host_port_rejects_event_shaped_payload_before_sink_call() -> None:
    from opensquilla.engine.agent_core import OpenSquillaTelemetryHostPort

    class RecordingSink:
        def emit(self, payload: dict[str, Any]) -> None:
            _ = payload
            raise AssertionError("event-shaped telemetry payload must not reach sink")

    port = OpenSquillaTelemetryHostPort(sink=RecordingSink())

    with pytest.raises(
        RuntimeError,
        match="telemetry.emit must not carry public AgentEvent payloads",
    ):
        await port.handle_intent(
            intent_type="telemetry.emit",
            payload={
                "kind": "event",
                "type": "text_delta",
                "payload": {"text": "must not leak"},
            },
            session_key="agent:main:test",
        )


@pytest.mark.parametrize(
    "payload",
    [
        {
            "kind": "intent_result",
            "type": "queue.poll",
            "payload": {"ok": True},
            "events": [],
            "session_key": "agent:main:test",
        },
        {
            "kind": "intent_result",
            "type": "unsupported.intent",
            "payload": {"ok": True},
            "events": [],
            "session_key": "agent:main:test",
        },
        {
            "kind": "intent_result",
            "type": {"not": "a string"},
            "payload": {"ok": True},
            "events": [],
            "session_key": "agent:main:test",
        },
    ],
)
@pytest.mark.asyncio
async def test_pi_telemetry_rejects_intent_result_payload_before_sink(
    payload: dict[str, Any],
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaTelemetryHostPort

    class RecordingSink:
        def emit(self, payload: dict[str, Any]) -> None:
            _ = payload
            raise AssertionError("intent_result-shaped telemetry payload must not reach sink")

    port = OpenSquillaTelemetryHostPort(sink=RecordingSink())

    with pytest.raises(
        RuntimeError,
        match="telemetry.emit must not carry Pi intent_result payloads",
    ):
        await port.handle_intent(
            intent_type="telemetry.emit",
            payload=payload,
            session_key="agent:main:test",
        )


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {
                "kind": "event",
                "type": "text_delta",
                "payload": {"text": "must not leak"},
            },
            "telemetry.emit must not carry public AgentEvent payloads",
        ),
        (
            {
                "kind": "intent_result",
                "type": "queue.poll",
                "payload": {"ok": True},
                "events": [],
                "session_key": "agent:main:test",
            },
            "telemetry.emit must not carry Pi intent_result payloads",
        ),
    ],
)
@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_reserved_telemetry_payloads_before_custom_port(
    payload: dict[str, Any],
    message: str,
) -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            _ = message, kwargs
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "telemetry.emit",
                "payload": payload,
            }

    class RecordingTelemetry:
        async def handle_intent(self, *, intent_type: str, payload: dict, session_key: str):
            _ = intent_type, session_key
            if payload.get("kind") in {"event", "intent_result"}:
                raise AssertionError(
                    "reserved telemetry payload reached custom telemetry port"
                )
            return []

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-telemetry"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(telemetry=RecordingTelemetry()),
    )

    with pytest.raises(RuntimeError, match=message):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_telemetry_event_frames() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    calls: list[tuple[str, dict, str]] = []

    class RecordingTelemetry:
        async def handle_intent(self, *, intent_type: str, payload: dict, session_key: str):
            calls.append((intent_type, payload, session_key))
            return []

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "telemetry",
                "payload": {"phase": "prepare-next-turn"},
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "ok"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-telemetry"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(telemetry=RecordingTelemetry()),
    )

    with pytest.raises(RuntimeError, match="Unsupported Pi sidecar event type"):
        _ = [event async for event in agent.run_turn("hello")]
    assert calls == []


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_yield_with_pending_tool_calls() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class RecordingPort:
        async def handle_intent(self, **kwargs):
            return []

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "tool.call.prepare",
                "payload": {"tool_call_id": "call-1", "tool_name": "read"},
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "yield.request",
                "payload": {"message": "wait"},
            }

    port = RecordingPort()
    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(tool_bridge=port, orchestration=port),
    )

    with pytest.raises(RuntimeError, match="pending tool calls"):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_yield_request_without_sessions_yield_result() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakeOrchestrationPort:
        async def handle_intent(self, **kwargs):
            assert kwargs["intent_type"] == "yield.request"
            return [TextDeltaEvent(text="orchestration leaked public text")]

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "yield.request",
                "payload": {"message": "wait for child"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-yield-leak"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(orchestration=FakeOrchestrationPort()),
    )

    with pytest.raises(
        RuntimeError,
        match="yield.request must return a sessions_yield ToolResultEvent",
    ):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_stops_consuming_after_yield_request() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakeOrchestrationPort:
        async def handle_intent(self, **kwargs):
            assert kwargs["intent_type"] == "yield.request"
            return [
                ToolResultEvent(
                    tool_use_id="yield-request",
                    tool_name="sessions_yield",
                    result='{"status":"yielded"}',
                )
            ]

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "yield.request",
                "payload": {"message": "wait for child"},
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "should not continue"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-yield-settled"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(orchestration=FakeOrchestrationPort()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        ToolResultEvent(
            tool_use_id="yield-request",
            tool_name="sessions_yield",
            result='{"status":"yielded"}',
        ),
        DoneEvent(text="", model="pi-yield-settled", cost_source="unavailable"),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_does_not_report_successful_yield_result_to_rpc_client() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakeOrchestrationPort:
        async def handle_intent(self, **kwargs):
            assert kwargs["intent_type"] == "yield.request"
            return [
                ToolResultEvent(
                    tool_use_id="yield-request",
                    tool_name="sessions_yield",
                    result='{"status":"yielded"}',
                )
            ]

    feedback_calls: list[dict[str, Any]] = []

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "yield.request",
                "payload": {"message": "wait for child"},
            }

        def receive_intent_result(self, **kwargs) -> None:
            feedback_calls.append(kwargs)

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-yield-settled"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(orchestration=FakeOrchestrationPort()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        ToolResultEvent(
            tool_use_id="yield-request",
            tool_name="sessions_yield",
            result='{"status":"yielded"}',
        ),
        DoneEvent(text="", model="pi-yield-settled", cost_source="unavailable"),
    ]
    assert feedback_calls == []


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_can_emit_yield_tool_start_for_public_parity() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakeOrchestrationPort:
        async def handle_intent(self, **kwargs):
            assert kwargs["intent_type"] == "yield.request"
            return [
                ToolResultEvent(
                    tool_use_id=kwargs["payload"]["tool_call_id"],
                    tool_name="sessions_yield",
                    result='{"status":"yielded"}',
                )
            ]

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "yield.request",
                "payload": {
                    "tool_call_id": "yield-1",
                    "message": "LIVE_AGENT_CORE_YIELD",
                },
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-yield-public-start"),
        session_key="agent:main:test",
        emit_yield_tool_start_events=True,
        host_ports=KernelHostPorts(orchestration=FakeOrchestrationPort()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        ToolUseStartEvent(tool_use_id="yield-1", tool_name="sessions_yield"),
        ToolResultEvent(
            tool_use_id="yield-1",
            tool_name="sessions_yield",
            result='{"status":"yielded"}',
        ),
        DoneEvent(text="", model="pi-yield-public-start", cost_source="unavailable"),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_host_events_after_yield_success() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
        PiSidecarProtocolError,
    )

    class FakeOrchestrationPort:
        async def handle_intent(self, **kwargs):
            assert kwargs["intent_type"] == "yield.request"
            return [
                ToolResultEvent(
                    tool_use_id="yield-request",
                    tool_name="sessions_yield",
                    result='{"status":"yielded"}',
                ),
                TextDeltaEvent(text="must not appear after yield"),
            ]

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "yield.request",
                "payload": {"message": "wait for child"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-yield-settled"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(orchestration=FakeOrchestrationPort()),
    )

    with pytest.raises(
        PiSidecarProtocolError,
        match="yield.request returned events after sessions_yield success",
    ):
        _ = [event async for event in agent.run_turn("hello")]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_does_not_report_invalid_yield_success_batch() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
        PiSidecarProtocolError,
    )

    class FakeOrchestrationPort:
        async def handle_intent(self, **kwargs):
            assert kwargs["intent_type"] == "yield.request"
            return [
                ToolResultEvent(
                    tool_use_id="yield-request",
                    tool_name="sessions_yield",
                    result='{"status":"yielded"}',
                ),
                TextDeltaEvent(text="must not be observed by sidecar"),
            ]

    feedback_calls: list[dict[str, Any]] = []

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "yield.request",
                "payload": {"message": "wait for child"},
            }

        def receive_intent_result(self, **kwargs) -> None:
            feedback_calls.append(kwargs)

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-yield-settled"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(orchestration=FakeOrchestrationPort()),
    )

    with pytest.raises(
        PiSidecarProtocolError,
        match="yield.request returned events after sessions_yield success",
    ):
        _ = [event async for event in agent.run_turn("hello")]

    assert feedback_calls == []


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_can_continue_after_yield_error_result() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakeOrchestrationPort:
        async def handle_intent(self, **kwargs):
            assert kwargs["intent_type"] == "yield.request"
            return [
                ToolResultEvent(
                    tool_use_id="yield-request",
                    tool_name="sessions_yield",
                    result='{"status":"error","message":"no child sessions"}',
                    is_error=True,
                )
            ]

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "yield.request",
                "payload": {"message": "wait for child"},
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "recovered after yield error"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-yield-error-recovery"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(orchestration=FakeOrchestrationPort()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        ToolResultEvent(
            tool_use_id="yield-request",
            tool_name="sessions_yield",
            result='{"status":"error","message":"no child sessions"}',
            is_error=True,
        ),
        TextDeltaEvent(text="recovered after yield error"),
        DoneEvent(
            text="recovered after yield error",
            model="pi-yield-error-recovery",
            cost_source="unavailable",
        ),
    ]


@pytest.mark.asyncio
async def test_pi_jsonl_command_is_closed_after_yield_request_settles(
    tmp_path: Path,
) -> None:
    import asyncio

    from opensquilla.engine.agent_core import (
        KernelHostPorts,
        PiJsonlCommandRpcClient,
        PiSidecarKernelRuntime,
    )

    marker = tmp_path / "terminated-after-yield.txt"
    script = tmp_path / "sleeping_pi_yield_rpc.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import json
            import signal
            import sys
            import time

            def on_term(signum, frame):
                _ = signum, frame
                with open({str(marker)!r}, "w", encoding="utf-8") as marker:
                    marker.write("terminated")
                sys.exit(0)

            signal.signal(signal.SIGTERM, on_term)
            print(json.dumps({{
                "protocol": "opensquilla.agent_core.v1",
                "kind": "intent",
                "type": "yield.request",
                "payload": {{"message": "wait for child"}},
            }}), flush=True)
            time.sleep(30)
            """
        ).lstrip(),
        encoding="utf-8",
    )

    class FakeOrchestrationPort:
        async def handle_intent(self, **kwargs):
            assert kwargs["intent_type"] == "yield.request"
            return [
                ToolResultEvent(
                    tool_use_id="yield-request",
                    tool_name="sessions_yield",
                    result='{"status":"yielded"}',
                )
            ]

    agent = PiSidecarKernelRuntime(
        rpc_client=PiJsonlCommandRpcClient(f"{sys.executable} {script}"),
        config=SimpleNamespace(model_id="pi-yield-jsonl"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(orchestration=FakeOrchestrationPort()),
    )

    async def collect_events():
        return [event async for event in agent.run_turn("hello")]

    events = await asyncio.wait_for(collect_events(), timeout=2.0)

    assert events == [
        ToolResultEvent(
            tool_use_id="yield-request",
            tool_name="sessions_yield",
            result='{"status":"yielded"}',
        ),
        DoneEvent(text="", model="pi-yield-jsonl", cost_source="unavailable"),
    ]
    assert marker.read_text(encoding="utf-8") == "terminated"


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_stream_end_with_pending_tool_calls() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakeToolBridge:
        async def handle_intent(self, **kwargs):
            return []

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "tool.call.prepare",
                "payload": {"tool_call_id": "call-1", "tool_name": "read"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-test"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(tool_bridge=FakeToolBridge()),
    )

    with pytest.raises(RuntimeError, match="pending tool calls"):
        [event async for event in agent.run_turn("hello")]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_clears_pending_tool_after_protocol_error() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakeToolBridge:
        async def handle_intent(self, **kwargs):
            return []

    class FakePiRpcClient:
        def __init__(self) -> None:
            self.turns = 0

        async def stream_prompt(self, message: str, **kwargs):
            self.turns += 1
            if self.turns == 1:
                yield {
                    "protocol": AGENT_CORE_PROTOCOL_VERSION,
                    "kind": "intent",
                    "type": "tool.call.prepare",
                    "payload": {"tool_call_id": "call-1", "tool_name": "read"},
                }
                return
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "clean next turn"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-protocol-recovery"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(tool_bridge=FakeToolBridge()),
    )

    with pytest.raises(RuntimeError, match="pending tool calls"):
        [event async for event in agent.run_turn("first")]

    events = [event async for event in agent.run_turn("second")]

    assert events == [
        TextDeltaEvent(text="clean next turn"),
        DoneEvent(
            text="clean next turn",
            model="pi-protocol-recovery",
            cost_source="unavailable",
        ),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_clears_pending_tool_after_consumer_close() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )
    from opensquilla.engine.types import ToolUseStartEvent

    class FakeToolBridge:
        async def handle_intent(self, **kwargs):
            return [
                ToolUseStartEvent(
                    tool_use_id=kwargs["payload"]["tool_call_id"],
                    tool_name=kwargs["payload"].get("tool_name", "read"),
                )
            ]

    class FakePiRpcClient:
        def __init__(self) -> None:
            self.turns = 0

        async def stream_prompt(self, message: str, **kwargs):
            self.turns += 1
            if self.turns == 1:
                yield {
                    "protocol": AGENT_CORE_PROTOCOL_VERSION,
                    "kind": "intent",
                    "type": "tool.call.prepare",
                    "payload": {"tool_call_id": "call-1", "tool_name": "read"},
                }
                return
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "clean after close"},
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-consumer-close-recovery"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(tool_bridge=FakeToolBridge()),
    )

    stream = agent.run_turn("first")
    first = await stream.__anext__()
    await stream.aclose()

    assert first == ToolUseStartEvent(tool_use_id="call-1", tool_name="read")

    events = [event async for event in agent.run_turn("second")]

    assert events == [
        TextDeltaEvent(text="clean after close"),
        DoneEvent(
            text="clean after close",
            model="pi-consumer-close-recovery",
            cost_source="unavailable",
        ),
    ]


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_concurrent_turns_on_same_runtime() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        PiSidecarKernelRuntime,
    )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": message},
            }
            await asyncio.sleep(30)

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-concurrent-turn"),
        session_key="agent:main:test",
    )

    first_stream = agent.run_turn("first")
    second_stream = None
    try:
        assert await asyncio.wait_for(anext(first_stream), timeout=1.0) == TextDeltaEvent(
            text="first"
        )

        second_stream = agent.run_turn("second")
        with pytest.raises(RuntimeError, match="already has an active turn"):
            await asyncio.wait_for(anext(second_stream), timeout=1.0)
    finally:
        if second_stream is not None:
            await second_stream.aclose()
        await first_stream.aclose()


@pytest.mark.asyncio
async def test_pi_kernel_built_from_runtime_config_wires_tool_intents_to_host_bridge() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        build_agent_for_kernel,
    )
    from opensquilla.engine.types import AgentConfig, ToolCall, ToolResult, ToolUseStartEvent

    calls: list[ToolCall] = []

    async def tool_handler(call: ToolCall) -> ToolResult:
        calls.append(call)
        return ToolResult(
            tool_use_id=call.tool_use_id,
            tool_name=call.tool_name,
            content=f"host handled {call.arguments['marker']}",
        )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "tool.call.prepare",
                "payload": {"tool_call_id": "call-1", "tool_name": "echo"},
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "tool.call.execute",
                "payload": {
                    "tool_call_id": "call-1",
                    "tool_name": "echo",
                    "arguments": {"marker": "from-pi"},
                },
            }

    agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_client=FakePiRpcClient(),
            allow_test_pi_rpc_client=True,
        ),
        provider=object(),
        config=AgentConfig(model_id="pi-host-tool"),
        tool_definitions=[],
        tool_handler=tool_handler,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        ToolUseStartEvent(tool_use_id="call-1", tool_name="echo"),
        ToolResultEvent(
            tool_use_id="call-1",
            tool_name="echo",
            result="host handled from-pi",
            arguments={"marker": "from-pi"},
        ),
        DoneEvent(text="", model="pi-host-tool", cost_source="unavailable"),
    ]
    assert [(call.tool_use_id, call.tool_name, call.arguments) for call in calls] == [
        ("call-1", "echo", {"marker": "from-pi"})
    ]


@pytest.mark.asyncio
async def test_pi_kernel_built_from_runtime_config_wires_provider_intents_to_host_port() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        build_agent_for_kernel,
    )
    from opensquilla.engine.types import AgentConfig, DoneEvent
    from opensquilla.provider import DoneEvent as ProviderDoneEvent
    from opensquilla.provider import TextDeltaEvent as ProviderTextDeltaEvent

    calls: list[dict] = []

    class FakeProvider:
        async def chat(self, messages, *, tools=None, config=None):
            calls.append({"messages": messages, "tools": tools, "config": config})
            yield ProviderTextDeltaEvent(text="host provider")
            yield ProviderDoneEvent(
                input_tokens=5,
                output_tokens=2,
                cached_tokens=1,
                cache_write_tokens=4,
                billed_cost=0.005,
                model="provider-model",
            )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "provider.request",
                "payload": {
                    "messages": [{"role": "user", "content": "hello provider"}],
                    "tools": None,
                    "config": {"max_tokens": 32, "temperature": 0.0},
                },
            }

    agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_client=FakePiRpcClient(),
            allow_test_pi_rpc_client=True,
        ),
        provider=FakeProvider(),
        config=AgentConfig(model_id="pi-host-provider"),
        tool_definitions=[],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events[0] == TextDeltaEvent(text="host provider")
    assert events[1] == DoneEvent(
        text="host provider",
        input_tokens=5,
        output_tokens=2,
        cached_tokens=1,
        cache_write_tokens=4,
        cost_usd=0.005,
        billed_cost=0.005,
        cost_source="provider_billed",
        model="provider-model",
        iterations=1,
    )
    assert calls[0]["messages"][0].content == "hello provider"
    assert calls[0]["config"].max_tokens == 16384
    assert calls[0]["config"].temperature is None


@pytest.mark.asyncio
async def test_pi_provider_usage_rejects_non_numeric_token_accounting() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        build_agent_for_kernel,
    )
    from opensquilla.engine.types import AgentConfig
    from opensquilla.provider import DoneEvent as ProviderDoneEvent

    class FakeProvider:
        async def chat(self, messages, *, tools=None, config=None):
            _ = messages, tools, config
            done = ProviderDoneEvent(
                input_tokens=3,
                output_tokens=2,
                billed_cost=0.005,
                model="provider-model",
            )
            done.input_tokens = "3"
            yield done

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "provider.request",
                "payload": {"messages": [{"role": "user", "content": "hello"}]},
            }

    agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_client=FakePiRpcClient(),
            allow_test_pi_rpc_client=True,
        ),
        provider=FakeProvider(),
        config=AgentConfig(model_id="pi-provider-usage"),
        tool_definitions=[],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        ErrorEvent(
            message="provider usage input_tokens must be an integer",
            code="pi_sidecar_error",
        )
    ]


@pytest.mark.asyncio
async def test_pi_provider_usage_rejects_negative_token_accounting() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        build_agent_for_kernel,
    )
    from opensquilla.engine.types import AgentConfig
    from opensquilla.provider import DoneEvent as ProviderDoneEvent

    class FakeProvider:
        async def chat(self, messages, *, tools=None, config=None):
            _ = messages, tools, config
            yield ProviderDoneEvent(
                input_tokens=-1,
                output_tokens=2,
                billed_cost=0.005,
                model="provider-model",
            )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "provider.request",
                "payload": {"messages": [{"role": "user", "content": "hello"}]},
            }

    agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_client=FakePiRpcClient(),
            allow_test_pi_rpc_client=True,
        ),
        provider=FakeProvider(),
        config=AgentConfig(model_id="pi-provider-usage"),
        tool_definitions=[],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        ErrorEvent(
            message="provider usage input_tokens must be a non-negative integer",
            code="pi_sidecar_error",
        )
    ]


@pytest.mark.parametrize("cache_field", ["cached_tokens", "cache_write_tokens"])
@pytest.mark.asyncio
async def test_pi_provider_usage_rejects_cache_tokens_above_input_in_accumulator(
    cache_field: str,
) -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        build_agent_for_kernel,
    )
    from opensquilla.engine.types import AgentConfig
    from opensquilla.provider import DoneEvent as ProviderDoneEvent

    class FakeProvider:
        async def chat(self, messages, *, tools=None, config=None):
            _ = messages, tools, config
            done = ProviderDoneEvent(
                input_tokens=2,
                output_tokens=1,
                cached_tokens=0,
                cache_write_tokens=0,
                billed_cost=0.005,
                model="provider-model",
            )
            setattr(done, cache_field, 3)
            yield done

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "provider.request",
                "payload": {"messages": [{"role": "user", "content": "hello"}]},
            }

    agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_client=FakePiRpcClient(),
            allow_test_pi_rpc_client=True,
        ),
        provider=FakeProvider(),
        config=AgentConfig(model_id="pi-provider-usage"),
        tool_definitions=[],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        ErrorEvent(
            message=f"provider usage {cache_field} must be <= input_tokens",
            code="pi_sidecar_error",
        )
    ]


@pytest.mark.asyncio
async def test_pi_provider_direct_done_rejects_non_numeric_cost_before_engine_done() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.provider import DoneEvent as ProviderDoneEvent

    class FakeProvider:
        async def chat(self, messages, *, tools=None, config=None):
            _ = messages, tools, config
            done = ProviderDoneEvent(
                input_tokens=3,
                output_tokens=2,
                billed_cost=0.005,
                model="provider-model",
            )
            done.billed_cost = "0.005"
            yield done

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="host-model"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    with pytest.raises(RuntimeError, match="provider usage billed_cost must be a number"):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={"messages": [{"role": "user", "content": "hello"}]},
        )


@pytest.mark.asyncio
async def test_pi_provider_direct_done_rejects_non_finite_cost_before_engine_done() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.provider import DoneEvent as ProviderDoneEvent

    class FakeProvider:
        async def chat(self, messages, *, tools=None, config=None):
            _ = messages, tools, config
            yield ProviderDoneEvent(
                input_tokens=3,
                output_tokens=2,
                billed_cost=float("inf"),
                model="provider-model",
            )

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="host-model"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    with pytest.raises(RuntimeError, match="provider usage billed_cost must be finite"):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={"messages": [{"role": "user", "content": "hello"}]},
        )


@pytest.mark.asyncio
async def test_pi_provider_direct_done_rejects_negative_cost_before_engine_done() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.provider import DoneEvent as ProviderDoneEvent

    class FakeProvider:
        async def chat(self, messages, *, tools=None, config=None):
            _ = messages, tools, config
            yield ProviderDoneEvent(
                input_tokens=3,
                output_tokens=2,
                billed_cost=-0.005,
                model="provider-model",
            )

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="host-model"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    with pytest.raises(
        RuntimeError,
        match="provider usage billed_cost must be a non-negative number",
    ):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={"messages": [{"role": "user", "content": "hello"}]},
        )


@pytest.mark.asyncio
async def test_pi_provider_done_rejects_non_string_stop_reason_before_terminal_handling() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.provider import DoneEvent as ProviderDoneEvent

    class FakeProvider:
        async def chat(self, messages, *, tools=None, config=None):
            _ = messages, tools, config
            done = ProviderDoneEvent(
                input_tokens=3,
                output_tokens=2,
                billed_cost=0.005,
                model="provider-model",
            )
            done.stop_reason = 3
            yield done

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="host-model"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    with pytest.raises(RuntimeError, match="provider done stop_reason must be a string"):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={"messages": [{"role": "user", "content": "hello"}]},
        )


@pytest.mark.parametrize(
    ("case", "expected_message"),
    [
        (
            "event_after_done",
            "KernelHostPorts.provider returned events after terminal event",
        ),
        (
            "multiple_done",
            "KernelHostPorts.provider returned multiple terminal events",
        ),
    ],
)
@pytest.mark.asyncio
async def test_pi_provider_direct_done_rejects_terminal_batch_violations(
    case: str,
    expected_message: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.provider import DoneEvent as ProviderDoneEvent
    from opensquilla.provider import TextDeltaEvent as ProviderTextDeltaEvent

    class FakeProvider:
        async def chat(self, messages, *, tools=None, config=None):
            _ = messages, tools, config
            yield ProviderDoneEvent(
                input_tokens=2,
                output_tokens=1,
                billed_cost=0.005,
                model="provider-model",
            )
            if case == "event_after_done":
                yield ProviderTextDeltaEvent(text="late")
            else:
                yield ProviderDoneEvent(
                    input_tokens=2,
                    output_tokens=1,
                    billed_cost=0.005,
                    model="provider-model",
                )

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="host-model"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    with pytest.raises(RuntimeError, match=expected_message):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={"messages": [{"role": "user", "content": "hello"}]},
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field_name", "match"),
    [
        ("model", "provider usage model must be a string"),
        ("cost_source", "provider usage cost_source must be a string"),
    ],
)
async def test_pi_provider_done_rejects_null_string_accounting_fields_before_fallback(
    field_name: str,
    match: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.provider import DoneEvent as ProviderDoneEvent

    class FakeProvider:
        async def chat(self, messages, *, tools=None, config=None):
            _ = messages, tools, config
            done = ProviderDoneEvent(
                input_tokens=3,
                output_tokens=2,
                billed_cost=0.005,
                model="provider-model",
                cost_source="provider_billed",
            )
            setattr(done, field_name, None)
            yield done

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="host-model"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    with pytest.raises(RuntimeError, match=match):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={"messages": [{"role": "user", "content": "hello"}]},
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("field_name", ["input_tokens", "cache_write_tokens"])
async def test_pi_provider_done_rejects_null_integer_accounting_fields_before_zero_fallback(
    field_name: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.provider import DoneEvent as ProviderDoneEvent

    class FakeProvider:
        async def chat(self, messages, *, tools=None, config=None):
            _ = messages, tools, config
            done = ProviderDoneEvent(
                input_tokens=3,
                output_tokens=2,
                cache_write_tokens=1,
                billed_cost=0.005,
                model="provider-model",
            )
            setattr(done, field_name, None)
            yield done

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="host-model"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    with pytest.raises(
        RuntimeError,
        match=f"provider usage {field_name} must be an integer",
    ):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={"messages": [{"role": "user", "content": "hello"}]},
        )


@pytest.mark.parametrize("cache_field", ["cached_tokens", "cache_write_tokens"])
@pytest.mark.asyncio
async def test_pi_provider_direct_done_rejects_cache_tokens_above_input_before_engine_done(
    cache_field: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.provider import DoneEvent as ProviderDoneEvent

    class FakeProvider:
        async def chat(self, messages, *, tools=None, config=None):
            _ = messages, tools, config
            done = ProviderDoneEvent(
                input_tokens=2,
                output_tokens=1,
                cached_tokens=0,
                cache_write_tokens=0,
                billed_cost=0.005,
                model="provider-model",
            )
            setattr(done, cache_field, 3)
            yield done

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="host-model"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    with pytest.raises(
        RuntimeError,
        match=f"provider usage {cache_field} must be <= input_tokens",
    ):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={"messages": [{"role": "user", "content": "hello"}]},
        )


@pytest.mark.asyncio
async def test_pi_provider_done_rejects_null_cost_accounting_before_zero_fallback() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.provider import DoneEvent as ProviderDoneEvent

    class FakeProvider:
        async def chat(self, messages, *, tools=None, config=None):
            _ = messages, tools, config
            done = ProviderDoneEvent(
                input_tokens=3,
                output_tokens=2,
                cache_write_tokens=1,
                billed_cost=0.005,
                model="provider-model",
            )
            done.billed_cost = None
            yield done

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="host-model"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    with pytest.raises(
        RuntimeError,
        match="provider usage billed_cost must be a number",
    ):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={"messages": [{"role": "user", "content": "hello"}]},
        )


@pytest.mark.asyncio
async def test_pi_provider_nonterminal_done_rejects_malformed_usage_without_accumulator() -> None:
    from opensquilla.engine.agent_core import OpenSquillaProviderHostPort
    from opensquilla.provider import DoneEvent as ProviderDoneEvent

    class FakeProvider:
        async def chat(self, messages, *, tools=None, config=None):
            _ = messages, tools, config
            done = ProviderDoneEvent(
                stop_reason="tool_use",
                input_tokens=3,
                output_tokens=2,
                billed_cost=0.005,
                model="provider-model",
            )
            done.input_tokens = "3"
            yield done

    host_agent = SimpleNamespace(
        provider=FakeProvider(),
        tool_definitions=[],
        config=SimpleNamespace(model_id="host-model"),
    )
    port = OpenSquillaProviderHostPort(host_agent)

    with pytest.raises(RuntimeError, match="provider usage input_tokens must be an integer"):
        await port.handle_intent(
            intent_type="provider.request",
            session_key="agent:main:test",
            payload={"messages": [{"role": "user", "content": "hello"}]},
        )


@pytest.mark.asyncio
async def test_pi_kernel_carries_nonterminal_provider_usage_to_final_done() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        build_agent_for_kernel,
    )
    from opensquilla.engine.types import AgentConfig, ToolCall, ToolResult, ToolUseStartEvent
    from opensquilla.provider import DoneEvent as ProviderDoneEvent
    from opensquilla.provider import ToolUseEndEvent as ProviderToolUseEndEvent
    from opensquilla.provider import ToolUseStartEvent as ProviderToolUseStartEvent

    async def tool_handler(call: ToolCall) -> ToolResult:
        return ToolResult(
            tool_use_id=call.tool_use_id,
            tool_name=call.tool_name,
            content=f"host handled {call.arguments['marker']}",
        )

    class FakeProvider:
        async def chat(self, messages, *, tools=None, config=None):
            _ = messages, tools, config
            yield ProviderToolUseStartEvent(tool_use_id="call-1", tool_name="echo")
            yield ProviderToolUseEndEvent(
                tool_use_id="call-1",
                tool_name="echo",
                arguments={"marker": "provider-tool"},
            )
            yield ProviderDoneEvent(
                stop_reason="tool_use",
                input_tokens=11,
                output_tokens=7,
                reasoning_tokens=5,
                cached_tokens=3,
                cache_write_tokens=2,
                billed_cost=0.125,
                model="provider-model",
            )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "provider.request",
                "payload": {
                    "messages": [{"role": "user", "content": "use echo"}],
                },
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "tool.call.prepare",
                "payload": {
                    "tool_call_id": "call-1",
                    "tool_name": "echo",
                    "arguments": {"marker": "provider-tool"},
                },
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "tool.call.execute",
                "payload": {
                    "tool_call_id": "call-1",
                    "tool_name": "echo",
                    "arguments": {"marker": "provider-tool"},
                },
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "final answer"},
            }

    agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_client=FakePiRpcClient(),
            allow_test_pi_rpc_client=True,
        ),
        provider=FakeProvider(),
        config=AgentConfig(model_id="pi-provider-usage"),
        tool_definitions=[],
        tool_handler=tool_handler,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        ToolUseStartEvent(tool_use_id="call-1", tool_name="echo"),
        ToolResultEvent(
            tool_use_id="call-1",
            tool_name="echo",
            result="host handled provider-tool",
            arguments={"marker": "provider-tool"},
        ),
        TextDeltaEvent(text="final answer"),
        DoneEvent(
            text="final answer",
            input_tokens=11,
            output_tokens=7,
            reasoning_tokens=5,
            cached_tokens=3,
            cache_write_tokens=2,
            cost_usd=0.125,
            billed_cost=0.125,
            cost_source="provider_billed",
            model="provider-model",
            iterations=1,
        ),
    ]


@pytest.mark.asyncio
async def test_pi_kernel_clears_nonterminal_provider_usage_after_error_turn() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        build_agent_for_kernel,
    )
    from opensquilla.engine.types import AgentConfig, ToolCall, ToolResult
    from opensquilla.provider import DoneEvent as ProviderDoneEvent
    from opensquilla.provider import ToolUseEndEvent as ProviderToolUseEndEvent
    from opensquilla.provider import ToolUseStartEvent as ProviderToolUseStartEvent

    async def tool_handler(call: ToolCall) -> ToolResult:
        return ToolResult(
            tool_use_id=call.tool_use_id,
            tool_name=call.tool_name,
            content="host handled first turn",
        )

    class FakeProvider:
        async def chat(self, messages, *, tools=None, config=None):
            _ = messages, tools, config
            yield ProviderToolUseStartEvent(tool_use_id="call-1", tool_name="echo")
            yield ProviderToolUseEndEvent(
                tool_use_id="call-1",
                tool_name="echo",
                arguments={"marker": "first-turn"},
            )
            yield ProviderDoneEvent(
                stop_reason="tool_use",
                input_tokens=11,
                output_tokens=7,
                cached_tokens=3,
                cache_write_tokens=2,
                billed_cost=0.125,
                model="provider-model",
            )

    class FakePiRpcClient:
        def __init__(self) -> None:
            self.turns = 0

        async def stream_prompt(self, message: str, **kwargs):
            self.turns += 1
            if self.turns == 1:
                yield {
                    "protocol": AGENT_CORE_PROTOCOL_VERSION,
                    "kind": "intent",
                    "type": "provider.request",
                    "payload": {
                        "messages": [{"role": "user", "content": "use echo"}],
                    },
                }
                yield {
                    "protocol": AGENT_CORE_PROTOCOL_VERSION,
                    "kind": "event",
                    "type": "error",
                    "payload": {"message": "sidecar failed", "code": "boom"},
                }
                return
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "clean next turn"},
            }

    agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_client=FakePiRpcClient(),
            allow_test_pi_rpc_client=True,
        ),
        provider=FakeProvider(),
        config=AgentConfig(model_id="pi-provider-usage-reset"),
        tool_definitions=[],
        tool_handler=tool_handler,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )

    first_turn = [event async for event in agent.run_turn("first")]
    second_turn = [event async for event in agent.run_turn("second")]

    assert first_turn[-1] == ErrorEvent(message="sidecar failed", code="boom")
    assert second_turn == [
        TextDeltaEvent(text="clean next turn"),
        DoneEvent(
            text="clean next turn",
            model="pi-provider-usage-reset",
            cost_source="unavailable",
        ),
    ]


@pytest.mark.asyncio
async def test_pi_kernel_provider_intent_error_stays_on_agent_event_stream() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        build_agent_for_kernel,
    )
    from opensquilla.engine.types import AgentConfig
    from opensquilla.provider import ErrorEvent as ProviderErrorEvent
    from opensquilla.provider import TextDeltaEvent as ProviderTextDeltaEvent

    class FakeProvider:
        async def chat(self, messages, *, tools=None, config=None):
            _ = messages, tools, config
            yield ProviderTextDeltaEvent(text="partial")
            yield ProviderErrorEvent(message="provider failed", code="rate_limit")

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "provider.request",
                "payload": {
                    "messages": [{"role": "user", "content": "hello provider"}],
                    "tools": None,
                    "config": {"max_tokens": 32},
                },
            }

    agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_client=FakePiRpcClient(),
            allow_test_pi_rpc_client=True,
        ),
        provider=FakeProvider(),
        config=AgentConfig(model_id="pi-host-provider"),
        tool_definitions=[],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="partial"),
        ErrorEvent(message="provider failed", code="rate_limit"),
    ]


@pytest.mark.asyncio
async def test_pi_kernel_built_from_runtime_config_wires_session_write_to_host_manager() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        build_agent_for_kernel,
    )
    from opensquilla.engine.types import AgentConfig

    writes: list[dict] = []
    context_entries: list[str] = []

    class FakeSessionManager:
        async def append_message(self, session_key: str, **kwargs):
            writes.append({"session_key": session_key, **kwargs})
            return SimpleNamespace(id="entry-1")

    @contextlib.asynccontextmanager
    async def write_context():
        context_entries.append("entered")
        yield
        context_entries.append("exited")

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "session.write.enqueue",
                "payload": {
                    "session_key": "agent:main:test",
                    "role": "assistant",
                    "content": "persist me",
                    "token_count": 7,
                },
            }

    agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_client=FakePiRpcClient(),
            allow_test_pi_rpc_client=True,
        ),
        provider=object(),
        config=AgentConfig(model_id="pi-host-session"),
        tool_definitions=[],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
        session_manager=FakeSessionManager(),
        session_write_context_factory=lambda session_key: write_context(),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        DoneEvent(text="", model="pi-host-session", cost_source="unavailable")
    ]
    assert context_entries == ["entered", "exited"]
    assert writes == [
        {
            "session_key": "agent:main:test",
            "role": "assistant",
            "content": "persist me",
            "tool_calls": None,
            "reasoning_content": None,
            "turn_usage": None,
            "token_count": 7,
        }
    ]


@pytest.mark.asyncio
async def test_pi_session_write_rejects_cross_session_target() -> None:
    from opensquilla.engine.agent_core import OpenSquillaSessionWritesHostPort

    class FakeSessionManager:
        async def append_message(self, session_key: str, **kwargs):
            _ = session_key, kwargs
            raise AssertionError("cross-session write must not reach SessionManager")

    port = OpenSquillaSessionWritesHostPort(session_manager=FakeSessionManager())

    with pytest.raises(RuntimeError, match="cannot target a different session_key"):
        await port.handle_intent(
            intent_type="session.write.enqueue",
            payload={
                "session_key": "agent:main:other",
                "role": "assistant",
                "content": "wrong target",
            },
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_session_write_rejects_non_string_host_session_key_before_manager_call() -> None:
    from opensquilla.engine.agent_core import OpenSquillaSessionWritesHostPort

    class FakeSessionManager:
        async def append_message(self, session_key: str, **kwargs):
            _ = session_key, kwargs
            raise AssertionError("non-string host session_key must not reach SessionManager")

    port = OpenSquillaSessionWritesHostPort(session_manager=FakeSessionManager())

    with pytest.raises(RuntimeError, match="session.write.enqueue session_key must be a string"):
        await port.handle_intent(
            intent_type="session.write.enqueue",
            payload={
                "role": "assistant",
                "content": "persist me",
            },
            session_key={"not": "a string"},  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_pi_session_write_rejects_privileged_system_role() -> None:
    from opensquilla.engine.agent_core import OpenSquillaSessionWritesHostPort

    class FakeSessionManager:
        async def append_message(self, session_key: str, **kwargs):
            _ = session_key, kwargs
            raise AssertionError("privileged role write must not reach SessionManager")

    port = OpenSquillaSessionWritesHostPort(session_manager=FakeSessionManager())

    with pytest.raises(RuntimeError, match="cannot write privileged role"):
        await port.handle_intent(
            intent_type="session.write.enqueue",
            payload={
                "session_key": "agent:main:test",
                "role": "system",
                "content": "sidecar-owned system prompt",
            },
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_session_write_normalizes_privileged_role_before_rejecting() -> None:
    from opensquilla.engine.agent_core import OpenSquillaSessionWritesHostPort

    class FakeSessionManager:
        async def append_message(self, session_key: str, **kwargs):
            _ = session_key, kwargs
            raise AssertionError("privileged role write must not reach SessionManager")

    port = OpenSquillaSessionWritesHostPort(session_manager=FakeSessionManager())

    with pytest.raises(RuntimeError, match="cannot write privileged role"):
        await port.handle_intent(
            intent_type="session.write.enqueue",
            payload={
                "session_key": "agent:main:test",
                "role": " System ",
                "content": "sidecar-owned system prompt",
            },
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_session_write_rejects_non_string_role_before_manager_call() -> None:
    from opensquilla.engine.agent_core import OpenSquillaSessionWritesHostPort

    class FakeSessionManager:
        async def append_message(self, session_key: str, **kwargs):
            _ = session_key, kwargs
            raise AssertionError("structured role write must not reach SessionManager")

    port = OpenSquillaSessionWritesHostPort(session_manager=FakeSessionManager())

    with pytest.raises(RuntimeError, match="session.write.enqueue role must be a string"):
        await port.handle_intent(
            intent_type="session.write.enqueue",
            payload={
                "session_key": "agent:main:test",
                "role": {"nested": "object"},
                "content": "structured role",
            },
            session_key="agent:main:test",
        )


@pytest.mark.parametrize("role", ["", "developer", "system_notice"])
@pytest.mark.asyncio
async def test_pi_session_write_rejects_unsupported_role_before_manager_call(
    role: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaSessionWritesHostPort

    class FakeSessionManager:
        async def append_message(self, session_key: str, **kwargs):
            _ = session_key, kwargs
            raise AssertionError("unsupported role write must not reach SessionManager")

    port = OpenSquillaSessionWritesHostPort(session_manager=FakeSessionManager())

    with pytest.raises(
        RuntimeError,
        match="session.write.enqueue role must be user, assistant, or tool",
    ):
        await port.handle_intent(
            intent_type="session.write.enqueue",
            payload={
                "session_key": "agent:main:test",
                "role": role,
                "content": "unsupported role",
            },
            session_key="agent:main:test",
        )


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("content", "session.write.enqueue content must be a string"),
        (
            "reasoning_content",
            "session.write.enqueue reasoning_content must be a string",
        ),
    ],
)
@pytest.mark.asyncio
async def test_pi_session_write_rejects_non_string_content_fields_before_manager_call(
    field: str,
    message: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaSessionWritesHostPort

    class FakeSessionManager:
        async def append_message(self, session_key: str, **kwargs):
            _ = session_key, kwargs
            raise AssertionError("structured content write must not reach SessionManager")

    port = OpenSquillaSessionWritesHostPort(session_manager=FakeSessionManager())
    payload = {
        "session_key": "agent:main:test",
        "role": "assistant",
        "content": "persist",
        field: {"nested": "object"},
    }

    with pytest.raises(RuntimeError, match=message):
        await port.handle_intent(
            intent_type="session.write.enqueue",
            payload=payload,
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_session_write_rejects_unknown_payload_fields_before_manager_call() -> None:
    from opensquilla.engine.agent_core import OpenSquillaSessionWritesHostPort

    class FakeSessionManager:
        async def append_message(self, session_key: str, **kwargs):
            _ = session_key, kwargs
            raise AssertionError("unknown session write field must not reach SessionManager")

    port = OpenSquillaSessionWritesHostPort(session_manager=FakeSessionManager())

    with pytest.raises(
        RuntimeError,
        match="session.write.enqueue unsupported payload field",
    ):
        await port.handle_intent(
            intent_type="session.write.enqueue",
            payload={
                "session_key": "agent:main:test",
                "role": "assistant",
                "content": "persist",
                "metadata": {"sidecar_owned": True},
            },
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_session_write_rejects_explicit_null_content_before_manager_call() -> None:
    from opensquilla.engine.agent_core import OpenSquillaSessionWritesHostPort

    class FakeSessionManager:
        async def append_message(self, session_key: str, **kwargs):
            _ = session_key, kwargs
            raise AssertionError("null content write must not reach SessionManager")

    port = OpenSquillaSessionWritesHostPort(session_manager=FakeSessionManager())

    with pytest.raises(RuntimeError, match="session.write.enqueue content must be a string"):
        await port.handle_intent(
            intent_type="session.write.enqueue",
            payload={
                "session_key": "agent:main:test",
                "role": "assistant",
                "content": None,
            },
            session_key="agent:main:test",
        )


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("tool_calls", "session.write.enqueue tool_calls must be a list"),
        ("turn_usage", "session.write.enqueue turn_usage must be an object"),
        ("token_count", "session.write.enqueue token_count must be an integer"),
        (
            "reasoning_content",
            "session.write.enqueue reasoning_content must be a string",
        ),
    ],
)
@pytest.mark.asyncio
async def test_pi_session_write_rejects_explicit_null_auxiliary_fields_before_manager_call(
    field: str,
    message: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaSessionWritesHostPort

    class FakeSessionManager:
        async def append_message(self, session_key: str, **kwargs):
            _ = session_key, kwargs
            raise AssertionError("null auxiliary field must not reach SessionManager")

    port = OpenSquillaSessionWritesHostPort(session_manager=FakeSessionManager())
    payload = {
        "session_key": "agent:main:test",
        "role": "assistant",
        "content": "persist",
        field: None,
    }

    with pytest.raises(RuntimeError, match=message):
        await port.handle_intent(
            intent_type="session.write.enqueue",
            payload=payload,
            session_key="agent:main:test",
        )


@pytest.mark.parametrize(
    ("field", "bad_value", "message"),
    [
        ("tool_calls", {"name": "read"}, "session.write.enqueue tool_calls must be a list"),
        ("turn_usage", ["tokens"], "session.write.enqueue turn_usage must be an object"),
        ("token_count", 1.5, "session.write.enqueue token_count must be an integer"),
        (
            "token_count",
            -1,
            "session.write.enqueue token_count must be a non-negative integer",
        ),
    ],
)
@pytest.mark.asyncio
async def test_pi_session_write_rejects_malformed_auxiliary_fields_before_manager_call(
    field: str,
    bad_value: object,
    message: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaSessionWritesHostPort

    class FakeSessionManager:
        async def append_message(self, session_key: str, **kwargs):
            _ = session_key, kwargs
            raise AssertionError("malformed auxiliary field must not reach SessionManager")

    port = OpenSquillaSessionWritesHostPort(session_manager=FakeSessionManager())
    payload = {
        "session_key": "agent:main:test",
        "role": "assistant",
        "content": "persist",
        field: bad_value,
    }

    with pytest.raises(RuntimeError, match=message):
        await port.handle_intent(
            intent_type="session.write.enqueue",
            payload=payload,
            session_key="agent:main:test",
        )


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("tool_calls", [{"name": "read", "arguments": {1: "numeric key"}}]),
        ("turn_usage", {"tokens": {"cached": float("nan")}}),
        ("turn_usage", {"opaque": object()}),
    ],
)
@pytest.mark.asyncio
async def test_pi_session_write_rejects_python_only_auxiliary_fields_before_manager_call(
    field: str,
    bad_value: object,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaSessionWritesHostPort

    class FakeSessionManager:
        async def append_message(self, session_key: str, **kwargs):
            _ = session_key, kwargs
            raise AssertionError("Python-only auxiliary field must not reach SessionManager")

    port = OpenSquillaSessionWritesHostPort(session_manager=FakeSessionManager())
    payload = {
        "session_key": "agent:main:test",
        "role": "assistant",
        "content": "persist",
        field: bad_value,
    }

    with pytest.raises(RuntimeError, match="Pi sidecar JSON"):
        await port.handle_intent(
            intent_type="session.write.enqueue",
            payload=payload,
            session_key="agent:main:test",
        )


@pytest.mark.parametrize(
    ("turn_usage", "message"),
    [
        (
            {"input_tokens": -1},
            "session.write.enqueue turn_usage input_tokens must be a non-negative integer",
        ),
        (
            {"total_tokens": -1},
            "session.write.enqueue turn_usage total_tokens must be a non-negative integer",
        ),
        (
            {"iterations": -1},
            "session.write.enqueue turn_usage iterations must be a non-negative integer",
        ),
        (
            {"runtime_context_chars": -1},
            "session.write.enqueue turn_usage runtime_context_chars must be a non-negative integer",
        ),
        (
            {"input_tokens": 4, "cached_tokens": 5},
            "session.write.enqueue turn_usage cached_tokens must be <= input_tokens",
        ),
    ],
)
@pytest.mark.asyncio
async def test_pi_session_write_rejects_impossible_turn_usage_before_manager_call(
    turn_usage: dict[str, object],
    message: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaSessionWritesHostPort

    class FakeSessionManager:
        async def append_message(self, session_key: str, **kwargs):
            _ = session_key, kwargs
            raise AssertionError("impossible turn_usage must not reach SessionManager")

    port = OpenSquillaSessionWritesHostPort(session_manager=FakeSessionManager())

    with pytest.raises(RuntimeError, match=message):
        await port.handle_intent(
            intent_type="session.write.enqueue",
            payload={
                "session_key": "agent:main:test",
                "role": "assistant",
                "content": "persist",
                "turn_usage": turn_usage,
            },
            session_key="agent:main:test",
        )


@pytest.mark.parametrize(
    ("turn_usage", "message"),
    [
        (
            {"total_savings_pct": -1.0},
            "session.write.enqueue turn_usage total_savings_pct must be a non-negative number",
        ),
        (
            {"total_savings_usd": -0.01},
            "session.write.enqueue turn_usage total_savings_usd must be a non-negative number",
        ),
    ],
)
@pytest.mark.asyncio
async def test_pi_session_write_rejects_impossible_turn_usage_savings_before_manager_call(
    turn_usage: dict[str, object],
    message: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaSessionWritesHostPort

    class FakeSessionManager:
        async def append_message(self, session_key: str, **kwargs):
            _ = session_key, kwargs
            raise AssertionError("impossible turn_usage savings must not reach SessionManager")

    port = OpenSquillaSessionWritesHostPort(session_manager=FakeSessionManager())

    with pytest.raises(RuntimeError, match=message):
        await port.handle_intent(
            intent_type="session.write.enqueue",
            payload={
                "session_key": "agent:main:test",
                "role": "assistant",
                "content": "persist",
                "turn_usage": turn_usage,
            },
            session_key="agent:main:test",
        )


@pytest.mark.parametrize(
    ("turn_usage", "message"),
    [
        (
            {"cost_source": {"source": "provider_billed"}},
            "session.write.enqueue turn_usage cost_source must be a string",
        ),
        (
            {"routed_tier": {"tier": "c2"}},
            "session.write.enqueue turn_usage routed_tier must be a string or None",
        ),
    ],
)
@pytest.mark.asyncio
async def test_pi_session_write_rejects_malformed_turn_usage_string_metadata_before_manager_call(
    turn_usage: dict[str, object],
    message: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaSessionWritesHostPort

    class FakeSessionManager:
        async def append_message(self, session_key: str, **kwargs):
            _ = session_key, kwargs
            raise AssertionError(
                "malformed turn_usage metadata must not reach SessionManager"
            )

    port = OpenSquillaSessionWritesHostPort(session_manager=FakeSessionManager())

    with pytest.raises(RuntimeError, match=message):
        await port.handle_intent(
            intent_type="session.write.enqueue",
            payload={
                "session_key": "agent:main:test",
                "role": "assistant",
                "content": "persist",
                "turn_usage": turn_usage,
            },
            session_key="agent:main:test",
        )


@pytest.mark.parametrize(
    ("turn_usage", "message"),
    [
        (
            {"routing_applied": "yes"},
            "session.write.enqueue turn_usage routing_applied must be a boolean",
        ),
        (
            {"cache_hit_active": "yes"},
            "session.write.enqueue turn_usage cache_hit_active must be a boolean",
        ),
    ],
)
@pytest.mark.asyncio
async def test_pi_session_write_rejects_malformed_turn_usage_boolean_metadata(
    turn_usage: dict[str, object],
    message: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaSessionWritesHostPort

    class FakeSessionManager:
        async def append_message(self, session_key: str, **kwargs):
            _ = session_key, kwargs
            raise AssertionError(
                "malformed turn_usage boolean metadata must not reach SessionManager"
            )

    port = OpenSquillaSessionWritesHostPort(session_manager=FakeSessionManager())

    with pytest.raises(RuntimeError, match=message):
        await port.handle_intent(
            intent_type="session.write.enqueue",
            payload={
                "session_key": "agent:main:test",
                "role": "assistant",
                "content": "persist",
                "turn_usage": turn_usage,
            },
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_session_write_rejects_bad_turn_usage_routing_confidence() -> None:
    from opensquilla.engine.agent_core import OpenSquillaSessionWritesHostPort

    class FakeSessionManager:
        async def append_message(self, session_key: str, **kwargs):
            _ = session_key, kwargs
            raise AssertionError(
                "out-of-range routing confidence must not reach SessionManager"
            )

    port = OpenSquillaSessionWritesHostPort(session_manager=FakeSessionManager())

    with pytest.raises(
        RuntimeError,
        match="session.write.enqueue turn_usage routing_confidence must be a probability",
    ):
        await port.handle_intent(
            intent_type="session.write.enqueue",
            payload={
                "session_key": "agent:main:test",
                "role": "assistant",
                "content": "persist",
                "turn_usage": {"routing_confidence": 1.5},
            },
            session_key="agent:main:test",
        )


@pytest.mark.parametrize("field_name", ["cache_hit_rate", "kv_cache_hit_rate"])
@pytest.mark.asyncio
async def test_pi_session_write_rejects_bad_turn_usage_cache_rate(
    field_name: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaSessionWritesHostPort

    class FakeSessionManager:
        async def append_message(self, session_key: str, **kwargs):
            _ = session_key, kwargs
            raise AssertionError(
                "out-of-range cache hit rate must not reach SessionManager"
            )

    port = OpenSquillaSessionWritesHostPort(session_manager=FakeSessionManager())

    with pytest.raises(
        RuntimeError,
        match=f"session.write.enqueue turn_usage {field_name} must be a probability",
    ):
        await port.handle_intent(
            intent_type="session.write.enqueue",
            payload={
                "session_key": "agent:main:test",
                "role": "assistant",
                "content": "persist",
                "turn_usage": {field_name: 1.5},
            },
            session_key="agent:main:test",
        )


@pytest.mark.parametrize("bad_tool_call", ["read", ["read"]])
@pytest.mark.asyncio
async def test_pi_session_write_rejects_non_object_tool_call_entries_before_manager_call(
    bad_tool_call: object,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaSessionWritesHostPort

    class FakeSessionManager:
        async def append_message(self, session_key: str, **kwargs):
            _ = session_key, kwargs
            raise AssertionError("malformed tool_call entry must not reach SessionManager")

    port = OpenSquillaSessionWritesHostPort(session_manager=FakeSessionManager())
    payload = {
        "session_key": "agent:main:test",
        "role": "assistant",
        "content": "persist",
        "tool_calls": [bad_tool_call],
    }

    with pytest.raises(
        RuntimeError,
        match="session.write.enqueue tool_calls entries must be objects",
    ):
        await port.handle_intent(
            intent_type="session.write.enqueue",
            payload=payload,
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_session_write_copies_nested_payload_before_manager_call() -> None:
    from opensquilla.engine.agent_core import OpenSquillaSessionWritesHostPort

    class FakeSessionManager:
        async def append_message(self, session_key: str, **kwargs):
            _ = session_key
            kwargs["tool_calls"][0]["arguments"]["value"] = "mutated"
            kwargs["turn_usage"]["tokens"]["input"] = 99
            return SimpleNamespace(id="entry-1")

    port = OpenSquillaSessionWritesHostPort(session_manager=FakeSessionManager())
    payload = {
        "session_key": "agent:main:test",
        "role": "assistant",
        "content": "persist",
        "tool_calls": [{"name": "read", "arguments": {"value": "original"}}],
        "turn_usage": {"tokens": {"input": 1}},
    }

    await port.handle_intent(
        intent_type="session.write.enqueue",
        payload=payload,
        session_key="agent:main:test",
    )

    assert payload == {
        "session_key": "agent:main:test",
        "role": "assistant",
        "content": "persist",
        "tool_calls": [{"name": "read", "arguments": {"value": "original"}}],
        "turn_usage": {"tokens": {"input": 1}},
    }


@pytest.mark.asyncio
async def test_pi_kernel_built_from_runtime_config_wires_yield_request_to_host_tool() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        build_agent_for_kernel,
    )
    from opensquilla.engine.types import AgentConfig, ToolCall, ToolResult

    calls: list[ToolCall] = []

    async def tool_handler(call: ToolCall) -> ToolResult:
        calls.append(call)
        return ToolResult(
            tool_use_id=call.tool_use_id,
            tool_name=call.tool_name,
            content='{"status":"yielded","waited":false}',
            terminates_turn=True,
        )

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "yield.request",
                "payload": {"message": "waiting for children"},
            }

    agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_client=FakePiRpcClient(),
            allow_test_pi_rpc_client=True,
        ),
        provider=object(),
        config=AgentConfig(model_id="pi-host-yield"),
        tool_definitions=[],
        tool_handler=tool_handler,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        ToolResultEvent(
            tool_use_id="yield-request",
            tool_name="sessions_yield",
            result='{"status":"yielded","waited":false}',
            arguments={
                "message": "waiting for children",
            },
        ),
        DoneEvent(text="", model="pi-host-yield", cost_source="unavailable"),
    ]
    assert [(call.tool_use_id, call.tool_name, call.arguments) for call in calls] == [
        (
            "yield-request",
            "sessions_yield",
            {
                "message": "waiting for children",
            },
        )
    ]


@pytest.mark.asyncio
async def test_pi_yield_request_rejects_cross_session_target() -> None:
    from opensquilla.engine.agent_core import OpenSquillaOrchestrationHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("cross-session yield must not reach tool execution")

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            _ = tool_call
            return result

    port = OpenSquillaOrchestrationHostPort(FakeHostAgent())

    with pytest.raises(RuntimeError, match="cannot target a different session_key"):
        await port.handle_intent(
            intent_type="yield.request",
            payload={
                "session_key": "agent:main:other",
                "message": "wrong session",
            },
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_yield_request_does_not_convert_current_session_key_to_legacy_wait() -> None:
    from opensquilla.engine.agent_core import OpenSquillaOrchestrationHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    calls: list[ToolCall] = []

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            calls.append(tool_call)
            return ToolResult(
                tool_use_id=tool_call.tool_use_id,
                tool_name=tool_call.tool_name,
                content='{"status":"yielded","waited":false}',
                terminates_turn=True,
            )

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            _ = tool_call
            return result

    port = OpenSquillaOrchestrationHostPort(FakeHostAgent())

    events = await port.handle_intent(
        intent_type="yield.request",
        payload={
            "session_key": "agent:main:test",
            "message": "waiting for children",
        },
        session_key="agent:main:test",
    )

    assert events == [
        ToolResultEvent(
            tool_use_id="yield-request",
            tool_name="sessions_yield",
            result='{"status":"yielded","waited":false}',
            arguments={"message": "waiting for children"},
        )
    ]
    assert [(call.tool_use_id, call.tool_name, call.arguments) for call in calls] == [
        ("yield-request", "sessions_yield", {"message": "waiting for children"})
    ]


@pytest.mark.asyncio
async def test_pi_yield_request_blank_tool_call_id_uses_host_default() -> None:
    from opensquilla.engine.agent_core import OpenSquillaOrchestrationHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    calls: list[ToolCall] = []

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            calls.append(tool_call)
            return ToolResult(
                tool_use_id=tool_call.tool_use_id,
                tool_name=tool_call.tool_name,
                content='{"status":"yielded","waited":false}',
                terminates_turn=True,
            )

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            _ = tool_call
            return result

    port = OpenSquillaOrchestrationHostPort(FakeHostAgent())

    await port.handle_intent(
        intent_type="yield.request",
        payload={
            "session_key": "agent:main:test",
            "tool_call_id": "   ",
        },
        session_key="agent:main:test",
    )

    assert [(call.tool_use_id, call.tool_name, call.arguments) for call in calls] == [
        ("yield-request", "sessions_yield", {})
    ]


@pytest.mark.asyncio
async def test_pi_yield_request_through_dispatch_uses_current_turn_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaOrchestrationHostPort
    from opensquilla.engine.types import ToolCall, ToolResult
    from opensquilla.gateway import subagent_announce
    from opensquilla.tools.builtin import sessions as sessions_mod
    from opensquilla.tools.dispatch import build_tool_handler
    from opensquilla.tools.registry import get_default_registry
    from opensquilla.tools.types import CallerKind, ToolContext, current_tool_context

    closed_groups: list[tuple[str, str, object, object]] = []

    async def fake_close_subagent_spawn_group(
        session_key: str,
        task_id: str,
        *,
        session_manager: object,
        task_runtime: object,
    ) -> bool:
        closed_groups.append((session_key, task_id, session_manager, task_runtime))
        return True

    monkeypatch.setattr(
        subagent_announce,
        "close_subagent_spawn_group",
        fake_close_subagent_spawn_group,
    )

    session_manager = object()
    task_runtime = object()
    sessions_mod.set_session_manager(session_manager)
    sessions_mod.set_task_runtime(task_runtime)

    ctx = ToolContext(
        caller_kind=CallerKind.AGENT,
        session_key="agent:main:test",
        task_id="task-parent-1",
    )
    handler = build_tool_handler(get_default_registry(), ctx)

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            return await handler(tool_call)

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            _ = tool_call
            return result

    try:
        events = await OpenSquillaOrchestrationHostPort(
            FakeHostAgent()
        ).handle_intent(
            intent_type="yield.request",
            payload={
                "session_key": "agent:main:test",
                "message": "waiting for children",
            },
            session_key="agent:main:test",
        )
    finally:
        sessions_mod.set_session_manager(None)
        sessions_mod.set_task_runtime(None)

    assert len(events) == 1
    assert events[0] == ToolResultEvent(
        tool_use_id="yield-request",
        tool_name="sessions_yield",
        result=(
            '{"status": "yielded", "waited": false, '
            '"message": "Current turn yielded; wait for pushed session events.", '
            '"yield_message": "waiting for children"}'
        ),
        arguments={"message": "waiting for children"},
    )
    assert closed_groups == [
        ("agent:main:test", "task-parent-1", session_manager, task_runtime)
    ]
    assert current_tool_context.get() is None


@pytest.mark.asyncio
async def test_pi_yield_request_rejects_unknown_payload_fields_before_host_tool() -> None:
    from opensquilla.engine.agent_core import OpenSquillaOrchestrationHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("unknown yield.request field must not reach host tool")

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            _ = tool_call
            return result

    port = OpenSquillaOrchestrationHostPort(FakeHostAgent())

    with pytest.raises(
        RuntimeError,
        match="yield.request unsupported payload field",
    ):
        await port.handle_intent(
            intent_type="yield.request",
            payload={
                "session_key": "agent:main:test",
                "message": "waiting for children",
                "orchestration_control": {"wake_parent": False},
            },
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_yield_request_rejects_non_string_tool_call_id_before_host_tool() -> None:
    from opensquilla.engine.agent_core import OpenSquillaOrchestrationHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("structured yield tool_call_id must not reach tool execution")

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            _ = tool_call
            return result

    port = OpenSquillaOrchestrationHostPort(FakeHostAgent())

    with pytest.raises(RuntimeError, match="yield.request tool_call_id must be a string"):
        await port.handle_intent(
            intent_type="yield.request",
            payload={
                "session_key": "agent:main:test",
                "tool_call_id": {"nested": "object"},
                "message": "waiting for children",
            },
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_yield_request_rejects_explicit_null_tool_call_id_before_host_tool() -> None:
    from opensquilla.engine.agent_core import OpenSquillaOrchestrationHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("null yield tool_call_id must not reach tool execution")

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            _ = tool_call
            return result

    port = OpenSquillaOrchestrationHostPort(FakeHostAgent())

    with pytest.raises(RuntimeError, match="yield.request tool_call_id must be a string"):
        await port.handle_intent(
            intent_type="yield.request",
            payload={
                "session_key": "agent:main:test",
                "tool_call_id": None,
                "message": "waiting for children",
            },
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_yield_request_rejects_non_numeric_timeout_before_host_tool() -> None:
    from opensquilla.engine.agent_core import OpenSquillaOrchestrationHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("non-numeric yield timeout must not reach host tool")

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            _ = tool_call
            return result

    port = OpenSquillaOrchestrationHostPort(FakeHostAgent())

    with pytest.raises(RuntimeError, match="yield.request timeout_seconds must be a number"):
        await port.handle_intent(
            intent_type="yield.request",
            payload={"timeout_seconds": "1.0"},
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_yield_request_rejects_explicit_null_timeout_before_host_tool() -> None:
    from opensquilla.engine.agent_core import OpenSquillaOrchestrationHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("null yield timeout must not reach host tool")

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            _ = tool_call
            return result

    port = OpenSquillaOrchestrationHostPort(FakeHostAgent())

    with pytest.raises(RuntimeError, match="yield.request timeout_seconds must be a number"):
        await port.handle_intent(
            intent_type="yield.request",
            payload={"timeout_seconds": None},
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_yield_request_rejects_non_finite_timeout_before_host_tool() -> None:
    from opensquilla.engine.agent_core import OpenSquillaOrchestrationHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("non-finite yield timeout must not reach host tool")

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            _ = tool_call
            return result

    port = OpenSquillaOrchestrationHostPort(FakeHostAgent())

    with pytest.raises(RuntimeError, match="yield.request timeout_seconds must be finite"):
        await port.handle_intent(
            intent_type="yield.request",
            payload={"timeout_seconds": float("nan")},
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_yield_request_rejects_negative_timeout_before_host_tool() -> None:
    from opensquilla.engine.agent_core import OpenSquillaOrchestrationHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("negative yield timeout must not reach host tool")

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            _ = tool_call
            return result

    port = OpenSquillaOrchestrationHostPort(FakeHostAgent())

    with pytest.raises(
        RuntimeError,
        match="yield.request timeout_seconds must be a non-negative number",
    ):
        await port.handle_intent(
            intent_type="yield.request",
            payload={"timeout_seconds": -1.0},
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_yield_request_timeout_is_host_clamped() -> None:
    from opensquilla.engine.agent_core import OpenSquillaOrchestrationHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    calls: list[ToolCall] = []

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            calls.append(tool_call)
            return ToolResult(
                tool_use_id=tool_call.tool_use_id,
                tool_name=tool_call.tool_name,
                content='{"status":"yielded"}',
            )

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            _ = tool_call
            return result

    port = OpenSquillaOrchestrationHostPort(FakeHostAgent())

    await port.handle_intent(
        intent_type="yield.request",
        payload={"timeout_seconds": 9999.0},
        session_key="agent:main:test",
    )

    assert [(call.tool_name, call.arguments) for call in calls] == [
        (
            "sessions_yield",
            {
                "timeout_seconds": 300.0,
            },
        )
    ]


@pytest.mark.parametrize(
    "bad_message",
    [
        {1: "numeric key"},
        {"tokens": float("nan")},
        {"opaque": object()},
    ],
)
@pytest.mark.asyncio
async def test_pi_yield_request_rejects_python_only_message_before_host_tool(
    bad_message: object,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaOrchestrationHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            _ = tool_call
            raise AssertionError("Python-only yield message must not reach host tool")

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            _ = tool_call
            return result

    port = OpenSquillaOrchestrationHostPort(FakeHostAgent())

    with pytest.raises(RuntimeError, match="Pi sidecar JSON"):
        await port.handle_intent(
            intent_type="yield.request",
            payload={"message": bad_message},
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_yield_request_copies_message_before_host_tool_call() -> None:
    from opensquilla.engine.agent_core import OpenSquillaOrchestrationHostPort
    from opensquilla.engine.types import ToolCall, ToolResult

    class FakeHostAgent:
        async def _execute_tool(self, tool_call: ToolCall) -> ToolResult:
            tool_call.arguments["message"]["text"] = "mutated"
            return ToolResult(
                tool_use_id=tool_call.tool_use_id,
                tool_name=tool_call.tool_name,
                content='{"status":"yielded"}',
            )

        async def _project_tool_result_for_delivery(
            self,
            result: ToolResult,
            *,
            tool_call: ToolCall,
        ) -> ToolResult:
            _ = tool_call
            return result

    port = OpenSquillaOrchestrationHostPort(FakeHostAgent())
    payload = {
        "session_key": "agent:main:test",
        "message": {"text": "original"},
    }

    await port.handle_intent(
        intent_type="yield.request",
        payload=payload,
        session_key="agent:main:test",
    )

    assert payload == {
        "session_key": "agent:main:test",
        "message": {"text": "original"},
    }


@pytest.mark.asyncio
async def test_pi_kernel_routes_spawn_tool_then_yield_request_through_host() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        build_agent_for_kernel,
    )
    from opensquilla.engine.types import AgentConfig, ToolCall, ToolResult, ToolUseStartEvent

    calls: list[ToolCall] = []

    async def tool_handler(call: ToolCall) -> ToolResult:
        calls.append(call)
        if call.tool_name == "sessions_spawn":
            return ToolResult(
                tool_use_id=call.tool_use_id,
                tool_name=call.tool_name,
                content='{"session_key":"agent:main:child-1"}',
            )
        if call.tool_name == "sessions_yield":
            return ToolResult(
                tool_use_id=call.tool_use_id,
                tool_name=call.tool_name,
                content='{"status":"yielded","children":1}',
                terminates_turn=True,
            )
        raise AssertionError(f"unexpected tool {call.tool_name}")

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "tool.call.prepare",
                "payload": {
                    "tool_call_id": "spawn-1",
                    "tool_name": "sessions_spawn",
                },
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "tool.call.execute",
                "payload": {
                    "tool_call_id": "spawn-1",
                    "tool_name": "sessions_spawn",
                    "arguments": {"prompt": "work in child"},
                },
            }
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "yield.request",
                "payload": {"message": "wait for child"},
            }

    agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_client=FakePiRpcClient(),
            allow_test_pi_rpc_client=True,
        ),
        provider=object(),
        config=AgentConfig(model_id="pi-host-orchestration"),
        tool_definitions=[],
        tool_handler=tool_handler,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        ToolUseStartEvent(tool_use_id="spawn-1", tool_name="sessions_spawn"),
        ToolResultEvent(
            tool_use_id="spawn-1",
            tool_name="sessions_spawn",
            result='{"session_key":"agent:main:child-1"}',
            arguments={"prompt": "work in child"},
        ),
        ToolResultEvent(
            tool_use_id="yield-request",
            tool_name="sessions_yield",
            result='{"status":"yielded","children":1}',
            arguments={
                "message": "wait for child",
            },
        ),
        DoneEvent(text="", model="pi-host-orchestration", cost_source="unavailable"),
    ]
    assert [(call.tool_use_id, call.tool_name, call.arguments) for call in calls] == [
        ("spawn-1", "sessions_spawn", {"prompt": "work in child"}),
        (
            "yield-request",
            "sessions_yield",
            {
                "message": "wait for child",
            },
        ),
    ]


@pytest.mark.asyncio
async def test_pi_kernel_built_from_runtime_config_wires_savepoint_to_host_manager() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        build_agent_for_kernel,
    )
    from opensquilla.engine.types import AgentConfig

    checkpoints: list[dict] = []
    context_entries: list[str] = []

    class FakeSessionManager:
        async def record_memory_checkpoint(self, session_key, transcript, **kwargs):
            checkpoints.append(
                {"session_key": session_key, "transcript": transcript, **kwargs}
            )
            return {"status": "ok"}

    @contextlib.asynccontextmanager
    async def write_context():
        context_entries.append("entered")
        yield
        context_entries.append("exited")

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "savepoint.request",
                "payload": {
                    "session_key": "agent:main:test",
                    "turn_id": "turn-1",
                    "source": "pi-sidecar",
                    "transcript": [{"role": "assistant", "content": "state"}],
                },
            }

    agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_client=FakePiRpcClient(),
            allow_test_pi_rpc_client=True,
        ),
        provider=object(),
        config=AgentConfig(model_id="pi-host-savepoint"),
        tool_definitions=[],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
        session_manager=FakeSessionManager(),
        session_write_context_factory=lambda session_key: write_context(),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        DoneEvent(text="", model="pi-host-savepoint", cost_source="unavailable")
    ]
    assert context_entries == ["entered", "exited"]
    assert len(checkpoints) == 1
    checkpoint = checkpoints[0]
    assert checkpoint["session_key"] == "agent:main:test"
    assert checkpoint["turn_id"] == "turn-1"
    assert checkpoint["source"] == "pi-sidecar"
    assert len(checkpoint["transcript"]) == 1
    entry = checkpoint["transcript"][0]
    assert getattr(entry, "role") == "assistant"
    assert getattr(entry, "content") == "state"


@pytest.mark.asyncio
async def test_pi_savepoint_rejects_cross_session_target() -> None:
    from opensquilla.engine.agent_core import OpenSquillaSavepointHostPort

    class FakeSessionManager:
        async def record_memory_checkpoint(self, session_key, transcript, **kwargs):
            _ = session_key, transcript, kwargs
            raise AssertionError("cross-session savepoint must not reach SessionManager")

    port = OpenSquillaSavepointHostPort(session_manager=FakeSessionManager())

    with pytest.raises(RuntimeError, match="cannot target a different session_key"):
        await port.handle_intent(
            intent_type="savepoint.request",
            payload={
                "session_key": "agent:main:other",
                "transcript": [{"role": "assistant", "content": "wrong target"}],
            },
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_savepoint_rejects_unknown_payload_fields_before_session_manager() -> None:
    from opensquilla.engine.agent_core import OpenSquillaSavepointHostPort

    class FakeSessionManager:
        async def record_memory_checkpoint(self, session_key, transcript, **kwargs):
            _ = session_key, transcript, kwargs
            raise AssertionError("unknown savepoint field must not reach SessionManager")

    port = OpenSquillaSavepointHostPort(session_manager=FakeSessionManager())

    with pytest.raises(
        RuntimeError,
        match="savepoint.request unsupported payload field",
    ):
        await port.handle_intent(
            intent_type="savepoint.request",
            payload={
                "session_key": "agent:main:test",
                "transcript": [{"role": "assistant", "content": "state"}],
                "checkpoint_policy": {"source": "host-owned"},
            },
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_savepoint_rejects_privileged_system_transcript_role() -> None:
    from opensquilla.engine.agent_core import OpenSquillaSavepointHostPort

    class FakeSessionManager:
        async def record_memory_checkpoint(self, session_key, transcript, **kwargs):
            _ = session_key, transcript, kwargs
            raise AssertionError("privileged transcript must not reach SessionManager")

    port = OpenSquillaSavepointHostPort(session_manager=FakeSessionManager())

    with pytest.raises(RuntimeError, match="cannot checkpoint privileged role"):
        await port.handle_intent(
            intent_type="savepoint.request",
            payload={
                "session_key": "agent:main:test",
                "transcript": [
                    {"role": "assistant", "content": "ok"},
                    {"role": "system", "content": "sidecar-owned system state"},
                ],
            },
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_savepoint_rejects_non_list_transcript_before_manager_call() -> None:
    from opensquilla.engine.agent_core import OpenSquillaSavepointHostPort

    class FakeSessionManager:
        async def record_memory_checkpoint(self, session_key, transcript, **kwargs):
            _ = session_key, transcript, kwargs
            raise AssertionError("non-list transcript must not reach SessionManager")

    port = OpenSquillaSavepointHostPort(session_manager=FakeSessionManager())

    with pytest.raises(RuntimeError, match="savepoint.request transcript must be a list"):
        await port.handle_intent(
            intent_type="savepoint.request",
            payload={
                "session_key": "agent:main:test",
                "transcript": {"role": "assistant", "content": "not a list"},
            },
            session_key="agent:main:test",
        )


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("transcript", "savepoint.request transcript must be a list"),
        ("turn_id", "savepoint.request turn_id must be a string"),
        ("source", "savepoint.request source must be a string"),
    ],
)
@pytest.mark.asyncio
async def test_pi_savepoint_rejects_explicit_null_top_level_fields_before_manager_call(
    field: str,
    message: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaSavepointHostPort

    class FakeSessionManager:
        async def record_memory_checkpoint(self, session_key, transcript, **kwargs):
            _ = session_key, transcript, kwargs
            raise AssertionError("null savepoint field must not reach SessionManager")

    port = OpenSquillaSavepointHostPort(session_manager=FakeSessionManager())
    payload = {
        "session_key": "agent:main:test",
        "turn_id": "turn-1",
        "source": "pi-sidecar",
        "transcript": [{"role": "assistant", "content": "state"}],
        field: None,
    }

    with pytest.raises(RuntimeError, match=message):
        await port.handle_intent(
            intent_type="savepoint.request",
            payload=payload,
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_savepoint_rejects_non_object_transcript_entry_before_manager_call() -> None:
    from opensquilla.engine.agent_core import OpenSquillaSavepointHostPort

    class FakeSessionManager:
        async def record_memory_checkpoint(self, session_key, transcript, **kwargs):
            _ = session_key, transcript, kwargs
            raise AssertionError("non-object transcript entry must not reach SessionManager")

    port = OpenSquillaSavepointHostPort(session_manager=FakeSessionManager())

    with pytest.raises(
        RuntimeError,
        match="savepoint.request transcript entries must be objects",
    ):
        await port.handle_intent(
            intent_type="savepoint.request",
            payload={
                "session_key": "agent:main:test",
                "transcript": ["assistant text without role metadata"],
            },
            session_key="agent:main:test",
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("role", {"nested": "assistant"}, "savepoint.request transcript role must be a string"),
        ("content", {"nested": "text"}, "savepoint.request transcript content must be a string"),
        (
            "reasoning_content",
            {"nested": "thought"},
            "savepoint.request transcript reasoning_content must be a string",
        ),
        (
            "tool_calls",
            {"id": "toolu-1"},
            "savepoint.request transcript tool_calls must be a list",
        ),
        (
            "tool_call_id",
            {"id": "toolu-1"},
            "savepoint.request transcript tool_call_id must be a string",
        ),
        (
            "tool_call_id",
            "   ",
            "savepoint.request transcript tool_call_id must be non-empty",
        ),
        (
            "token_count",
            True,
            "savepoint.request transcript token_count must be an integer",
        ),
        (
            "token_count",
            {"tokens": 12},
            "savepoint.request transcript token_count must be an integer",
        ),
        (
            "token_count",
            -1,
            "savepoint.request transcript token_count must be a non-negative integer",
        ),
    ],
)
@pytest.mark.asyncio
async def test_pi_savepoint_rejects_malformed_transcript_entry_fields_before_manager_call(
    field: str,
    value: object,
    message: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaSavepointHostPort

    class FakeSessionManager:
        async def record_memory_checkpoint(self, session_key, transcript, **kwargs):
            _ = session_key, transcript, kwargs
            raise AssertionError("malformed transcript entry must not reach SessionManager")

    port = OpenSquillaSavepointHostPort(session_manager=FakeSessionManager())
    entry: dict[str, object] = {"role": "assistant", "content": "state"}
    entry[field] = value

    with pytest.raises(RuntimeError, match=message):
        await port.handle_intent(
            intent_type="savepoint.request",
            payload={
                "session_key": "agent:main:test",
                "transcript": [entry],
            },
            session_key="agent:main:test",
        )


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("content", "savepoint.request transcript content must be a string"),
        ("reasoning_content", "savepoint.request transcript reasoning_content must be a string"),
        ("tool_calls", "savepoint.request transcript tool_calls must be a list"),
        ("tool_call_id", "savepoint.request transcript tool_call_id must be a string"),
        ("token_count", "savepoint.request transcript token_count must be an integer"),
    ],
)
@pytest.mark.asyncio
async def test_pi_savepoint_rejects_explicit_null_transcript_entry_fields_before_manager_call(
    field: str,
    message: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaSavepointHostPort

    class FakeSessionManager:
        async def record_memory_checkpoint(self, session_key, transcript, **kwargs):
            _ = session_key, transcript, kwargs
            raise AssertionError("null transcript entry field must not reach SessionManager")

    port = OpenSquillaSavepointHostPort(session_manager=FakeSessionManager())
    entry: dict[str, object] = {"role": "assistant", "content": "state"}
    entry[field] = None

    with pytest.raises(RuntimeError, match=message):
        await port.handle_intent(
            intent_type="savepoint.request",
            payload={
                "session_key": "agent:main:test",
                "transcript": [entry],
            },
            session_key="agent:main:test",
        )


@pytest.mark.parametrize(
    "bad_tool_calls",
    [
        [{"name": "read", "arguments": {1: "numeric key"}}],
        [{"name": "read", "arguments": {"tokens": float("nan")}}],
        [{"name": "read", "arguments": {"opaque": object()}}],
    ],
)
@pytest.mark.asyncio
async def test_pi_savepoint_rejects_python_only_transcript_tool_calls_before_manager_call(
    bad_tool_calls: list[dict[str, object]],
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaSavepointHostPort

    class FakeSessionManager:
        async def record_memory_checkpoint(self, session_key, transcript, **kwargs):
            _ = session_key, transcript, kwargs
            raise AssertionError(
                "Python-only transcript tool_calls must not reach SessionManager"
            )

    port = OpenSquillaSavepointHostPort(session_manager=FakeSessionManager())

    with pytest.raises(RuntimeError, match="Pi sidecar JSON"):
        await port.handle_intent(
            intent_type="savepoint.request",
            payload={
                "session_key": "agent:main:test",
                "transcript": [
                    {
                        "role": "assistant",
                        "content": "state",
                        "tool_calls": bad_tool_calls,
                    }
                ],
            },
            session_key="agent:main:test",
        )


@pytest.mark.parametrize("bad_tool_call", ["read", ["read"]])
@pytest.mark.asyncio
async def test_pi_savepoint_rejects_non_object_transcript_tool_call_entries_before_manager_call(
    bad_tool_call: object,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaSavepointHostPort

    class FakeSessionManager:
        async def record_memory_checkpoint(self, session_key, transcript, **kwargs):
            _ = session_key, transcript, kwargs
            raise AssertionError(
                "malformed transcript tool_call entry must not reach SessionManager"
            )

    port = OpenSquillaSavepointHostPort(session_manager=FakeSessionManager())

    with pytest.raises(
        RuntimeError,
        match="savepoint.request transcript tool_calls entries must be objects",
    ):
        await port.handle_intent(
            intent_type="savepoint.request",
            payload={
                "session_key": "agent:main:test",
                "transcript": [
                    {
                        "role": "assistant",
                        "content": "state",
                        "tool_calls": [bad_tool_call],
                    }
                ],
            },
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_savepoint_normalizes_json_transcript_entries_for_checkpoint_builder() -> None:
    from opensquilla.engine.agent_core import OpenSquillaSavepointHostPort

    captured: dict[str, object] = {}

    class FakeSessionManager:
        async def record_memory_checkpoint(self, session_key, transcript, **kwargs):
            _ = session_key, kwargs
            entry = transcript[0]
            captured.update(
                role=getattr(entry, "role", None),
                content=getattr(entry, "content", None),
                reasoning_content=getattr(entry, "reasoning_content", None),
                tool_call_id=getattr(entry, "tool_call_id", None),
                token_count=getattr(entry, "token_count", None),
                tool_name=getattr(entry, "tool_name", "missing"),
            )
            entry.content = "mutated"
            return {"status": "ok"}

    port = OpenSquillaSavepointHostPort(session_manager=FakeSessionManager())
    payload = {
        "session_key": "agent:main:test",
        "turn_id": "turn-1",
        "transcript": [
            {
                "role": "assistant",
                "content": "original",
                "reasoning_content": "thoughts",
                "tool_call_id": "toolu-1",
                "token_count": 12,
            }
        ],
    }

    await port.handle_intent(
        intent_type="savepoint.request",
        payload=payload,
        session_key="agent:main:test",
    )

    assert captured == {
        "role": "assistant",
        "content": "original",
        "reasoning_content": "thoughts",
        "tool_call_id": "toolu-1",
        "token_count": 12,
        "tool_name": "missing",
    }
    assert payload["transcript"][0]["content"] == "original"


@pytest.mark.asyncio
async def test_pi_savepoint_canonicalizes_json_transcript_entry_role() -> None:
    from opensquilla.engine.agent_core import OpenSquillaSavepointHostPort

    captured: dict[str, object] = {}

    class FakeSessionManager:
        async def record_memory_checkpoint(self, session_key, transcript, **kwargs):
            _ = session_key, kwargs
            entry = transcript[0]
            captured["role"] = getattr(entry, "role", None)
            return {"status": "ok"}

    port = OpenSquillaSavepointHostPort(session_manager=FakeSessionManager())

    await port.handle_intent(
        intent_type="savepoint.request",
        payload={
            "session_key": "agent:main:test",
            "transcript": [{"role": " Assistant ", "content": "state"}],
        },
        session_key="agent:main:test",
    )

    assert captured == {"role": "assistant"}


@pytest.mark.parametrize("role", ["", "   ", "developer"])
@pytest.mark.asyncio
async def test_pi_savepoint_rejects_unsupported_transcript_entry_role_before_manager_call(
    role: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaSavepointHostPort

    class FakeSessionManager:
        async def record_memory_checkpoint(self, session_key, transcript, **kwargs):
            _ = session_key, transcript, kwargs
            raise AssertionError("unsupported transcript role must not reach SessionManager")

    port = OpenSquillaSavepointHostPort(session_manager=FakeSessionManager())

    with pytest.raises(
        RuntimeError,
        match="savepoint.request transcript role must be user, assistant, or tool",
    ):
        await port.handle_intent(
            intent_type="savepoint.request",
            payload={
                "session_key": "agent:main:test",
                "transcript": [{"role": role, "content": "sidecar note"}],
            },
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["host", "OpenSquilla", " session-manager "])
async def test_pi_savepoint_rejects_privileged_source_before_manager_call(
    source: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaSavepointHostPort

    class FakeSessionManager:
        async def record_memory_checkpoint(self, session_key, transcript, **kwargs):
            _ = session_key, transcript, kwargs
            raise AssertionError("privileged source must not reach SessionManager")

    port = OpenSquillaSavepointHostPort(session_manager=FakeSessionManager())

    with pytest.raises(RuntimeError, match="cannot claim privileged source"):
        await port.handle_intent(
            intent_type="savepoint.request",
            payload={
                "session_key": "agent:main:test",
                "source": source,
                "transcript": [{"role": "assistant", "content": "state"}],
            },
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_savepoint_normalizes_privileged_transcript_role_before_rejecting() -> None:
    from opensquilla.engine.agent_core import OpenSquillaSavepointHostPort

    class FakeSessionManager:
        async def record_memory_checkpoint(self, session_key, transcript, **kwargs):
            _ = session_key, transcript, kwargs
            raise AssertionError("privileged transcript must not reach SessionManager")

    port = OpenSquillaSavepointHostPort(session_manager=FakeSessionManager())

    with pytest.raises(RuntimeError, match="cannot checkpoint privileged role"):
        await port.handle_intent(
            intent_type="savepoint.request",
            payload={
                "session_key": "agent:main:test",
                "transcript": [
                    {"role": " System ", "content": "sidecar-owned system state"}
                ],
            },
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_savepoint_blank_turn_id_uses_host_default() -> None:
    from opensquilla.engine.agent_core import OpenSquillaSavepointHostPort

    captured: dict[str, object] = {}

    class FakeSessionManager:
        async def record_memory_checkpoint(self, session_key, transcript, **kwargs):
            captured["session_key"] = session_key
            captured["transcript"] = transcript
            captured["turn_id"] = kwargs["turn_id"]
            captured["source"] = kwargs["source"]

    port = OpenSquillaSavepointHostPort(session_manager=FakeSessionManager())

    await port.handle_intent(
        intent_type="savepoint.request",
        payload={"session_key": "agent:main:test", "turn_id": "   "},
        session_key="agent:main:test",
    )

    assert captured["turn_id"] == ""
    assert captured["source"] == "pi_sidecar"


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("turn_id", "savepoint.request turn_id must be a string"),
        ("source", "savepoint.request source must be a string"),
    ],
)
@pytest.mark.asyncio
async def test_pi_savepoint_rejects_non_string_metadata_before_manager_call(
    field: str,
    message: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaSavepointHostPort

    class FakeSessionManager:
        async def record_memory_checkpoint(self, session_key, transcript, **kwargs):
            _ = session_key, transcript, kwargs
            raise AssertionError("structured savepoint metadata must not reach SessionManager")

    port = OpenSquillaSavepointHostPort(session_manager=FakeSessionManager())
    payload = {
        "session_key": "agent:main:test",
        "transcript": [{"role": "assistant", "content": "state"}],
        field: {"nested": "object"},
    }

    with pytest.raises(RuntimeError, match=message):
        await port.handle_intent(
            intent_type="savepoint.request",
            payload=payload,
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_savepoint_copies_transcript_before_manager_call() -> None:
    from opensquilla.engine.agent_core import OpenSquillaSavepointHostPort

    class FakeSessionManager:
        async def record_memory_checkpoint(self, session_key, transcript, **kwargs):
            _ = session_key, kwargs
            transcript[0].content = "mutated"
            return {"status": "ok"}

    port = OpenSquillaSavepointHostPort(session_manager=FakeSessionManager())
    payload = {
        "session_key": "agent:main:test",
        "turn_id": "turn-1",
        "transcript": [{"role": "assistant", "content": "original"}],
    }

    await port.handle_intent(
        intent_type="savepoint.request",
        payload=payload,
        session_key="agent:main:test",
    )

    assert payload == {
        "session_key": "agent:main:test",
        "turn_id": "turn-1",
        "transcript": [{"role": "assistant", "content": "original"}],
    }


@pytest.mark.asyncio
async def test_pi_kernel_built_from_runtime_config_wires_queue_poll_to_task_runtime() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        build_agent_for_kernel,
    )
    from opensquilla.engine.types import AgentConfig

    calls: list[tuple[str, float | None]] = []

    class FakeTaskRuntime:
        async def wait(self, task_id: str, timeout: float | None = None):
            calls.append((task_id, timeout))
            return SimpleNamespace(
                task_id=task_id,
                status="done",
                terminal_reason="completed",
            )

    class FakeSessionManager:
        def __init__(self) -> None:
            self._task_runtime = FakeTaskRuntime()

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "queue.poll",
                "payload": {"task_id": "task-1", "timeout_seconds": 0.25},
            }

    agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_client=FakePiRpcClient(),
            allow_test_pi_rpc_client=True,
        ),
        provider=object(),
        config=AgentConfig(model_id="pi-host-queue"),
        tool_definitions=[],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
        session_manager=FakeSessionManager(),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        RunHeartbeatEvent(
            phase="queue",
            message=(
                '{"status":"done","task_id":"task-1",'
                '"terminal_reason":"completed"}'
            ),
        ),
        DoneEvent(text="", model="pi-host-queue", cost_source="unavailable"),
    ]
    assert calls == [("task-1", 0.25)]


@pytest.mark.asyncio
async def test_pi_queue_poll_reports_status_without_draining_task_runtime() -> None:
    from opensquilla.engine.agent_core import OpenSquillaQueueHostPort

    calls: list[tuple[str, str, float | None]] = []

    class FakeTaskRuntime:
        async def wait(self, task_id: str, timeout: float | None = None):
            calls.append(("wait", task_id, timeout))
            return SimpleNamespace(
                task_id=task_id,
                status="succeeded",
                terminal_reason="completed",
            )

        async def status(self, task_id: str):
            calls.append(("status", task_id, None))
            return SimpleNamespace(
                task_id=task_id,
                status="running",
                terminal_reason=None,
            )

        async def cancel(self, *args, **kwargs):
            raise AssertionError("queue.poll must not cancel tasks")

        async def list(self, *args, **kwargs):
            raise AssertionError("queue.poll must not drain/list tasks")

    port = OpenSquillaQueueHostPort(task_runtime=FakeTaskRuntime())

    wait_events = await port.handle_intent(
        intent_type="queue.poll",
        payload={"task_id": "task-1", "timeout_seconds": 0.25},
        session_key="agent:main:test",
    )
    status_events = await port.handle_intent(
        intent_type="queue.poll",
        payload={"task_id": "task-2"},
        session_key="agent:main:test",
    )

    assert calls == [
        ("wait", "task-1", 0.25),
        ("status", "task-2", None),
    ]
    assert wait_events == [
        RunHeartbeatEvent(
            phase="queue",
            message=(
                '{"status":"succeeded","task_id":"task-1",'
                '"terminal_reason":"completed"}'
            ),
        )
    ]
    assert status_events == [
        RunHeartbeatEvent(
            phase="queue",
            message='{"status":"running","task_id":"task-2"}',
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "bad_value", "match"),
    [
        ("status", {"bad": "status"}, "queue.poll status must be a string"),
        ("task_id", {"bad": "task"}, "queue.poll heartbeat task_id must be a string"),
        (
            "terminal_reason",
            {"bad": "reason"},
            "queue.poll terminal_reason must be a string or None",
        ),
    ],
)
async def test_pi_queue_poll_rejects_malformed_task_runtime_status_fields(
    field: str,
    bad_value: Any,
    match: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaQueueHostPort

    class FakeTaskRuntime:
        async def status(self, task_id: str):
            payload: dict[str, Any] = {
                "task_id": task_id,
                "status": "running",
                "terminal_reason": None,
            }
            payload[field] = bad_value
            return SimpleNamespace(**payload)

    port = OpenSquillaQueueHostPort(task_runtime=FakeTaskRuntime())

    with pytest.raises(RuntimeError, match=match):
        await port.handle_intent(
            intent_type="queue.poll",
            payload={"task_id": "task-1"},
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_queue_poll_rejects_non_string_task_id_before_task_runtime() -> None:
    from opensquilla.engine.agent_core import OpenSquillaQueueHostPort

    class FakeTaskRuntime:
        async def status(self, task_id: str):
            _ = task_id
            raise AssertionError("invalid task_id must not reach TaskRuntime")

    port = OpenSquillaQueueHostPort(task_runtime=FakeTaskRuntime())

    with pytest.raises(RuntimeError, match="queue.poll task_id must be a string"):
        await port.handle_intent(
            intent_type="queue.poll",
            payload={"task_id": {"nested": "object"}},
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_queue_poll_rejects_cross_session_target_before_task_runtime() -> None:
    from opensquilla.engine.agent_core import OpenSquillaQueueHostPort

    class FakeTaskRuntime:
        async def status(self, task_id: str):
            _ = task_id
            raise AssertionError("cross-session queue.poll must not reach TaskRuntime")

    port = OpenSquillaQueueHostPort(task_runtime=FakeTaskRuntime())

    with pytest.raises(
        RuntimeError,
        match="Pi sidecar queue.poll cannot target a different session_key",
    ):
        await port.handle_intent(
            intent_type="queue.poll",
            payload={"session_key": "agent:main:other", "task_id": "task-1"},
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_queue_poll_rejects_unknown_payload_fields_before_task_runtime() -> None:
    from opensquilla.engine.agent_core import OpenSquillaQueueHostPort

    class FakeTaskRuntime:
        async def status(self, task_id: str):
            _ = task_id
            raise AssertionError("unknown queue.poll field must not reach TaskRuntime")

    port = OpenSquillaQueueHostPort(task_runtime=FakeTaskRuntime())

    with pytest.raises(
        RuntimeError,
        match="queue.poll unsupported payload field",
    ):
        await port.handle_intent(
            intent_type="queue.poll",
            payload={
                "task_id": "task-1",
                "queue_control": {"operation": "drain"},
            },
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_cross_session_queue_poll_before_host_port() -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakeQueuePort:
        async def handle_intent(self, **kwargs):
            _ = kwargs
            raise AssertionError("cross-session queue.poll must not reach queue port")

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": "queue.poll",
                "payload": {
                    "session_key": "agent:main:other",
                    "task_id": "task-1",
                },
            }

    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-queue-session"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(queue=FakeQueuePort()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        ErrorEvent(
            message="Pi sidecar queue.poll cannot target a different session_key",
            code="pi_sidecar_error",
        )
    ]


@pytest.mark.parametrize(
    ("intent_type", "payload", "host_port_kwargs", "message"),
    [
        (
            "provider.request",
            {
                "session_key": "agent:main:other",
                "messages": [{"role": "user", "content": "hello"}],
            },
            {"provider": "port"},
            "Pi sidecar provider.request cannot target a different session_key",
        ),
        (
            "session.write.enqueue",
            {
                "session_key": "agent:main:other",
                "role": "assistant",
                "content": "wrong target",
            },
            {"session_writes": "port"},
            "Pi sidecar session.write.enqueue cannot target a different session_key",
        ),
        (
            "savepoint.request",
            {
                "session_key": "agent:main:other",
                "transcript": [{"role": "assistant", "content": "wrong target"}],
            },
            {"savepoints": "port"},
            "Pi sidecar savepoint.request cannot target a different session_key",
        ),
        (
            "yield.request",
            {
                "session_key": "agent:main:other",
                "message": "wrong session",
            },
            {"orchestration": "port"},
            "Pi sidecar yield.request cannot target a different session_key",
        ),
    ],
)
@pytest.mark.asyncio
async def test_pi_sidecar_kernel_rejects_cross_session_host_owned_intents_before_custom_ports(
    intent_type: str,
    payload: dict[str, Any],
    host_port_kwargs: dict[str, str],
    message: str,
) -> None:
    from opensquilla.engine.agent_core import (
        AGENT_CORE_PROTOCOL_VERSION,
        KernelHostPorts,
        PiSidecarKernelRuntime,
    )

    class FakeHostPort:
        async def handle_intent(self, **kwargs):
            _ = kwargs
            raise AssertionError(f"cross-session {intent_type} must not reach host port")

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            _ = message, kwargs
            yield {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "intent",
                "type": intent_type,
                "payload": payload,
            }

    port = FakeHostPort()
    agent = PiSidecarKernelRuntime(
        rpc_client=FakePiRpcClient(),
        config=SimpleNamespace(model_id="pi-session-boundary"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(
            **{name: port for name in host_port_kwargs},
        ),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [ErrorEvent(message=message, code="pi_sidecar_error")]


@pytest.mark.parametrize("field", ["operation", "action"])
@pytest.mark.asyncio
async def test_pi_queue_poll_rejects_non_string_control_field_before_task_runtime(
    field: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaQueueHostPort

    class FakeTaskRuntime:
        async def status(self, task_id: str):
            _ = task_id
            raise AssertionError("structured queue control field must not reach TaskRuntime")

    port = OpenSquillaQueueHostPort(task_runtime=FakeTaskRuntime())

    with pytest.raises(RuntimeError, match=f"queue.poll {field} must be a string"):
        await port.handle_intent(
            intent_type="queue.poll",
            payload={"task_id": "task-1", field: {"nested": "object"}},
            session_key="agent:main:test",
        )


@pytest.mark.parametrize("field", ["operation", "action"])
@pytest.mark.asyncio
async def test_pi_queue_poll_rejects_explicit_null_control_field_before_task_runtime(
    field: str,
) -> None:
    from opensquilla.engine.agent_core import OpenSquillaQueueHostPort

    class FakeTaskRuntime:
        async def status(self, task_id: str):
            _ = task_id
            raise AssertionError("null queue control field must not reach TaskRuntime")

    port = OpenSquillaQueueHostPort(task_runtime=FakeTaskRuntime())

    with pytest.raises(RuntimeError, match=f"queue.poll {field} must be a string"):
        await port.handle_intent(
            intent_type="queue.poll",
            payload={"task_id": "task-1", field: None},
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_queue_poll_rejects_non_numeric_timeout_before_task_runtime() -> None:
    from opensquilla.engine.agent_core import OpenSquillaQueueHostPort

    class FakeTaskRuntime:
        async def wait(self, task_id: str, timeout: float | None = None):
            _ = task_id, timeout
            raise AssertionError("non-numeric queue timeout must not reach TaskRuntime")

        async def status(self, task_id: str):
            _ = task_id
            raise AssertionError("non-numeric queue timeout must not reach TaskRuntime")

    port = OpenSquillaQueueHostPort(task_runtime=FakeTaskRuntime())

    with pytest.raises(RuntimeError, match="queue.poll timeout_seconds must be a number"):
        await port.handle_intent(
            intent_type="queue.poll",
            payload={"task_id": "task-1", "timeout_seconds": "1.0"},
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_queue_poll_rejects_explicit_null_timeout_before_task_runtime() -> None:
    from opensquilla.engine.agent_core import OpenSquillaQueueHostPort

    class FakeTaskRuntime:
        async def wait(self, task_id: str, timeout: float | None = None):
            _ = task_id, timeout
            raise AssertionError("null queue timeout must not reach TaskRuntime")

        async def status(self, task_id: str):
            _ = task_id
            raise AssertionError("null queue timeout must not reach TaskRuntime")

    port = OpenSquillaQueueHostPort(task_runtime=FakeTaskRuntime())

    with pytest.raises(RuntimeError, match="queue.poll timeout_seconds must be a number"):
        await port.handle_intent(
            intent_type="queue.poll",
            payload={"task_id": "task-1", "timeout_seconds": None},
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_queue_poll_rejects_non_finite_timeout_before_task_runtime() -> None:
    from opensquilla.engine.agent_core import OpenSquillaQueueHostPort

    class FakeTaskRuntime:
        async def wait(self, task_id: str, timeout: float | None = None):
            _ = task_id, timeout
            raise AssertionError("non-finite queue timeout must not reach TaskRuntime")

        async def status(self, task_id: str):
            _ = task_id
            raise AssertionError("non-finite queue timeout must not reach TaskRuntime")

    port = OpenSquillaQueueHostPort(task_runtime=FakeTaskRuntime())

    with pytest.raises(RuntimeError, match="queue.poll timeout_seconds must be finite"):
        await port.handle_intent(
            intent_type="queue.poll",
            payload={"task_id": "task-1", "timeout_seconds": float("inf")},
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_queue_poll_rejects_negative_timeout_before_task_runtime() -> None:
    from opensquilla.engine.agent_core import OpenSquillaQueueHostPort

    class FakeTaskRuntime:
        async def wait(self, task_id: str, timeout: float | None = None):
            _ = task_id, timeout
            raise AssertionError("negative queue timeout must not reach TaskRuntime")

        async def status(self, task_id: str):
            _ = task_id
            raise AssertionError("negative queue timeout must not reach TaskRuntime")

    port = OpenSquillaQueueHostPort(task_runtime=FakeTaskRuntime())

    with pytest.raises(
        RuntimeError,
        match="queue.poll timeout_seconds must be a non-negative number",
    ):
        await port.handle_intent(
            intent_type="queue.poll",
            payload={"task_id": "task-1", "timeout_seconds": -1.0},
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_queue_poll_wait_timeout_is_host_clamped() -> None:
    from opensquilla.engine.agent_core import OpenSquillaQueueHostPort

    calls: list[float | None] = []

    class FakeTaskRuntime:
        async def wait(self, task_id: str, timeout: float | None = None):
            _ = task_id
            calls.append(timeout)
            return SimpleNamespace(
                task_id="task-1",
                status="running",
                terminal_reason=None,
            )

    port = OpenSquillaQueueHostPort(task_runtime=FakeTaskRuntime())

    await port.handle_intent(
        intent_type="queue.poll",
        payload={"task_id": "task-1", "timeout_seconds": 9999.0},
        session_key="agent:main:test",
    )

    assert calls == [5.0]


@pytest.mark.asyncio
async def test_pi_queue_poll_rejects_embedded_queue_control_operation() -> None:
    from opensquilla.engine.agent_core import OpenSquillaQueueHostPort

    class FakeTaskRuntime:
        async def status(self, task_id: str):
            return SimpleNamespace(
                task_id=task_id,
                status="running",
                terminal_reason=None,
            )

    port = OpenSquillaQueueHostPort(task_runtime=FakeTaskRuntime())

    with pytest.raises(
        RuntimeError,
        match="queue.poll cannot request queue control operation 'drain'",
    ):
        await port.handle_intent(
            intent_type="queue.poll",
            payload={"task_id": "task-1", "operation": "drain"},
            session_key="agent:main:test",
        )


@pytest.mark.asyncio
async def test_pi_kernel_can_use_configured_jsonl_command(tmp_path: Path) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.provider.types import ToolDefinition, ToolInputSchema, ToolParam

    script = tmp_path / "fake_pi_rpc.py"
    script.write_text(
        textwrap.dedent(
            """
            import json
            import os
            import sys

            protocol = os.environ["OPENSQUILLA_AGENT_CORE_PROTOCOL"]
            assert "OPENSQUILLA_PI_AGENT_PROMPT" not in os.environ
            assert "OPENSQUILLA_PI_AGENT_RPC_KWARGS" not in os.environ
            frame = json.loads(sys.stdin.readline())
            assert frame["protocol"] == "opensquilla.agent_core.v1"
            assert frame["kind"] == "turn_start"
            prompt = frame["payload"]["prompt"]
            kwargs = frame["payload"]["kwargs"]
            assert prompt == "hello"
            assert protocol == "opensquilla.agent_core.v1"
            assert kwargs["session_key"] == "agent:main:test"
            assert kwargs["turn_snapshot"]["session_key"] == "agent:main:test"
            assert kwargs["turn_snapshot"]["agent_id"] == "main"
            assert kwargs["turn_snapshot"]["turn_id"] == "agent:main:test:turn-1"
            assert kwargs["turn_snapshot"]["turn_input"] == "hello"
            assert kwargs["turn_snapshot"]["request_context_prompt"] == "jsonl request context"
            assert kwargs["turn_snapshot"]["model_id"] == "pi-jsonl"
            assert kwargs["turn_snapshot"]["tool_definitions"] == [{
                "name": "echo_marker",
                "description": "Return the marker exactly.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "marker": {
                            "type": "string",
                            "description": "Marker to echo",
                            "enum": None,
                        },
                    },
                    "required": ["marker"],
                },
                "execution_timeout_seconds": None,
                "execution_timeout_argument": None,
                "execution_timeout_padding": 0.0,
            }]
            print(json.dumps({
                "protocol": "opensquilla.agent_core.v1",
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "jsonl pi"},
            }))
            """
        ).lstrip(),
        encoding="utf-8",
    )

    agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_command=f"{sys.executable} {script}",
            allow_test_pi_rpc_command=True,
        ),
        provider=object(),
        config=SimpleNamespace(
            model_id="pi-jsonl",
            request_context_prompt="jsonl request context",
        ),
        tool_definitions=[
            ToolDefinition(
                name="echo_marker",
                description="Return the marker exactly.",
                input_schema=ToolInputSchema(
                    properties={
                        "marker": ToolParam(
                            type="string",
                            description="Marker to echo",
                        ),
                    },
                    required=["marker"],
                ),
            )
        ],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="jsonl pi"),
        DoneEvent(text="jsonl pi", model="pi-jsonl", cost_source="unavailable"),
    ]


@pytest.mark.asyncio
async def test_pi_jsonl_command_sends_turn_start_over_stdin_without_prompt_env(
    tmp_path: Path,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    script = tmp_path / "bootstrap_pi_rpc.py"
    script.write_text(
        textwrap.dedent(
            """
            import json
            import os
            import select
            import sys

            assert "OPENSQUILLA_PI_AGENT_PROMPT" not in os.environ
            assert "OPENSQUILLA_PI_AGENT_RPC_KWARGS" not in os.environ
            assert os.environ["OPENSQUILLA_AGENT_CORE_PROTOCOL"] == "opensquilla.agent_core.v1"

            ready, _, _ = select.select([sys.stdin], [], [], 2.0)
            if not ready:
                print("missing turn_start frame", file=sys.stderr)
                sys.exit(3)

            frame = json.loads(sys.stdin.readline())
            assert frame["protocol"] == "opensquilla.agent_core.v1"
            assert frame["kind"] == "turn_start"
            assert frame["payload"]["prompt"] == "secret prompt"
            assert frame["payload"]["kwargs"] == {
                "session_key": "agent:main:test",
                "turn_snapshot": {"turn_input": "secret prompt"},
            }

            print(json.dumps({
                "protocol": "opensquilla.agent_core.v1",
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "bootstrapped"},
            }), flush=True)
            """
        ).lstrip(),
        encoding="utf-8",
    )

    client = PiJsonlCommandRpcClient(f"{sys.executable} {script}")

    frames = [
        frame
        async for frame in client.stream_prompt(
            "secret prompt",
            session_key="agent:main:test",
            turn_snapshot={"turn_input": "secret prompt"},
        )
    ]

    assert frames == [
        {
            "protocol": "opensquilla.agent_core.v1",
            "kind": "event",
            "type": "text.delta",
            "payload": {"text": "bootstrapped"},
        }
    ]


@pytest.mark.asyncio
async def test_pi_jsonl_command_does_not_inherit_host_provider_or_pi_config_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    monkeypatch.setenv("OPENROUTER_API_KEY", "host-provider-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "host-openai-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "host-anthropic-secret")
    monkeypatch.setenv("OPENSQUILLA_PI_AGENT_RPC_COMMAND", "host-pi-command")
    monkeypatch.setenv(
        "OPENSQUILLA_PI_AGENT_RPC_COMMAND_PROVENANCE",
        "host-pi-provenance",
    )

    script = tmp_path / "sanitized_env_pi_rpc.py"
    script.write_text(
        textwrap.dedent(
            """
            import json
            import os
            import sys

            leaked = [
                name for name in (
                    "OPENROUTER_API_KEY",
                    "OPENAI_API_KEY",
                    "ANTHROPIC_API_KEY",
                    "OPENSQUILLA_PI_AGENT_RPC_COMMAND",
                    "OPENSQUILLA_PI_AGENT_RPC_COMMAND_PROVENANCE",
                )
                if name in os.environ
            ]
            if leaked:
                print("leaked env: " + ",".join(leaked), file=sys.stderr)
                sys.exit(7)
            assert os.environ["OPENSQUILLA_AGENT_CORE_PROTOCOL"] == "opensquilla.agent_core.v1"

            frame = json.loads(sys.stdin.readline())
            assert frame["kind"] == "turn_start"
            print(json.dumps({
                "protocol": "opensquilla.agent_core.v1",
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "env sanitized"},
            }), flush=True)
            """
        ).lstrip(),
        encoding="utf-8",
    )

    client = PiJsonlCommandRpcClient(f"{sys.executable} {script}")

    frames = [frame async for frame in client.stream_prompt("hello")]

    assert frames == [
        {
            "protocol": "opensquilla.agent_core.v1",
            "kind": "event",
            "type": "text.delta",
            "payload": {"text": "env sanitized"},
        }
    ]


@pytest.mark.asyncio
async def test_pi_jsonl_command_drains_stderr_without_blocking_stdout(
    tmp_path: Path,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    script = tmp_path / "noisy_pi_rpc.py"
    script.write_text(
        textwrap.dedent(
            """
            import json
            import sys

            sys.stderr.buffer.write(b"x" * (1024 * 1024))
            sys.stderr.flush()
            _ = sys.stdin.readline()
            print(json.dumps({
                "protocol": "opensquilla.agent_core.v1",
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "stdout survived noisy stderr"},
            }), flush=True)
            """
        ).lstrip(),
        encoding="utf-8",
    )

    client = PiJsonlCommandRpcClient(f"{sys.executable} {script}")

    async def collect_frames() -> list[dict[str, Any]]:
        return [frame async for frame in client.stream_prompt("noisy sidecar")]

    frames = await asyncio.wait_for(
        collect_frames(),
        timeout=2.0,
    )

    assert frames == [
        {
            "protocol": "opensquilla.agent_core.v1",
            "kind": "event",
            "type": "text.delta",
            "payload": {"text": "stdout survived noisy stderr"},
        }
    ]


@pytest.mark.asyncio
async def test_pi_jsonl_command_rejects_duplicate_jsonl_object_keys(
    tmp_path: Path,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    script = tmp_path / "duplicate_key_pi_rpc.py"
    script.write_text(
        textwrap.dedent(
            """
            import sys

            _ = sys.stdin.readline()
            print(
                '{"protocol":"opensquilla.agent_core.v1",'
                '"kind":"event","kind":"intent",'
                '"type":"text.delta","payload":{"text":"duplicate key"}}',
                flush=True,
            )
            """
        ).lstrip(),
        encoding="utf-8",
    )

    client = PiJsonlCommandRpcClient(f"{sys.executable} {script}")

    with pytest.raises(RuntimeError, match="duplicate JSON object key 'kind'"):
        _ = [frame async for frame in client.stream_prompt("duplicate key")]


@pytest.mark.asyncio
async def test_pi_jsonl_command_rejects_non_finite_stdout_jsonl(
    tmp_path: Path,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    script = tmp_path / "non_finite_stdout_pi_rpc.py"
    script.write_text(
        textwrap.dedent(
            """
            import sys

            _ = sys.stdin.readline()
            print(
                '{"protocol":"opensquilla.agent_core.v1",'
                '"kind":"event","type":"text.delta",'
                '"payload":{"text":"bad number","score":NaN}}',
                flush=True,
            )
            """
        ).lstrip(),
        encoding="utf-8",
    )

    client = PiJsonlCommandRpcClient(f"{sys.executable} {script}")

    with pytest.raises(RuntimeError, match="non-finite JSON value NaN"):
        _ = [frame async for frame in client.stream_prompt("non-finite stdout")]


@pytest.mark.asyncio
async def test_pi_jsonl_command_rejects_invalid_utf8_stdout_jsonl(
    tmp_path: Path,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    script = tmp_path / "invalid_utf8_stdout_pi_rpc.py"
    script.write_text(
        textwrap.dedent(
            """
            import sys

            _ = sys.stdin.readline()
            sys.stdout.buffer.write(
                b'{"protocol":"opensquilla.agent_core.v1",'
                b'"kind":"event","type":"text.delta",'
                b'"payload":{"text":"bad '
                + bytes([0xff])
                + b' utf8"}}\\n'
            )
            sys.stdout.flush()
            """
        ).lstrip(),
        encoding="utf-8",
    )

    client = PiJsonlCommandRpcClient(f"{sys.executable} {script}")

    with pytest.raises(RuntimeError, match="invalid UTF-8 JSONL"):
        _ = [frame async for frame in client.stream_prompt("invalid utf8")]


@pytest.mark.asyncio
async def test_pi_jsonl_command_rejects_overlong_stdout_jsonl_frame(
    tmp_path: Path,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    script = tmp_path / "overlong_stdout_pi_rpc.py"
    script.write_text(
        textwrap.dedent(
            """
            import sys

            _ = sys.stdin.readline()
            sys.stdout.buffer.write(b'{' + (b'"x":' + b'"y"' * 70000))
            sys.stdout.flush()
            """
        ).lstrip(),
        encoding="utf-8",
    )

    client = PiJsonlCommandRpcClient(f"{sys.executable} {script}")

    with pytest.raises(RuntimeError, match="overlong JSONL frame"):
        _ = [frame async for frame in client.stream_prompt("overlong stdout")]


@pytest.mark.asyncio
async def test_pi_jsonl_command_reassembles_chunked_stdout_frame(
    tmp_path: Path,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    script = tmp_path / "chunked_stdout_pi_rpc.py"
    script.write_text(
        textwrap.dedent(
            """
            import base64
            import json
            import sys

            _ = sys.stdin.readline()
            frame = {
                "protocol": "opensquilla.agent_core.v1",
                "kind": "intent",
                "type": "provider.request",
                "payload": {
                    "session_key": "agent:main:test",
                    "messages": [
                        {"role": "user", "content": "x" * 100000},
                    ],
                    "tools": [],
                    "config": {},
                },
            }
            encoded = base64.b64encode(
                json.dumps(frame, separators=(",", ":")).encode("utf-8")
            ).decode("ascii")
            chunks = [encoded[index : index + 24000] for index in range(0, len(encoded), 24000)]
            for index, data in enumerate(chunks):
                print(
                    json.dumps(
                        {
                            "protocol": "opensquilla.agent_core.v1",
                            "kind": "chunk",
                            "chunk_id": "provider-large-1",
                            "index": index,
                            "total": len(chunks),
                            "encoding": "base64-json",
                            "data": data,
                        },
                        separators=(",", ":"),
                    ),
                    flush=True,
                )
            """
        ).lstrip(),
        encoding="utf-8",
    )

    client = PiJsonlCommandRpcClient(f"{sys.executable} {script}")

    frames = [frame async for frame in client.stream_prompt("chunked stdout")]

    assert len(frames) == 1
    assert frames[0]["kind"] == "intent"
    assert frames[0]["type"] == "provider.request"
    assert frames[0]["payload"]["messages"][0]["content"] == "x" * 100000


@pytest.mark.asyncio
async def test_pi_jsonl_command_rejects_non_finite_turn_start_values_before_stdin(
    tmp_path: Path,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    script = tmp_path / "non_finite_bootstrap_pi_rpc.py"
    script.write_text(
        textwrap.dedent(
            """
            import json
            import sys

            _ = sys.stdin.readline()
            print(json.dumps({
                "protocol": "opensquilla.agent_core.v1",
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "non-finite leaked"},
            }), flush=True)
            """
        ).lstrip(),
        encoding="utf-8",
    )

    client = PiJsonlCommandRpcClient(f"{sys.executable} {script}")

    with pytest.raises(RuntimeError, match="non-finite"):
        _ = [
            frame
            async for frame in client.stream_prompt(
                "hello",
                turn_snapshot={"cache_hit_rate": float("inf")},
            )
        ]


@pytest.mark.asyncio
async def test_pi_jsonl_command_rejects_non_json_turn_kwargs_before_process_launch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    class PythonOnlyValue:
        pass

    launched = False

    async def forbidden_process_launch(*args, **kwargs):
        nonlocal launched
        launched = True
        _ = args, kwargs
        raise AssertionError("sidecar process must not launch for invalid turn kwargs")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden_process_launch)

    client = PiJsonlCommandRpcClient("python -c pass")

    with pytest.raises(RuntimeError, match="JSON value"):
        _ = [
            frame
            async for frame in client.stream_prompt(
                "hello",
                turn_snapshot={"python_only": PythonOnlyValue()},
            )
        ]
    assert launched is False


@pytest.mark.asyncio
@pytest.mark.parametrize("turn_snapshot", [None, [], "snapshot"])
async def test_pi_jsonl_command_rejects_non_object_turn_snapshot_before_process_launch(
    turn_snapshot: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    launched = False

    async def forbidden_process_launch(*args, **kwargs):
        nonlocal launched
        launched = True
        _ = args, kwargs
        raise AssertionError("sidecar process must not launch for invalid turn_snapshot")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden_process_launch)

    client = PiJsonlCommandRpcClient("python -c pass")

    with pytest.raises(RuntimeError, match="turn_start turn_snapshot must be an object"):
        _ = [
            frame
            async for frame in client.stream_prompt(
                "hello",
                turn_snapshot=turn_snapshot,
            )
        ]
    assert launched is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("session_key", None, "turn_start turn_snapshot.session_key must be a string"),
        ("session_key", "", "turn_start turn_snapshot.session_key must be non-empty"),
        ("session_key", "   ", "turn_start turn_snapshot.session_key must be non-empty"),
        (
            "session_key",
            {"session": "agent:main:test"},
            "turn_start turn_snapshot.session_key must be a string",
        ),
        ("session_id", None, "turn_start turn_snapshot.session_id must be a string"),
        ("session_id", "", "turn_start turn_snapshot.session_id must be non-empty"),
        ("session_id", "   ", "turn_start turn_snapshot.session_id must be non-empty"),
        (
            "session_id",
            ["agent:main:test"],
            "turn_start turn_snapshot.session_id must be a string",
        ),
    ],
)
async def test_pi_jsonl_command_rejects_invalid_turn_snapshot_identity_before_process_launch(
    field_name: str,
    value: object,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    launched = False

    async def forbidden_process_launch(*args, **kwargs):
        nonlocal launched
        launched = True
        _ = args, kwargs
        raise AssertionError("sidecar process must not launch for invalid snapshot identity")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden_process_launch)

    client = PiJsonlCommandRpcClient("python -c pass")

    with pytest.raises(RuntimeError, match=message):
        _ = [
            frame
            async for frame in client.stream_prompt(
                "hello",
                turn_snapshot={field_name: value},
            )
        ]
    assert launched is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("session_id", "message"),
    [
        (None, "turn_start session_id must be a string"),
        ("", "turn_start session_id must be non-empty"),
        ("   ", "turn_start session_id must be non-empty"),
        ({"session": "agent:main:test"}, "turn_start session_id must be a string"),
    ],
)
async def test_pi_jsonl_command_rejects_invalid_turn_start_session_id_before_process_launch(
    session_id: object,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    launched = False

    async def forbidden_process_launch(*args, **kwargs):
        nonlocal launched
        launched = True
        _ = args, kwargs
        raise AssertionError("sidecar process must not launch for invalid session_id")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden_process_launch)

    client = PiJsonlCommandRpcClient("python -c pass")

    with pytest.raises(RuntimeError, match=message):
        _ = [
            frame
            async for frame in client.stream_prompt(
                "hello",
                session_id=session_id,
            )
        ]
    assert launched is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("session_key", "message"),
    [
        (None, "turn_start session_key must be a string"),
        ("", "turn_start session_key must be non-empty"),
        ("   ", "turn_start session_key must be non-empty"),
        ({"session": "agent:main:test"}, "turn_start session_key must be a string"),
    ],
)
async def test_pi_jsonl_command_rejects_invalid_turn_start_session_key_before_process_launch(
    session_key: object,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    launched = False

    async def forbidden_process_launch(*args, **kwargs):
        nonlocal launched
        launched = True
        _ = args, kwargs
        raise AssertionError("sidecar process must not launch for invalid session_key")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden_process_launch)

    client = PiJsonlCommandRpcClient("python -c pass")

    with pytest.raises(RuntimeError, match=message):
        _ = [
            frame
            async for frame in client.stream_prompt(
                "hello",
                session_key=session_key,
            )
        ]
    assert launched is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field_name", "message"),
    [
        (
            "session_key",
            "turn_start turn_snapshot.session_key must match session_key",
        ),
        (
            "session_id",
            "turn_start turn_snapshot.session_id must match session_id",
        ),
    ],
)
async def test_pi_jsonl_command_rejects_turn_start_identity_mismatch_before_process_launch(
    field_name: str,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    launched = False

    async def forbidden_process_launch(*args, **kwargs):
        nonlocal launched
        launched = True
        _ = args, kwargs
        raise AssertionError("sidecar process must not launch for mismatched identity")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden_process_launch)

    client = PiJsonlCommandRpcClient("python -c pass")

    with pytest.raises(RuntimeError, match=message):
        _ = [
            frame
            async for frame in client.stream_prompt(
                "hello",
                **{
                    field_name: "agent:main:test",
                    "turn_snapshot": {field_name: "agent:other:test"},
                },
            )
        ]
    assert launched is False


@pytest.mark.asyncio
async def test_pi_jsonl_command_rejects_non_finite_prompt_before_stdin(
    tmp_path: Path,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    script = tmp_path / "non_finite_prompt_pi_rpc.py"
    script.write_text(
        textwrap.dedent(
            """
            import json
            import sys

            _ = sys.stdin.readline()
            print(json.dumps({
                "protocol": "opensquilla.agent_core.v1",
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "non-finite prompt leaked"},
            }), flush=True)
            """
        ).lstrip(),
        encoding="utf-8",
    )

    client = PiJsonlCommandRpcClient(f"{sys.executable} {script}")

    with pytest.raises(RuntimeError, match="turn_start prompt must be a string"):
        _ = [frame async for frame in client.stream_prompt(float("nan"))]  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_pi_jsonl_command_rejects_structured_prompt_before_stdin(
    tmp_path: Path,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    script = tmp_path / "structured_prompt_pi_rpc.py"
    script.write_text(
        textwrap.dedent(
            """
            import json
            import sys

            _ = sys.stdin.readline()
            print(json.dumps({
                "protocol": "opensquilla.agent_core.v1",
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "structured prompt leaked"},
            }), flush=True)
            """
        ).lstrip(),
        encoding="utf-8",
    )

    client = PiJsonlCommandRpcClient(f"{sys.executable} {script}")

    with pytest.raises(RuntimeError, match="turn_start prompt must be a string"):
        _ = [
            frame
            async for frame in client.stream_prompt({"not": "a string"})  # type: ignore[arg-type]
        ]


@pytest.mark.asyncio
@pytest.mark.parametrize("prompt", ["", "   ", "\n\t"])
async def test_pi_jsonl_command_rejects_blank_prompt_before_process_launch(
    prompt: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    launched = False

    async def forbidden_process_launch(*args, **kwargs):
        nonlocal launched
        launched = True
        _ = args, kwargs
        raise AssertionError("sidecar process must not launch for blank prompt")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden_process_launch)

    client = PiJsonlCommandRpcClient("python -c pass")

    with pytest.raises(RuntimeError, match="turn_start prompt must be non-empty"):
        _ = [frame async for frame in client.stream_prompt(prompt)]
    assert launched is False


@pytest.mark.asyncio
async def test_pi_jsonl_command_rejects_structured_intent_result_string_fields() -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    class FakeStdin:
        def __init__(self) -> None:
            self.writes: list[bytes] = []

        def is_closing(self) -> bool:
            return False

        def write(self, data: bytes) -> None:
            self.writes.append(data)

        async def drain(self) -> None:
            pass

    stdin = FakeStdin()
    client = PiJsonlCommandRpcClient("python -c pass")
    client._active_stdin = stdin

    with pytest.raises(RuntimeError, match="intent_result type must be a string"):
        await client.receive_intent_result(
            intent_type={"not": "a string"},  # type: ignore[arg-type]
            payload={},
            events=[],
            session_key="agent:main:test",
        )
    assert stdin.writes == []

    with pytest.raises(RuntimeError, match="intent_result type must be non-empty"):
        await client.receive_intent_result(
            intent_type="   ",
            payload={},
            events=[],
            session_key="agent:main:test",
        )
    assert stdin.writes == []

    with pytest.raises(RuntimeError, match="intent_result session_key must be a string"):
        await client.receive_intent_result(
            intent_type="queue.poll",
            payload={},
            events=[],
            session_key={"not": "a string"},  # type: ignore[arg-type]
        )
    assert stdin.writes == []

    with pytest.raises(RuntimeError, match="intent_result session_key must be non-empty"):
        await client.receive_intent_result(
            intent_type="queue.poll",
            payload={},
            events=[],
            session_key="",
        )
    assert stdin.writes == []

    client._active_stream = True
    try:
        with pytest.raises(
            RuntimeError,
            match="intent_result session_key must be non-empty",
        ):
            await client.receive_intent_result(
                intent_type="queue.poll",
                payload={},
                events=[],
                session_key="   ",
            )
        assert stdin.writes == []
    finally:
        client._active_stream = False


@pytest.mark.asyncio
async def test_pi_jsonl_command_rejects_unsupported_intent_result_type() -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    class FakeStdin:
        def __init__(self) -> None:
            self.writes: list[bytes] = []

        def is_closing(self) -> bool:
            return False

        def write(self, data: bytes) -> None:
            self.writes.append(data)

        async def drain(self) -> None:
            pass

    stdin = FakeStdin()
    client = PiJsonlCommandRpcClient("python -c pass")
    client._active_stdin = stdin

    with pytest.raises(RuntimeError, match="Unsupported Pi sidecar intent_result"):
        await client.receive_intent_result(
            intent_type="unknown.intent",
            payload={},
            events=[],
            session_key="agent:main:test",
        )
    assert stdin.writes == []


@pytest.mark.asyncio
async def test_pi_jsonl_command_rejects_structured_intent_result_payload_and_events() -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    class FakeStdin:
        def __init__(self) -> None:
            self.writes: list[bytes] = []

        def is_closing(self) -> bool:
            return False

        def write(self, data: bytes) -> None:
            self.writes.append(data)

        async def drain(self) -> None:
            pass

    stdin = FakeStdin()
    client = PiJsonlCommandRpcClient("python -c pass")
    client._active_stdin = stdin

    with pytest.raises(RuntimeError, match="intent_result payload must be a JSON object"):
        await client.receive_intent_result(
            intent_type="queue.poll",
            payload=["not", "an", "object"],  # type: ignore[arg-type]
            events=[],
            session_key="agent:main:test",
        )
    assert stdin.writes == []

    with pytest.raises(RuntimeError, match="intent_result events must be a list"):
        await client.receive_intent_result(
            intent_type="queue.poll",
            payload={},
            events={"not": "a list"},  # type: ignore[arg-type]
            session_key="agent:main:test",
        )
    assert stdin.writes == []

    with pytest.raises(
        RuntimeError,
        match="intent_result events entries must be JSON objects",
    ):
        await client.receive_intent_result(
            intent_type="queue.poll",
            payload={},
            events=["not an event object"],
            session_key="agent:main:test",
        )
    assert stdin.writes == []

    with pytest.raises(
        RuntimeError,
        match="intent_result events entries must include string kind",
    ):
        await client.receive_intent_result(
            intent_type="queue.poll",
            payload={},
            events=[{"message": "missing kind"}],
            session_key="agent:main:test",
        )
    assert stdin.writes == []

    with pytest.raises(
        RuntimeError,
        match="intent_result events entries kind must be non-empty",
    ):
        await client.receive_intent_result(
            intent_type="queue.poll",
            payload={},
            events=[{"kind": "   "}],
            session_key="agent:main:test",
        )
    assert stdin.writes == []

    with pytest.raises(
        RuntimeError,
        match="Unsupported Pi sidecar intent_result event kind",
    ):
        await client.receive_intent_result(
            intent_type="queue.poll",
            payload={},
            events=[{"kind": "unknown_event"}],
            session_key="agent:main:test",
        )
    assert stdin.writes == []

    with pytest.raises(
        RuntimeError,
        match="intent_result events entries must include string kind",
    ):
        await client.receive_intent_result(
            intent_type="queue.poll",
            payload={},
            events=[{"kind": {"not": "a string"}}],
            session_key="agent:main:test",
        )
    assert stdin.writes == []


@pytest.mark.parametrize(
    ("events", "message"),
    [
        (
            [
                {"kind": "done", "text": "done"},
                {"kind": "run_heartbeat", "message": "late"},
            ],
            "intent_result events returned events after terminal event",
        ),
        (
            [
                {"kind": "error", "message": "failed"},
                {"kind": "done", "text": "done"},
            ],
            "intent_result events returned multiple terminal events",
        ),
    ],
)
@pytest.mark.asyncio
async def test_pi_jsonl_command_rejects_terminal_ordering_in_intent_result_feedback(
    events: list[dict[str, Any]],
    message: str,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    class FakeStdin:
        def __init__(self) -> None:
            self.writes: list[bytes] = []

        def is_closing(self) -> bool:
            return False

        def write(self, data: bytes) -> None:
            self.writes.append(data)

        async def drain(self) -> None:
            pass

    stdin = FakeStdin()
    client = PiJsonlCommandRpcClient("python -c pass")
    client._active_stdin = stdin
    client._active_stream = True

    try:
        with pytest.raises(RuntimeError, match=message):
            await client.receive_intent_result(
                intent_type="queue.poll",
                payload={},
                events=events,
                session_key="agent:main:test",
            )
        assert stdin.writes == []
    finally:
        client._active_stream = False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "events", "message"),
    [
        (
            {"score": float("nan")},
            [{"kind": "run_heartbeat", "message": "queue empty"}],
            "intent_result payload must be JSON-compatible",
        ),
        (
            {},
            [{"kind": "run_heartbeat", "detail": object()}],
            "intent_result events must be JSON-compatible",
        ),
    ],
)
async def test_pi_jsonl_command_rejects_non_json_safe_intent_result_feedback(
    payload: dict[str, Any],
    events: list[dict[str, Any]],
    message: str,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    class FakeStdin:
        def __init__(self) -> None:
            self.writes: list[bytes] = []

        def is_closing(self) -> bool:
            return False

        def write(self, data: bytes) -> None:
            self.writes.append(data)

        async def drain(self) -> None:
            pass

    stdin = FakeStdin()
    client = PiJsonlCommandRpcClient("python -c pass")
    client._active_stdin = stdin
    client._active_stream = True
    try:
        with pytest.raises(RuntimeError, match=message):
            await client.receive_intent_result(
                intent_type="queue.poll",
                payload=payload,
                events=events,
                session_key="agent:main:test",
            )
        assert stdin.writes == []
    finally:
        client._active_stream = False


@pytest.mark.asyncio
async def test_pi_jsonl_command_rejects_intent_result_without_active_stream() -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    class FakeStdin:
        def __init__(self) -> None:
            self.writes: list[bytes] = []

        def is_closing(self) -> bool:
            return False

        def write(self, data: bytes) -> None:
            self.writes.append(data)

        async def drain(self) -> None:
            pass

    stdin = FakeStdin()
    client = PiJsonlCommandRpcClient("python -c pass")
    client._active_stdin = stdin

    with pytest.raises(RuntimeError, match="requires an active stream"):
        await client.receive_intent_result(
            intent_type="queue.poll",
            payload={},
            events=[{"kind": "run_heartbeat", "message": "queue empty"}],
            session_key="agent:main:test",
        )
    assert stdin.writes == []


@pytest.mark.asyncio
async def test_pi_jsonl_command_rejects_concurrent_streams_on_same_client(
    tmp_path: Path,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    script = tmp_path / "sleeping_pi_rpc.py"
    script.write_text(
        textwrap.dedent(
            """
            import json
            import time

            print(json.dumps({
                "protocol": "opensquilla.agent_core.v1",
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "stream opened"},
            }), flush=True)
            time.sleep(30)
            """
        ).lstrip(),
        encoding="utf-8",
    )

    client = PiJsonlCommandRpcClient(f"{sys.executable} {script}")
    first_stream = client.stream_prompt("first")
    second_stream = None
    try:
        assert await asyncio.wait_for(anext(first_stream), timeout=1.0) == {
            "protocol": "opensquilla.agent_core.v1",
            "kind": "event",
            "type": "text.delta",
            "payload": {"text": "stream opened"},
        }

        second_stream = client.stream_prompt("second")
        with pytest.raises(RuntimeError, match="already has an active stream"):
            await asyncio.wait_for(anext(second_stream), timeout=1.0)
    finally:
        if second_stream is not None:
            await second_stream.aclose()
        await first_stream.aclose()


@pytest.mark.asyncio
async def test_pi_jsonl_command_rejects_active_stream_before_prompt_validation(
    tmp_path: Path,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    script = tmp_path / "sleeping_pi_rpc.py"
    script.write_text(
        textwrap.dedent(
            """
            import json
            import time

            print(json.dumps({
                "protocol": "opensquilla.agent_core.v1",
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "stream opened"},
            }), flush=True)
            time.sleep(30)
            """
        ).lstrip(),
        encoding="utf-8",
    )

    client = PiJsonlCommandRpcClient(f"{sys.executable} {script}")
    first_stream = client.stream_prompt("first")
    second_stream = None
    try:
        assert await asyncio.wait_for(anext(first_stream), timeout=1.0) == {
            "protocol": "opensquilla.agent_core.v1",
            "kind": "event",
            "type": "text.delta",
            "payload": {"text": "stream opened"},
        }

        second_stream = client.stream_prompt({"not": "a string"})  # type: ignore[arg-type]
        with pytest.raises(RuntimeError, match="already has an active stream"):
            await asyncio.wait_for(anext(second_stream), timeout=1.0)
    finally:
        if second_stream is not None:
            await second_stream.aclose()
        await first_stream.aclose()


@pytest.mark.asyncio
async def test_pi_jsonl_command_rejects_active_stream_before_turn_kwargs_validation(
    tmp_path: Path,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    class PythonOnlyValue:
        pass

    script = tmp_path / "sleeping_pi_rpc.py"
    script.write_text(
        textwrap.dedent(
            """
            import json
            import time

            print(json.dumps({
                "protocol": "opensquilla.agent_core.v1",
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "stream opened"},
            }), flush=True)
            time.sleep(30)
            """
        ).lstrip(),
        encoding="utf-8",
    )

    client = PiJsonlCommandRpcClient(f"{sys.executable} {script}")
    first_stream = client.stream_prompt("first")
    second_stream = None
    try:
        assert await asyncio.wait_for(anext(first_stream), timeout=1.0) == {
            "protocol": "opensquilla.agent_core.v1",
            "kind": "event",
            "type": "text.delta",
            "payload": {"text": "stream opened"},
        }

        second_stream = client.stream_prompt(
            "second",
            turn_snapshot={"python_only": PythonOnlyValue()},
        )
        with pytest.raises(RuntimeError, match="already has an active stream"):
            await asyncio.wait_for(anext(second_stream), timeout=1.0)
    finally:
        if second_stream is not None:
            await second_stream.aclose()
        await first_stream.aclose()


@pytest.mark.asyncio
async def test_pi_jsonl_command_receives_host_intent_results_over_stdin(
    tmp_path: Path,
) -> None:
    from opensquilla.engine.agent_core import (
        KernelHostPorts,
        PiJsonlCommandRpcClient,
        PiSidecarKernelRuntime,
    )

    script = tmp_path / "feedback_pi_rpc.py"
    script.write_text(
        textwrap.dedent(
            """
            import json
            import select
            import sys

            bootstrap = json.loads(sys.stdin.readline())
            assert bootstrap["protocol"] == "opensquilla.agent_core.v1"
            assert bootstrap["kind"] == "turn_start"

            print(json.dumps({
                "protocol": "opensquilla.agent_core.v1",
                "kind": "intent",
                "type": "queue.poll",
                "payload": {"task_id": "task-1", "timeout_seconds": 0.25},
            }), flush=True)

            ready, _, _ = select.select([sys.stdin], [], [], 2.0)
            if not ready:
                print("missing intent_result feedback", file=sys.stderr)
                sys.exit(3)

            line = sys.stdin.readline()
            if not line:
                print("empty intent_result feedback", file=sys.stderr)
                sys.exit(4)

            feedback = json.loads(line)
            assert feedback["protocol"] == "opensquilla.agent_core.v1"
            assert feedback["kind"] == "intent_result"
            assert feedback["type"] == "queue.poll"
            assert feedback["session_key"] == "agent:main:test"
            assert feedback["payload"] == {"task_id": "task-1", "timeout_seconds": 0.25}
            assert feedback["events"] == [{
                "kind": "run_heartbeat",
                "phase": "queue",
                "elapsed_ms": 0,
                "idle_ms": 0,
                "message": "queue empty",
            }]

            print(json.dumps({
                "protocol": "opensquilla.agent_core.v1",
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "feedback received"},
            }), flush=True)
            """
        ).lstrip(),
        encoding="utf-8",
    )

    class FakeQueuePort:
        async def handle_intent(self, **kwargs):
            assert kwargs["intent_type"] == "queue.poll"
            assert kwargs["payload"] == {"task_id": "task-1", "timeout_seconds": 0.25}
            assert kwargs["session_key"] == "agent:main:test"
            return [
                RunHeartbeatEvent(
                    phase="queue",
                    message="queue empty",
                )
            ]

    class FakeFinalizerPort:
        async def handle_intent(self, **kwargs):
            assert kwargs["intent_type"] == "turn.finalize"
            return [
                DoneEvent(
                    text=kwargs["payload"]["text"],
                    model=kwargs["payload"]["model"],
                    cost_source="unavailable",
                )
            ]

    agent = PiSidecarKernelRuntime(
        rpc_client=PiJsonlCommandRpcClient(f"{sys.executable} {script}"),
        config=SimpleNamespace(model_id="pi-jsonl-feedback"),
        session_key="agent:main:test",
        host_ports=KernelHostPorts(
            queue=FakeQueuePort(),
            finalizer=FakeFinalizerPort(),
        ),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        RunHeartbeatEvent(phase="queue", message="queue empty"),
        TextDeltaEvent(text="feedback received"),
        DoneEvent(
            text="feedback received",
            model="pi-jsonl-feedback",
            cost_source="unavailable",
        ),
    ]


@pytest.mark.asyncio
async def test_pi_jsonl_provider_request_feedback_can_continue_sidecar_loop(
    tmp_path: Path,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig
    from opensquilla.provider import DoneEvent as ProviderDoneEvent
    from opensquilla.provider import TextDeltaEvent as ProviderTextDeltaEvent

    script = tmp_path / "provider_feedback_pi_rpc.py"
    script.write_text(
        textwrap.dedent(
            """
            import json
            import select
            import sys

            bootstrap = json.loads(sys.stdin.readline())
            assert bootstrap["protocol"] == "opensquilla.agent_core.v1"
            assert bootstrap["kind"] == "turn_start"

            print(json.dumps({
                "protocol": "opensquilla.agent_core.v1",
                "kind": "intent",
                "type": "provider.request",
                "payload": {
                    "messages": [{"role": "user", "content": "ask host provider"}],
                },
            }), flush=True)

            ready, _, _ = select.select([sys.stdin], [], [], 2.0)
            if not ready:
                print("missing provider intent_result feedback", file=sys.stderr)
                sys.exit(3)

            feedback = json.loads(sys.stdin.readline())
            assert feedback["protocol"] == "opensquilla.agent_core.v1"
            assert feedback["kind"] == "intent_result"
            assert feedback["type"] == "provider.request"
            assert feedback["session_key"] == "agent:main:test"
            assert feedback["events"][0] == {
                "kind": "text_delta",
                "text": "host provider",
            }

            print(json.dumps({
                "protocol": "opensquilla.agent_core.v1",
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "sidecar saw host provider"},
            }), flush=True)
            """
        ).lstrip(),
        encoding="utf-8",
    )

    class FakeProvider:
        async def chat(self, messages, *, tools=None, config=None):
            assert messages[0].content == "ask host provider"
            assert tools is None
            assert config.max_tokens == 16384
            yield ProviderTextDeltaEvent(text="host provider")
            yield ProviderDoneEvent(
                input_tokens=7,
                output_tokens=5,
                cached_tokens=2,
                cache_write_tokens=3,
                billed_cost=0.01,
                model="provider-model",
            )

    agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_command=f"{sys.executable} {script}",
            allow_test_pi_rpc_command=True,
        ),
        provider=FakeProvider(),
        config=AgentConfig(model_id="pi-jsonl-provider-feedback"),
        tool_definitions=[],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="host provider"),
        TextDeltaEvent(text="sidecar saw host provider"),
        DoneEvent(
            text="host providersidecar saw host provider",
            input_tokens=7,
            output_tokens=5,
            cached_tokens=2,
            cache_write_tokens=3,
            cost_usd=0.01,
            billed_cost=0.01,
            cost_source="provider_billed",
            model="provider-model",
            iterations=1,
        ),
    ]


@pytest.mark.asyncio
async def test_pi_jsonl_tool_feedback_can_continue_sidecar_loop(
    tmp_path: Path,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig, ToolCall, ToolResult, ToolUseStartEvent

    script = tmp_path / "tool_feedback_pi_rpc.py"
    script.write_text(
        textwrap.dedent(
            """
            import json
            import select
            import sys

            bootstrap = json.loads(sys.stdin.readline())
            assert bootstrap["protocol"] == "opensquilla.agent_core.v1"
            assert bootstrap["kind"] == "turn_start"

            def read_feedback(expected_type):
                ready, _, _ = select.select([sys.stdin], [], [], 2.0)
                if not ready:
                    print(f"missing {expected_type} feedback", file=sys.stderr)
                    sys.exit(3)
                frame = json.loads(sys.stdin.readline())
                assert frame["protocol"] == "opensquilla.agent_core.v1"
                assert frame["kind"] == "intent_result"
                assert frame["type"] == expected_type
                assert frame["session_key"] == "agent:main:test"
                return frame

            print(json.dumps({
                "protocol": "opensquilla.agent_core.v1",
                "kind": "intent",
                "type": "tool.call.prepare",
                "payload": {"tool_call_id": "call-1", "tool_name": "echo"},
            }), flush=True)

            prepare = read_feedback("tool.call.prepare")
            assert prepare["events"] == [{
                "kind": "tool_use_start",
                "tool_use_id": "call-1",
                "tool_name": "echo",
                "synthetic_from_text": False,
            }]

            print(json.dumps({
                "protocol": "opensquilla.agent_core.v1",
                "kind": "intent",
                "type": "tool.call.execute",
                "payload": {
                    "tool_call_id": "call-1",
                    "tool_name": "echo",
                    "arguments": {"marker": "from-sidecar"},
                },
            }), flush=True)

            execute = read_feedback("tool.call.execute")
            result = execute["events"][0]
            assert result["kind"] == "tool_result"
            assert result["tool_use_id"] == "call-1"
            assert result["tool_name"] == "echo"
            assert result["result"] == "echo from-sidecar"
            assert result["arguments"] == {"marker": "from-sidecar"}
            assert result["is_error"] is False

            print(json.dumps({
                "protocol": "opensquilla.agent_core.v1",
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "tool feedback received"},
            }), flush=True)
            """
        ).lstrip(),
        encoding="utf-8",
    )

    calls: list[ToolCall] = []

    async def tool_handler(call: ToolCall) -> ToolResult:
        calls.append(call)
        return ToolResult(
            tool_use_id=call.tool_use_id,
            tool_name=call.tool_name,
            content=f"echo {call.arguments['marker']}",
        )

    agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_command=f"{sys.executable} {script}",
            allow_test_pi_rpc_command=True,
        ),
        provider=object(),
        config=AgentConfig(model_id="pi-jsonl-tool-feedback"),
        tool_definitions=[],
        tool_handler=tool_handler,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        ToolUseStartEvent(tool_use_id="call-1", tool_name="echo"),
        ToolResultEvent(
            tool_use_id="call-1",
            tool_name="echo",
            result="echo from-sidecar",
            arguments={"marker": "from-sidecar"},
        ),
        TextDeltaEvent(text="tool feedback received"),
        DoneEvent(
            text="tool feedback received",
            model="pi-jsonl-tool-feedback",
            cost_source="unavailable",
        ),
    ]
    assert [(call.tool_use_id, call.tool_name, call.arguments) for call in calls] == [
        ("call-1", "echo", {"marker": "from-sidecar"})
    ]


@pytest.mark.asyncio
async def test_pi_jsonl_session_write_feedback_can_continue_sidecar_loop(
    tmp_path: Path,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    script = tmp_path / "session_write_feedback_pi_rpc.py"
    script.write_text(
        textwrap.dedent(
            """
            import json
            import select
            import sys

            bootstrap = json.loads(sys.stdin.readline())
            assert bootstrap["protocol"] == "opensquilla.agent_core.v1"
            assert bootstrap["kind"] == "turn_start"

            print(json.dumps({
                "protocol": "opensquilla.agent_core.v1",
                "kind": "intent",
                "type": "session.write.enqueue",
                "payload": {
                    "session_key": "agent:main:test",
                    "role": "assistant",
                    "content": "persist from sidecar",
                    "token_count": 11,
                },
            }), flush=True)

            ready, _, _ = select.select([sys.stdin], [], [], 2.0)
            if not ready:
                print("missing session write feedback", file=sys.stderr)
                sys.exit(3)

            feedback = json.loads(sys.stdin.readline())
            assert feedback["protocol"] == "opensquilla.agent_core.v1"
            assert feedback["kind"] == "intent_result"
            assert feedback["type"] == "session.write.enqueue"
            assert feedback["session_key"] == "agent:main:test"
            assert feedback["payload"] == {
                "session_key": "agent:main:test",
                "role": "assistant",
                "content": "persist from sidecar",
                "token_count": 11,
            }
            assert feedback["events"] == []

            print(json.dumps({
                "protocol": "opensquilla.agent_core.v1",
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "session feedback received"},
            }), flush=True)
            """
        ).lstrip(),
        encoding="utf-8",
    )

    writes: list[dict[str, Any]] = []
    context_entries: list[str] = []

    class FakeSessionManager:
        async def append_message(self, session_key: str, **kwargs):
            writes.append({"session_key": session_key, **kwargs})
            return SimpleNamespace(id="entry-1")

    @contextlib.asynccontextmanager
    async def write_context():
        context_entries.append("entered")
        yield
        context_entries.append("exited")

    agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_command=f"{sys.executable} {script}",
            allow_test_pi_rpc_command=True,
        ),
        provider=object(),
        config=AgentConfig(model_id="pi-jsonl-session-feedback"),
        tool_definitions=[],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
        session_manager=FakeSessionManager(),
        session_write_context_factory=lambda session_key: write_context(),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="session feedback received"),
        DoneEvent(
            text="session feedback received",
            model="pi-jsonl-session-feedback",
            cost_source="unavailable",
        ),
    ]
    assert context_entries == ["entered", "exited"]
    assert writes == [
        {
            "session_key": "agent:main:test",
            "role": "assistant",
            "content": "persist from sidecar",
            "tool_calls": None,
            "reasoning_content": None,
            "turn_usage": None,
            "token_count": 11,
        }
    ]


@pytest.mark.asyncio
async def test_pi_jsonl_savepoint_feedback_can_continue_sidecar_loop(
    tmp_path: Path,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    script = tmp_path / "savepoint_feedback_pi_rpc.py"
    script.write_text(
        textwrap.dedent(
            """
            import json
            import select
            import sys

            bootstrap = json.loads(sys.stdin.readline())
            assert bootstrap["protocol"] == "opensquilla.agent_core.v1"
            assert bootstrap["kind"] == "turn_start"

            print(json.dumps({
                "protocol": "opensquilla.agent_core.v1",
                "kind": "intent",
                "type": "savepoint.request",
                "payload": {
                    "session_key": "agent:main:test",
                    "turn_id": "turn-1",
                    "source": "pi-sidecar",
                    "transcript": [{"role": "assistant", "content": "state"}],
                },
            }), flush=True)

            ready, _, _ = select.select([sys.stdin], [], [], 2.0)
            if not ready:
                print("missing savepoint feedback", file=sys.stderr)
                sys.exit(3)

            feedback = json.loads(sys.stdin.readline())
            assert feedback["protocol"] == "opensquilla.agent_core.v1"
            assert feedback["kind"] == "intent_result"
            assert feedback["type"] == "savepoint.request"
            assert feedback["session_key"] == "agent:main:test"
            assert feedback["payload"] == {
                "session_key": "agent:main:test",
                "turn_id": "turn-1",
                "source": "pi-sidecar",
                "transcript": [{"role": "assistant", "content": "state"}],
            }
            assert feedback["events"] == []

            print(json.dumps({
                "protocol": "opensquilla.agent_core.v1",
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "savepoint feedback received"},
            }), flush=True)
            """
        ).lstrip(),
        encoding="utf-8",
    )

    checkpoints: list[dict[str, Any]] = []
    context_entries: list[str] = []

    class FakeSessionManager:
        async def record_memory_checkpoint(self, session_key, transcript, **kwargs):
            checkpoints.append(
                {"session_key": session_key, "transcript": transcript, **kwargs}
            )
            return {"status": "ok"}

    @contextlib.asynccontextmanager
    async def write_context():
        context_entries.append("entered")
        yield
        context_entries.append("exited")

    agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_command=f"{sys.executable} {script}",
            allow_test_pi_rpc_command=True,
        ),
        provider=object(),
        config=AgentConfig(model_id="pi-jsonl-savepoint-feedback"),
        tool_definitions=[],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
        session_manager=FakeSessionManager(),
        session_write_context_factory=lambda session_key: write_context(),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="savepoint feedback received"),
        DoneEvent(
            text="savepoint feedback received",
            model="pi-jsonl-savepoint-feedback",
            cost_source="unavailable",
        ),
    ]
    assert context_entries == ["entered", "exited"]
    assert len(checkpoints) == 1
    checkpoint = checkpoints[0]
    assert checkpoint["session_key"] == "agent:main:test"
    assert checkpoint["turn_id"] == "turn-1"
    assert checkpoint["source"] == "pi-sidecar"
    assert len(checkpoint["transcript"]) == 1
    entry = checkpoint["transcript"][0]
    assert getattr(entry, "role") == "assistant"
    assert getattr(entry, "content") == "state"


@pytest.mark.asyncio
async def test_pi_jsonl_command_terminates_process_when_stream_is_closed(
    tmp_path: Path,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient

    marker = tmp_path / "terminated.txt"
    script = tmp_path / "sleeping_pi_rpc.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import json
            import signal
            import sys
            import time

            def on_term(signum, frame):
                _ = signum, frame
                with open({str(marker)!r}, "w", encoding="utf-8") as marker:
                    marker.write("terminated")
                sys.exit(0)

            signal.signal(signal.SIGTERM, on_term)
            print(json.dumps({{
                "protocol": "opensquilla.agent_core.v1",
                "kind": "event",
                "type": "text.delta",
                "payload": {{"text": "first"}},
            }}), flush=True)
            time.sleep(30)
            """
        ).lstrip(),
        encoding="utf-8",
    )

    stream = PiJsonlCommandRpcClient(f"{sys.executable} {script}").stream_prompt(
        "hello"
    )
    first = await stream.__anext__()
    await stream.aclose()

    assert first["payload"]["text"] == "first"
    assert marker.read_text(encoding="utf-8") == "terminated"


@pytest.mark.asyncio
async def test_pi_jsonl_command_is_closed_after_host_terminal_event(
    tmp_path: Path,
) -> None:
    from opensquilla.engine.agent_core import (
        AgentCoreConfig,
        KernelHostPorts,
        PiJsonlCommandRpcClient,
        PiSidecarKernelRuntime,
    )

    marker = tmp_path / "terminated-after-host-done.txt"
    script = tmp_path / "sleeping_pi_host_done_rpc.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import json
            import signal
            import sys
            import time

            def on_term(signum, frame):
                _ = signum, frame
                with open({str(marker)!r}, "w", encoding="utf-8") as marker:
                    marker.write("terminated")
                sys.exit(0)

            signal.signal(signal.SIGTERM, on_term)
            print(json.dumps({{
                "protocol": "opensquilla.agent_core.v1",
                "kind": "intent",
                "type": "provider.request",
                "payload": {{
                    "messages": [{{"role": "user", "content": "host terminal"}}],
                    "tools": None,
                    "config": {{}},
                }},
            }}), flush=True)
            time.sleep(30)
            """
        ).lstrip(),
        encoding="utf-8",
    )

    class FakeProviderPort:
        async def handle_intent(self, **kwargs):
            assert kwargs["intent_type"] == "provider.request"
            return [
                TextDeltaEvent(text="host terminal"),
                DoneEvent(
                    text="host terminal",
                    input_tokens=2,
                    output_tokens=3,
                    iterations=1,
                    cost_source="unavailable",
                    model="provider-model",
                ),
            ]

    agent = PiSidecarKernelRuntime(
        rpc_client=PiJsonlCommandRpcClient(f"{sys.executable} {script}"),
        config=SimpleNamespace(model_id="pi-host-terminal"),
        session_key="agent:main:test",
        agent_core_config=AgentCoreConfig(
            kernel="pi",
            allow_test_pi_rpc_command=True,
        ),
        host_ports=KernelHostPorts(provider=FakeProviderPort()),
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        TextDeltaEvent(text="host terminal"),
        DoneEvent(
            text="host terminal",
            input_tokens=2,
            output_tokens=3,
            iterations=1,
            cost_source="unavailable",
            model="provider-model",
        ),
    ]
    assert marker.read_text(encoding="utf-8") == "terminated"


@pytest.mark.asyncio
async def test_pi_jsonl_command_is_closed_after_sidecar_terminal_error(
    tmp_path: Path,
) -> None:
    from opensquilla.engine.agent_core import PiJsonlCommandRpcClient, PiSidecarKernelRuntime
    from opensquilla.engine.types import ErrorEvent

    marker = tmp_path / "terminated-after-sidecar-error.txt"
    script = tmp_path / "sleeping_pi_sidecar_error_rpc.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import json
            import signal
            import sys
            import time

            def on_term(signum, frame):
                _ = signum, frame
                with open({str(marker)!r}, "w", encoding="utf-8") as marker:
                    marker.write("terminated")
                sys.exit(0)

            signal.signal(signal.SIGTERM, on_term)
            _ = sys.stdin.readline()
            print(json.dumps({{
                "protocol": "opensquilla.agent_core.v1",
                "kind": "event",
                "type": "error",
                "payload": {{"message": "sidecar terminal", "code": "sidecar_terminal"}},
            }}), flush=True)
            time.sleep(30)
            """
        ).lstrip(),
        encoding="utf-8",
    )

    agent = PiSidecarKernelRuntime(
        rpc_client=PiJsonlCommandRpcClient(f"{sys.executable} {script}"),
        config=SimpleNamespace(model_id="pi-sidecar-terminal"),
        session_key="agent:main:test",
    )

    events = [event async for event in agent.run_turn("hello")]

    assert events == [
        ErrorEvent(message="sidecar terminal", code="sidecar_terminal"),
    ]
    assert marker.read_text(encoding="utf-8") == "terminated"


@pytest.mark.asyncio
async def test_pi_sidecar_run_turn_closes_jsonl_command_on_consumer_close(
    tmp_path: Path,
) -> None:
    from opensquilla.engine.agent_core import build_agent_for_kernel
    from opensquilla.engine.types import AgentConfig

    marker = tmp_path / "terminated-after-consumer-close.txt"
    script = tmp_path / "sleeping_pi_consumer_close_rpc.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import json
            import signal
            import sys
            import time

            def on_term(signum, frame):
                _ = signum, frame
                with open({str(marker)!r}, "w", encoding="utf-8") as marker:
                    marker.write("terminated")
                sys.exit(0)

            signal.signal(signal.SIGTERM, on_term)
            print(json.dumps({{
                "protocol": "opensquilla.agent_core.v1",
                "kind": "event",
                "type": "text.delta",
                "payload": {{"text": "streaming"}},
            }}), flush=True)
            time.sleep(30)
            """
        ).lstrip(),
        encoding="utf-8",
    )

    agent = build_agent_for_kernel(
        runtime_config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_command=f"{sys.executable} {script}",
            allow_test_pi_rpc_command=True,
        ),
        provider=object(),
        config=AgentConfig(model_id="pi-consumer-close"),
        tool_definitions=[],
        tool_handler=None,
        usage_tracker=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        session_flush_service=None,
        tool_registry=None,
        tool_context=None,
    )

    stream = agent.run_turn("hello")
    first = await stream.__anext__()
    await stream.aclose()

    assert first == TextDeltaEvent(text="streaming")
    assert marker.read_text(encoding="utf-8") == "terminated"
