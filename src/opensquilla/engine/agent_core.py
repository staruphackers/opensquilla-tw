"""Selectable agent-kernel boundary for OpenSquilla runtime.

The public runtime contract remains ``AgentEvent``. Kernel-specific event
protocols, including Pi RPC events, must be normalized before they reach
``StreamConsumerStage``.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import copy
import hashlib
import inspect
import json
import math
import os
import shlex
from collections.abc import AsyncIterable, AsyncIterator, Iterable, Sequence
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, cast, runtime_checkable
from urllib.parse import unquote

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
    ThinkingEvent,
    ToolCall,
    ToolResult,
    ToolResultEvent,
    ToolUseEndEvent,
    ToolUseStartEvent,
    WarningEvent,
)
from opensquilla.engine.usage import SessionTotalsSnapshot

AgentKernelId = Literal["opensquilla", "pi"]
DEFAULT_AGENT_KERNEL: AgentKernelId = "opensquilla"
SUPPORTED_AGENT_KERNELS: frozenset[str] = frozenset({"opensquilla", "pi"})
AGENT_CORE_PROTOCOL_VERSION = "opensquilla.agent_core.v1"
PI_QUEUE_POLL_MAX_TIMEOUT_SECONDS = 5.0
PI_YIELD_REQUEST_MAX_TIMEOUT_SECONDS = 300.0
PI_SIDECAR_STDERR_CAPTURE_BYTES = 64 * 1024


def pi_sidecar_bridge_path() -> Path:
    """Return the packaged OpenSquilla Pi sidecar bridge entrypoint."""

    return Path(__file__).with_name("pi_sidecar_bridge.mjs").resolve()


def pi_sidecar_bridge_command(*, node_executable: str = "node") -> str:
    """Build a JSONL command for the packaged Pi sidecar bridge.

    The command only points at OpenSquilla's protocol bridge. Production callers
    still need upstream Pi/runtime provenance in AgentCoreConfig.
    """

    if not isinstance(node_executable, str) or not node_executable.strip():
        raise ValueError("node_executable must be a non-empty string")
    return shlex.join([node_executable, str(pi_sidecar_bridge_path())])


_TEST_FIXTURE_PI_RPC_COMMAND_MARKERS = (
    "fake_pi",
    "fake-pi",
    "fakepi",
    "fake_sidecar",
    "fake-sidecar",
    "mock_pi",
    "mock-pi",
    "mock_sidecar",
    "mock-sidecar",
    "dummy_pi",
    "dummy-pi",
    "pi_dummy",
    "pi-dummy",
    "dummy_sidecar",
    "dummy-sidecar",
    "stub_pi",
    "stub-pi",
    "pi_stub",
    "pi-stub",
    "stub_sidecar",
    "stub-sidecar",
    "fixture_pi",
    "fixture-pi",
    "pi_fixture",
    "pi-fixture",
    "fixture_sidecar",
    "fixture-sidecar",
    "test_pi",
    "test-pi",
    "test_sidecar",
    "test-sidecar",
    "test_fixture",
    "test-fixture",
    "test_agent_core",
    "contract_test",
    "contract-test",
    "example_pi",
    "example-pi",
    "example_sidecar",
    "example-sidecar",
    "sample_pi",
    "sample-pi",
    "sample_sidecar",
    "sample-sidecar",
    "demo_pi",
    "demo-pi",
    "demo_sidecar",
    "demo-sidecar",
    "examples/",
    "examples\\",
    "/examples/",
    "\\examples\\",
    "-m examples.",
    "samples/",
    "samples\\",
    "/samples/",
    "\\samples\\",
    "-m samples.",
    "demos/",
    "demos\\",
    "/demos/",
    "\\demos\\",
    "-m demos.",
    "tests/",
    "tests\\",
    "/tests/",
    "\\tests\\",
    "-m tests.",
)
_TEST_FIXTURE_PI_RPC_CLIENT_MARKERS = (
    "fake",
    "mock",
    "dummy",
    "stub",
    "fixture",
    "test",
    "example",
    "sample",
    "demo",
)
_TEST_FIXTURE_PI_RPC_PROVENANCE_MARKERS = (
    "fake",
    "mock",
    "dummy",
    "stub",
    "fixture",
    "test fixture",
    "test-only",
    "contract test",
    "contract-test",
    "example",
    "sample",
    "demo",
)
_PI_LOOP_REWRITE_PROVENANCE_MARKERS = (
    "preparenextturn",
    "safepointqueue",
    "beforetoolcall",
    "aftertoolcall",
    "beforeaftertoolhook",
    "beforetoolhook",
    "aftertoolhook",
    "nothrowstream",
    "shouldstopafterturn",
    "paralleltoolexecution",
    "paralleltoolcalls",
    "getsteeringmessages",
    "getfollowupmessages",
    "steeringfollowupqueue",
    "steeringqueue",
    "followupqueue",
    "toolscheduling",
    "toolscheduler",
    "agentlooplogic",
    "piagentloop",
    "sessionlifecycle",
)
_PI_LOOP_REWRITE_PROVENANCE_PHRASES = (
    ("reimplement", "loop"),
    ("reimplements", "loop"),
    ("rewrites", "loop"),
    ("contains", "loop"),
    ("implements", "loop"),
    ("reimplement", "tool scheduling"),
    ("reimplements", "tool scheduling"),
    ("rewrites", "tool scheduling"),
    ("implements", "tool scheduling"),
    ("reimplement", "tool invocation scheduling"),
    ("reimplements", "tool invocation scheduling"),
    ("rewrites", "tool invocation scheduling"),
    ("implements", "tool invocation scheduling"),
    ("parallel", "tool invocation scheduling"),
    ("reimplement", "parallel tool execution"),
    ("reimplements", "parallel tool execution"),
    ("rewrites", "parallel tool execution"),
    ("implements", "parallel tool execution"),
    ("reimplement", "steering", "queue"),
    ("reimplements", "steering", "queue"),
    ("rewrites", "steering", "queue"),
    ("implements", "steering", "queue"),
    ("reimplement", "follow-up", "queue"),
    ("reimplements", "follow-up", "queue"),
    ("rewrites", "follow-up", "queue"),
    ("implements", "follow-up", "queue"),
    ("reimplement", "session lifecycle"),
    ("reimplements", "session lifecycle"),
    ("rewrites", "session lifecycle"),
    ("implements", "session lifecycle"),
)
_UPSTREAM_PI_RPC_COMMAND_MARKERS = (
    "@earendil-works/pi-agent-core",
    "@earendil-works/pi-coding-agent",
    "pi-ai",
    "pi-agent-core",
    "pi-coding-agent",
    "pi-tui",
    "profile-coding-agent-node",
    "profile-coding-agent-node.mjs",
)
_UPSTREAM_PI_PACKAGE_NAMESPACE_PREFIX = "@earendil-works/pi-"
_UPSTREAM_PI_REPO_SOURCE_PATH_SEGMENTS = (
    "/packages/agent/",
    "/packages/ai/",
    "/packages/coding-agent/",
    "/packages/tui/",
)
_NATIVE_PI_PACKAGE_RUNNER_COMMANDS = frozenset({"npx", "npm", "pnpm", "yarn", "bunx", "bun"})
_COREPACK_PACKAGE_MANAGER_COMMANDS = frozenset({"npm", "npx", "pnpm", "yarn"})
_NATIVE_PI_SCRIPT_INTERPRETER_COMMANDS = frozenset({"node", "nodejs"})
_NATIVE_PI_SOURCE_EXECUTOR_COMMANDS = frozenset(
    {"tsx", "ts-node", "ts-node-esm", "jiti", "esno"}
)
_NATIVE_PI_SHELL_COMMANDS = frozenset(
    {
        "bash",
        "cmd",
        "cmd.exe",
        "csh",
        "dash",
        "fish",
        "ksh",
        "powershell",
        "powershell.exe",
        "pwsh",
        "pwsh.exe",
        "sh",
        "tcsh",
        "zsh",
    }
)
_PROCESS_LAUNCH_WRAPPER_COMMANDS = frozenset(
    {"nice", "nohup", "setsid", "stdbuf"}
)
_WINDOWS_COMMAND_SUFFIXES = (".exe", ".cmd", ".bat", ".ps1")
_SHELL_COMMAND_PREFIXES = frozenset({"command", "exec"})
_SHELL_CONTROL_CHARACTERS = frozenset(";&|()")
_NODE_OPTIONS_WITH_VALUE = frozenset(
    {"--experimental-loader", "--import", "--loader", "--require", "-r"}
)
_NODE_INLINE_CODE_OPTIONS_WITH_VALUE = frozenset({"--eval", "--print", "-e", "-p"})
_PACKAGE_RUNNER_OPTIONS_WITH_VALUE = frozenset({"--package", "-p"})
_PACKAGE_RUNNER_SHELL_OPTIONS_WITH_VALUE = frozenset({"--call", "-c"})
_PACKAGE_RUNNER_SUBCOMMANDS_WITH_PACKAGE_TARGET = frozenset(
    {"create", "dlx", "exec", "init", "x"}
)
_PACKAGE_RUNNER_SCRIPT_SUBCOMMANDS = frozenset({"run", "run-script"})
_SIDECAR_COMMAND_VALUE_OPTIONS_WITH_VALUE = frozenset(
    {
        "--cmd",
        "--command",
        "--exec",
        "--execute",
        "--program",
        "--runtime-cmd",
        "--runtimecmd",
        "--runtime_cmd",
        "--runtime-command",
        "--runtime_command",
        "--runtimecommand",
        "--agent-command",
        "--agent-cmd",
        "--agent_command",
        "--agentcommand",
        "--agent_cmd",
        "--agentcmd",
        "--spawn",
        "--spawn-command",
        "--spawn-cmd",
        "--spawn_command",
        "--spawncommand",
        "--spawn_cmd",
        "--spawncmd",
    }
)
_SIDECAR_RUNTIME_REFERENCE_OPTIONS_WITH_VALUE = frozenset(
    {
        "--agent-runtime",
        "--agent_runtime",
        "--agentruntime",
        "--pi-runtime",
        "--pi_runtime",
        "--piruntime",
        "--runtime",
        "--runtime-package",
        "--runtime_package",
        "--runtimepackage",
    }
)
_SIDECAR_MODULE_ROOT_OPTIONS_WITH_VALUE = frozenset(
    {"--module-root", "--module_root", "--moduleroot"}
)
_SIDECAR_COMMAND_VALUE_ENV_NAME_PARTS = frozenset(
    {"cmd", "command", "exec", "execute", "program", "spawn"}
)
_SIDECAR_MODE_ENV_NAME_PARTS = frozenset({"mode"})
_SIDECAR_RUNTIME_REFERENCE_ENV_NAME_PARTS = frozenset({"runtime"})
_ENV_OPTIONS_WITH_VALUE = frozenset(
    {"--unset", "-u", "--chdir", "-c", "--split-string", "-s"}
)
_SHELL_STARTUP_ENV_VARS = frozenset({"bash_env", "env", "zdotdir"})
_TIMEOUT_OPTIONS_WITH_VALUE = frozenset({"--kill-after", "-k", "--signal", "-s"})
_NICE_OPTIONS_WITH_VALUE = frozenset({"--adjustment", "-n"})
_STDBUF_OPTIONS_WITH_VALUE = frozenset({"--input", "--output", "--error", "-i", "-o", "-e"})
_COREPACK_OPTIONS_WITH_VALUE = frozenset({"--install-directory", "--cache-directory"})
_UPSTREAM_PI_PROVENANCE_PACKAGE_MARKERS = (
    "@earendil-works/pi-agent-core",
    "@earendil-works/pi-coding-agent",
    "@earendil-works/pi-ai",
    "@earendil-works/pi-tui",
    "@mariozechner/pi-agent-core",
    "@mariozechner/pi-coding-agent",
    "@mariozechner/pi-ai",
    "@mariozechner/pi-tui",
)
_UPSTREAM_PI_REPO_PROVENANCE_MARKERS = (
    "github.com/earendil-works/pi",
    "github.com/badlogic/pi-mono",
)
_UPSTREAM_PI_PROVENANCE_MARKERS = (
    *_UPSTREAM_PI_PROVENANCE_PACKAGE_MARKERS,
    *_UPSTREAM_PI_REPO_PROVENANCE_MARKERS,
)
_UPSTREAM_PI_RPC_CLIENT_IDENTITY_MARKERS = (
    "pi_agent_core",
    "piagentcore",
    "pi_coding_agent",
    "picodingagent",
)
_AGENT_CORE_SIDECAR_PROVENANCE_MARKERS = (
    AGENT_CORE_PROTOCOL_VERSION,
    "opensquilla agent-core",
    "opensquilla-agent-core",
)
_PI_SIDECAR_LAUNCH_ENV_ALLOWLIST = frozenset(
    {
        "COMSPEC",
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "TMPDIR",
    }
)
_HOST_OWNED_PI_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "agent_start",
        "agent_end",
        "artifact",
        "auto_retry_end",
        "auto_retry_start",
        "compaction",
        "compaction_end",
        "compaction_start",
        "done",
        "message_end",
        "message_start",
        "message_update",
        "provider.done",
        "provider.request",
        "provider_done",
        "provider_request",
        "queue_update",
        "queue.poll",
        "router_control_replay",
        "router_decision",
        "run_heartbeat",
        "session.write",
        "session.write.enqueue",
        "savepoint.request",
        "state_change",
        "text_delta",
        "telemetry.emit",
        "tool.call.execute",
        "tool.call.prepare",
        "thinking",
        "tool.result",
        "tool_result",
        "tool_use_delta",
        "tool_use_end",
        "tool_use_start",
        "tool_execution_end",
        "tool_execution_start",
        "tool_execution_update",
        "turn_start",
        "turn_end",
        "warning",
        "yield",
        "yield.request",
    }
)
_PI_INTENT_PORTS: dict[str, str] = {
    "provider.request": "provider",
    "tool.call.prepare": "tool_bridge",
    "tool.call.execute": "tool_bridge",
    "session.write.enqueue": "session_writes",
    "queue.poll": "queue",
    "savepoint.request": "savepoints",
    "yield.request": "orchestration",
    "telemetry.emit": "telemetry",
}
_PI_SESSION_SCOPED_INTENT_MESSAGES: dict[str, str] = {
    "provider.request": "Pi sidecar provider.request cannot target a different session_key",
    "tool.call.prepare": "Pi sidecar tool intent cannot target a different session_key",
    "tool.call.execute": "Pi sidecar tool intent cannot target a different session_key",
    "session.write.enqueue": (
        "Pi sidecar session.write.enqueue cannot target a different session_key"
    ),
    "queue.poll": "Pi sidecar queue.poll cannot target a different session_key",
    "savepoint.request": (
        "Pi sidecar savepoint.request cannot target a different session_key"
    ),
    "yield.request": "Pi sidecar yield.request cannot target a different session_key",
    "telemetry.emit": "Pi sidecar telemetry.emit cannot target a different session_key",
}
_PI_NON_TERMINAL_PORTS: frozenset[str] = frozenset(
    {
        "tool_bridge",
        "session_writes",
        "queue",
        "savepoints",
        "orchestration",
        "telemetry",
    }
)
_PI_SIDECAR_FRAME_KEYS: frozenset[str] = frozenset(
    {"protocol", "kind", "type", "payload"}
)
_PI_EVENT_PAYLOAD_KEYS: dict[str, frozenset[str]] = {
    "text.delta": frozenset({"text"}),
    "error": frozenset({"message", "code"}),
}
_PI_PROVIDER_REQUEST_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "session_key",
        "messages",
        "prompt",
        "message",
        "tools",
        "config",
    }
)
_HOST_PROVIDER_REQUEST_INTERNAL_KEYS: frozenset[str] = frozenset(
    {
        "_host_request_context_prompt",
        "_host_runtime_context",
        "_host_runtime_context_chars",
        "_host_runtime_context_hash",
        "_host_turn_input",
    }
)
_PI_TOOL_INTENT_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "session_key",
        "tool_call_id",
        "toolCallId",
        "id",
        "tool_name",
        "name",
        "arguments",
        "input",
        "synthetic_from_text",
        "origin_trace",
    }
)
_PI_SESSION_WRITE_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "session_key",
        "role",
        "content",
        "reasoning_content",
        "tool_calls",
        "turn_usage",
        "token_count",
    }
)
_PI_QUEUE_POLL_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "session_key",
        "task_id",
        "operation",
        "action",
        "timeout_seconds",
    }
)
_PI_SAVEPOINT_REQUEST_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "session_key",
        "transcript",
        "turn_id",
        "source",
    }
)
_PI_YIELD_REQUEST_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "session_key",
        "message",
        "reason",
        "timeout_seconds",
        "tool_call_id",
    }
)
_PI_INTENT_PAYLOAD_KEYS: dict[str, frozenset[str]] = {
    "provider.request": _PI_PROVIDER_REQUEST_PAYLOAD_KEYS,
    "tool.call.prepare": _PI_TOOL_INTENT_PAYLOAD_KEYS,
    "tool.call.execute": _PI_TOOL_INTENT_PAYLOAD_KEYS,
    "session.write.enqueue": _PI_SESSION_WRITE_PAYLOAD_KEYS,
    "queue.poll": _PI_QUEUE_POLL_PAYLOAD_KEYS,
    "savepoint.request": _PI_SAVEPOINT_REQUEST_PAYLOAD_KEYS,
    "yield.request": _PI_YIELD_REQUEST_PAYLOAD_KEYS,
}
_PI_INTENT_PAYLOAD_ERROR_LABELS: dict[str, str] = {
    "tool.call.prepare": "tool intent",
    "tool.call.execute": "tool intent",
}
_SESSION_WRITE_TURN_USAGE_INT_FIELDS: frozenset[str] = frozenset(
    {
        "input_tokens",
        "total_tokens",
        "output_tokens",
        "reasoning_tokens",
        "cached_tokens",
        "cache_write_tokens",
        "iterations",
        "runtime_context_chars",
    }
)
_SESSION_WRITE_TURN_USAGE_COST_FIELDS: frozenset[str] = frozenset(
    {
        "cost_usd",
        "billed_cost",
        "savings_pct",
        "savings_usd",
        "total_savings_pct",
        "total_savings_usd",
    }
)
_SESSION_WRITE_TURN_USAGE_PROBABILITY_FIELDS: frozenset[str] = frozenset(
    {
        "cache_hit_rate",
        "kv_cache_hit_rate",
        "routing_confidence",
    }
)
_SESSION_WRITE_TURN_USAGE_STRING_FIELDS: frozenset[str] = frozenset(
    {
        "cost_source",
        "model",
        "routed_model",
        "routing_source",
        "rollout_phase",
        "baseline_model",
    }
)
_SESSION_WRITE_TURN_USAGE_OPTIONAL_STRING_FIELDS: frozenset[str] = frozenset(
    {
        "routed_tier",
        "runtime_context_hash",
        "reasoning_content",
    }
)
_SESSION_WRITE_TURN_USAGE_BOOLEAN_FIELDS: frozenset[str] = frozenset(
    {
        "cache_hit_active",
        "routing_applied",
    }
)
_AGENT_EVENT_TYPES = (
    ThinkingEvent,
    TextDeltaEvent,
    RunHeartbeatEvent,
    ToolUseStartEvent,
    ToolUseEndEvent,
    ToolResultEvent,
    RouterControlReplayEvent,
    ArtifactEvent,
    StateChangeEvent,
    ErrorEvent,
    DoneEvent,
    CompactionEvent,
    WarningEvent,
    RouterDecisionEvent,
)
_AGENT_EVENT_KINDS = frozenset(
    {
        "artifact",
        "compaction",
        "done",
        "error",
        "router_control_replay",
        "router_decision",
        "run_heartbeat",
        "state_change",
        "text_delta",
        "thinking",
        "tool_result",
        "tool_use_delta",
        "tool_use_end",
        "tool_use_start",
        "warning",
    }
)
_HOST_RUNTIME_POLICY_SNAPSHOT_FIELDS = (
    "flush_enabled",
    "flush_triggers",
    "flush_pre_compaction",
    "flush_timeout_seconds",
    "flush_compaction_requires_safe_receipt",
    "flush_compaction_safety_mode",
    "compaction_profile",
    "compaction_protected_recent_messages",
)


@dataclass(frozen=True)
class AgentCoreConfig:
    """Configuration for the selectable agent-kernel boundary."""

    kernel: AgentKernelId = DEFAULT_AGENT_KERNEL
    protocol_version: str = AGENT_CORE_PROTOCOL_VERSION
    pi_rpc_client: Any | None = None
    pi_rpc_client_provenance: str | None = None
    pi_rpc_command: str | None = None
    pi_rpc_command_provenance: str | None = None
    allow_test_pi_rpc_client: bool = False
    allow_test_pi_rpc_command: bool = False
    strict_host_provider: bool = True
    strict_host_tools: bool = True
    strict_host_sessions: bool = True
    strict_host_orchestration: bool = True
    strict_host_finalizer: bool = True

    @classmethod
    def from_runtime_config(cls, runtime_config: Any | None) -> AgentCoreConfig:
        agent_core = (
            getattr(runtime_config, "agent_core", None) if runtime_config is not None else None
        )
        kernel = resolve_agent_kernel_id(None, config=runtime_config)
        protocol_version = _string_config_value(
            _first_config_value(
                runtime_config,
                agent_core,
                "agent_core_protocol_version",
                "protocol_version",
                default=AGENT_CORE_PROTOCOL_VERSION,
            ),
            field_name="agent_core_protocol_version",
        )
        return cls(
            kernel=kernel,
            protocol_version=protocol_version or AGENT_CORE_PROTOCOL_VERSION,
            pi_rpc_client=_first_config_value(
                runtime_config,
                agent_core,
                "pi_agent_rpc_client",
                "pi_rpc_client",
            ),
            pi_rpc_client_provenance=_string_config_value(
                _first_config_value(
                    runtime_config,
                    agent_core,
                    "pi_agent_rpc_client_provenance",
                    "pi_rpc_client_provenance",
                ),
                field_name="pi_rpc_client_provenance",
            ),
            pi_rpc_command=_string_config_value(
                _first_config_value(
                    runtime_config,
                    agent_core,
                    "pi_agent_rpc_command",
                    "pi_rpc_command",
                ),
                field_name="pi_rpc_command",
            ),
            pi_rpc_command_provenance=_string_config_value(
                _first_config_value(
                    runtime_config,
                    agent_core,
                    "pi_agent_rpc_command_provenance",
                    "pi_rpc_command_provenance",
                ),
                field_name="pi_rpc_command_provenance",
            ),
            allow_test_pi_rpc_client=_bool_config_value(
                _first_config_value(
                    runtime_config,
                    agent_core,
                    "allow_test_pi_rpc_client",
                    "_allow_test_pi_rpc_client",
                    default=False,
                ),
                field_name="allow_test_pi_rpc_client",
            ),
            allow_test_pi_rpc_command=_bool_config_value(
                _first_config_value(
                    runtime_config,
                    agent_core,
                    "allow_test_pi_rpc_command",
                    "_allow_test_pi_rpc_command",
                    default=False,
                ),
                field_name="allow_test_pi_rpc_command",
            ),
            strict_host_provider=_bool_config_value(
                _first_config_value(
                    runtime_config,
                    agent_core,
                    "strict_host_provider",
                    default=True,
                ),
                field_name="strict_host_provider",
            ),
            strict_host_tools=_bool_config_value(
                _first_config_value(
                    runtime_config,
                    agent_core,
                    "strict_host_tools",
                    default=True,
                ),
                field_name="strict_host_tools",
            ),
            strict_host_sessions=_bool_config_value(
                _first_config_value(
                    runtime_config,
                    agent_core,
                    "strict_host_sessions",
                    default=True,
                ),
                field_name="strict_host_sessions",
            ),
            strict_host_orchestration=_bool_config_value(
                _first_config_value(
                    runtime_config,
                    agent_core,
                    "strict_host_orchestration",
                    default=True,
                ),
                field_name="strict_host_orchestration",
            ),
            strict_host_finalizer=_bool_config_value(
                _first_config_value(
                    runtime_config,
                    agent_core,
                    "strict_host_finalizer",
                    default=True,
                ),
                field_name="strict_host_finalizer",
            ),
        )


@dataclass(frozen=True)
class KernelTurnSnapshot:
    """Host-owned turn input snapshot passed into a kernel runtime."""

    session_key: str
    agent_id: str
    turn_id: str
    turn_input: str
    system_prompt: str
    request_context_prompt: str
    model_id: str
    session_id: str | None = None
    tool_definitions: list[Any] = field(default_factory=list)
    extra_messages: list[Any] | None = None
    semantic_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.session_key, str):
            raise RuntimeError("KernelTurnSnapshot session_key must be a string")
        if not self.session_key.strip():
            raise RuntimeError("KernelTurnSnapshot session_key must be non-empty")
        if self.session_id is None:
            object.__setattr__(self, "session_id", self.session_key)
        for field_name in ("agent_id", "turn_id", "session_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise RuntimeError(
                    f"KernelTurnSnapshot {field_name} must be a string"
                )
            if not value.strip():
                raise RuntimeError(
                    f"KernelTurnSnapshot {field_name} must be non-empty"
                )
        for field_name in (
            "turn_input",
            "system_prompt",
            "request_context_prompt",
            "model_id",
        ):
            if not isinstance(getattr(self, field_name), str):
                raise RuntimeError(
                    f"KernelTurnSnapshot {field_name} must be a string"
                )
        if not isinstance(self.tool_definitions, list):
            raise RuntimeError("KernelTurnSnapshot tool_definitions must be a list")
        if self.extra_messages is not None and not isinstance(self.extra_messages, list):
            raise RuntimeError(
                "KernelTurnSnapshot extra_messages must be a list or None"
            )
        if self.semantic_message is not None and not isinstance(
            self.semantic_message, str
        ):
            raise RuntimeError(
                "KernelTurnSnapshot semantic_message must be a string or None"
            )
        if not isinstance(self.metadata, dict):
            raise RuntimeError("KernelTurnSnapshot metadata must be an object")
        for field_name in ("tool_definitions", "extra_messages", "metadata"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _json_safe_value(value))
        if "cache_hit_rate" in self.metadata:
            cache_hit_rate = _finite_number(
                self.metadata["cache_hit_rate"],
                field_name="KernelTurnSnapshot metadata cache_hit_rate",
            )
            if cache_hit_rate < 0.0 or cache_hit_rate > 1.0:
                raise RuntimeError(
                    "KernelTurnSnapshot metadata cache_hit_rate must be a probability"
                )


@dataclass
class KernelHostPorts:
    """OpenSquilla-owned side-effect ports available to foreign kernels."""

    provider: Any | None = None
    tool_bridge: Any | None = None
    session_writes: Any | None = None
    queue: Any | None = None
    savepoints: Any | None = None
    orchestration: Any | None = None
    finalizer: Any | None = None
    telemetry: Any | None = None


@dataclass
class _PiCheckpointTranscriptEntry:
    """Attribute-shaped checkpoint entry built from Pi JSON transcript data."""

    role: Any = ""
    content: Any = None
    tool_calls: Any = None
    tool_call_id: Any = None
    reasoning_content: Any = None
    token_count: Any = None


@dataclass(frozen=True)
class _ProviderIdentityForHistory:
    """Read-only provider identity exposed for host history/context selection."""

    provider_name: str = ""
    provider_kind: str = ""


def _provider_usage_int(provider_done: Any, field_name: str) -> int:
    value = getattr(provider_done, field_name, 0)
    if value is None:
        raise RuntimeError(f"provider usage {field_name} must be an integer")
    if not isinstance(value, int) or isinstance(value, bool):
        raise RuntimeError(f"provider usage {field_name} must be an integer")
    if value < 0:
        raise RuntimeError(
            f"provider usage {field_name} must be a non-negative integer"
        )
    return value


def _provider_usage_int_less_than_or_equal(
    provider_done: Any,
    field_name: str,
    maximum: int,
    maximum_field_name: str,
) -> int:
    value = _provider_usage_int(provider_done, field_name)
    if value > maximum:
        raise RuntimeError(
            f"provider usage {field_name} must be <= {maximum_field_name}"
        )
    return value


def _finite_number(value: Any, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(f"{field_name} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise RuntimeError(f"{field_name} must be finite")
    return result


def _provider_usage_float(provider_done: Any, field_name: str) -> float:
    value = getattr(provider_done, field_name, 0.0)
    if value is None:
        raise RuntimeError(f"provider usage {field_name} must be a number")
    result = _finite_number(value, field_name=f"provider usage {field_name}")
    if result < 0:
        raise RuntimeError(f"provider usage {field_name} must be a non-negative number")
    return result


def _provider_usage_string(
    provider_done: Any,
    field_name: str,
    default: str = "",
    *,
    allow_none: bool = False,
) -> str:
    value = getattr(provider_done, field_name, default)
    if value is None:
        if allow_none:
            return default
        raise RuntimeError(f"provider usage {field_name} must be a string")
    if value == "":
        return default
    if not isinstance(value, str):
        raise RuntimeError(f"provider usage {field_name} must be a string")
    return value


def _config_string_or_empty(config: Any, field_name: str, *, owner: str) -> str:
    value = getattr(config, field_name, None)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise RuntimeError(f"{owner} {field_name} must be a string")
    return value


def _provider_public_string(raw_event: Any, event_name: str, field_name: str) -> str:
    value = getattr(raw_event, field_name, "")
    if not isinstance(value, str):
        raise RuntimeError(f"provider {event_name} {field_name} must be a string")
    return value


def _provider_tool_use_string(raw_event: Any, event_name: str, field_name: str) -> str:
    value = getattr(raw_event, field_name, "")
    if not isinstance(value, str):
        raise RuntimeError(
            f"provider tool-use {event_name} {field_name} must be a string"
        )
    if field_name in {"tool_use_id", "tool_name"} and not value.strip():
        raise RuntimeError(
            f"provider tool-use {event_name} {field_name} "
            "must be a non-empty string"
        )
    return value


def _provider_tool_use_bool(raw_event: Any, event_name: str, field_name: str) -> bool:
    value = getattr(raw_event, field_name, False)
    if not isinstance(value, bool):
        raise RuntimeError(
            f"provider tool-use {event_name} {field_name} must be a boolean"
        )
    return value


@dataclass
class _ProviderUsageAccumulator:
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cached_tokens: int = 0
    cache_write_tokens: int = 0
    billed_cost: float = 0.0
    provider_done_count: int = 0
    cost_source: str = "none"
    model: str = ""
    reasoning_parts: list[str] = field(default_factory=list)

    def record(self, provider_done: Any) -> None:
        input_tokens = _provider_usage_int(provider_done, "input_tokens")
        cached_tokens = _provider_usage_int_less_than_or_equal(
            provider_done,
            "cached_tokens",
            input_tokens,
            "input_tokens",
        )
        cache_write_tokens = _provider_usage_int_less_than_or_equal(
            provider_done,
            "cache_write_tokens",
            input_tokens,
            "input_tokens",
        )
        self.input_tokens += input_tokens
        self.output_tokens += _provider_usage_int(provider_done, "output_tokens")
        self.reasoning_tokens += _provider_usage_int(provider_done, "reasoning_tokens")
        self.cached_tokens += cached_tokens
        self.cache_write_tokens += cache_write_tokens
        self.billed_cost += _provider_usage_float(provider_done, "billed_cost")
        self.provider_done_count += 1
        cost_source = _provider_usage_string(provider_done, "cost_source", "none")
        if cost_source != "none":
            self.cost_source = cost_source
        model = _provider_usage_string(provider_done, "model")
        if model:
            self.model = model
        reasoning_content = _provider_usage_string(
            provider_done,
            "reasoning_content",
            allow_none=True,
        )
        if reasoning_content:
            self.reasoning_parts.append(reasoning_content)

    def drain(self) -> dict[str, Any]:
        snapshot = {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "cached_tokens": self.cached_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "billed_cost": self.billed_cost,
            "provider_done_count": self.provider_done_count,
            "cost_source": self.cost_source,
            "model": self.model,
            "reasoning_content": (
                "\n".join(self.reasoning_parts) if self.reasoning_parts else None
            ),
        }
        self.input_tokens = 0
        self.output_tokens = 0
        self.reasoning_tokens = 0
        self.cached_tokens = 0
        self.cache_write_tokens = 0
        self.billed_cost = 0.0
        self.provider_done_count = 0
        self.cost_source = "none"
        self.model = ""
        self.reasoning_parts.clear()
        return snapshot

    def reset(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.reasoning_tokens = 0
        self.cached_tokens = 0
        self.cache_write_tokens = 0
        self.billed_cost = 0.0
        self.provider_done_count = 0
        self.cost_source = "none"
        self.model = ""
        self.reasoning_parts.clear()


class KernelRuntime(Protocol):
    """Common runtime shape consumed below ``TurnRunner``."""

    def set_history(self, history: list[Any]) -> None: ...

    def refresh_system_prompt(self, system_prompt: str) -> None: ...

    def run_turn(
        self,
        turn_input: str,
        *,
        extra_messages: list[Any] | None = None,
        semantic_message: str | None = None,
    ) -> AsyncIterator[AgentEvent]: ...


class OpenSquillaPythonKernelRuntime:
    """Delegating wrapper for the existing Python ``Agent`` kernel."""

    def __init__(self, agent: Any) -> None:
        self._agent = agent
        # Compatibility surface for existing Python-agent callers. The
        # KernelRuntime protocol itself does not require foreign kernels to
        # expose Python Agent configuration.
        self.config = getattr(agent, "config", None)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._agent, name)

    def refresh_system_prompt(self, system_prompt: str) -> None:
        return self._agent.refresh_system_prompt(system_prompt)

    def set_history(self, history: list[Any]) -> None:
        return self._agent.set_history(history)

    def run_turn(
        self,
        turn_input: str,
        *,
        extra_messages: list[Any] | None = None,
        semantic_message: str | None = None,
    ) -> AsyncIterator[AgentEvent]:
        return self._agent.run_turn(
            turn_input,
            extra_messages=extra_messages,
            semantic_message=semantic_message,
        )


@runtime_checkable
class PiRpcClient(Protocol):
    """Minimal Pi RPC stream client consumed by ``PiAgentRuntimeAdapter``."""

    def stream_prompt(
        self,
        message: str,
        **kwargs: Any,
    ) -> AsyncIterator[dict[str, Any]]: ...


def _pi_sidecar_launch_env() -> dict[str, str]:
    env = {
        name: value
        for name, value in os.environ.items()
        if name in _PI_SIDECAR_LAUNCH_ENV_ALLOWLIST
    }
    env["OPENSQUILLA_AGENT_CORE_PROTOCOL"] = AGENT_CORE_PROTOCOL_VERSION
    return env


def _json_loads_sidecar_stdout_frame(line: str) -> dict[str, Any]:
    def _reject_duplicate_pairs(pairs: list[tuple[Any, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON object key {key!r}")
            result[key] = value
        return result

    def _reject_non_finite_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON value {value}")

    try:
        payload = json.loads(
            line,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_non_finite_constant,
        )
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Pi RPC command emitted invalid JSONL: {line}") from exc
    except ValueError as exc:
        raise RuntimeError(f"Pi RPC command emitted invalid JSONL: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Pi RPC command emitted non-object JSONL: {line}")
    return cast(dict[str, Any], payload)


async def _drain_pi_sidecar_stderr(stderr: asyncio.StreamReader | None) -> bytes:
    if stderr is None:
        return b""
    chunks: list[bytes] = []
    captured = 0
    total = 0
    while True:
        chunk = await stderr.read(4096)
        if not chunk:
            break
        total += len(chunk)
        if captured >= PI_SIDECAR_STDERR_CAPTURE_BYTES:
            continue
        keep = chunk[: PI_SIDECAR_STDERR_CAPTURE_BYTES - captured]
        chunks.append(keep)
        captured += len(keep)
    if total > PI_SIDECAR_STDERR_CAPTURE_BYTES:
        chunks.append(b"\n[stderr truncated]")
    return b"".join(chunks)


class PiJsonlCommandRpcClient:
    """Run a Pi-compatible command that streams one JSON event per stdout line."""

    def __init__(self, command: str) -> None:
        self._command = command
        self._argv = shlex.split(command)
        if not self._argv:
            raise ValueError("pi_agent_rpc_command must not be empty")
        self._active_stream = False
        self._active_stdin: asyncio.StreamWriter | None = None

    def stream_prompt(
        self,
        message: str,
        **kwargs: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        return self._stream_prompt(message, **kwargs)

    async def _stream_prompt(
        self,
        message: str,
        **kwargs: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        if self._active_stream:
            raise RuntimeError(
                "Pi RPC command client already has an active stream; "
                "create a separate client per concurrent Pi sidecar stream"
            )
        if not isinstance(message, str):
            raise RuntimeError("Pi RPC command turn_start prompt must be a string")
        if not message.strip():
            raise RuntimeError("Pi RPC command turn_start prompt must be non-empty")
        for field_name in ("session_key", "session_id"):
            if field_name not in kwargs:
                continue
            value = kwargs[field_name]
            if not isinstance(value, str):
                raise RuntimeError(
                    f"Pi RPC command turn_start {field_name} must be a string"
                )
            if not value.strip():
                raise RuntimeError(
                    f"Pi RPC command turn_start {field_name} must be non-empty"
                )
        safe_kwargs = _json_safe_value(kwargs)
        turn_snapshot = safe_kwargs.get("turn_snapshot")
        if "turn_snapshot" in safe_kwargs and not isinstance(turn_snapshot, dict):
            raise RuntimeError("Pi RPC command turn_start turn_snapshot must be an object")
        if isinstance(turn_snapshot, dict):
            for field_name in ("session_key", "session_id"):
                if field_name not in turn_snapshot:
                    continue
                snapshot_value = turn_snapshot[field_name]
                if not isinstance(snapshot_value, str):
                    raise RuntimeError(
                        "Pi RPC command turn_start "
                        f"turn_snapshot.{field_name} must be a string"
                    )
                if not snapshot_value.strip():
                    raise RuntimeError(
                        "Pi RPC command turn_start "
                        f"turn_snapshot.{field_name} must be non-empty"
                    )
                if field_name not in safe_kwargs:
                    continue
                if snapshot_value != safe_kwargs[field_name]:
                    raise RuntimeError(
                        "Pi RPC command turn_start "
                        f"turn_snapshot.{field_name} must match {field_name}"
                    )
        self._active_stream = True
        process: Any | None = None
        stderr_task: asyncio.Task[bytes] | None = None
        completed = False
        try:
            env = _pi_sidecar_launch_env()
            process = await asyncio.create_subprocess_exec(
                *self._argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
                env=env,
            )
            if process.stdout is None:
                raise RuntimeError(f"Pi RPC command produced no stdout: {self._command}")
            if process.stdin is None:
                raise RuntimeError(f"Pi RPC command produced no stdin: {self._command}")

            stderr_task = asyncio.create_task(
                _drain_pi_sidecar_stderr(process.stderr)
            )
            self._active_stdin = process.stdin
            turn_start_frame = {
                "protocol": AGENT_CORE_PROTOCOL_VERSION,
                "kind": "turn_start",
                "payload": {
                    "prompt": message,
                    "kwargs": safe_kwargs,
                },
            }
            process.stdin.write(
                (_json_dumps_sidecar_frame(turn_start_frame) + "\n").encode("utf-8")
            )
            await process.stdin.drain()
            chunk_buffers: dict[str, dict[str, Any]] = {}

            def _string_chunk_field(
                frame: dict[str, Any],
                field_name: str,
            ) -> str:
                value = frame.get(field_name)
                if not isinstance(value, str) or not value:
                    raise RuntimeError(
                        "Pi RPC command emitted malformed chunked JSONL frame"
                    )
                return value

            def _int_chunk_field(frame: dict[str, Any], field_name: str) -> int:
                value = frame.get(field_name)
                if not isinstance(value, int):
                    raise RuntimeError(
                        "Pi RPC command emitted malformed chunked JSONL frame"
                    )
                return value

            def _maybe_reassemble_chunked_frame(
                frame: dict[str, Any],
            ) -> dict[str, Any] | None:
                if frame.get("kind") != "chunk":
                    return frame
                if frame.get("protocol") != AGENT_CORE_PROTOCOL_VERSION:
                    raise RuntimeError("Pi RPC command emitted chunk protocol mismatch")
                if frame.get("encoding") != "base64-json":
                    raise RuntimeError("Pi RPC command emitted unsupported chunk encoding")
                chunk_id = _string_chunk_field(frame, "chunk_id")
                index = _int_chunk_field(frame, "index")
                total = _int_chunk_field(frame, "total")
                if total < 1 or index < 0 or index >= total:
                    raise RuntimeError(
                        "Pi RPC command emitted malformed chunked JSONL frame"
                    )
                data = _string_chunk_field(frame, "data")
                chunk_state = chunk_buffers.setdefault(
                    chunk_id,
                    {"total": total, "parts": {}},
                )
                if chunk_state["total"] != total:
                    raise RuntimeError(
                        "Pi RPC command emitted inconsistent chunked JSONL frame"
                    )
                parts = cast(dict[int, str], chunk_state["parts"])
                if index in parts:
                    raise RuntimeError(
                        "Pi RPC command emitted duplicate chunked JSONL frame"
                    )
                parts[index] = data
                if len(parts) < total:
                    return None
                encoded = "".join(parts[position] for position in range(total))
                del chunk_buffers[chunk_id]
                try:
                    raw_payload = base64.b64decode(encoded.encode("ascii"), validate=True)
                except (UnicodeEncodeError, binascii.Error) as exc:
                    raise RuntimeError(
                        "Pi RPC command emitted invalid chunked JSONL payload"
                    ) from exc
                try:
                    reassembled_line = raw_payload.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise RuntimeError(
                        "Pi RPC command emitted invalid UTF-8 chunked JSONL payload"
                    ) from exc
                return _json_loads_sidecar_stdout_frame(reassembled_line)

            while True:
                try:
                    raw_line = await process.stdout.readline()
                except ValueError as exc:
                    raise RuntimeError(
                        "Pi RPC command emitted overlong JSONL frame"
                    ) from exc
                if not raw_line:
                    break
                try:
                    line = raw_line.decode("utf-8").strip()
                except UnicodeDecodeError as exc:
                    raise RuntimeError(
                        "Pi RPC command emitted invalid UTF-8 JSONL"
                    ) from exc
                if not line:
                    continue
                frame = _maybe_reassemble_chunked_frame(
                    _json_loads_sidecar_stdout_frame(line)
                )
                if frame is not None:
                    yield frame

            if chunk_buffers:
                raise RuntimeError(
                    "Pi RPC command ended with incomplete chunked JSONL frame"
                )

            return_code = await process.wait()
            stderr = await stderr_task if stderr_task is not None else b""
            completed = True
            if return_code != 0:
                stderr_text = stderr.decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"Pi RPC command failed code={return_code}: {stderr_text}"
                )
        finally:
            self._active_stream = False
            if process is not None:
                if self._active_stdin is process.stdin:
                    self._active_stdin = None
                if not completed and process.returncode is None:
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=1.0)
                    except TimeoutError:
                        process.kill()
                        await process.wait()
                if stderr_task is not None:
                    if not stderr_task.done() and process.returncode is None:
                        stderr_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await stderr_task
                if process.stdin is not None and not process.stdin.is_closing():
                    process.stdin.close()
                    with contextlib.suppress(Exception):
                        await process.stdin.wait_closed()

    async def receive_intent_result(
        self,
        *,
        intent_type: str,
        payload: dict[str, Any],
        events: list[Any],
        session_key: str,
    ) -> None:
        if not isinstance(intent_type, str):
            raise RuntimeError("Pi RPC command intent_result type must be a string")
        if not intent_type.strip():
            raise RuntimeError("Pi RPC command intent_result type must be non-empty")
        if intent_type not in _PI_INTENT_PORTS:
            raise RuntimeError(
                f"Unsupported Pi sidecar intent_result {intent_type!r}"
            )
        if not isinstance(session_key, str):
            raise RuntimeError(
                "Pi RPC command intent_result session_key must be a string"
            )
        if not session_key.strip():
            raise RuntimeError(
                "Pi RPC command intent_result session_key must be non-empty"
            )
        if not isinstance(payload, dict):
            raise RuntimeError(
                "Pi RPC command intent_result payload must be a JSON object"
            )
        if not isinstance(events, list):
            raise RuntimeError("Pi RPC command intent_result events must be a list")
        terminal_seen = False
        for event in events:
            if not isinstance(event, dict):
                raise RuntimeError(
                    "Pi RPC command intent_result events entries must be JSON objects"
                )
            event_kind = event.get("kind")
            if not isinstance(event_kind, str):
                raise RuntimeError(
                    "Pi RPC command intent_result events entries must include string kind"
                )
            if not event_kind.strip():
                raise RuntimeError(
                    "Pi RPC command intent_result events entries kind must be non-empty"
                )
            if event_kind not in _AGENT_EVENT_KINDS:
                raise RuntimeError(
                    f"Unsupported Pi sidecar intent_result event kind {event_kind!r}"
                )
            if event_kind in {"done", "error"}:
                if terminal_seen:
                    raise RuntimeError(
                        "Pi RPC command intent_result events returned multiple "
                        "terminal events"
                    )
                terminal_seen = True
            elif terminal_seen:
                raise RuntimeError(
                    "Pi RPC command intent_result events returned events after "
                    "terminal event"
                )
        try:
            safe_payload = _json_safe_value(payload)
        except RuntimeError as exc:
            raise RuntimeError(
                "Pi RPC command intent_result payload must be JSON-compatible"
            ) from exc
        try:
            safe_events = _json_safe_value(events)
        except RuntimeError as exc:
            raise RuntimeError(
                "Pi RPC command intent_result events must be JSON-compatible"
            ) from exc
        if not self._active_stream:
            raise RuntimeError(
                "Pi RPC command intent_result feedback requires an active stream"
            )
        stdin = self._active_stdin
        if stdin is None or stdin.is_closing():
            raise RuntimeError(
                "Pi RPC command stdin is not available for intent_result feedback"
            )
        frame = {
            "protocol": AGENT_CORE_PROTOCOL_VERSION,
            "kind": "intent_result",
            "type": intent_type,
            "payload": safe_payload,
            "session_key": session_key,
            "events": safe_events,
        }
        stdin.write((_json_dumps_sidecar_frame(frame) + "\n").encode("utf-8"))
        await stdin.drain()


def _config_alias_values_match(left: Any, right: Any) -> bool:
    if left is right:
        return True
    if isinstance(left, str) and isinstance(right, str):
        return left.strip() == right.strip()
    scalar_types = (bool, int, float, type(None))
    if isinstance(left, scalar_types) and isinstance(right, scalar_types):
        return type(left) is type(right) and left == right
    return False


def _first_config_value(
    runtime_config: Any | None,
    agent_core_config: Any | None,
    runtime_attr: str,
    agent_core_attr: str | None = None,
    *,
    default: Any = None,
) -> Any:
    attrs = (runtime_attr,) if agent_core_attr is None else (runtime_attr, agent_core_attr)
    found: list[tuple[str, Any]] = []
    if runtime_config is not None:
        for attr in attrs:
            if hasattr(runtime_config, attr):
                value = getattr(runtime_config, attr)
                if value is not None:
                    found.append((attr, value))
    if agent_core_config is not None:
        for attr in attrs:
            if hasattr(agent_core_config, attr):
                value = getattr(agent_core_config, attr)
                if value is not None:
                    found.append((f"agent_core.{attr}", value))
    if not found:
        return default

    selected_name, selected_value = found[0]
    for name, value in found[1:]:
        if not _config_alias_values_match(value, selected_value):
            field_names = "/".join(attrs)
            raise ValueError(
                f"conflicting config values for {field_names}: "
                f"{selected_name} != {name}"
            )
    return selected_value


def _string_config_value(value: Any | None, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    text = value.strip()
    return text or None


def _bool_config_value(value: Any, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
    raise ValueError(f"{field_name} must be a boolean")


def resolve_agent_kernel_id(value: Any | None, *, config: Any | None = None) -> AgentKernelId:
    """Resolve a configured kernel id, defaulting to the current Python agent."""

    raw = value
    if raw is None and config is not None:
        raw = getattr(config, "agent_kernel", None)
    if raw is None and config is not None:
        agent_core = getattr(config, "agent_core", None)
        raw = getattr(agent_core, "kernel", None) if agent_core is not None else None
    if raw is None:
        return DEFAULT_AGENT_KERNEL
    if not isinstance(raw, str):
        raise ValueError("agent kernel must be a string")
    if raw.strip() == "":
        return DEFAULT_AGENT_KERNEL

    normalized = raw.strip().lower().replace("_", "-")
    if normalized == "open-squilla":
        normalized = "opensquilla"
    if normalized not in SUPPORTED_AGENT_KERNELS:
        supported = ", ".join(sorted(SUPPORTED_AGENT_KERNELS))
        raise ValueError(f"Unsupported agent kernel {raw!r}; expected one of: {supported}")
    return normalized  # type: ignore[return-value]


def _validate_pi_strict_host_ports(agent_core_config: AgentCoreConfig) -> None:
    disabled: list[str] = []
    for name in (
        "strict_host_provider",
        "strict_host_tools",
        "strict_host_sessions",
        "strict_host_orchestration",
        "strict_host_finalizer",
    ):
        enabled = _bool_config_value(getattr(agent_core_config, name), field_name=name)
        if not enabled:
            disabled.append(name)
    if disabled:
        joined = ", ".join(disabled)
        raise ValueError(
            "Pi sidecar kernel v1 requires strict host-owned ports; "
            f"disabled flags: {joined}"
        )


def _validate_pi_kernel_id(agent_core_config: AgentCoreConfig) -> None:
    kernel = resolve_agent_kernel_id(agent_core_config.kernel, config=None)
    if kernel != "pi":
        raise ValueError("Pi sidecar kernel requires pi agent kernel")


def _validate_pi_protocol_version(agent_core_config: AgentCoreConfig) -> str:
    protocol_version = _string_config_value(
        agent_core_config.protocol_version,
        field_name="agent_core_protocol_version",
    )
    protocol_version = protocol_version or AGENT_CORE_PROTOCOL_VERSION
    if protocol_version != AGENT_CORE_PROTOCOL_VERSION:
        raise ValueError(
            "Unsupported Pi sidecar protocol "
            f"{protocol_version!r}; expected "
            f"{AGENT_CORE_PROTOCOL_VERSION!r}"
        )
    return protocol_version


def _validate_test_fixture_opt_in(
    enabled: Any,
    *,
    fixture_type: str,
    field_name: str,
) -> bool:
    if not _bool_config_value(enabled, field_name=field_name):
        return False
    if "PYTEST_CURRENT_TEST" not in os.environ:
        raise ValueError(
            f"test-only Pi RPC {fixture_type} opt-in requires pytest"
        )
    return True

def _pi_normalized_command_text_candidates(text: str) -> tuple[str, ...]:
    normalized = text.casefold().replace("\\", "/")
    candidates = [normalized]
    decoded = normalized
    for _ in range(3):
        decoded_next = unquote(decoded).replace("\\", "/")
        if decoded_next == decoded:
            break
        candidates.append(decoded_next)
        decoded = decoded_next
    return tuple(candidates)


def _pi_command_basename(token: str) -> str:
    basename = os.path.basename(token.replace("\\", "/")).casefold()
    for suffix in _WINDOWS_COMMAND_SUFFIXES:
        if basename.endswith(suffix):
            return basename[: -len(suffix)]
    return basename


def _pi_command_token_matches_upstream_marker(token: str, marker: str) -> bool:
    candidates = list(_pi_normalized_command_text_candidates(token))
    for normalized in tuple(candidates):
        if "=" in normalized:
            candidates.extend(_pi_normalized_command_text_candidates(normalized.rsplit("=", 1)[1]))
    for candidate in candidates:
        if candidate == marker or candidate.startswith(f"{marker}@"):
            return True
        if f"/{marker}/" in f"/{candidate}/":
            return True
    return False

def _pi_command_token_is_upstream_repo_source_path(token: str) -> bool:
    return any(
        segment in f"/{candidate}/"
        for candidate in _pi_normalized_command_text_candidates(token)
        for segment in _UPSTREAM_PI_REPO_SOURCE_PATH_SEGMENTS
    )


def _pi_command_token_is_short_pi_bin_spec(token: str) -> bool:
    for candidate in _pi_normalized_command_text_candidates(token):
        normalized = _pi_command_basename(candidate)
        if normalized == "pi":
            return True
        package_name, separator, package_version = normalized.partition("@")
        if package_name == "pi" and separator and package_version.strip():
            return True
    return False


def _pi_command_token_names_upstream_runtime(token: str) -> bool:
    if _pi_command_token_is_upstream_repo_source_path(token):
        return True
    candidates = list(_pi_normalized_command_text_candidates(token))
    for normalized in tuple(candidates):
        if "=" in normalized:
            candidates.extend(_pi_normalized_command_text_candidates(normalized.rsplit("=", 1)[1]))
        if normalized.startswith("npm:"):
            candidates.extend(_pi_normalized_command_text_candidates(normalized[len("npm:") :]))
    if any(
        candidate.startswith(_UPSTREAM_PI_PACKAGE_NAMESPACE_PREFIX)
        or f"/{_UPSTREAM_PI_PACKAGE_NAMESPACE_PREFIX}" in f"/{candidate}"
        for candidate in candidates
    ):
        return True
    return any(
        _pi_command_token_matches_upstream_marker(token, marker)
        for marker in _UPSTREAM_PI_RPC_COMMAND_MARKERS
    )

def _pi_command_text_mentions_upstream_runtime(text: str) -> bool:
    return any(
        _UPSTREAM_PI_PACKAGE_NAMESPACE_PREFIX in candidate
        or any(marker in candidate for marker in _UPSTREAM_PI_RPC_COMMAND_MARKERS)
        or any(
            segment in f"/{candidate}/"
            for segment in _UPSTREAM_PI_REPO_SOURCE_PATH_SEGMENTS
        )
        for candidate in _pi_normalized_command_text_candidates(text)
    )




def _pi_powershell_encoded_command_is_opaque(command: str) -> bool:
    argv = _pi_command_effective_argv(command)
    if not argv:
        return False
    command_name = _pi_command_basename(argv[0])
    if command_name not in {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}:
        return False
    for index, token in enumerate(argv[1:], start=1):
        option_name, separator, _ = token.casefold().partition(":")
        if option_name in {
            "-encodedcommand",
            "-enc",
            "-e",
            "/encodedcommand",
            "/enc",
            "/e",
        }:
            encoded_command = (
                token.partition(":")[2]
                if separator
                else (argv[index + 1] if index + 1 < len(argv) else "")
            )
            return _pi_powershell_decoded_command(encoded_command) is None
    return False
def _pi_powershell_decoded_command(encoded_command: str) -> str | None:
    try:
        decoded_command = base64.b64decode(
            encoded_command,
            validate=True,
        ).decode("utf-16le")
    except (binascii.Error, UnicodeDecodeError):
        return None
    return decoded_command or None


def _pi_command_token_is_inline_code_arg(token: str) -> bool:
    candidates = list(_pi_normalized_command_text_candidates(token))
    for normalized in tuple(candidates):
        if "=" in normalized:
            candidates.extend(
                _pi_normalized_command_text_candidates(normalized.split("=", 1)[1])
            )
    inline_code_prefixes = (
        "data:text/javascript",
        "data:application/javascript",
        "javascript:",
    )
    return any(
        candidate.startswith(inline_code_prefixes)
        and _pi_command_text_mentions_upstream_runtime(candidate)
        for candidate in candidates
    )


def _pi_shell_command_string(argv: Sequence[str]) -> str | None:
    if not argv:
        return None
    command_name = _pi_command_basename(argv[0])
    if command_name in {"cmd", "cmd.exe"}:
        for index, token in enumerate(argv[1:], start=1):
            if token.casefold() in {"/c", "/k"}:
                return " ".join(argv[index + 1 :]) if index + 1 < len(argv) else None
        return None
    if command_name in {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}:
        for index, token in enumerate(argv[1:], start=1):
            normalized = token.casefold()
            option_name, separator, _ = normalized.partition(":")
            if option_name in {"-command", "-c", "/command", "/c"}:
                if separator:
                    return token.partition(":")[2]
                return " ".join(argv[index + 1 :]) if index + 1 < len(argv) else None
            if option_name in {
                "-encodedcommand",
                "-enc",
                "-e",
                "/encodedcommand",
                "/enc",
                "/e",
            }:
                encoded_command = (
                    token.partition(":")[2]
                    if separator
                    else (argv[index + 1] if index + 1 < len(argv) else "")
                )
                return _pi_powershell_decoded_command(encoded_command)
            if option_name in {"-file", "-f", "/file", "/f"}:
                file_command = token.partition(":")[2] if separator else ""
                if not file_command and index + 1 < len(argv):
                    file_command = argv[index + 1]
                    return " ".join([file_command, *argv[index + 2 :]])
                return file_command or None
        return None
    for index, token in enumerate(argv[1:], start=1):
        if token == "--":
            continue
        if token == "-c" or (
            token.startswith("-")
            and not token.startswith("--")
            and "c" in token[1:]
        ):
            return argv[index + 1] if index + 1 < len(argv) else None
    return None


def _pi_env_unwrapped_argv(argv: Sequence[str]) -> list[str] | None:
    if not argv or _pi_command_basename(argv[0]) != "env":
        return None
    index = 1
    while index < len(argv):
        token = argv[index]
        if token == "--":
            index += 1
            continue
        normalized = token.casefold()
        option_name, separator, _ = normalized.partition("=")
        if option_name in _ENV_OPTIONS_WITH_VALUE:
            if option_name in {"--split-string", "-s"}:
                _, original_separator, original_inline_value = token.partition("=")
                split_source = (
                    original_inline_value
                    if original_separator
                    else (argv[index + 1] if index + 1 < len(argv) else "")
                )
                try:
                    split_argv = shlex.split(split_source)
                except ValueError:
                    split_argv = [split_source] if split_source else []
                unwrapped_split_argv = _pi_env_unwrapped_argv(["env", *split_argv])
                if unwrapped_split_argv is not None:
                    split_argv = unwrapped_split_argv
                remainder_index = index + 1 if original_separator else index + 2
                return split_argv + list(argv[remainder_index:])
            index += 1 if separator else 2
            continue
        if normalized in {"-", "-i", "--ignore-environment", "-0", "--null"}:
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        if "=" in token and not token.startswith("="):
            index += 1
            continue
        return list(argv[index:])
    return []


def _pi_timeout_unwrapped_argv(argv: Sequence[str]) -> list[str] | None:
    if not argv or _pi_command_basename(argv[0]) != "timeout":
        return None
    index = 1
    while index < len(argv):
        token = argv[index]
        if token == "--":
            index += 1
            continue
        option_name, separator, _ = token.casefold().partition("=")
        if option_name in _TIMEOUT_OPTIONS_WITH_VALUE:
            index += 1 if separator else 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        return list(argv[index + 1 :])
    return []


def _pi_cmd_builtin_unwrapped_argv(argv: Sequence[str]) -> list[str] | None:
    if not argv:
        return None
    command_name = _pi_command_basename(argv[0])
    if command_name == "call":
        start_index = 2 if len(argv) > 1 and argv[1] == "--" else 1
        return list(argv[start_index:])
    if command_name != "start":
        return None

    index = 1
    options_without_value = {
        "/b",
        "/i",
        "/min",
        "/max",
        "/separate",
        "/shared",
        "/low",
        "/normal",
        "/high",
        "/realtime",
        "/abovenormal",
        "/belownormal",
        "/wait",
    }
    options_with_value = {"/d", "/node", "/affinity", "/machine"}
    while index < len(argv):
        token = argv[index]
        if token == "--":
            index += 1
            continue
        normalized = token.casefold()
        if normalized in options_without_value:
            index += 1
            continue
        if normalized in options_with_value:
            index += 2
            continue
        if normalized.startswith("/d") and normalized != "/d":
            index += 1
            continue
        if token == "" or (" " in token and index + 1 < len(argv)):
            index += 1
            continue
        return list(argv[index:])
    return []


def _pi_process_wrapper_unwrapped_argv(argv: Sequence[str]) -> list[str] | None:
    if not argv:
        return None
    command_name = _pi_command_basename(argv[0])
    if command_name not in _PROCESS_LAUNCH_WRAPPER_COMMANDS:
        return None
    if command_name == "nohup":
        start_index = 2 if len(argv) > 1 and argv[1] == "--" else 1
        return list(argv[start_index:])
    index = 1
    while index < len(argv):
        token = argv[index]
        if token == "--":
            index += 1
            continue
        normalized = token.casefold()
        option_name, separator, _ = normalized.partition("=")
        if command_name == "nice":
            numeric_adjustment = normalized.lstrip("+-").isdigit()
            glued_adjustment = normalized.startswith("-n") and normalized != "-n"
            if option_name in _NICE_OPTIONS_WITH_VALUE:
                index += 1 if separator else 2
                continue
            if numeric_adjustment or glued_adjustment:
                index += 1
                continue
        if command_name == "stdbuf":
            glued_stdio_option = (
                len(normalized) > 2 and normalized[:2] in {"-i", "-o", "-e"}
            )
            if option_name in _STDBUF_OPTIONS_WITH_VALUE:
                index += 1 if separator or glued_stdio_option else 2
                continue
        if token.startswith("-"):
            index += 1
            continue
        return list(argv[index:])
    return []


def _pi_corepack_unwrapped_argv(argv: Sequence[str]) -> list[str] | None:
    if not argv or _pi_command_basename(argv[0]) != "corepack":
        return None
    entry_arg, entry_index = _pi_command_first_non_option_arg(
        argv,
        options_with_value=_COREPACK_OPTIONS_WITH_VALUE,
    )
    if entry_arg is None or entry_index is None:
        return []
    if _pi_command_basename(entry_arg) not in _COREPACK_PACKAGE_MANAGER_COMMANDS:
        return None
    return list(argv[entry_index:])


def _pi_effective_argv(argv: Sequence[str]) -> list[str]:
    argv = list(argv)
    while argv:
        command_name = _pi_command_basename(argv[0])
        if command_name == "env":
            argv = _pi_env_unwrapped_argv(argv) or []
            continue
        if command_name == "timeout":
            argv = _pi_timeout_unwrapped_argv(argv) or []
            continue
        if command_name in _PROCESS_LAUNCH_WRAPPER_COMMANDS:
            argv = _pi_process_wrapper_unwrapped_argv(argv) or []
            continue
        if command_name == "corepack":
            corepack_argv = _pi_corepack_unwrapped_argv(argv)
            if corepack_argv is not None:
                argv = corepack_argv
                continue
            return argv
        cmd_builtin_argv = _pi_cmd_builtin_unwrapped_argv(argv)
        if cmd_builtin_argv is not None:
            argv = cmd_builtin_argv
            continue
        if command_name in _NATIVE_PI_SHELL_COMMANDS:
            shell_command = _pi_shell_command_string(argv)
            if shell_command is None:
                return argv
            argv = shlex.split(shell_command)
            continue
        if command_name in _SHELL_COMMAND_PREFIXES:
            argv = argv[1:]
            if argv and argv[0] == "--":
                argv = argv[1:]
            continue
        return argv
    return []


def _pi_command_effective_argv(command: str) -> list[str]:
    return _pi_effective_argv(shlex.split(command))


def _pi_command_embedded_shell_string(command: str) -> str | None:
    argv = shlex.split(command)
    while argv:
        command_name = _pi_command_basename(argv[0])
        if command_name == "env":
            argv = _pi_env_unwrapped_argv(argv) or []
            continue
        if command_name == "timeout":
            argv = _pi_timeout_unwrapped_argv(argv) or []
            continue
        if command_name in _PROCESS_LAUNCH_WRAPPER_COMMANDS:
            argv = _pi_process_wrapper_unwrapped_argv(argv) or []
            continue
        if command_name == "corepack":
            corepack_argv = _pi_corepack_unwrapped_argv(argv)
            if corepack_argv is not None:
                argv = corepack_argv
                continue
            return None
        cmd_builtin_argv = _pi_cmd_builtin_unwrapped_argv(argv)
        if cmd_builtin_argv is not None:
            argv = cmd_builtin_argv
            continue
        if command_name in _NATIVE_PI_SHELL_COMMANDS:
            return _pi_shell_command_string(argv)
        if command_name in _SHELL_COMMAND_PREFIXES:
            argv = argv[1:]
            if argv and argv[0] == "--":
                argv = argv[1:]
            continue
        return None
    return None


def _pi_shell_command_tokens(command: str) -> list[str]:
    try:
        lexer = shlex.shlex(
            command,
            posix=True,
            punctuation_chars="".join(_SHELL_CONTROL_CHARACTERS),
        )
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:
        return []


def _pi_shell_command_segments(command: str) -> list[list[str]]:
    segments: list[list[str]] = []
    current_segment: list[str] = []
    for token in _pi_shell_command_tokens(command):
        if token and all(char in _SHELL_CONTROL_CHARACTERS for char in token):
            if current_segment:
                segments.append(current_segment)
                current_segment = []
            continue
        current_segment.append(token)
    if current_segment:
        segments.append(current_segment)
    return segments


def _pi_node_options_env_assignment_names_upstream_runtime(token: str) -> bool:
    if "=" not in token or token.startswith("="):
        return False
    name, _, value = token.partition("=")
    if name.casefold() != "node_options" or not value:
        return False
    if _pi_command_text_mentions_upstream_runtime(value):
        return True
    try:
        option_argv = shlex.split(value)
    except ValueError:
        option_argv = [value]
    node_argv = ["node", *option_argv]
    return _pi_command_node_preload_options_name_upstream_runtime(
        node_argv
    ) or _pi_command_node_inline_code_names_upstream_runtime(node_argv)


def _pi_shell_startup_env_assignment_names_upstream_runtime(token: str) -> bool:
    if "=" not in token or token.startswith("="):
        return False
    name, _, value = token.partition("=")
    return (
        name.casefold() in _SHELL_STARTUP_ENV_VARS
        and bool(value)
        and _pi_command_text_mentions_upstream_runtime(value)
    )


def _pi_env_name_contains_any_part(name: str, parts: frozenset[str]) -> bool:
    compact_name = "".join(
        character for character in name.casefold() if character.isalnum()
    )
    return any(part in compact_name for part in parts)


def _pi_env_name_contains_mode_part(name: str) -> bool:
    parts: list[str] = []
    current: list[str] = []
    for character in name.casefold():
        if character.isalnum():
            current.append(character)
        elif current:
            parts.append("".join(current))
            current = []
    if current:
        parts.append("".join(current))
    if "mode" in parts:
        return True
    compact_name = "".join(parts)
    return compact_name.endswith("mode")


def _pi_sidecar_config_env_assignment_names_upstream_runtime(token: str) -> bool:
    if "=" not in token or token.startswith("="):
        return False
    name, _, value = token.partition("=")
    if not name or not value:
        return False
    if _pi_env_name_contains_any_part(name, _SIDECAR_COMMAND_VALUE_ENV_NAME_PARTS):
        return _pi_shell_command_names_upstream_runtime(value)
    if _pi_env_name_contains_any_part(name, _SIDECAR_RUNTIME_REFERENCE_ENV_NAME_PARTS):
        return _pi_command_token_is_inline_code_arg(
            value
        ) or _pi_command_token_is_upstream_repo_source_path(value)
    return False


def _pi_sidecar_runtime_env_assignment_names_upstream_runtime(token: str) -> bool:
    if "=" not in token or token.startswith("="):
        return False
    name, _, value = token.partition("=")
    return (
        bool(name)
        and bool(value)
        and _pi_env_name_contains_any_part(
            name, _SIDECAR_RUNTIME_REFERENCE_ENV_NAME_PARTS
        )
        and _pi_command_token_names_upstream_runtime(value)
    )


def _pi_sidecar_mode_env_assignment_requests_upstream_rpc_mode(token: str) -> bool:
    if "=" not in token or token.startswith("="):
        return False
    name, _, value = token.partition("=")
    return (
        bool(name)
        and _pi_env_name_contains_mode_part(name)
        and value.strip().casefold() == "rpc"
    )


def _pi_sidecar_env_assignments_name_upstream_runtime(argv: Sequence[str]) -> bool:
    has_runtime_reference = False
    has_rpc_mode = False
    for token in argv:
        if "=" not in token or token.startswith("=") or token.startswith("-"):
            continue
        has_runtime_reference = (
            has_runtime_reference
            or _pi_sidecar_runtime_env_assignment_names_upstream_runtime(token)
        )
        has_rpc_mode = (
            has_rpc_mode
            or _pi_sidecar_mode_env_assignment_requests_upstream_rpc_mode(token)
        )
        if has_runtime_reference and has_rpc_mode:
            return True
    return False


def _pi_sidecar_config_env_assignment_requests_upstream_rpc_mode(token: str) -> bool:
    if "=" not in token or token.startswith("="):
        return False
    name, _, value = token.partition("=")
    return (
        bool(name)
        and bool(value)
        and _pi_env_name_contains_any_part(name, _SIDECAR_COMMAND_VALUE_ENV_NAME_PARTS)
        and _pi_shell_command_requests_upstream_rpc_mode(value)
    )


def _pi_env_assignment_names_upstream_runtime(token: str) -> bool:
    return _pi_node_options_env_assignment_names_upstream_runtime(
        token
    ) or _pi_shell_startup_env_assignment_names_upstream_runtime(
        token
    ) or _pi_sidecar_config_env_assignment_names_upstream_runtime(token)


def _pi_prefix_env_assignments_name_upstream_runtime(argv: Sequence[str]) -> bool:
    for token in argv:
        if "=" in token and not token.startswith("=") and not token.startswith("-"):
            if _pi_env_assignment_names_upstream_runtime(token):
                return True
            continue
        return False
    return False


def _pi_argv_env_assignments_name_upstream_runtime(argv: Sequence[str]) -> bool:
    if not argv:
        return False
    if _pi_sidecar_env_assignments_name_upstream_runtime(argv):
        return True
    command_name = _pi_command_basename(argv[0])
    if command_name == "env":
        index = 1
        while index < len(argv):
            token = argv[index]
            if token == "--":
                index += 1
                continue
            normalized = token.casefold()
            option_name, separator, _ = normalized.partition("=")
            if option_name in _ENV_OPTIONS_WITH_VALUE:
                if option_name in {"--split-string", "-s"}:
                    _, original_separator, original_inline_value = token.partition("=")
                    split_source = (
                        original_inline_value
                        if original_separator
                        else (argv[index + 1] if index + 1 < len(argv) else "")
                    )
                    try:
                        split_argv = shlex.split(split_source)
                    except ValueError:
                        split_argv = [split_source] if split_source else []
                    if _pi_argv_env_assignments_name_upstream_runtime(
                        ["env", *split_argv]
                    ):
                        return True
                    index += 1 if original_separator else 2
                    continue
                index += 1 if separator else 2
                continue
            if normalized in {"-", "-i", "--ignore-environment", "-0", "--null"}:
                index += 1
                continue
            if token.startswith("-"):
                index += 1
                continue
            if "=" in token and not token.startswith("="):
                if _pi_env_assignment_names_upstream_runtime(token):
                    return True
                index += 1
                continue
            return False
        return False
    if command_name == "timeout":
        unwrapped_argv = _pi_timeout_unwrapped_argv(argv)
        return unwrapped_argv is not None and _pi_argv_env_assignments_name_upstream_runtime(
            unwrapped_argv
        )
    if command_name in _PROCESS_LAUNCH_WRAPPER_COMMANDS:
        unwrapped_argv = _pi_process_wrapper_unwrapped_argv(argv)
        return unwrapped_argv is not None and _pi_argv_env_assignments_name_upstream_runtime(
            unwrapped_argv
        )
    if command_name == "corepack":
        unwrapped_argv = _pi_corepack_unwrapped_argv(argv)
        return unwrapped_argv is not None and _pi_argv_env_assignments_name_upstream_runtime(
            unwrapped_argv
        )
    if command_name in _NATIVE_PI_SHELL_COMMANDS:
        shell_command = _pi_shell_command_string(argv)
        return shell_command is not None and _pi_command_env_assignments_name_upstream_runtime(
            shell_command
        )
    if command_name in _SHELL_COMMAND_PREFIXES:
        return _pi_argv_env_assignments_name_upstream_runtime(
            argv[2:] if len(argv) > 1 and argv[1] == "--" else argv[1:]
        )
    return _pi_prefix_env_assignments_name_upstream_runtime(argv)


def _pi_command_env_assignments_name_upstream_runtime(command: str) -> bool:
    try:
        argv = shlex.split(command)
    except ValueError:
        return False
    return _pi_argv_env_assignments_name_upstream_runtime(argv)


def _pi_command_first_non_option_arg(
    argv: Sequence[str],
    *,
    start_index: int = 1,
    options_with_value: frozenset[str] = frozenset(),
) -> tuple[str | None, int | None]:
    skip_option_value = False
    for index, token in enumerate(argv[start_index:], start=start_index):
        if skip_option_value:
            skip_option_value = False
            continue
        if token == "--":
            continue
        option_name = token.casefold().split("=", 1)[0]
        if option_name in options_with_value:
            skip_option_value = "=" not in token
            continue
        if token.startswith("-"):
            continue
        return token, index
    return None, None


def _pi_command_script_entry_arg(argv: Sequence[str]) -> str | None:
    entry_arg, _ = _pi_command_first_non_option_arg(
        argv,
        options_with_value=_NODE_OPTIONS_WITH_VALUE,
    )
    return entry_arg


def _pi_command_option_value(
    argv: Sequence[str],
    index: int,
    separator: str,
    inline_value: str,
) -> str:
    if separator:
        return inline_value
    return argv[index + 1] if index + 1 < len(argv) else ""


def _pi_command_node_preload_options_name_upstream_runtime(argv: Sequence[str]) -> bool:
    for index, token in enumerate(argv[1:], start=1):
        option_name, separator, inline_value = token.casefold().partition("=")
        if option_name not in _NODE_OPTIONS_WITH_VALUE:
            continue
        value = _pi_command_option_value(argv, index, separator, inline_value)
        if value and (
            _pi_command_token_names_upstream_runtime(value)
            or _pi_command_text_mentions_upstream_runtime(value)
        ):
            return True
    return False


def _pi_command_node_inline_code_names_upstream_runtime(argv: Sequence[str]) -> bool:
    for index, token in enumerate(argv[1:], start=1):
        option_name, separator, inline_value = token.casefold().partition("=")
        if option_name not in _NODE_INLINE_CODE_OPTIONS_WITH_VALUE:
            continue
        value = _pi_command_option_value(argv, index, separator, inline_value)
        if value and _pi_command_text_mentions_upstream_runtime(value):
            return True
    return False


def _pi_command_node_run_script_names_upstream_runtime(argv: Sequence[str]) -> bool:
    for index, token in enumerate(argv[1:], start=1):
        option_name, separator, inline_value = token.casefold().partition("=")
        if option_name != "--run":
            continue
        value = _pi_command_option_value(argv, index, separator, inline_value)
        normalized_value = _pi_command_basename(value)
        return normalized_value == "pi" or _pi_command_token_names_upstream_runtime(
            value
        )
    return False


def _pi_script_interpreter_names_upstream_runtime(argv: Sequence[str]) -> bool:
    if _pi_command_node_preload_options_name_upstream_runtime(argv):
        return True
    if _pi_command_node_inline_code_names_upstream_runtime(argv):
        return True
    if _pi_command_node_run_script_names_upstream_runtime(argv):
        return True
    script_arg = _pi_command_script_entry_arg(argv)
    return script_arg is not None and _pi_command_token_names_upstream_runtime(
        script_arg
    )


def _pi_source_executor_names_upstream_runtime(argv: Sequence[str]) -> bool:
    return any(_pi_command_token_names_upstream_runtime(token) for token in argv[1:])


def _pi_deno_run_names_upstream_runtime(argv: Sequence[str]) -> bool:
    entry_arg, entry_index = _pi_command_first_non_option_arg(argv)
    if (
        entry_arg is None
        or entry_index is None
        or _pi_command_basename(entry_arg) != "run"
    ):
        return False
    return any(
        _pi_command_token_names_upstream_runtime(token)
        for token in argv[entry_index + 1 :]
    )


def _pi_command_package_runner_entry(
    argv: Sequence[str],
) -> tuple[str | None, int | None]:
    entry_arg, entry_index = _pi_command_first_non_option_arg(
        argv,
        options_with_value=_PACKAGE_RUNNER_OPTIONS_WITH_VALUE,
    )
    if entry_arg is None or entry_index is None:
        return None, None
    command_name = _pi_command_basename(argv[0]) if argv else ""
    if (
        command_name in {"npm", "pnpm", "yarn", "bun"}
        and entry_arg.casefold() in _PACKAGE_RUNNER_SUBCOMMANDS_WITH_PACKAGE_TARGET
    ):
        entry_arg, entry_index = _pi_command_first_non_option_arg(
            argv,
            start_index=entry_index + 1,
            options_with_value=_PACKAGE_RUNNER_OPTIONS_WITH_VALUE,
        )
    return entry_arg, entry_index


def _pi_command_package_runner_entry_arg(argv: Sequence[str]) -> str | None:
    entry_arg, _ = _pi_command_package_runner_entry(argv)
    return entry_arg


def _pi_command_package_options_name_upstream_runtime(argv: Sequence[str]) -> bool:
    skip_option_value = False
    for index, token in enumerate(argv[1:], start=1):
        if skip_option_value:
            skip_option_value = False
            continue
        option_name, _, inline_value = token.casefold().partition("=")
        if option_name not in _PACKAGE_RUNNER_OPTIONS_WITH_VALUE:
            continue
        value = inline_value or (argv[index + 1] if index + 1 < len(argv) else "")
        if not inline_value:
            skip_option_value = True
        if value and _pi_command_token_names_upstream_runtime(value):
            return True
    return False


def _pi_command_package_runner_shell_commands(argv: Sequence[str]) -> list[str]:
    shell_commands: list[str] = []
    skip_option_value = False
    for index, token in enumerate(argv[1:], start=1):
        if skip_option_value:
            skip_option_value = False
            continue
        option_name, _, _ = token.casefold().partition("=")
        if option_name not in _PACKAGE_RUNNER_SHELL_OPTIONS_WITH_VALUE:
            continue
        _, separator, inline_value = token.partition("=")
        value = _pi_command_option_value(argv, index, separator, inline_value)
        if not separator:
            skip_option_value = True
        if value:
            shell_commands.append(value)
    return shell_commands


def _pi_package_runner_shell_commands_name_upstream_runtime(
    argv: Sequence[str],
) -> bool:
    return any(
        _pi_shell_command_names_upstream_runtime(shell_command)
        for shell_command in _pi_command_package_runner_shell_commands(argv)
    )


def _pi_command_value_option_values(argv: Sequence[str]) -> list[str]:
    values: list[str] = []
    skip_option_value = False
    for index, token in enumerate(argv[1:], start=1):
        if skip_option_value:
            skip_option_value = False
            continue
        option_name, _, _ = token.casefold().partition("=")
        if option_name not in _SIDECAR_COMMAND_VALUE_OPTIONS_WITH_VALUE:
            continue
        _, separator, inline_value = token.partition("=")
        value = _pi_command_option_value(argv, index, separator, inline_value)
        if not separator:
            skip_option_value = True
        if value:
            values.append(value)
    return values


def _pi_runtime_reference_option_values(argv: Sequence[str]) -> list[str]:
    values: list[str] = []
    skip_option_value = False
    for index, token in enumerate(argv[1:], start=1):
        if skip_option_value:
            skip_option_value = False
            continue
        option_name, _, _ = token.casefold().partition("=")
        if option_name not in _SIDECAR_RUNTIME_REFERENCE_OPTIONS_WITH_VALUE:
            continue
        _, separator, inline_value = token.partition("=")
        value = _pi_command_option_value(argv, index, separator, inline_value)
        if not separator:
            skip_option_value = True
        if value:
            values.append(value)
    return values


def _pi_module_root_option_values(argv: Sequence[str]) -> list[str]:
    values: list[str] = []
    skip_option_value = False
    for index, token in enumerate(argv[1:], start=1):
        if skip_option_value:
            skip_option_value = False
            continue
        option_name, _, _ = token.casefold().partition("=")
        if option_name not in _SIDECAR_MODULE_ROOT_OPTIONS_WITH_VALUE:
            continue
        _, separator, inline_value = token.partition("=")
        value = _pi_command_option_value(argv, index, separator, inline_value)
        if not separator:
            skip_option_value = True
        if value:
            values.append(value)
    return values


def _pi_command_path_points_inside_opensquilla_source(token: str) -> bool:
    for candidate in _pi_normalized_command_text_candidates(token):
        path_parts = [part for part in candidate.strip("\"'").split("/") if part]
        for index, part in enumerate(path_parts[:-1]):
            if part == "src" and path_parts[index + 1] == "opensquilla":
                return True
    return False


def _pi_module_root_options_point_to_disallowed_source(
    argv: Sequence[str],
) -> bool:
    return any(
        _pi_command_path_points_inside_opensquilla_source(value)
        or _pi_command_token_is_upstream_repo_source_path(value)
        for value in _pi_module_root_option_values(argv)
    )


def _pi_command_module_root_options_point_to_disallowed_source(
    command: str,
) -> bool:
    return _pi_module_root_options_point_to_disallowed_source(
        _pi_command_effective_argv(command)
    )


def _pi_runtime_reference_options_name_upstream_runtime(
    argv: Sequence[str],
) -> bool:
    return any(
        _pi_command_token_is_inline_code_arg(value)
        or _pi_command_token_is_upstream_repo_source_path(value)
        for value in _pi_runtime_reference_option_values(argv)
    )


def _pi_runtime_reference_options_name_upstream_package(
    argv: Sequence[str],
) -> bool:
    return any(
        _pi_command_token_names_upstream_runtime(value)
        for value in _pi_runtime_reference_option_values(argv)
    )


def _pi_command_package_runner_script_entry(
    argv: Sequence[str],
) -> tuple[str | None, int | None]:
    if not argv:
        return None, None
    command_name = _pi_command_basename(argv[0])
    entry_arg, entry_index = _pi_command_first_non_option_arg(
        argv,
        options_with_value=(
            _PACKAGE_RUNNER_OPTIONS_WITH_VALUE
            | _PACKAGE_RUNNER_SHELL_OPTIONS_WITH_VALUE
        ),
    )
    if entry_arg is None or entry_index is None:
        return None, None
    normalized_entry_arg = _pi_command_basename(entry_arg)
    if normalized_entry_arg in _PACKAGE_RUNNER_SCRIPT_SUBCOMMANDS:
        return _pi_command_first_non_option_arg(argv, start_index=entry_index + 1)
    if command_name == "yarn" and (
        _pi_command_token_is_short_pi_bin_spec(entry_arg)
        or _pi_command_token_names_upstream_runtime(entry_arg)
    ):
        return entry_arg, entry_index
    return None, None


def _pi_package_runner_script_names_upstream_runtime(argv: Sequence[str]) -> bool:
    script_arg, _ = _pi_command_package_runner_script_entry(argv)
    if script_arg is None:
        return False
    return _pi_command_token_is_short_pi_bin_spec(
        script_arg
    ) or _pi_command_token_names_upstream_runtime(script_arg)


def _pi_package_runner_native_command_tail_names_upstream_runtime(
    argv: Sequence[str],
) -> bool:
    entry_arg, entry_index = _pi_command_package_runner_entry(argv)
    if entry_arg is None or entry_index is None:
        return False
    tail = list(argv[entry_index + 1 :])
    while tail and tail[0] == "--":
        tail = tail[1:]
    if not tail:
        return False
    tail_command = tail[0]
    if _pi_command_token_is_short_pi_bin_spec(tail_command):
        return True
    if _pi_command_token_names_upstream_runtime(tail_command):
        return True
    return _pi_argv_names_upstream_runtime(tail)


def _pi_package_runner_names_upstream_runtime(argv: Sequence[str]) -> bool:
    entry_arg, entry_index = _pi_command_package_runner_entry(argv)
    if _pi_command_package_options_name_upstream_runtime(argv):
        return True
    if _pi_package_runner_script_names_upstream_runtime(argv):
        return True
    if entry_arg is None or entry_index is None:
        return _pi_package_runner_shell_commands_name_upstream_runtime(argv)
    if _pi_package_runner_shell_commands_name_upstream_runtime(argv):
        return True
    if _pi_package_runner_native_command_tail_names_upstream_runtime(argv):
        return True
    if _pi_command_token_names_upstream_runtime(entry_arg):
        return True
    if _pi_command_basename(entry_arg) in _NATIVE_PI_SCRIPT_INTERPRETER_COMMANDS:
        return _pi_script_interpreter_names_upstream_runtime(argv[entry_index:])
    if _pi_command_basename(entry_arg) in _NATIVE_PI_SOURCE_EXECUTOR_COMMANDS:
        return any(
            _pi_command_token_is_upstream_repo_source_path(token)
            for token in argv[entry_index + 1 :]
        )
    return _pi_command_token_is_short_pi_bin_spec(entry_arg)


def _pi_shell_command_names_upstream_runtime(command: str) -> bool:
    return any(
        _pi_argv_env_assignments_name_upstream_runtime(segment)
        or _pi_argv_names_upstream_runtime(_pi_effective_argv(segment))
        for segment in _pi_shell_command_segments(command)
    )


def _pi_command_value_options_name_upstream_runtime(
    argv: Sequence[str],
) -> bool:
    return any(
        _pi_shell_command_names_upstream_runtime(command_value)
        for command_value in _pi_command_value_option_values(argv)
    )


def _pi_argv_names_upstream_runtime(argv: Sequence[str]) -> bool:
    if not argv:
        return False
    if any(_pi_command_token_is_inline_code_arg(token) for token in argv):
        return True
    if _pi_runtime_reference_options_request_upstream_rpc_mode(argv):
        return True
    if _pi_runtime_reference_options_name_upstream_runtime(argv):
        return True
    if _pi_command_value_options_name_upstream_runtime(argv):
        return True
    if _pi_command_token_names_upstream_runtime(argv[0]):
        return True
    command_name = _pi_command_basename(argv[0])
    if command_name == "pi" or _pi_command_token_names_upstream_runtime(command_name):
        return True
    if command_name in _NATIVE_PI_SCRIPT_INTERPRETER_COMMANDS:
        return _pi_script_interpreter_names_upstream_runtime(argv)
    if command_name in _NATIVE_PI_SOURCE_EXECUTOR_COMMANDS:
        return _pi_source_executor_names_upstream_runtime(argv)
    if command_name == "deno":
        return _pi_deno_run_names_upstream_runtime(argv)
    if command_name not in _NATIVE_PI_PACKAGE_RUNNER_COMMANDS:
        return False
    return _pi_package_runner_names_upstream_runtime(argv)


def _pi_shell_segments_name_upstream_runtime(command: str) -> bool:
    shell_command = _pi_command_embedded_shell_string(command)
    if shell_command is None:
        return False
    return _pi_shell_command_names_upstream_runtime(shell_command)


def _pi_command_names_upstream_runtime(command: str) -> bool:
    argv = _pi_command_effective_argv(command)
    return (
        _pi_command_env_assignments_name_upstream_runtime(command)
        or _pi_argv_names_upstream_runtime(argv)
        or _pi_shell_segments_name_upstream_runtime(command)
    )


def _pi_command_invokes_native_cli_or_package(command: str) -> bool:
    return _pi_command_names_upstream_runtime(command)


def _pi_argv_directly_requests_upstream_rpc_mode(argv: Sequence[str]) -> bool:
    for index, token in enumerate(argv):
        normalized = token.casefold()
        if normalized == "--rpc":
            return True
        option_name, separator, inline_value = token.partition("=")
        if (
            separator
            and option_name.casefold() == "--mode"
            and inline_value.strip().casefold() == "rpc"
        ):
            return True
        if (
            normalized == "--mode"
            and index + 1 < len(argv)
            and argv[index + 1].strip().casefold() == "rpc"
        ):
            return True
    return False


def _pi_runtime_reference_options_request_upstream_rpc_mode(
    argv: Sequence[str],
) -> bool:
    return _pi_runtime_reference_options_name_upstream_package(
        argv
    ) and _pi_argv_directly_requests_upstream_rpc_mode(argv)


def _pi_argv_requests_upstream_rpc_mode(argv: Sequence[str]) -> bool:
    if any(
        _pi_sidecar_config_env_assignment_requests_upstream_rpc_mode(token)
        or _pi_sidecar_mode_env_assignment_requests_upstream_rpc_mode(token)
        for token in argv
    ):
        return True
    if _pi_argv_directly_requests_upstream_rpc_mode(argv):
        return True
    if _pi_runtime_reference_options_request_upstream_rpc_mode(argv):
        return True
    if _pi_command_value_options_request_upstream_rpc_mode(argv):
        return True
    command_name = _pi_command_basename(argv[0]) if argv else ""
    return (
        command_name in _NATIVE_PI_PACKAGE_RUNNER_COMMANDS
        and _pi_package_runner_shell_commands_request_upstream_rpc_mode(argv)
    )


def _pi_shell_command_requests_upstream_rpc_mode(command: str) -> bool:
    return any(
        _pi_argv_requests_upstream_rpc_mode(_pi_effective_argv(segment))
        for segment in _pi_shell_command_segments(command)
    )


def _pi_package_runner_shell_commands_request_upstream_rpc_mode(
    argv: Sequence[str],
) -> bool:
    return any(
        _pi_shell_command_requests_upstream_rpc_mode(shell_command)
        for shell_command in _pi_command_package_runner_shell_commands(argv)
    )


def _pi_command_value_options_request_upstream_rpc_mode(
    argv: Sequence[str],
) -> bool:
    return any(
        _pi_shell_command_requests_upstream_rpc_mode(command_value)
        for command_value in _pi_command_value_option_values(argv)
    )


def _pi_shell_segments_request_upstream_rpc_mode(command: str) -> bool:
    shell_command = _pi_command_embedded_shell_string(command)
    if shell_command is None:
        return False
    return _pi_shell_command_requests_upstream_rpc_mode(shell_command)


def _pi_command_requests_upstream_rpc_mode(command: str) -> bool:
    try:
        raw_argv = shlex.split(command)
    except ValueError:
        raw_argv = []
    argv = _pi_command_effective_argv(command)
    return (
        _pi_argv_requests_upstream_rpc_mode(raw_argv)
        or _pi_argv_requests_upstream_rpc_mode(argv)
        or _pi_shell_segments_request_upstream_rpc_mode(command)
    )


def _provenance_names_upstream_pi(provenance: str | None) -> bool:
    if provenance is None:
        return False
    normalized = provenance.casefold()
    if any(marker in normalized for marker in _UPSTREAM_PI_REPO_PROVENANCE_MARKERS):
        return True
    try:
        tokens = shlex.split(normalized)
    except ValueError:
        tokens = normalized.split()
    return any(
        _pi_command_token_matches_upstream_marker(
            token.strip(".,;:()[]{}<>\"'`"),
            marker,
        )
        for token in tokens
        for marker in _UPSTREAM_PI_PROVENANCE_PACKAGE_MARKERS
    )


def _provenance_declares_agent_core_sidecar(provenance: str | None) -> bool:
    if provenance is None:
        return False
    normalized = provenance.casefold()
    return any(marker in normalized for marker in _AGENT_CORE_SIDECAR_PROVENANCE_MARKERS)


def _provenance_declares_test_fixture(provenance: str | None) -> bool:
    if provenance is None:
        return False
    normalized = provenance.casefold()
    return any(
        marker in normalized for marker in _TEST_FIXTURE_PI_RPC_PROVENANCE_MARKERS
    )


def _provenance_declares_upstream_pi_loop_owner(
    normalized: str,
    compact: str,
) -> bool:
    owns_loop = any(
        phrase in normalized
        for phrase in (
            "upstream pi owns",
            "upstream pi handles",
            "real upstream pi owns",
            "real upstream pi handles",
            "pi runtime owns",
            "pi runtime handles",
            "upstream runtime owns",
            "upstream runtime handles",
        )
    ) or any(
        phrase in compact
        for phrase in (
            "upstreampiowns",
            "upstreampihandles",
            "realupstreampiowns",
            "realupstreampihandles",
            "piruntimeowns",
            "piruntimehandles",
            "upstreamruntimeowns",
            "upstreamruntimehandles",
        )
    )
    adapter_only_translates = any(
        phrase in normalized
        for phrase in (
            "only translates io",
            "only translates protocol",
            "only translate io",
            "only translate protocol",
            "io bridge",
        )
    ) or any(
        phrase in compact
        for phrase in (
            "onlytranslatesio",
            "onlytranslatesprotocol",
            "onlytranslateio",
            "onlytranslateprotocol",
            "iobridge",
        )
    )
    return owns_loop and adapter_only_translates


def _provenance_declares_pi_loop_rewrite(provenance: str | None) -> bool:
    if provenance is None:
        return False
    normalized = provenance.casefold()
    compact = (
        normalized.replace("-", "")
        .replace("_", "")
        .replace("/", "")
        .replace(" ", "")
    )
    rewrite_phrase = any(
        all(part in normalized for part in phrase)
        for phrase in _PI_LOOP_REWRITE_PROVENANCE_PHRASES
    )
    loop_marker = any(
        marker in compact for marker in _PI_LOOP_REWRITE_PROVENANCE_MARKERS
    )
    return rewrite_phrase or (
        loop_marker
        and not _provenance_declares_upstream_pi_loop_owner(normalized, compact)
    )


def _pi_command_pythonpath_part_names_test_fixture(path_part: str) -> bool:
    normalized_path = path_part.casefold().replace("\\", "/").strip("'\"")
    normalized_path = normalized_path.split(None, 1)[0]
    fixture_roots = {"tests", "examples", "samples", "demos"}
    return (
        normalized_path in fixture_roots
        or normalized_path in {f"./{root}" for root in fixture_roots}
        or any(normalized_path.endswith(f"/{root}") for root in fixture_roots)
        or any(f"/{root}/" in normalized_path for root in fixture_roots)
    )


def _pi_command_pythonpath_names_test_fixture(command: str) -> bool:
    raw_tokens = command.replace("\\", "/").split()
    for raw_token in raw_tokens:
        name, separator, value = raw_token.partition("=")
        if separator and name.casefold() == "pythonpath" and any(
            _pi_command_pythonpath_part_names_test_fixture(path_part)
            for path_part in value.replace(";", os.pathsep).split(os.pathsep)
        ):
            return True

    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    for token in tokens:
        name, separator, value = token.partition("=")
        normalized_name = name.casefold()
        if separator and normalized_name == "--split-string":
            if _pi_command_pythonpath_names_test_fixture(value):
                return True
            continue
        if not separator or normalized_name != "pythonpath":
            continue
        if any(
            _pi_command_pythonpath_part_names_test_fixture(path_part)
            for path_part in value.replace(";", os.pathsep).split(os.pathsep)
        ):
            return True
    return False


def _pi_client_identity_names_upstream_runtime(client: Any) -> bool:
    client_type = type(client)
    module_name = client_type.__module__.casefold()
    qualname = client_type.__qualname__.casefold()
    compact_qualname = qualname.replace("_", "").replace("-", "")
    identity = f"{module_name}.{qualname}"
    native_module_prefixes = (
        "pi.agent",
        "pi.coding_agent",
        "pi.codingagent",
        "pi_agent_core",
        "piagentcore",
        "pi_coding_agent",
        "picodingagent",
    )
    native_qualname_markers = (
        "piagentruntime",
        "piagentcore",
        "picodingagent",
    )
    if module_name.startswith(native_module_prefixes) or any(
        marker in compact_qualname for marker in native_qualname_markers
    ):
        return True
    if any(marker in identity for marker in ("opensquilla", "bridge", "sidecar")):
        return False
    return any(
        marker in identity
        for marker in _UPSTREAM_PI_RPC_CLIENT_IDENTITY_MARKERS
    )


def _validate_pi_rpc_command(
    command: str,
    *,
    provenance: str | None,
    allow_test_command: bool,
) -> None:
    normalized_command = command.casefold()
    if _pi_powershell_encoded_command_is_opaque(command):
        raise ValueError(
            "PowerShell encoded command must decode before sidecar validation"
        )
    names_upstream_runtime = _pi_command_names_upstream_runtime(command)
    if names_upstream_runtime and _pi_command_requests_upstream_rpc_mode(command):
        raise ValueError(
            "native Pi RPC mode is not an OpenSquilla agent-core sidecar"
        )
    if _pi_command_invokes_native_cli_or_package(command):
        raise ValueError(
            "native Pi CLI/package is not an OpenSquilla agent-core sidecar"
        )
    if _pi_command_module_root_options_point_to_disallowed_source(command):
        raise ValueError(
            "Pi module root must not point inside OpenSquilla source or upstream "
            "Pi source packages"
        )
    if _validate_test_fixture_opt_in(
        allow_test_command,
        fixture_type="command",
        field_name="allow_test_pi_rpc_command",
    ):
        return
    if _pi_command_pythonpath_names_test_fixture(command) or any(
        marker in normalized_command
        for marker in _TEST_FIXTURE_PI_RPC_COMMAND_MARKERS
    ):
        raise ValueError(
            "test-only Pi RPC command is not allowed in production config"
        )
    if _provenance_declares_test_fixture(provenance):
        raise ValueError(
            "test-only Pi RPC command provenance is not allowed in production config"
        )
    if _provenance_declares_pi_loop_rewrite(provenance):
        raise ValueError(
            "Pi RPC command provenance must not declare Pi agent loop rewrite"
        )
    names_upstream_provenance = _provenance_names_upstream_pi(provenance)
    declares_agent_core_sidecar = _provenance_declares_agent_core_sidecar(
        provenance
    )
    if not names_upstream_provenance:
        raise ValueError(
            "Pi RPC command must declare upstream Pi runtime provenance"
        )
    if not declares_agent_core_sidecar:
        raise ValueError(
            "Pi RPC command must declare OpenSquilla agent-core sidecar protocol "
            "provenance"
        )


def _validate_pi_rpc_client(
    client: Any,
    *,
    provenance: str | None,
    allow_test_client: bool,
) -> None:
    if not callable(getattr(client, "stream_prompt", None)):
        raise ValueError(
            "Pi RPC client must provide callable stream_prompt"
        )
    if _pi_client_identity_names_upstream_runtime(client):
        raise ValueError(
            "native Pi RPC client is not an OpenSquilla agent-core sidecar"
        )
    if _validate_test_fixture_opt_in(
        allow_test_client,
        fixture_type="client",
        field_name="allow_test_pi_rpc_client",
    ):
        return
    client_type = type(client)
    identity = f"{client_type.__module__}.{client_type.__qualname__}".casefold()
    if any(
        marker in identity
        for marker in _TEST_FIXTURE_PI_RPC_CLIENT_MARKERS
    ):
        raise ValueError(
            "test-only Pi RPC client is not allowed in production config"
        )
    if _provenance_declares_test_fixture(provenance):
        raise ValueError(
            "test-only Pi RPC client provenance is not allowed in production config"
        )
    if _provenance_declares_pi_loop_rewrite(provenance):
        raise ValueError(
            "Pi RPC client provenance must not declare Pi agent loop rewrite"
        )
    if not _provenance_names_upstream_pi(provenance):
        raise ValueError(
            "Pi RPC client must declare upstream Pi runtime provenance"
        )
    if not _provenance_declares_agent_core_sidecar(provenance):
        raise ValueError(
            "Pi RPC client must declare OpenSquilla agent-core sidecar protocol "
            "provenance"
        )


def _pi_rpc_client_from_config(config: Any | None) -> PiRpcClient | None:
    agent_core_config = (
        config
        if isinstance(config, AgentCoreConfig)
        else AgentCoreConfig.from_runtime_config(config)
    )
    command = _string_config_value(
        agent_core_config.pi_rpc_command,
        field_name="pi_rpc_command",
    )
    if agent_core_config.pi_rpc_client is not None and command is not None:
        raise ValueError(
            "pi_rpc_client and pi_agent_rpc_command cannot both be configured"
        )
    if agent_core_config.pi_rpc_client is not None:
        client_provenance = _string_config_value(
            agent_core_config.pi_rpc_client_provenance,
            field_name="pi_rpc_client_provenance",
        )
        allow_test_client = _bool_config_value(
            agent_core_config.allow_test_pi_rpc_client,
            field_name="allow_test_pi_rpc_client",
        )
        _validate_pi_rpc_client(
            agent_core_config.pi_rpc_client,
            provenance=client_provenance,
            allow_test_client=allow_test_client,
        )
        return cast(PiRpcClient, agent_core_config.pi_rpc_client)
    if command is not None:
        command_provenance = _string_config_value(
            agent_core_config.pi_rpc_command_provenance,
            field_name="pi_rpc_command_provenance",
        )
        allow_test_command = _bool_config_value(
            agent_core_config.allow_test_pi_rpc_command,
            field_name="allow_test_pi_rpc_command",
        )
        _validate_pi_rpc_command(
            command,
            provenance=command_provenance,
            allow_test_command=allow_test_command,
        )
        return PiJsonlCommandRpcClient(command)
    if config is None:
        return None
    return None


def _provider_identity_for_history(provider: Any | None) -> _ProviderIdentityForHistory:
    from opensquilla.provider.protocol import provider_metadata

    metadata = provider_metadata(provider)
    return _ProviderIdentityForHistory(
        provider_name=metadata.provider_name or metadata.provider_kind,
        provider_kind=metadata.provider_kind or metadata.provider_name,
    )


def build_agent_for_kernel(
    *,
    runtime_config: Any | None,
    provider: Any,
    config: Any,
    tool_definitions: list[Any],
    tool_handler: Any | None,
    usage_tracker: Any | None,
    session_key: str,
    turn_call_logger: Any | None,
    memory_sync_manager: Any | None,
    session_flush_service: Any | None,
    tool_registry: Any | None,
    tool_context: Any | None,
    session_manager: Any | None = None,
    session_write_context_factory: Any | None = None,
) -> Any:
    """Build the selected kernel behind the existing AgentRunPort boundary."""

    agent_core_config = AgentCoreConfig.from_runtime_config(runtime_config)
    if agent_core_config.kernel == "opensquilla":
        from opensquilla.engine.agent import Agent

        return OpenSquillaPythonKernelRuntime(
            Agent(
                provider=provider,
                config=config,
                tool_definitions=tool_definitions,
                tool_handler=tool_handler,
                usage_tracker=usage_tracker,
                session_key=session_key,
                turn_call_logger=turn_call_logger,
                memory_sync_manager=memory_sync_manager,
                session_flush_service=session_flush_service,
                tool_registry=tool_registry,
                tool_context=tool_context,
            )
        )

    rpc_client = _pi_rpc_client_from_config(agent_core_config)
    if rpc_client is None:
        raise RuntimeError(
            "Pi agent kernel selected but no pi_agent_rpc_command or "
            "pi_agent_rpc_client is configured"
        )
    from opensquilla.engine.agent import Agent

    host_agent = Agent(
        provider=provider,
        config=_host_agent_config(config),
        tool_definitions=tool_definitions,
        tool_handler=tool_handler,
        usage_tracker=usage_tracker,
        session_key=session_key,
        turn_call_logger=turn_call_logger,
        memory_sync_manager=memory_sync_manager,
        session_flush_service=session_flush_service,
        tool_registry=tool_registry,
        tool_context=tool_context,
    )
    task_runtime = _task_runtime_from_session_manager(session_manager)
    provider_usage = _ProviderUsageAccumulator()
    production_pi_sidecar = not (
        agent_core_config.allow_test_pi_rpc_client
        or agent_core_config.allow_test_pi_rpc_command
    )
    return PiSidecarKernelRuntime(
        rpc_client=rpc_client,
        config=config,
        session_key=session_key,
        provider_identity=_provider_identity_for_history(provider),
        agent_core_config=agent_core_config,
        tool_definitions=tool_definitions,
        host_agent=host_agent,
        emit_state_events=production_pi_sidecar,
        inject_host_runtime_context=production_pi_sidecar,
        emit_yield_tool_start_events=production_pi_sidecar,
        coalesce_tool_state_events=production_pi_sidecar,
        host_ports=KernelHostPorts(
            provider=OpenSquillaProviderHostPort(
                host_agent,
                provider_usage=provider_usage,
            ),
            tool_bridge=OpenSquillaToolBridgeHostPort(host_agent),
            session_writes=(
                OpenSquillaSessionWritesHostPort(
                    session_manager=session_manager,
                    session_write_context_factory=session_write_context_factory,
                )
                if session_manager is not None
                else None
            ),
            queue=(
                OpenSquillaQueueHostPort(task_runtime=task_runtime)
                if task_runtime is not None
                else None
            ),
            savepoints=(
                OpenSquillaSavepointHostPort(
                    session_manager=session_manager,
                    session_write_context_factory=session_write_context_factory,
                )
                if session_manager is not None
                else None
            ),
            orchestration=OpenSquillaOrchestrationHostPort(host_agent),
            finalizer=OpenSquillaFinalizerHostPort(
                config=config,
                provider_usage=provider_usage,
            ),
            telemetry=OpenSquillaTelemetryHostPort(),
        ),
    )


class OpenSquillaProviderHostPort:
    """Host-owned provider port for Pi sidecar provider intents."""

    def __init__(
        self,
        host_agent: Any,
        provider_usage: _ProviderUsageAccumulator | None = None,
    ) -> None:
        self._host_agent = host_agent
        self._provider_usage = provider_usage

    def refresh_system_prompt(self, system_prompt: str) -> None:
        refresh = getattr(self._host_agent, "refresh_system_prompt", None)
        if callable(refresh):
            refresh(system_prompt)

    async def handle_intent(
        self,
        *,
        intent_type: str,
        payload: dict[str, Any],
        session_key: str,
    ) -> list[AgentEvent]:
        if intent_type != "provider.request":
            raise RuntimeError(f"Unsupported provider intent {intent_type!r}")
        _validate_pi_intent_session_key(
            payload,
            session_key=session_key,
            intent_type="provider.request",
            cross_session_message=(
                "Pi sidecar provider.request cannot target a different session_key"
            ),
        )
        sidecar_payload = _provider_request_sidecar_payload(payload)
        _validate_pi_provider_request_payload_fields(sidecar_payload)
        _validate_provider_request_sidecar_tools(sidecar_payload)
        _validate_provider_request_sidecar_config(sidecar_payload)

        from opensquilla.provider import DoneEvent as ProviderDoneEvent
        from opensquilla.provider import ErrorEvent as ProviderErrorEvent
        from opensquilla.provider import ProviderHeartbeatEvent
        from opensquilla.provider import TextDeltaEvent as ProviderTextDeltaEvent
        from opensquilla.provider import ToolUseDeltaEvent as ProviderToolUseDeltaEvent
        from opensquilla.provider import ToolUseEndEvent as ProviderToolUseEndEvent
        from opensquilla.provider import ToolUseStartEvent as ProviderToolUseStartEvent

        events: list[AgentEvent] = []
        text_parts: list[str] = []
        pending_tool_starts: dict[str, ProviderToolUseStartEvent] = {}
        pending_tool_fragments: dict[str, list[str]] = {}
        provider_messages = _provider_messages_from_payload(
            payload,
            host_agent=self._host_agent,
        )
        async for raw_event in self._host_agent.provider.chat(
            provider_messages,
            tools=_provider_tools_from_payload(payload, self._host_agent),
            config=_provider_chat_config_from_payload(
                payload,
                self._host_agent,
                messages=provider_messages,
            ),
        ):
            if isinstance(raw_event, ProviderTextDeltaEvent):
                text = _provider_public_string(raw_event, "text.delta", "text")
                text_parts.append(text)
                events.append(TextDeltaEvent(text=text))
            elif isinstance(raw_event, ProviderToolUseStartEvent):
                tool_use_id = _provider_tool_use_string(
                    raw_event,
                    "start",
                    "tool_use_id",
                )
                tool_name = _provider_tool_use_string(
                    raw_event,
                    "start",
                    "tool_name",
                )
                synthetic_from_text = _provider_tool_use_bool(
                    raw_event,
                    "start",
                    "synthetic_from_text",
                )
                if tool_use_id in pending_tool_starts:
                    raise RuntimeError(
                        "Pi provider.request received duplicate provider tool-use "
                        f"start {tool_use_id!r}"
                    )
                pending_tool_starts[tool_use_id] = raw_event
                pending_tool_fragments[tool_use_id] = []
                events.append(
                    ToolUseStartEvent(
                        tool_use_id=tool_use_id,
                        tool_name=tool_name,
                        synthetic_from_text=synthetic_from_text,
                    )
                )
            elif isinstance(raw_event, ProviderToolUseDeltaEvent):
                tool_use_id = _provider_tool_use_string(
                    raw_event,
                    "delta",
                    "tool_use_id",
                )
                json_fragment = _provider_tool_use_string(
                    raw_event,
                    "delta",
                    "json_fragment",
                )
                fragments = pending_tool_fragments.get(tool_use_id)
                if fragments is None:
                    raise RuntimeError(
                        "Pi provider.request received provider tool-use delta "
                        f"without start {tool_use_id!r}"
                    )
                fragments.append(json_fragment)
            elif isinstance(raw_event, ProviderToolUseEndEvent):
                tool_use_id = _provider_tool_use_string(
                    raw_event,
                    "end",
                    "tool_use_id",
                )
                end_tool_name = _provider_tool_use_string(
                    raw_event,
                    "end",
                    "tool_name",
                )
                end_synthetic_from_text = _provider_tool_use_bool(
                    raw_event,
                    "end",
                    "synthetic_from_text",
                )
                start = pending_tool_starts.pop(tool_use_id, None)
                fragments = pending_tool_fragments.pop(tool_use_id, None)
                if start is None or fragments is None:
                    raise RuntimeError(
                        "Pi provider.request received provider tool-use end "
                        f"without start {tool_use_id!r}"
                    )
                if end_tool_name != start.tool_name:
                    raise RuntimeError(
                        "provider tool-use end tool_name must match start tool_name"
                    )
                tool_name = end_tool_name
                arguments = _sidecar_input_copy(raw_event.arguments)
                if arguments is None:
                    arguments = {}
                if not arguments and fragments:
                    try:
                        parsed_arguments = json.loads("".join(fragments))
                    except json.JSONDecodeError as exc:
                        raise RuntimeError(
                            "Pi provider.request provider tool-use arguments "
                            "must decode to an object"
                        ) from exc
                    if not isinstance(parsed_arguments, dict):
                        raise RuntimeError(
                            "Pi provider.request provider tool-use arguments "
                            "must decode to an object"
                        )
                    arguments = parsed_arguments
                if not isinstance(arguments, dict):
                    raise RuntimeError(
                        "Pi provider.request provider tool-use arguments "
                        "must be an object"
                    )
                arguments = cast(dict[str, Any], _sidecar_json_input_copy(arguments))
                events.append(
                    ToolUseEndEvent(
                        tool_use_id=tool_use_id,
                        tool_name=tool_name,
                        arguments=arguments,
                        synthetic_from_text=end_synthetic_from_text
                        or start.synthetic_from_text,
                    )
                )
            elif isinstance(raw_event, ProviderErrorEvent):
                message = _provider_public_string(raw_event, "error", "message")
                code = _provider_public_string(raw_event, "error", "code")
                events.append(ErrorEvent(message=message, code=code))
            elif isinstance(raw_event, ProviderHeartbeatEvent):
                phase = _provider_public_string(raw_event, "heartbeat", "phase")
                message = _provider_public_string(raw_event, "heartbeat", "message")
                events.append(
                    RunHeartbeatEvent(
                        phase=phase,
                        message=message,
                    )
                )
            elif isinstance(raw_event, ProviderDoneEvent):
                stop_reason = raw_event.stop_reason
                if not isinstance(stop_reason, str):
                    raise RuntimeError("provider done stop_reason must be a string")
                if self._provider_usage is not None:
                    self._provider_usage.record(raw_event)
                    continue
                input_tokens = _provider_usage_int(raw_event, "input_tokens")
                output_tokens = _provider_usage_int(raw_event, "output_tokens")
                reasoning_tokens = _provider_usage_int(raw_event, "reasoning_tokens")
                cached_tokens = _provider_usage_int_less_than_or_equal(
                    raw_event,
                    "cached_tokens",
                    input_tokens,
                    "input_tokens",
                )
                cache_write_tokens = _provider_usage_int_less_than_or_equal(
                    raw_event,
                    "cache_write_tokens",
                    input_tokens,
                    "input_tokens",
                )
                billed_cost = _provider_usage_float(raw_event, "billed_cost")
                cost_source = _provider_usage_string(raw_event, "cost_source", "none")
                model = _provider_usage_string(raw_event, "model")
                reasoning_content = _provider_usage_string(
                    raw_event,
                    "reasoning_content",
                    allow_none=True,
                )
                if stop_reason not in {"end_turn", "stop"}:
                    continue
                events.append(
                    DoneEvent(
                        text="".join(text_parts),
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        reasoning_tokens=reasoning_tokens,
                        cached_tokens=cached_tokens,
                        cache_write_tokens=cache_write_tokens,
                        iterations=1,
                        cost_usd=billed_cost,
                        billed_cost=billed_cost,
                        cost_source=(
                            cost_source
                            if cost_source != "none"
                            else (
                                "provider_billed"
                                if billed_cost > 0.0
                                else "unavailable"
                            )
                        ),
                        model=model
                        or _config_string_or_empty(
                            self._host_agent.config,
                            "model_id",
                            owner="provider config",
                        ),
                        reasoning_content=reasoning_content or None,
                    )
                )
        if pending_tool_starts:
            pending = ", ".join(sorted(pending_tool_starts))
            raise RuntimeError(
                "Pi provider.request ended with pending provider tool-use "
                f"streams: {pending}"
            )
        _validate_host_port_terminal_batch(events, port_name="provider")
        return events


class OpenSquillaToolBridgeHostPort:
    """Host-owned tool bridge for Pi sidecar tool intents."""

    def __init__(self, host_agent: Any) -> None:
        self._host_agent = host_agent

    def refresh_system_prompt(self, system_prompt: str) -> None:
        refresh = getattr(self._host_agent, "refresh_system_prompt", None)
        if callable(refresh):
            refresh(system_prompt)

    async def handle_intent(
        self,
        *,
        intent_type: str,
        payload: dict[str, Any],
        session_key: str,
    ) -> list[AgentEvent]:
        _ = session_key
        if intent_type not in {"tool.call.prepare", "tool.call.execute"}:
            raise RuntimeError(f"Unsupported tool bridge intent {intent_type!r}")
        _validate_pi_intent_session_key(
            payload,
            session_key=session_key,
            intent_type=intent_type,
            cross_session_message=(
                "Pi sidecar tool intent cannot target a different session_key"
            ),
        )
        _validate_pi_tool_intent_payload_fields(payload)
        tool_call = _tool_call_from_pi_payload(payload)
        if tool_call.tool_name == "sessions_yield":
            raise RuntimeError(
                "KernelHostPorts.tool_bridge must not execute sessions_yield"
            )
        if intent_type == "tool.call.prepare":
            return [
                ToolUseStartEvent(
                    tool_use_id=tool_call.tool_use_id,
                    tool_name=tool_call.tool_name,
                    synthetic_from_text=tool_call.synthetic_from_text,
                )
            ]
        return await self._execute_tool_call(tool_call)

    async def _execute_tool_call(self, tool_call: ToolCall) -> list[AgentEvent]:
        host_agent = self._host_agent

        async def _run_host_tool(current_call: ToolCall) -> ToolResult:
            timeout_fn = getattr(host_agent, "_tool_execution_timeout", None)
            if not callable(timeout_fn):
                return await host_agent._execute_tool(current_call)
            timeout = max(0.001, float(timeout_fn(current_call)))
            try:
                return await asyncio.wait_for(
                    host_agent._execute_tool(current_call),
                    timeout=timeout,
                )
            except TimeoutError:
                from opensquilla.execution_status import runtime_execution_status

                return ToolResult(
                    tool_use_id=current_call.tool_use_id,
                    tool_name=current_call.tool_name,
                    content=(
                        f"Tool '{current_call.tool_name}' timed out after "
                        f"{timeout}s"
                    ),
                    is_error=True,
                    execution_status=runtime_execution_status(
                        "timeout",
                        reason="runtime_timeout",
                        timed_out=True,
                    ),
                )

        def _artifact_event_from_result_artifact(artifact: Any) -> ArtifactEvent:
            return _artifact_event_from_tool_artifact(artifact)

        def _router_replay_event(content: Any) -> AgentEvent | None:
            from opensquilla.router_control import router_control_replay_event_from_payload

            replay_event = router_control_replay_event_from_payload(content)
            if replay_event is None:
                return None
            return _validated_router_replay_event(replay_event)

        def _pending_approval(content: Any) -> dict[str, Any] | None:
            from opensquilla.engine.agent import _pending_approval_payload

            return _pending_approval_payload(content)

        async def _wait_for_approval(payload: dict[str, Any]) -> None:
            from opensquilla.engine.agent import _wait_for_pending_approval_resolution

            await _wait_for_pending_approval_resolution(
                payload,
                timeout=host_agent._approval_wait_timeout(),
            )

        async def _append_projected_tool_result_events(
            *,
            result: ToolResult,
            result_tool_call: ToolCall,
            events: list[AgentEvent],
        ) -> None:
            for artifact in _tool_result_artifacts(result):
                events.append(_artifact_event_from_result_artifact(artifact))

            projected_result = await host_agent._project_tool_result_for_delivery(
                result,
                tool_call=result_tool_call,
            )
            events.append(_tool_result_event_from_projection(projected_result, result_tool_call))
            replay_event = _router_replay_event(result.content)
            if replay_event is not None:
                events.append(replay_event)

        async def _run_host_meta_tool(current_call: ToolCall) -> list[AgentEvent]:
            from opensquilla.tools.types import ToolContext, current_tool_context

            run_meta = getattr(host_agent, "_run_one_streaming", None)
            if not callable(run_meta):
                raise RuntimeError("meta_invoke requires host agent meta stream support")
            tool_context = (
                current_tool_context.get()
                or getattr(host_agent, "_tool_context", None)
                or ToolContext()
            )
            events: list[AgentEvent] = []
            async for event in run_meta(current_call, tool_context):
                if isinstance(event, ToolResult):
                    await _append_projected_tool_result_events(
                        result=event,
                        result_tool_call=current_call,
                        events=events,
                    )
                elif isinstance(event, (ToolUseStartEvent, ToolUseEndEvent, ToolResultEvent)):
                    if (
                        event.tool_use_id == current_call.tool_use_id
                        and event.tool_name == current_call.tool_name
                    ) or event.tool_name.startswith("meta-step:"):
                        events.append(event)
                else:
                    events.append(event)
            return events

        if tool_call.tool_name == "meta_invoke":
            return await _run_host_meta_tool(tool_call)

        result = await _run_host_tool(tool_call)
        result_tool_call = tool_call
        events: list[AgentEvent] = []
        await _append_projected_tool_result_events(
            result=result,
            result_tool_call=result_tool_call,
            events=events,
        )

        pending_approval = _pending_approval(result.content)
        if pending_approval is not None and not tool_call.arguments.get("approval_id"):
            await _wait_for_approval(pending_approval)
            retry_arguments = dict(tool_call.arguments)
            retry_arguments["approval_id"] = pending_approval["approval_id"]
            retry_call = ToolCall(
                tool_use_id=tool_call.tool_use_id,
                tool_name=tool_call.tool_name,
                arguments=retry_arguments,
                synthetic_from_text=tool_call.synthetic_from_text,
                origin_trace=tool_call.origin_trace,
            )
            retry_result = await _run_host_tool(retry_call)
            await _append_projected_tool_result_events(
                result=retry_result,
                result_tool_call=retry_call,
                events=events,
            )

        return events


class OpenSquillaSessionWritesHostPort:
    """Host-owned session write port for Pi sidecar session intents."""

    def __init__(
        self,
        *,
        session_manager: Any,
        session_write_context_factory: Any | None = None,
    ) -> None:
        self._session_manager = session_manager
        self._session_write_context_factory = session_write_context_factory

    async def handle_intent(
        self,
        *,
        intent_type: str,
        payload: dict[str, Any],
        session_key: str,
    ) -> list[AgentEvent]:
        if intent_type != "session.write.enqueue":
            raise RuntimeError(f"Unsupported session write intent {intent_type!r}")
        target_session_key = _validate_pi_intent_session_key(
            payload,
            session_key=session_key,
            intent_type="session.write.enqueue",
            cross_session_message=(
                "Pi sidecar session.write.enqueue cannot target a different "
                "session_key"
            ),
        )
        _validate_pi_intent_payload_fields("session.write.enqueue", payload)
        raw_role = payload.get("role", "assistant")
        if not isinstance(raw_role, str):
            raise RuntimeError("session.write.enqueue role must be a string")
        role = raw_role.strip().lower()
        if _is_privileged_transcript_role(role):
            raise RuntimeError(
                "Pi sidecar session.write.enqueue cannot write privileged role "
                f"{raw_role!r}"
            )
        if role not in {"user", "assistant", "tool"}:
            raise RuntimeError(
                "session.write.enqueue role must be user, assistant, or tool"
            )
        if "content" not in payload:
            content = ""
        else:
            raw_content = payload["content"]
            if not isinstance(raw_content, str):
                raise RuntimeError("session.write.enqueue content must be a string")
            content = raw_content
        if "reasoning_content" not in payload:
            reasoning_content = None
        else:
            raw_reasoning_content = payload["reasoning_content"]
            if not isinstance(raw_reasoning_content, str):
                raise RuntimeError(
                    "session.write.enqueue reasoning_content must be a string"
                )
            reasoning_content = raw_reasoning_content
        if "tool_calls" not in payload:
            tool_calls = None
        else:
            raw_tool_calls = payload["tool_calls"]
            if not isinstance(raw_tool_calls, list):
                raise RuntimeError("session.write.enqueue tool_calls must be a list")
            if not all(isinstance(tool_call, dict) for tool_call in raw_tool_calls):
                raise RuntimeError(
                    "session.write.enqueue tool_calls entries must be objects"
                )
            tool_calls = cast(list[Any], _sidecar_json_input_copy(raw_tool_calls))
        if "turn_usage" not in payload:
            turn_usage = None
        else:
            raw_turn_usage = payload["turn_usage"]
            if not isinstance(raw_turn_usage, dict):
                raise RuntimeError("session.write.enqueue turn_usage must be an object")
            turn_usage = cast(dict[str, Any], _sidecar_json_input_copy(raw_turn_usage))
            _validate_session_write_turn_usage(turn_usage)
        if "token_count" not in payload:
            token_count = None
        else:
            raw_token_count = payload["token_count"]
            if not isinstance(raw_token_count, int) or isinstance(raw_token_count, bool):
                raise RuntimeError("session.write.enqueue token_count must be an integer")
            if raw_token_count < 0:
                raise RuntimeError(
                    "session.write.enqueue token_count must be a non-negative integer"
                )
            token_count = raw_token_count
        async with _session_write_context(
            self._session_write_context_factory,
            target_session_key,
        ):
            await self._session_manager.append_message(
                target_session_key,
                role=role,
                content=content,
                tool_calls=tool_calls,
                reasoning_content=reasoning_content,
                turn_usage=turn_usage,
                token_count=token_count,
            )
        return []


class OpenSquillaOrchestrationHostPort:
    """Host-owned orchestration port for Pi yield intents."""

    def __init__(self, host_agent: Any) -> None:
        self._tool_bridge = OpenSquillaToolBridgeHostPort(host_agent)

    async def handle_intent(
        self,
        *,
        intent_type: str,
        payload: dict[str, Any],
        session_key: str,
    ) -> list[AgentEvent]:
        if intent_type != "yield.request":
            raise RuntimeError(f"Unsupported orchestration intent {intent_type!r}")
        _validate_pi_intent_session_key(
            payload,
            session_key=session_key,
            intent_type="yield.request",
            cross_session_message=(
                "Pi sidecar yield.request cannot target a different session_key"
            ),
        )
        _validate_pi_intent_payload_fields("yield.request", payload)
        arguments: dict[str, Any] = {}
        if "message" in payload:
            arguments["message"] = _sidecar_json_input_copy(payload["message"])
        if "reason" in payload:
            arguments["reason"] = _sidecar_json_input_copy(payload["reason"])
        timeout = None
        if "timeout_seconds" in payload:
            timeout = _optional_non_negative_float(
                payload["timeout_seconds"],
                field_name="yield.request timeout_seconds",
            )
        if timeout is not None:
            arguments["timeout_seconds"] = min(
                timeout,
                PI_YIELD_REQUEST_MAX_TIMEOUT_SECONDS,
            )
        if "tool_call_id" not in payload:
            tool_call_id = "yield-request"
        else:
            raw_tool_call_id = payload["tool_call_id"]
            if not isinstance(raw_tool_call_id, str):
                raise RuntimeError("yield.request tool_call_id must be a string")
            tool_call_id = raw_tool_call_id if raw_tool_call_id.strip() else "yield-request"
        return await self._tool_bridge._execute_tool_call(
            ToolCall(
                tool_use_id=tool_call_id,
                tool_name="sessions_yield",
                arguments=arguments,
            )
        )


class OpenSquillaSavepointHostPort:
    """Host-owned savepoint port for Pi sidecar lifecycle intents."""

    def __init__(
        self,
        *,
        session_manager: Any,
        session_write_context_factory: Any | None = None,
    ) -> None:
        self._session_manager = session_manager
        self._session_write_context_factory = session_write_context_factory

    async def handle_intent(
        self,
        *,
        intent_type: str,
        payload: dict[str, Any],
        session_key: str,
    ) -> list[AgentEvent]:
        if intent_type != "savepoint.request":
            raise RuntimeError(f"Unsupported savepoint intent {intent_type!r}")
        if not hasattr(self._session_manager, "record_memory_checkpoint"):
            raise RuntimeError(
                "KernelHostPorts.savepoints requires "
                "session_manager.record_memory_checkpoint"
            )
        target_session_key = _validate_pi_intent_session_key(
            payload,
            session_key=session_key,
            intent_type="savepoint.request",
            cross_session_message=(
                "Pi sidecar savepoint.request cannot target a different session_key"
            ),
        )
        _validate_pi_intent_payload_fields("savepoint.request", payload)
        if "transcript" not in payload:
            transcript = []
        elif isinstance(payload["transcript"], list):
            raw_transcript = payload["transcript"]
            transcript = [
                _pi_checkpoint_transcript_entry_from_payload(entry)
                for entry in raw_transcript
            ]
        else:
            raise RuntimeError("savepoint.request transcript must be a list")
        for entry in transcript:
            if _is_privileged_transcript_role(entry.role):
                raise RuntimeError(
                    "Pi sidecar savepoint.request cannot checkpoint privileged "
                    "role 'system'"
                )
        if "turn_id" not in payload:
            turn_id = ""
        else:
            raw_turn_id = payload["turn_id"]
            if not isinstance(raw_turn_id, str):
                raise RuntimeError("savepoint.request turn_id must be a string")
            turn_id = raw_turn_id if raw_turn_id.strip() else ""
        if "source" not in payload or payload["source"] == "":
            source = "pi_sidecar"
        else:
            raw_source = payload["source"]
            if not isinstance(raw_source, str):
                raise RuntimeError("savepoint.request source must be a string")
            source = raw_source.strip()
            if not source:
                source = "pi_sidecar"
            elif _is_privileged_savepoint_source(source):
                raise RuntimeError(
                    "Pi sidecar savepoint.request cannot claim privileged source "
                    f"{raw_source!r}"
                )
        async with _session_write_context(
            self._session_write_context_factory,
            target_session_key,
        ):
            await self._session_manager.record_memory_checkpoint(
                target_session_key,
                transcript,
                turn_id=turn_id,
                source=source,
            )
        return []


def _queue_poll_heartbeat(record: Any, *, task_id: str) -> RunHeartbeatEvent:
    status = getattr(record, "status", "")
    status_value = getattr(status, "value", status)
    if status_value is None:
        status_text = ""
    elif not isinstance(status_value, str):
        raise RuntimeError("queue.poll status must be a string")
    else:
        status_text = status_value
    record_task_id = getattr(record, "task_id", "")
    if record_task_id is None or record_task_id == "":
        heartbeat_task_id = task_id
    elif not isinstance(record_task_id, str):
        raise RuntimeError("queue.poll heartbeat task_id must be a string")
    else:
        heartbeat_task_id = record_task_id
    terminal_reason = getattr(record, "terminal_reason", None)
    if terminal_reason is not None and not isinstance(terminal_reason, str):
        raise RuntimeError("queue.poll terminal_reason must be a string or None")
    payload: dict[str, Any] = {
        "status": status_text,
        "task_id": heartbeat_task_id,
    }
    if terminal_reason:
        payload["terminal_reason"] = terminal_reason
    return RunHeartbeatEvent(
        phase="queue",
        message=json.dumps(payload, sort_keys=True, separators=(",", ":")),
    )


class OpenSquillaQueueHostPort:
    """Host-owned queue port backed by OpenSquilla TaskRuntime."""

    def __init__(self, *, task_runtime: Any) -> None:
        self._task_runtime = task_runtime

    async def handle_intent(
        self,
        *,
        intent_type: str,
        payload: dict[str, Any],
        session_key: str,
    ) -> list[AgentEvent]:
        if intent_type != "queue.poll":
            raise RuntimeError(f"Unsupported queue intent {intent_type!r}")
        _validate_pi_intent_session_key(
            payload,
            session_key=session_key,
            intent_type="queue.poll",
            cross_session_message=(
                "Pi sidecar queue.poll cannot target a different session_key"
            ),
        )
        _validate_pi_intent_payload_fields("queue.poll", payload)
        raw_task_id = payload.get("task_id", "")
        if not isinstance(raw_task_id, str):
            raise RuntimeError("queue.poll task_id must be a string")
        task_id = raw_task_id.strip()
        if not task_id:
            raise RuntimeError("queue.poll requires task_id")
        raw_operation = payload["operation"] if "operation" in payload else ""
        raw_action = payload["action"] if "action" in payload else ""
        if not isinstance(raw_operation, str):
            raise RuntimeError("queue.poll operation must be a string")
        if not isinstance(raw_action, str):
            raise RuntimeError("queue.poll action must be a string")
        requested_operation = (raw_operation or raw_action or "").strip()
        if requested_operation and requested_operation != "poll":
            raise RuntimeError(
                "queue.poll cannot request queue control operation "
                f"{requested_operation!r}"
            )
        timeout = None
        if "timeout_seconds" in payload:
            timeout = _optional_non_negative_float(
                payload["timeout_seconds"],
                field_name="queue.poll timeout_seconds",
            )
        if timeout is not None:
            timeout = min(timeout, PI_QUEUE_POLL_MAX_TIMEOUT_SECONDS)
        record: Any
        if timeout is not None and hasattr(self._task_runtime, "wait"):
            record = await self._task_runtime.wait(task_id, timeout=timeout)
        elif hasattr(self._task_runtime, "status"):
            record = await self._task_runtime.status(task_id)
        elif hasattr(self._task_runtime, "wait"):
            record = await self._task_runtime.wait(task_id)
        else:
            raise RuntimeError("KernelHostPorts.queue requires TaskRuntime status or wait")
        return [_queue_poll_heartbeat(record, task_id=task_id)]


def _finalizer_usage_int(usage: dict[str, Any], field_name: str) -> int:
    value = usage[field_name] if field_name in usage else 0
    if value is None:
        raise RuntimeError(f"finalizer usage {field_name} must be an integer")
    if not isinstance(value, int) or isinstance(value, bool):
        raise RuntimeError(f"finalizer usage {field_name} must be an integer")
    if value < 0:
        raise RuntimeError(
            f"finalizer usage {field_name} must be a non-negative integer"
        )
    return value


def _finalizer_usage_int_less_than_or_equal(
    usage: dict[str, Any],
    field_name: str,
    maximum: int,
    maximum_field_name: str,
) -> int:
    value = _finalizer_usage_int(usage, field_name)
    if value > maximum:
        raise RuntimeError(
            f"finalizer usage {field_name} must be <= {maximum_field_name}"
        )
    return value


def _finalizer_usage_float(usage: dict[str, Any], field_name: str) -> float:
    value = usage[field_name] if field_name in usage else 0.0
    if value is None:
        raise RuntimeError(f"finalizer usage {field_name} must be a number")
    result = _finite_number(value, field_name=f"finalizer usage {field_name}")
    if result < 0:
        raise RuntimeError(
            f"finalizer usage {field_name} must be a non-negative number"
        )
    return result


def _finalizer_usage_string(
    usage: dict[str, Any],
    field_name: str,
    default: str = "",
) -> str:
    value = usage[field_name] if field_name in usage else default
    if value is None:
        raise RuntimeError(f"finalizer usage {field_name} must be a string")
    if value == "":
        return default
    if not isinstance(value, str):
        raise RuntimeError(f"finalizer usage {field_name} must be a string")
    return value


def _finalizer_usage_optional_string(
    usage: dict[str, Any],
    field_name: str,
) -> str | None:
    value = usage.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise RuntimeError(
            f"finalizer usage {field_name} must be a string or None"
        )
    return value


class OpenSquillaFinalizerHostPort:
    """Host-owned terminal success finalizer for foreign kernels."""

    def __init__(
        self,
        *,
        config: Any,
        provider_usage: _ProviderUsageAccumulator | None = None,
    ) -> None:
        self._config = config
        self._provider_usage = provider_usage

    def reset_provider_usage(self) -> None:
        if self._provider_usage is not None:
            self._provider_usage.reset()

    async def handle_intent(
        self,
        *,
        intent_type: str,
        payload: dict[str, Any],
        session_key: str,
    ) -> list[AgentEvent]:
        _ = session_key
        if intent_type != "turn.finalize":
            raise RuntimeError(f"Unsupported finalizer intent {intent_type!r}")
        usage = (
            self._provider_usage.drain()
            if self._provider_usage is not None
            else {}
        )
        if not isinstance(usage, dict):
            raise RuntimeError("finalizer usage summary must be an object")
        input_tokens = _finalizer_usage_int(usage, "input_tokens")
        output_tokens = _finalizer_usage_int(usage, "output_tokens")
        reasoning_tokens = _finalizer_usage_int(usage, "reasoning_tokens")
        cached_tokens = _finalizer_usage_int_less_than_or_equal(
            usage,
            "cached_tokens",
            input_tokens,
            "input_tokens",
        )
        cache_write_tokens = _finalizer_usage_int_less_than_or_equal(
            usage,
            "cache_write_tokens",
            input_tokens,
            "input_tokens",
        )
        billed_cost = _finalizer_usage_float(usage, "billed_cost")
        provider_done_count = _finalizer_usage_int(usage, "provider_done_count")
        usage_cost_source = _finalizer_usage_string(usage, "cost_source", "none")
        cost_source = (
            usage_cost_source
            if usage_cost_source != "none"
            else ("provider_billed" if billed_cost > 0.0 else "unavailable")
        )
        raw_payload_model = None
        if "model" in payload:
            raw_payload_model = payload["model"]
            if not isinstance(raw_payload_model, str):
                raise RuntimeError("turn.finalize model must be a string")
        usage_model = _finalizer_usage_string(usage, "model")
        config_model = _config_string_or_empty(
            self._config,
            "model_id",
            owner="finalizer config",
        )
        model = usage_model or raw_payload_model or config_model
        if "text" not in payload:
            text = ""
        else:
            raw_text = payload["text"]
            if not isinstance(raw_text, str):
                raise RuntimeError("turn.finalize text must be a string")
            text = raw_text
        reasoning_content = _finalizer_usage_optional_string(
            usage,
            "reasoning_content",
        )
        runtime_context_hash = None
        if "runtime_context_hash" in payload:
            raw_runtime_context_hash = payload["runtime_context_hash"]
            if raw_runtime_context_hash is not None and not isinstance(
                raw_runtime_context_hash,
                str,
            ):
                raise RuntimeError(
                    "turn.finalize runtime_context_hash must be a string or None"
                )
            runtime_context_hash = raw_runtime_context_hash
        runtime_context_chars = 0
        if "runtime_context_chars" in payload:
            raw_runtime_context_chars = payload["runtime_context_chars"]
            if (
                not isinstance(raw_runtime_context_chars, int)
                or raw_runtime_context_chars < 0
            ):
                raise RuntimeError(
                    "turn.finalize runtime_context_chars must be a non-negative integer"
                )
            runtime_context_chars = raw_runtime_context_chars
        return [
            DoneEvent(
                text=text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                reasoning_tokens=reasoning_tokens,
                cached_tokens=cached_tokens,
                cache_write_tokens=cache_write_tokens,
                iterations=provider_done_count,
                cost_usd=billed_cost,
                billed_cost=billed_cost,
                cost_source=cost_source,
                model=model,
                runtime_context_hash=runtime_context_hash,
                runtime_context_chars=runtime_context_chars,
                reasoning_content=reasoning_content,
            )
        ]


class OpenSquillaTelemetryHostPort:
    """Host-owned non-user-facing telemetry sink for foreign kernels."""

    def __init__(self, *, sink: Any | None = None) -> None:
        self._sink = sink

    async def handle_intent(
        self,
        *,
        intent_type: str,
        payload: dict[str, Any],
        session_key: str,
    ) -> list[AgentEvent]:
        _ = session_key
        if intent_type != "telemetry.emit":
            raise RuntimeError(f"Unsupported telemetry intent {intent_type!r}")
        copied_payload = _sidecar_json_input_copy(payload)
        if not isinstance(copied_payload, dict):
            raise RuntimeError("telemetry.emit payload must be an object")
        sink_payload = cast(dict[str, Any], copied_payload)
        _validate_pi_intent_session_key(
            sink_payload,
            session_key=session_key,
            intent_type="telemetry.emit",
            cross_session_message=(
                "Pi sidecar telemetry.emit cannot target a different session_key"
            ),
        )
        _validate_pi_telemetry_reserved_payloads(sink_payload)
        if self._sink is None:
            return []
        if hasattr(self._sink, "emit"):
            sink_call = self._sink.emit
        elif callable(self._sink):
            sink_call = self._sink
        else:
            raise RuntimeError("KernelHostPorts.telemetry sink must be callable or emit")
        try:
            result = sink_call(sink_payload)
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, _AGENT_EVENT_TYPES):
                raise RuntimeError("telemetry sink must not return AgentEvents")
            if isinstance(result, AsyncIterable):
                async for event in result:
                    if isinstance(event, _AGENT_EVENT_TYPES):
                        raise RuntimeError("telemetry sink must not return AgentEvents")
            elif (
                isinstance(result, Iterable)
                and not isinstance(result, (str, bytes, dict))
                and any(isinstance(event, _AGENT_EVENT_TYPES) for event in result)
            ):
                raise RuntimeError("telemetry sink must not return AgentEvents")
        except RuntimeError as exc:
            if str(exc) == "telemetry sink must not return AgentEvents":
                raise
            return []
        except Exception:
            return []
        return []


class PiSidecarProtocolError(RuntimeError):
    """Protocol or contract violation from a Pi sidecar frame."""


def _validate_sidecar_json_payload(value: Any, *, frame_type: str, path: str = "payload") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise PiSidecarProtocolError(
                    f"Pi sidecar {frame_type} payload contains non-JSON object key at {path}"
                )
            _validate_sidecar_json_payload(
                item,
                frame_type=frame_type,
                path=f"{path}.{key}",
            )
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_sidecar_json_payload(
                item,
                frame_type=frame_type,
                path=f"{path}[{index}]",
            )
        return
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float) and math.isfinite(value):
        return
    raise PiSidecarProtocolError(
        f"Pi sidecar {frame_type} payload contains non-JSON value at {path}"
    )


def _validate_sidecar_json_frame_shell(frame: dict[Any, Any]) -> None:
    for key, value in frame.items():
        if not isinstance(key, str):
            raise PiSidecarProtocolError(
                "Pi sidecar frame contains non-JSON object key at frame"
            )
        if key not in _PI_SIDECAR_FRAME_KEYS:
            raise PiSidecarProtocolError(
                f"Pi sidecar frame contains unsupported top-level field {key!r}"
            )
        try:
            _validate_sidecar_json_payload(
                value,
                frame_type="frame",
                path=f"frame.{key}",
            )
        except PiSidecarProtocolError as exc:
            message = str(exc).replace("frame payload contains", "frame contains")
            raise PiSidecarProtocolError(message) from None


class PiSidecarKernelRuntime:
    """Consume Pi sidecar protocol frames behind host-owned OpenSquilla ports."""

    def __init__(
        self,
        *,
        rpc_client: PiRpcClient,
        config: Any,
        session_key: str,
        provider_identity: Any | None = None,
        agent_core_config: AgentCoreConfig | None = None,
        host_ports: KernelHostPorts | None = None,
        tool_definitions: list[Any] | None = None,
        metadata: dict[str, Any] | None = None,
        host_agent: Any | None = None,
        emit_state_events: bool = False,
        inject_host_runtime_context: bool = False,
        emit_yield_tool_start_events: bool = False,
        coalesce_tool_state_events: bool = False,
    ) -> None:
        if not callable(getattr(rpc_client, "stream_prompt", None)):
            raise ValueError(
                "Pi RPC client must provide callable stream_prompt"
            )
        self._rpc_client = rpc_client
        self.config = config
        self.provider = provider_identity or _provider_identity_for_history(None)
        if not isinstance(session_key, str):
            raise RuntimeError("Pi sidecar session_key must be a string")
        if not session_key.strip():
            raise RuntimeError("Pi sidecar session_key must be non-empty")
        self._session_key = session_key
        self._system_prompt = getattr(config, "system_prompt", "")
        self._agent_core_config = agent_core_config or AgentCoreConfig(kernel="pi")
        _validate_pi_kernel_id(self._agent_core_config)
        self._protocol_version = _validate_pi_protocol_version(self._agent_core_config)
        _validate_pi_strict_host_ports(self._agent_core_config)
        self._delegate_provider_feedback_visibility = not (
            self._agent_core_config.allow_test_pi_rpc_client
            or self._agent_core_config.allow_test_pi_rpc_command
        )
        self._host_ports = host_ports or KernelHostPorts()
        self._host_agent = host_agent
        if self._host_ports.finalizer is None:
            self._host_ports.finalizer = OpenSquillaFinalizerHostPort(config=config)
        if self._host_ports.telemetry is None:
            self._host_ports.telemetry = OpenSquillaTelemetryHostPort()
        self._history: list[Any] = []
        self._pending_tool_calls: set[str] = set()
        if tool_definitions is not None and not isinstance(tool_definitions, list):
            raise RuntimeError("Pi sidecar tool_definitions must be a list")
        copied_tool_definitions = _sidecar_json_input_copy(
            [] if tool_definitions is None else tool_definitions
        )
        self._tool_definitions = cast(list[Any], copied_tool_definitions)
        copied_metadata = _sidecar_json_input_copy({} if metadata is None else metadata)
        if not isinstance(copied_metadata, dict):
            raise RuntimeError("Pi sidecar metadata must be an object")
        self._metadata = cast(dict[str, Any], copied_metadata)
        self._turn_index = 0
        self._yield_request_settled = False
        self._active_turn = False
        self._state = AgentState.IDLE
        self._pending_provider_fallback_events: list[AgentEvent] = []
        self._active_turn_input = ""
        self._active_runtime_context = ""
        self._active_runtime_context_hash: str | None = None
        self._active_runtime_context_chars = 0
        self._emit_state_events = emit_state_events
        self._inject_host_runtime_context = inject_host_runtime_context
        self._emit_yield_tool_start_events = emit_yield_tool_start_events
        self._coalesce_tool_state_events = coalesce_tool_state_events

    def refresh_system_prompt(self, system_prompt: str) -> None:
        system_prompt = _kernel_turn_snapshot_required_string(
            system_prompt,
            field_name="system_prompt",
        )
        self._system_prompt = system_prompt
        refreshed_targets: set[int] = set()
        for port in (
            self._host_ports.provider,
            self._host_ports.tool_bridge,
            self._host_ports.orchestration,
        ):
            refresh = getattr(port, "refresh_system_prompt", None)
            if not callable(refresh):
                continue
            refresh_target = getattr(port, "_host_agent", port)
            refresh_id = id(refresh_target)
            if refresh_id in refreshed_targets:
                continue
            refreshed_targets.add(refresh_id)
            refresh(system_prompt)
        if hasattr(self.config, "system_prompt"):
            self.config.system_prompt = system_prompt

    def set_history(self, history: list[Any]) -> None:
        if not isinstance(history, list):
            raise RuntimeError("Pi sidecar history must be a list")
        _sidecar_json_input_copy(history)
        copied_history = _sidecar_input_copy(history)
        self._history = cast(list[Any], copied_history)

    def _transition(self, to: AgentState) -> StateChangeEvent | None:
        event = StateChangeEvent(from_state=self._state, to_state=to)
        self._state = to
        if not self._emit_state_events:
            return None
        return event

    def _transition_if_needed(self, to: AgentState) -> StateChangeEvent | None:
        if self._state == to:
            return None
        return self._transition(to)

    def _host_runtime_context_block(self) -> str:
        if not self._inject_host_runtime_context:
            return ""
        runtime_context = getattr(self._host_agent, "_runtime_context_block", None)
        if not callable(runtime_context):
            return ""
        value = runtime_context()
        if not isinstance(value, str):
            raise RuntimeError("host runtime context block must be a string")
        return value

    def _sync_host_agent_turn_input(self, turn_input: str) -> None:
        host_agent = self._host_agent
        if host_agent is None:
            return
        setattr(host_agent, "_current_turn_message", turn_input)
        config = getattr(host_agent, "config", None)
        metadata = getattr(config, "metadata", None)
        if isinstance(metadata, dict):
            metadata["user_message"] = turn_input

    def _begin_host_runtime_context(self, turn_input: str) -> None:
        self._active_turn_input = turn_input
        self._sync_host_agent_turn_input(turn_input)
        self._active_runtime_context = self._host_runtime_context_block()
        if self._active_runtime_context:
            self._active_runtime_context_hash = hashlib.sha256(
                self._active_runtime_context.encode("utf-8")
            ).hexdigest()[:16]
            self._active_runtime_context_chars = len(self._active_runtime_context)
        else:
            self._active_runtime_context_hash = None
            self._active_runtime_context_chars = 0

    def _host_context_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        request_context = _kernel_turn_snapshot_string(
            getattr(self.config, "request_context_prompt", ""),
            field_name="request_context_prompt",
        )
        if request_context:
            payload["_host_request_context_prompt"] = request_context
        if request_context or self._active_runtime_context:
            payload["_host_turn_input"] = self._active_turn_input
        if self._active_runtime_context:
            payload.update(
                {
                    "_host_runtime_context": self._active_runtime_context,
                    "_host_runtime_context_hash": self._active_runtime_context_hash,
                    "_host_runtime_context_chars": self._active_runtime_context_chars,
                }
            )
        return payload

    async def run_turn(
        self,
        turn_input: str,
        *,
        extra_messages: list[Any] | None = None,
        semantic_message: str | None = None,
    ) -> AsyncIterator[AgentEvent]:
        if self._active_turn:
            raise RuntimeError(
                "Pi sidecar kernel already has an active turn; use host queueing "
                "or create a separate runtime per concurrent session"
            )
        self._active_turn = True
        stream = self._run_turn_unchecked(
            turn_input,
            extra_messages=extra_messages,
            semantic_message=semantic_message,
        )
        try:
            async for event in stream:
                yield event
        finally:
            await _close_async_iterator(stream)
            self._active_turn = False
            self._state = AgentState.IDLE

    async def _run_turn_unchecked(
        self,
        turn_input: str,
        *,
        extra_messages: list[Any] | None = None,
        semantic_message: str | None = None,
    ) -> AsyncIterator[AgentEvent]:
        text_parts: list[str] = []
        terminal_seen = False
        self._yield_request_settled = False
        self._pending_provider_fallback_events = []
        self._reset_provider_usage()
        self._turn_index += 1
        snapshot_turn_input = _kernel_turn_snapshot_required_string(
            turn_input,
            field_name="turn_input",
        )
        self._begin_host_runtime_context(snapshot_turn_input)
        transition = self._transition(AgentState.THINKING)
        if transition is not None:
            yield transition
        turn_history = cast(list[Any], _sidecar_json_input_copy(self._history))
        if extra_messages is not None and not isinstance(extra_messages, list):
            raise RuntimeError(
                "KernelTurnSnapshot extra_messages must be a list or None"
            )
        turn_extra_messages = (
            _kernel_turn_snapshot_optional_list(
                _sidecar_json_input_copy(extra_messages),
                field_name="extra_messages",
            )
            if extra_messages is not None
            else None
        )
        turn_tool_definitions = cast(
            list[Any],
            _sidecar_json_input_copy(self._tool_definitions),
        )
        snapshot_extra_messages = (
            cast(list[Any], _sidecar_json_input_copy(turn_extra_messages))
            if turn_extra_messages is not None
            else None
        )
        snapshot_system_prompt = _kernel_turn_snapshot_string(
            self._system_prompt,
            field_name="system_prompt",
        )
        snapshot_request_context_prompt = _kernel_turn_snapshot_string(
            getattr(self.config, "request_context_prompt", ""),
            field_name="request_context_prompt",
        )
        snapshot_model_id = _kernel_turn_snapshot_string(
            getattr(self.config, "model_id", ""),
            field_name="model_id",
        )
        snapshot_semantic_message = _kernel_turn_snapshot_optional_string(
            semantic_message,
            field_name="semantic_message",
        )
        snapshot_metadata = cast(dict[str, Any], _sidecar_json_input_copy(self._metadata))
        snapshot_metadata.update(_host_runtime_policy_snapshot_metadata(self.config))
        if self._active_runtime_context:
            snapshot_metadata.update(
                {
                    "runtime_context": self._active_runtime_context,
                    "runtime_context_hash": self._active_runtime_context_hash,
                    "runtime_context_chars": self._active_runtime_context_chars,
                }
            )
        turn_snapshot = KernelTurnSnapshot(
            session_key=self._session_key,
            agent_id=_agent_id_from_session_key(self._session_key),
            turn_id=f"{self._session_key}:turn-{self._turn_index}",
            turn_input=snapshot_turn_input,
            system_prompt=snapshot_system_prompt,
            request_context_prompt=snapshot_request_context_prompt,
            model_id=snapshot_model_id,
            tool_definitions=cast(list[Any], _sidecar_json_input_copy(turn_tool_definitions)),
            extra_messages=snapshot_extra_messages,
            semantic_message=snapshot_semantic_message,
            metadata=snapshot_metadata,
        )
        try:
            stream = self._rpc_client.stream_prompt(
                snapshot_turn_input,
                extra_messages=turn_extra_messages,
                semantic_message=snapshot_semantic_message,
                session_key=self._session_key,
                session_id=turn_snapshot.session_id,
                system_prompt=snapshot_system_prompt,
                history=turn_history,
                protocol_version=self._protocol_version,
                turn_snapshot=turn_snapshot,
            )
        except (GeneratorExit, asyncio.CancelledError):
            self._pending_tool_calls.clear()
            self._reset_provider_usage()
            raise
        except Exception as exc:
            self._pending_tool_calls.clear()
            self._reset_provider_usage()
            yield ErrorEvent(message=str(exc), code="pi_sidecar_error")
            return
        try:
            try:
                async for raw_event in stream:
                    if self._yield_request_settled:
                        raise PiSidecarProtocolError(
                            "Pi sidecar emitted frame after yield.request settled"
                        )
                    async for event in self._normalize_event(raw_event, text_parts):
                        if self._pending_provider_fallback_events and isinstance(
                            event,
                            (
                                TextDeltaEvent,
                                ToolUseStartEvent,
                                ToolUseEndEvent,
                                ToolResultEvent,
                                DoneEvent,
                                ErrorEvent,
                            ),
                        ):
                            self._pending_provider_fallback_events = []
                        if isinstance(event, TextDeltaEvent):
                            transition = self._transition_if_needed(
                                AgentState.STREAMING
                            )
                            if transition is not None:
                                yield transition
                            text_parts.append(event.text)
                        elif isinstance(event, ErrorEvent):
                            self._pending_tool_calls.clear()
                            self._reset_provider_usage()
                            transition = self._transition_if_needed(AgentState.ERROR)
                            if transition is not None:
                                yield transition
                            yield event
                            return
                        elif isinstance(event, DoneEvent):
                            if self._pending_tool_calls:
                                pending = ", ".join(sorted(self._pending_tool_calls))
                                raise PiSidecarProtocolError(
                                    "Pi sidecar terminal host event rejected with "
                                    f"pending tool calls: {pending}"
                                )
                            transition = self._transition_if_needed(AgentState.DONE)
                            if transition is not None:
                                yield transition
                            yield event
                            return
                        yield event
                    if self._yield_request_settled:
                        break
            except (GeneratorExit, asyncio.CancelledError):
                self._pending_tool_calls.clear()
                self._reset_provider_usage()
                raise
            finally:
                await _close_async_iterator(stream)
        except PiSidecarProtocolError:
            self._pending_tool_calls.clear()
            self._reset_provider_usage()
            raise
        except Exception as exc:
            self._pending_tool_calls.clear()
            self._reset_provider_usage()
            yield ErrorEvent(message=str(exc), code="pi_sidecar_error")
            return

        if self._pending_tool_calls:
            pending = ", ".join(sorted(self._pending_tool_calls))
            self._pending_tool_calls.clear()
            self._reset_provider_usage()
            raise PiSidecarProtocolError(
                "Pi sidecar stream ended with pending tool calls: "
                f"{pending}"
            )

        if self._pending_provider_fallback_events:
            fallback_events = self._pending_provider_fallback_events
            self._pending_provider_fallback_events = []
            for event in fallback_events:
                if isinstance(event, TextDeltaEvent):
                    transition = self._transition_if_needed(AgentState.STREAMING)
                    if transition is not None:
                        yield transition
                    text_parts.append(event.text)
                elif isinstance(event, ErrorEvent):
                    transition = self._transition_if_needed(AgentState.ERROR)
                    if transition is not None:
                        yield transition
                    yield event
                    return
                elif isinstance(event, DoneEvent):
                    transition = self._transition_if_needed(AgentState.DONE)
                    if transition is not None:
                        yield transition
                    yield event
                    return
                yield event

        if not terminal_seen:
            try:
                async for event in self._finalize_turn(text="".join(text_parts)):
                    yield event
            except PiSidecarProtocolError:
                self._pending_tool_calls.clear()
                self._reset_provider_usage()
                raise
            except Exception as exc:
                self._pending_tool_calls.clear()
                self._reset_provider_usage()
                yield ErrorEvent(message=str(exc), code="pi_sidecar_error")
                return

    def _reset_provider_usage(self) -> None:
        finalizer = self._host_ports.finalizer
        reset = getattr(finalizer, "reset_provider_usage", None)
        if callable(reset):
            reset()

    async def _finalize_turn(self, *, text: str) -> AsyncIterator[AgentEvent]:
        finalizer = self._host_ports.finalizer
        if finalizer is None:
            raise PiSidecarProtocolError(
                "Pi sidecar terminal success requires KernelHostPorts.finalizer"
            )
        payload = {
            "text": text,
            "model": _kernel_turn_snapshot_string(
                getattr(self.config, "model_id", ""),
                field_name="model_id",
            ),
        }
        if self._active_runtime_context:
            payload.update(
                {
                    "runtime_context_hash": self._active_runtime_context_hash,
                    "runtime_context_chars": self._active_runtime_context_chars,
                }
            )
        result = await self._call_host_port(
            finalizer,
            intent_type="turn.finalize",
            payload=payload,
        )
        events = [event async for event in _coerce_host_port_events(result)]
        _validate_host_port_event_session_scope(
            events,
            session_key=self._session_key,
            port_name="finalizer",
        )
        terminal_indexes = [
            index
            for index, event in enumerate(events)
            if isinstance(event, (DoneEvent, ErrorEvent))
        ]
        if len(terminal_indexes) > 1:
            raise RuntimeError(
                "KernelHostPorts.finalizer returned multiple terminal events"
            )
        if terminal_indexes and terminal_indexes[-1] != len(events) - 1:
            raise RuntimeError(
                "KernelHostPorts.finalizer returned events after terminal event"
            )
        if not terminal_indexes:
            raise RuntimeError(
                "KernelHostPorts.finalizer must return a terminal "
                "DoneEvent or ErrorEvent"
            )
        for event in events:
            if isinstance(event, DoneEvent):
                transition = self._transition_if_needed(AgentState.DONE)
                if transition is not None:
                    yield transition
            elif isinstance(event, ErrorEvent):
                transition = self._transition_if_needed(AgentState.ERROR)
                if transition is not None:
                    yield transition
            yield event

    async def _normalize_event(
        self,
        raw_event: dict[str, Any],
        text_parts: list[str],
    ) -> AsyncIterator[AgentEvent]:
        if not isinstance(raw_event, dict):
            raise PiSidecarProtocolError(
                "Pi sidecar frame must be a JSON object"
            )
        _validate_sidecar_json_frame_shell(raw_event)
        protocol = raw_event.get("protocol")
        if not isinstance(protocol, str):
            raise PiSidecarProtocolError("Pi sidecar frame protocol must be a string")
        if not protocol.strip():
            raise PiSidecarProtocolError("Pi sidecar frame protocol must be non-empty")
        if protocol != protocol.strip():
            raise PiSidecarProtocolError(
                "Pi sidecar frame protocol must not contain surrounding whitespace"
            )
        if protocol != self._protocol_version:
            raise PiSidecarProtocolError(
                "Pi sidecar frame missing protocol "
                f"{self._protocol_version!r}"
            )

        kind = raw_event.get("kind")
        if not isinstance(kind, str):
            raise PiSidecarProtocolError("Pi sidecar frame kind must be a string")
        if not kind.strip():
            raise PiSidecarProtocolError("Pi sidecar frame kind must be non-empty")
        if kind != kind.strip():
            raise PiSidecarProtocolError(
                "Pi sidecar frame kind must not contain surrounding whitespace"
            )

        event_type = raw_event.get("type")
        if not isinstance(event_type, str):
            if kind == "intent":
                raise PiSidecarProtocolError("Pi sidecar intent type must be a string")
            raise PiSidecarProtocolError("Pi sidecar frame type must be a string")
        if not event_type.strip():
            if kind == "intent":
                raise PiSidecarProtocolError("Pi sidecar intent type must be non-empty")
            raise PiSidecarProtocolError("Pi sidecar frame type must be non-empty")
        if event_type != event_type.strip():
            if kind == "intent":
                raise PiSidecarProtocolError(
                    "Pi sidecar intent type must not contain surrounding whitespace"
                )
            raise PiSidecarProtocolError(
                "Pi sidecar frame type must not contain surrounding whitespace"
            )

        if kind == "event":
            async for event in self._normalize_protocol_event(raw_event, text_parts):
                yield event
            return

        if kind == "intent":
            async for event in self._handle_intent(raw_event):
                yield event
            return

        raise PiSidecarProtocolError(f"Unsupported Pi sidecar frame kind {kind!r}")

    async def _normalize_protocol_event(
        self,
        raw_event: dict[str, Any],
        text_parts: list[str],
    ) -> AsyncIterator[AgentEvent]:
        event_type = raw_event.get("type")
        payload = raw_event.get("payload")
        if "payload" in raw_event and not isinstance(payload, dict):
            raise PiSidecarProtocolError(
                f"Pi sidecar event {event_type!r} payload must be a JSON object"
            )
        if not isinstance(payload, dict):
            payload = {}
        _validate_sidecar_json_payload(payload, frame_type=f"event {event_type!r}")
        allowed_payload_keys = _PI_EVENT_PAYLOAD_KEYS.get(cast(str, event_type))
        if allowed_payload_keys is not None:
            unknown_payload_keys = set(payload) - allowed_payload_keys
            if unknown_payload_keys:
                fields = ", ".join(sorted(unknown_payload_keys))
                raise PiSidecarProtocolError(
                    f"Pi sidecar event {event_type!r} unsupported payload field: {fields}"
                )

        if event_type in _HOST_OWNED_PI_EVENT_TYPES:
            raise PiSidecarProtocolError(
                f"Pi sidecar attempted to emit host-owned event {event_type!r}"
            )

        if event_type == "text.delta":
            text = payload.get("text", "")
            if not isinstance(text, str):
                raise PiSidecarProtocolError(
                    "Pi sidecar text.delta text must be a string"
                )
            yield TextDeltaEvent(text=text)
            return

        if event_type == "error":
            message = payload.get("message", "")
            code = payload.get("code", "pi_error")
            if not isinstance(message, str):
                raise PiSidecarProtocolError(
                    "Pi sidecar error message must be a string"
                )
            if not isinstance(code, str):
                raise PiSidecarProtocolError(
                    "Pi sidecar error code must be a string"
                )
            if not code.strip():
                raise PiSidecarProtocolError(
                    "Pi sidecar error code must be non-empty"
                )
            yield ErrorEvent(message=message, code=code)
            return

        raise PiSidecarProtocolError(f"Unsupported Pi sidecar event type {event_type!r}")

    async def _handle_intent(self, raw_event: dict[str, Any]) -> AsyncIterator[AgentEvent]:
        intent_type = cast(str, raw_event["type"])
        payload = raw_event.get("payload")
        if "payload" in raw_event and not isinstance(payload, dict):
            raise PiSidecarProtocolError(
                f"Pi sidecar intent {intent_type!r} payload must be a JSON object"
            )
        if not isinstance(payload, dict):
            payload = {}
        _validate_sidecar_json_payload(payload, frame_type=f"intent {intent_type!r}")

        port_name = _PI_INTENT_PORTS.get(intent_type)
        if port_name is None:
            raise PiSidecarProtocolError(f"Unsupported Pi sidecar intent {intent_type!r}")
        port = getattr(self._host_ports, port_name)
        if port is None:
            raise PiSidecarProtocolError(
                f"Pi sidecar intent {intent_type!r} requires KernelHostPorts.{port_name}"
            )
        cross_session_message = _PI_SESSION_SCOPED_INTENT_MESSAGES.get(intent_type)
        if cross_session_message is not None:
            _validate_pi_intent_session_key(
                payload,
                session_key=self._session_key,
                intent_type=intent_type,
                cross_session_message=cross_session_message,
            )

        _validate_pi_intent_payload_fields(intent_type, payload)
        if intent_type == "telemetry.emit":
            _validate_pi_telemetry_reserved_payloads(payload)

        tool_call_id = _intent_tool_call_id(payload)
        if intent_type in {"tool.call.prepare", "tool.call.execute"} and not tool_call_id:
            raise PiSidecarProtocolError(
                f"Pi sidecar intent {intent_type!r} requires tool_call_id"
            )
        expected_tool_name: str | None = None
        if intent_type in {"tool.call.prepare", "tool.call.execute"}:
            raw_tool_name = payload.get("tool_name", payload.get("name", ""))
            if not isinstance(raw_tool_name, str):
                raise PiSidecarProtocolError(
                    f"Pi sidecar intent {intent_type!r} requires string tool_name"
                )
            tool_name = raw_tool_name.strip()
            if not tool_name:
                raise PiSidecarProtocolError(
                    f"Pi sidecar intent {intent_type!r} requires tool_name"
                )
            expected_tool_name = tool_name
            if tool_name == "sessions_yield":
                raise PiSidecarProtocolError(
                    "Pi sidecar must use yield.request for sessions_yield"
                )
        if intent_type == "tool.call.prepare" and tool_call_id:
            if tool_call_id in self._pending_tool_calls:
                raise PiSidecarProtocolError(
                    "Pi sidecar duplicate tool.call.prepare: "
                    f"{tool_call_id}"
                )
            self._pending_tool_calls.add(tool_call_id)
        if intent_type == "tool.call.execute" and tool_call_id:
            if tool_call_id not in self._pending_tool_calls:
                raise PiSidecarProtocolError(
                    "Pi sidecar tool.call.execute without matching prepare: "
                    f"{tool_call_id}"
                )
        if intent_type == "yield.request" and self._pending_tool_calls:
            pending = ", ".join(sorted(self._pending_tool_calls))
            raise PiSidecarProtocolError(
                "Pi sidecar yield.request rejected with pending tool calls: "
                f"{pending}"
            )

        if intent_type == "provider.request":
            if (
                self._coalesce_tool_state_events
                and self._state == AgentState.TOOL_CALLING
            ):
                transition = self._transition(AgentState.THINKING)
                if transition is not None:
                    yield transition
            transition = self._transition_if_needed(AgentState.STREAMING)
            if transition is not None:
                yield transition

        port_payload = cast(dict[str, Any], _sidecar_input_copy(payload))
        if intent_type == "provider.request":
            port_payload.update(self._host_context_payload())
        result = await self._call_host_port(
            port,
            intent_type=intent_type,
            payload=port_payload,
        )
        if intent_type == "tool.call.execute" and tool_call_id:
            self._pending_tool_calls.discard(tool_call_id)
        events = [event async for event in _coerce_host_port_events(result)]
        _validate_host_port_event_session_scope(
            events,
            session_key=self._session_key,
            port_name=port_name,
        )
        _validate_host_port_terminal_batch(events, port_name=port_name)
        if intent_type != "yield.request" and any(
            isinstance(event, ToolResultEvent) and event.tool_name == "sessions_yield"
            for event in events
        ):
            raise PiSidecarProtocolError(
                f"KernelHostPorts.{port_name} must not return "
                "sessions_yield outside yield.request"
            )
        if intent_type in {"tool.call.prepare", "tool.call.execute"}:
            _validate_host_port_tool_identity(
                events,
                tool_call_id=tool_call_id,
                tool_name=expected_tool_name or "",
                port_name=port_name,
            )
        if self._pending_tool_calls and any(
            isinstance(event, (DoneEvent, ErrorEvent)) for event in events
        ):
            pending = ", ".join(sorted(self._pending_tool_calls))
            raise PiSidecarProtocolError(
                "Pi sidecar terminal host event rejected with "
                f"pending tool calls: {pending}"
            )
        if port_name in _PI_NON_TERMINAL_PORTS and any(
            isinstance(event, (DoneEvent, ErrorEvent)) for event in events
        ):
            raise PiSidecarProtocolError(
                f"KernelHostPorts.{port_name} must not return terminal events"
            )
        if intent_type == "telemetry.emit" and events:
            raise RuntimeError("KernelHostPorts.telemetry must not return AgentEvents")
        yield_success_indexes = [
            index
            for index, event in enumerate(events)
            if isinstance(event, ToolResultEvent)
            and event.tool_name == "sessions_yield"
            and not event.is_error
        ]
        report_intent_result = True
        if intent_type == "yield.request" and yield_success_indexes:
            if yield_success_indexes[-1] != len(events) - 1:
                raise PiSidecarProtocolError(
                    "Pi sidecar yield.request returned events after "
                    "sessions_yield success"
                )
        if intent_type == "yield.request" and (
            len(events) != 1
            or not isinstance(events[0], ToolResultEvent)
            or events[0].tool_name != "sessions_yield"
        ):
            raise PiSidecarProtocolError(
                "Pi sidecar yield.request must return a "
                "sessions_yield ToolResultEvent"
            )
        if intent_type == "yield.request" and yield_success_indexes:
            self._yield_request_settled = True
            report_intent_result = False
        intent_result_reported = False
        if report_intent_result:
            intent_result_reported = await self._report_intent_result(
                intent_type=intent_type,
                payload=payload,
                events=events,
            )
        visible_events = events
        if intent_type == "yield.request" and self._emit_yield_tool_start_events:
            visible_events = [
                ToolUseStartEvent(
                    tool_use_id=tool_call_id or "yield-request",
                    tool_name="sessions_yield",
                ),
                *events,
            ]
        if intent_type == "provider.request":
            if intent_result_reported and self._delegate_provider_feedback_visibility:
                self._pending_provider_fallback_events = [
                    event
                    for event in events
                    if isinstance(event, (TextDeltaEvent, DoneEvent))
                ]
                visible_events = [
                    event
                    for event in events
                    if not isinstance(
                        event,
                        (
                            TextDeltaEvent,
                            DoneEvent,
                            ToolUseStartEvent,
                            ToolUseEndEvent,
                        ),
                    )
                ]
            else:
                self._pending_provider_fallback_events = []
                visible_events = [
                    event
                    for event in events
                    if not isinstance(event, (ToolUseStartEvent, ToolUseEndEvent))
                ]
        if intent_type == "tool.call.execute":
            transition = self._transition_if_needed(AgentState.TOOL_CALLING)
            if transition is not None:
                yield transition
        for event in visible_events:
            if isinstance(event, ErrorEvent):
                transition = self._transition_if_needed(AgentState.ERROR)
                if transition is not None:
                    yield transition
            yield event
            if isinstance(event, ErrorEvent):
                return
        if intent_type == "tool.call.execute" and not self._coalesce_tool_state_events:
            transition = self._transition_if_needed(AgentState.THINKING)
            if transition is not None:
                yield transition

    async def _report_intent_result(
        self,
        *,
        intent_type: str,
        payload: dict[str, Any],
        events: list[AgentEvent],
    ) -> bool:
        receive = getattr(self._rpc_client, "receive_intent_result", None)
        if not callable(receive):
            return False
        try:
            feedback_payload = cast(dict[str, Any], _sidecar_json_input_copy(payload))
            feedback_events = cast(list[Any], _sidecar_json_input_copy(events))
        except RuntimeError as exc:
            raise PiSidecarProtocolError(
                "Pi sidecar intent_result feedback must be JSON-compatible"
            ) from exc
        try:
            result = receive(
                intent_type=intent_type,
                payload=feedback_payload,
                events=feedback_events,
                session_key=self._session_key,
            )
            if inspect.isawaitable(result):
                await result
        except Exception:
            return False
        return True

    async def _call_host_port(
        self,
        port: Any,
        *,
        intent_type: str,
        payload: dict[str, Any],
    ) -> Any:
        if hasattr(port, "handle_intent"):
            result = port.handle_intent(
                intent_type=intent_type,
                payload=payload,
                session_key=self._session_key,
            )
        elif intent_type == "telemetry.emit" and hasattr(port, "emit"):
            try:
                result = port.emit(cast(dict[str, Any], _sidecar_input_copy(payload)))
            except Exception:
                return []
        elif intent_type == "telemetry.emit" and callable(port):
            try:
                result = port(cast(dict[str, Any], _sidecar_input_copy(payload)))
            except Exception:
                return []
        else:
            raise RuntimeError(
                f"KernelHostPorts target for {intent_type!r} must provide handle_intent"
            )
        if inspect.isawaitable(result):
            return await result
        return result


PiAgentRuntimeAdapter = PiSidecarKernelRuntime


def _validate_pi_provider_request_payload_fields(payload: dict[str, Any]) -> None:
    _validate_pi_intent_payload_fields("provider.request", payload)


def _validate_pi_tool_intent_payload_fields(payload: dict[str, Any]) -> None:
    _validate_pi_intent_payload_fields("tool.call.execute", payload)


def _validate_pi_intent_payload_fields(
    intent_type: str,
    payload: dict[str, Any],
) -> None:
    allowed_payload_keys = _PI_INTENT_PAYLOAD_KEYS.get(intent_type)
    if allowed_payload_keys is None:
        return
    unknown_payload_keys = set(payload) - allowed_payload_keys
    if unknown_payload_keys:
        fields = ", ".join(sorted(unknown_payload_keys))
        label = _PI_INTENT_PAYLOAD_ERROR_LABELS.get(intent_type, intent_type)
        raise PiSidecarProtocolError(
            f"{label} unsupported payload field: {fields}"
        )


def _validate_pi_telemetry_reserved_payloads(payload: dict[str, Any]) -> None:
    raw_kind = payload.get("kind")
    raw_type = payload.get("type")
    if raw_kind == "event" and isinstance(raw_type, str):
        normalized_event_type = raw_type.replace(".", "_")
        if normalized_event_type in _AGENT_EVENT_KINDS:
            raise PiSidecarProtocolError(
                "telemetry.emit must not carry public AgentEvent payloads"
            )
    if raw_kind == "intent_result":
        raise PiSidecarProtocolError(
            "telemetry.emit must not carry Pi intent_result payloads"
        )


def _tool_call_from_pi_payload(payload: dict[str, Any]) -> ToolCall:
    tool_call_id = _intent_tool_call_id(payload)
    if not tool_call_id:
        raise PiSidecarProtocolError("Pi sidecar intent requires tool_call_id")
    raw_tool_name = payload.get("tool_name", payload.get("name", ""))
    if not isinstance(raw_tool_name, str):
        raise PiSidecarProtocolError(
            "Pi sidecar intent requires string tool_name"
        )
    tool_name = raw_tool_name.strip()
    if not tool_name:
        raise PiSidecarProtocolError("Pi sidecar intent requires tool_name")
    if "arguments" in payload:
        raw_arguments = payload["arguments"]
    elif "input" in payload:
        raw_arguments = payload["input"]
    else:
        raw_arguments = {}
    if not isinstance(raw_arguments, dict):
        raise PiSidecarProtocolError(
            "Pi sidecar intent arguments must be an object"
        )
    arguments = cast(dict[str, Any], _sidecar_json_input_copy(raw_arguments))
    if "arguments" in payload and "input" in payload:
        raw_input = payload["input"]
        if not isinstance(raw_input, dict):
            raise PiSidecarProtocolError(
                "Pi sidecar intent arguments must be an object"
            )
        _sidecar_json_input_copy(raw_input)
    for approval_field_name in ("approval_id", "approvalId"):
        if approval_field_name in arguments:
            raise PiSidecarProtocolError(
                "Pi sidecar tool intent must not supply host-owned approval_id"
            )
    raw_synthetic_from_text = payload.get("synthetic_from_text", False)
    if not isinstance(raw_synthetic_from_text, bool):
        raise PiSidecarProtocolError(
            "Pi sidecar intent synthetic_from_text must be a boolean"
        )
    origin_trace = None
    if "origin_trace" in payload:
        raw_origin_trace = payload["origin_trace"]
        if not isinstance(raw_origin_trace, str):
            raise PiSidecarProtocolError(
                "Pi sidecar intent origin_trace must be a string"
            )
        origin_trace = raw_origin_trace
    return ToolCall(
        tool_use_id=tool_call_id,
        tool_name=tool_name,
        arguments=arguments,
        synthetic_from_text=raw_synthetic_from_text,
        origin_trace=origin_trace,
    )


def _host_agent_config(config: Any) -> Any:
    from opensquilla.engine.types import AgentConfig

    if isinstance(config, AgentConfig):
        return config

    values = {
        config_field.name: getattr(config, config_field.name)
        for config_field in fields(AgentConfig)
        if hasattr(config, config_field.name)
    }
    return AgentConfig(**values)


def _host_runtime_policy_snapshot_metadata(config: Any) -> dict[str, Any]:
    policy = {
        field_name: getattr(config, field_name)
        for field_name in _HOST_RUNTIME_POLICY_SNAPSHOT_FIELDS
        if hasattr(config, field_name)
    }
    if not policy:
        return {}
    return {"host_runtime_policy": _json_safe_value(policy)}


def _task_runtime_from_session_manager(session_manager: Any | None) -> Any | None:
    if session_manager is None:
        return None
    return getattr(session_manager, "_task_runtime", None)


def _validate_pi_intent_session_key(
    payload: dict[str, Any],
    *,
    session_key: str,
    intent_type: str,
    cross_session_message: str,
    ) -> str:
    if not isinstance(session_key, str):
        raise RuntimeError(f"{intent_type} session_key must be a string")
    target_session_key = session_key
    if "session_key" not in payload:
        return target_session_key
    payload_session_key = payload["session_key"]
    if not isinstance(payload_session_key, str):
        raise RuntimeError(f"{intent_type} session_key must be a string")
    if payload_session_key != target_session_key:
        raise RuntimeError(cross_session_message)
    return target_session_key


def _validate_session_write_turn_usage(turn_usage: dict[str, Any]) -> None:
    for field_name in _SESSION_WRITE_TURN_USAGE_INT_FIELDS:
        if field_name not in turn_usage:
            continue
        value = turn_usage[field_name]
        if not isinstance(value, int) or isinstance(value, bool):
            raise RuntimeError(
                f"session.write.enqueue turn_usage {field_name} must be an integer"
            )
        if value < 0:
            raise RuntimeError(
                f"session.write.enqueue turn_usage {field_name} must be a "
                "non-negative integer"
            )
    input_tokens = turn_usage.get("input_tokens")
    if isinstance(input_tokens, int) and not isinstance(input_tokens, bool):
        for cache_field_name in ("cached_tokens", "cache_write_tokens"):
            cache_value = turn_usage.get(cache_field_name)
            if (
                isinstance(cache_value, int)
                and not isinstance(cache_value, bool)
                and cache_value > input_tokens
            ):
                raise RuntimeError(
                    f"session.write.enqueue turn_usage {cache_field_name} "
                    "must be <= input_tokens"
                )
    for field_name in _SESSION_WRITE_TURN_USAGE_COST_FIELDS:
        if field_name not in turn_usage:
            continue
        value = _finite_number(
            turn_usage[field_name],
            field_name=f"session.write.enqueue turn_usage {field_name}",
        )
        if value < 0.0:
            raise RuntimeError(
                f"session.write.enqueue turn_usage {field_name} must be a "
                "non-negative number"
            )
    for field_name in _SESSION_WRITE_TURN_USAGE_PROBABILITY_FIELDS:
        if field_name not in turn_usage:
            continue
        value = _finite_number(
            turn_usage[field_name],
            field_name=f"session.write.enqueue turn_usage {field_name}",
        )
        if value < 0.0 or value > 1.0:
            raise RuntimeError(
                f"session.write.enqueue turn_usage {field_name} must be a probability"
            )
    for field_name in _SESSION_WRITE_TURN_USAGE_STRING_FIELDS:
        if field_name not in turn_usage:
            continue
        if not isinstance(turn_usage[field_name], str):
            raise RuntimeError(
                f"session.write.enqueue turn_usage {field_name} must be a string"
            )
    for field_name in _SESSION_WRITE_TURN_USAGE_OPTIONAL_STRING_FIELDS:
        if field_name not in turn_usage:
            continue
        value = turn_usage[field_name]
        if value is not None and not isinstance(value, str):
            raise RuntimeError(
                f"session.write.enqueue turn_usage {field_name} must be a "
                "string or None"
            )
    for field_name in _SESSION_WRITE_TURN_USAGE_BOOLEAN_FIELDS:
        if field_name not in turn_usage:
            continue
        if not isinstance(turn_usage[field_name], bool):
            raise RuntimeError(
                f"session.write.enqueue turn_usage {field_name} must be a boolean"
            )


def _optional_float(value: Any, *, field_name: str) -> float | None:
    if value is None:
        raise RuntimeError(f"{field_name} must be a number")
    return _finite_number(value, field_name=field_name)


def _optional_non_negative_float(value: Any, *, field_name: str) -> float | None:
    result = _optional_float(value, field_name=field_name)
    if result is not None and result < 0.0:
        raise RuntimeError(f"{field_name} must be a non-negative number")
    return result


def _pi_checkpoint_transcript_entry_from_payload(
    entry: Any,
) -> _PiCheckpointTranscriptEntry:
    if not isinstance(entry, dict):
        raise RuntimeError("savepoint.request transcript entries must be objects")

    raw_role = entry.get("role", "")
    if not isinstance(raw_role, str):
        raise RuntimeError("savepoint.request transcript role must be a string")
    role = raw_role.strip().lower()
    if not role or role not in {"user", "assistant", "tool", "system"}:
        raise RuntimeError(
            "savepoint.request transcript role must be user, assistant, or tool"
        )

    raw_content = None
    if "content" in entry:
        raw_content = entry["content"]
        if not isinstance(raw_content, str):
            raise RuntimeError("savepoint.request transcript content must be a string")

    raw_tool_calls = None
    if "tool_calls" in entry:
        raw_tool_calls = entry["tool_calls"]
        if not isinstance(raw_tool_calls, list):
            raise RuntimeError("savepoint.request transcript tool_calls must be a list")
        if not all(isinstance(tool_call, dict) for tool_call in raw_tool_calls):
            raise RuntimeError(
                "savepoint.request transcript tool_calls entries must be objects"
            )

    raw_tool_call_id = None
    if "tool_call_id" in entry:
        raw_tool_call_id = entry["tool_call_id"]
        if not isinstance(raw_tool_call_id, str):
            raise RuntimeError(
                "savepoint.request transcript tool_call_id must be a string"
            )
        if not raw_tool_call_id.strip():
            raise RuntimeError(
                "savepoint.request transcript tool_call_id must be non-empty"
            )

    raw_reasoning_content = None
    if "reasoning_content" in entry:
        raw_reasoning_content = entry["reasoning_content"]
        if not isinstance(raw_reasoning_content, str):
            raise RuntimeError(
                "savepoint.request transcript reasoning_content must be a string"
            )

    raw_token_count = None
    if "token_count" in entry:
        raw_token_count = entry["token_count"]
        if not isinstance(raw_token_count, int) or isinstance(raw_token_count, bool):
            raise RuntimeError(
                "savepoint.request transcript token_count must be an integer"
            )
        if raw_token_count < 0:
            raise RuntimeError(
                "savepoint.request transcript token_count must be a non-negative integer"
            )

    return _PiCheckpointTranscriptEntry(
        role=role,
        content=raw_content,
        tool_calls=cast(list[Any] | None, _sidecar_json_input_copy(raw_tool_calls)),
        tool_call_id=raw_tool_call_id,
        reasoning_content=raw_reasoning_content,
        token_count=raw_token_count,
    )

def _is_privileged_transcript_role(role: Any) -> bool:
    return str(role or "").strip().lower() == "system"


def _is_privileged_savepoint_source(source: Any) -> bool:
    normalized = str(source or "").strip().casefold().replace("_", "-")
    return normalized in {
        "host",
        "opensquilla",
        "open-squilla",
        "session-manager",
        "sessionmanager",
    }


def _agent_id_from_session_key(session_key: str) -> str:
    parts = session_key.split(":")
    if len(parts) >= 2 and parts[0] == "agent" and parts[1]:
        return parts[1]
    return session_key


def _kernel_turn_snapshot_string(value: Any, *, field_name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise RuntimeError(f"KernelTurnSnapshot {field_name} must be a string")
    return value


def _kernel_turn_snapshot_required_string(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise RuntimeError(f"KernelTurnSnapshot {field_name} must be a string")
    return value


def _kernel_turn_snapshot_optional_string(
    value: Any,
    *,
    field_name: str,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise RuntimeError(
            f"KernelTurnSnapshot {field_name} must be a string or None"
        )
    return value


def _kernel_turn_snapshot_optional_list(
    value: Any,
    *,
    field_name: str,
) -> list[Any] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise RuntimeError(f"KernelTurnSnapshot {field_name} must be a list or None")
    return value


def _sidecar_input_copy(value: Any) -> Any:
    try:
        return copy.deepcopy(value)
    except Exception:
        return _json_safe_value(value)


def _sidecar_json_input_copy(value: Any) -> Any:
    return _json_safe_value(_sidecar_input_copy(value))


def _json_safe_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe_value(asdict(value))
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _json_safe_value(model_dump())
    dict_method = getattr(value, "dict", None)
    if callable(dict_method):
        return _json_safe_value(dict_method())
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise RuntimeError("Pi sidecar JSON object keys must be strings")
            result[key] = _json_safe_value(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise RuntimeError("Pi sidecar JSON value must not be non-finite")
        return value
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise RuntimeError(
        f"Pi sidecar JSON value must be a JSON value, got {type(value).__name__}"
    )


def _json_dumps_sidecar_frame(frame: dict[str, Any]) -> str:
    try:
        return json.dumps(frame, sort_keys=True, allow_nan=False)
    except ValueError as exc:
        raise RuntimeError("Pi sidecar JSON frame must not contain non-finite values") from exc
    except TypeError as exc:
        raise RuntimeError("Pi sidecar JSON frame must contain only JSON values") from exc


@contextlib.asynccontextmanager
async def _session_write_context(
    factory: Any | None,
    session_key: str,
) -> AsyncIterator[None]:
    if factory is None:
        yield
        return
    candidate = factory(session_key)
    context_manager = (
        candidate()
        if callable(candidate) and not hasattr(candidate, "__aenter__")
        else candidate
    )
    async with context_manager:
        yield


def _validate_provider_request_sidecar_tools(payload: dict[str, Any]) -> None:
    if "tools" not in payload or payload["tools"] is None:
        return
    copied_tools = _sidecar_json_input_copy(payload["tools"])
    if not isinstance(copied_tools, list):
        raise RuntimeError("provider.request tools must be a list")


def _validate_provider_request_sidecar_config(payload: dict[str, Any]) -> None:
    if "config" not in payload:
        return
    copied_config = _sidecar_json_input_copy(payload["config"])
    if not isinstance(copied_config, dict):
        raise RuntimeError("provider.request config must be an object")


def _provider_request_sidecar_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key not in _HOST_PROVIDER_REQUEST_INTERNAL_KEYS
    }


def _provider_messages_from_payload(payload: dict[str, Any], *, host_agent: Any) -> list[Any]:
    from opensquilla.engine.history import repair_tool_pairing
    from opensquilla.provider import Message

    raw_messages = payload.get("messages")
    if "messages" in payload and not isinstance(raw_messages, list):
        raise ValueError("provider.request messages must be a list")
    if isinstance(raw_messages, list):
        messages: list[Any] = []
        allowed_context_controls = _host_owned_provider_context_control_fingerprints(
            host_agent
        )
        for index, raw_message in enumerate(raw_messages):
            if isinstance(raw_message, Message):
                message_payload = cast(
                    dict[str, Any],
                    _sidecar_json_input_copy(raw_message),
                )
                _validate_provider_message_tool_calls(message_payload, index=index)
                _normalize_provider_message_tool_calls(message_payload, index=index)
                _reject_sidecar_owned_provider_context_controls(
                    message_payload,
                    index=index,
                    allowed_fingerprints=allowed_context_controls,
                )
                message = Message.model_validate(message_payload)
                messages.append(message)
            elif isinstance(raw_message, dict):
                message_payload = cast(
                    dict[str, Any],
                    _sidecar_json_input_copy(raw_message),
                )
                _validate_provider_message_tool_calls(message_payload, index=index)
                _normalize_provider_message_tool_calls(message_payload, index=index)
                _reject_sidecar_owned_provider_context_controls(
                    message_payload,
                    index=index,
                    allowed_fingerprints=allowed_context_controls,
                )
                try:
                    message = Message.model_validate(message_payload)
                except Exception as exc:
                    raise ValueError(
                        f"Invalid provider.request message at index {index}"
                    ) from exc
                _reject_sidecar_owned_provider_context_controls(
                    message,
                    index=index,
                    allowed_fingerprints=allowed_context_controls,
                )
                messages.append(message)
            else:
                raise ValueError(
                    f"Invalid provider.request message at index {index}"
                )
        repaired_messages = repair_tool_pairing(messages)
        if not repaired_messages:
            raise ValueError("provider.request messages are empty after repair")
        return _provider_messages_with_host_context(
            repaired_messages,
            payload=payload,
        )

    if "prompt" in payload:
        prompt = payload["prompt"]
        field_name = "prompt"
    elif "message" in payload:
        prompt = payload["message"]
        field_name = "message"
    else:
        raise ValueError("provider.request requires messages, prompt, or message")
    if not isinstance(prompt, str):
        raise ValueError(f"provider.request {field_name} must be a string")
    if not prompt.strip():
        raise ValueError(f"provider.request {field_name} must be non-empty")
    return _provider_messages_with_host_context(
        [Message(role="user", content=prompt)],
        payload=payload,
    )


def _provider_messages_with_host_context(
    messages: list[Any],
    *,
    payload: dict[str, Any],
) -> list[Any]:
    from opensquilla.provider import Message

    runtime_context = payload.get("_host_runtime_context")
    if runtime_context is not None and not isinstance(runtime_context, str):
        raise RuntimeError("_host_runtime_context must be a string")
    request_context = payload.get("_host_request_context_prompt")
    if request_context is not None and not isinstance(request_context, str):
        raise RuntimeError("_host_request_context_prompt must be a string")
    if not (runtime_context and runtime_context.strip()) and not (
        request_context and request_context.strip()
    ):
        return messages

    result = list(messages)
    runtime_index = _provider_runtime_context_message_index(
        result,
        turn_input=payload.get("_host_turn_input"),
    )
    insert_index = runtime_index if runtime_index is not None else 0
    if request_context and request_context.strip():
        result.insert(
            insert_index,
            Message(
                role="user",
                content="\n".join(
                    [
                        "[Request context for this turn]",
                        (
                            "This request-scoped context is not a user request "
                            "and is not transcript history."
                        ),
                        (
                            "Use it only when it is relevant to the current "
                            "user request."
                        ),
                        request_context.strip(),
                    ]
                ),
            ),
        )
        if runtime_index is not None and insert_index <= runtime_index:
            runtime_index += 1

    if runtime_context and runtime_context.strip():
        runtime_message = Message(role="user", content=runtime_context)
        if runtime_index is not None:
            result[runtime_index] = _append_runtime_context_to_provider_message(
                result[runtime_index],
                runtime_message,
            )
        else:
            result.insert(insert_index, runtime_message)
    return result


def _provider_runtime_context_message_index(
    messages: list[Any],
    *,
    turn_input: Any,
) -> int | None:
    user_indexes = [
        index
        for index, message in enumerate(messages)
        if getattr(message, "role", None) == "user"
    ]
    if not user_indexes:
        return None
    if isinstance(turn_input, str) and turn_input:
        for index in user_indexes:
            if turn_input in _provider_content_text(
                getattr(messages[index], "content", "")
            ):
                return index
    return user_indexes[0]


def _append_runtime_context_to_provider_message(
    message: Any,
    runtime_message: Any,
) -> Any:
    from opensquilla.provider import Message

    runtime_content = getattr(runtime_message, "content", None)
    if not isinstance(runtime_content, str):
        return runtime_message
    if runtime_content in _provider_content_text(getattr(message, "content", "")):
        return message
    reasoning_content = getattr(message, "reasoning_content", None)
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return Message(
            role=getattr(message, "role", "user"),
            content=f"{content}\n\n{runtime_content}",
            reasoning_content=reasoning_content,
        )
    if isinstance(content, list):
        return Message(
            role=getattr(message, "role", "user"),
            content=[
                *content,
                {"type": "text", "text": f"\n\n{runtime_content}"},
            ],
            reasoning_content=reasoning_content,
        )
    return runtime_message


def _validate_provider_message_tool_calls(message: dict[str, Any], *, index: int) -> None:
    raw_tool_calls = message.get("tool_calls")
    if raw_tool_calls is None:
        return
    if not isinstance(raw_tool_calls, list):
        raise ValueError(
            f"provider.request message at index {index} tool_calls must be a list"
        )
    if not all(isinstance(tool_call, dict) for tool_call in raw_tool_calls):
        raise ValueError(
            "provider.request message at index "
            f"{index} tool_calls entries must be objects"
        )


def _normalize_provider_message_tool_calls(
    message: dict[str, Any],
    *,
    index: int,
) -> None:
    raw_tool_calls = message.pop("tool_calls", None)
    if raw_tool_calls is None:
        return
    if message.get("role") != "assistant":
        raise ValueError(
            f"provider.request message at index {index} tool_calls require assistant role"
        )

    content = message.get("content")
    if isinstance(content, str):
        content_blocks: list[Any] = (
            [{"type": "text", "text": content}] if content else []
        )
    elif isinstance(content, list):
        content_blocks = list(content)
    elif content is None:
        content_blocks = []
    else:
        raise ValueError(f"Invalid provider.request message at index {index}")

    for tool_call_index, tool_call in enumerate(raw_tool_calls):
        tool_call_type = tool_call.get("type", "function")
        if tool_call_type != "function":
            raise ValueError(
                "provider.request message at index "
                f"{index} tool_calls[{tool_call_index}].type must be 'function'"
            )
        function = tool_call.get("function")
        if not isinstance(function, dict):
            raise ValueError(
                "provider.request message at index "
                f"{index} tool_calls[{tool_call_index}].function must be an object"
            )
        tool_use_id = tool_call.get("id")
        if not isinstance(tool_use_id, str) or not tool_use_id.strip():
            raise ValueError(
                "provider.request message at index "
                f"{index} tool_calls[{tool_call_index}].id must be a non-empty string"
            )
        name = function.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(
                "provider.request message at index "
                f"{index} tool_calls[{tool_call_index}].function.name "
                "must be a non-empty string"
            )
        raw_arguments = function.get("arguments", {})
        if isinstance(raw_arguments, str):
            try:
                arguments = json.loads(raw_arguments) if raw_arguments else {}
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "provider.request message at index "
                    f"{index} tool_calls[{tool_call_index}].function.arguments "
                    "must decode to an object"
                ) from exc
        else:
            arguments = raw_arguments
        if not isinstance(arguments, dict):
            raise ValueError(
                "provider.request message at index "
                f"{index} tool_calls[{tool_call_index}].function.arguments "
                "must be an object"
            )
        content_blocks.append(
            {
                "type": "tool_use",
                "id": tool_use_id,
                "name": name,
                "input": arguments,
            }
        )

    message["content"] = content_blocks


def _host_owned_provider_context_control_fingerprints(host_agent: Any) -> set[str]:
    history = getattr(host_agent, "_history", None)
    if not isinstance(history, list):
        return set()
    fingerprints: set[str] = set()
    for message in history:
        reasoning_fingerprint = _provider_message_reasoning_control_fingerprint(message)
        if reasoning_fingerprint is not None:
            fingerprints.add(reasoning_fingerprint)
        if isinstance(message, dict):
            content = message.get("content")
        else:
            content = getattr(message, "content", None)
        if not isinstance(content, list):
            continue
        for block in content:
            if _provider_context_control_kind(block) is None:
                continue
            fingerprints.add(_provider_context_control_fingerprint(block))
    return fingerprints


def _provider_message_reasoning_control_fingerprint(message: Any) -> str | None:
    if isinstance(message, dict):
        if "reasoning_content" not in message or message.get("reasoning_content") is None:
            return None
        raw_reasoning_content = message.get("reasoning_content")
        role = message.get("role")
        content = message.get("content")
    else:
        raw_reasoning_content = getattr(message, "reasoning_content", None)
        if raw_reasoning_content is None:
            return None
        role = getattr(message, "role", None)
        content = getattr(message, "content", None)
    return json.dumps(
        _json_safe_value(
            {
                "kind": "reasoning_content",
                "role": role,
                "content": content,
                "reasoning_content": raw_reasoning_content,
            }
        ),
        sort_keys=True,
        allow_nan=False,
    )


def _provider_context_control_kind(block: Any) -> str | None:
    if isinstance(block, dict):
        block_type = block.get("type")
        has_cache_control = "cache_control" in block
    else:
        block_type = getattr(block, "type", None)
        has_cache_control = hasattr(block, "cache_control")
    if block_type == "compaction":
        return "compaction"
    if block_type == "thinking":
        return "thinking"
    if has_cache_control:
        return "cache_control"
    return None


def _provider_context_control_fingerprint(block: Any) -> str:
    return json.dumps(_json_safe_value(block), sort_keys=True, allow_nan=False)


def _reject_sidecar_owned_provider_context_controls(
    message: Any,
    *,
    index: int,
    allowed_fingerprints: set[str],
) -> None:
    if isinstance(message, dict):
        content = message.get("content")
    else:
        content = getattr(message, "content", None)
    reasoning_fingerprint = _provider_message_reasoning_control_fingerprint(message)
    if (
        reasoning_fingerprint is not None
        and reasoning_fingerprint not in allowed_fingerprints
    ):
        raise ValueError(
            "provider.request message at index "
            f"{index} contains host-owned reasoning_content"
        )
    if not isinstance(content, list):
        return
    for block in content:
        control_kind = _provider_context_control_kind(block)
        if control_kind is None:
            continue
        try:
            fingerprint = _provider_context_control_fingerprint(block)
        except RuntimeError as exc:
            raise ValueError(
                "provider.request message at index "
                f"{index} contains invalid host-owned {control_kind}"
            ) from exc
        if fingerprint in allowed_fingerprints:
            continue
        if control_kind == "compaction":
            raise ValueError(
                "provider.request message at index "
                f"{index} contains host-owned compaction block"
            )
        if control_kind == "thinking":
            raise ValueError(
                "provider.request message at index "
                f"{index} contains host-owned thinking block"
            )
        raise ValueError(
            "provider.request message at index "
            f"{index} contains host-owned cache_control"
        )


def _provider_tools_from_payload(payload: dict[str, Any], host_agent: Any) -> Any:
    _ = payload
    tool_definitions = host_agent.tool_definitions or None
    if tool_definitions is None:
        return None
    return _sidecar_input_copy(tool_definitions)


def _provider_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
        elif isinstance(block, dict) and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "\n".join(parts)


def _provider_thinking_prompt_from_messages(messages: list[Any]) -> str | None:
    for message in reversed(messages):
        if getattr(message, "role", None) != "user":
            continue
        prompt = _provider_content_text(getattr(message, "content", None))
        if prompt:
            return prompt
    return None


def _provider_chat_config_from_payload(
    payload: dict[str, Any],
    host_agent: Any,
    *,
    messages: list[Any],
) -> Any:
    from opensquilla.engine.types import ThinkingLevel
    from opensquilla.provider import ChatConfig

    _ = payload
    host_context = getattr(host_agent, "_context", None)
    host_system_prompt = getattr(host_context, "system_prompt", None)
    if host_system_prompt is None:
        host_system_prompt = getattr(host_agent.config, "system_prompt", None)
    host_thinking = getattr(host_agent.config, "thinking", False)
    resolve_thinking = getattr(host_agent.config, "resolve_thinking", None)
    thinking_prompt = _provider_thinking_prompt_from_messages(messages)
    if callable(resolve_thinking):
        thinking_enabled, thinking_budget = resolve_thinking(prompt=thinking_prompt)
    else:
        thinking_enabled = bool(host_thinking)
        thinking_budget = getattr(host_agent.config, "thinking_budget_tokens", 5000)
    return ChatConfig(
        max_tokens=getattr(host_agent.config, "max_tokens", 16384),
        temperature=getattr(host_agent.config, "temperature", None),
        system=host_system_prompt,
        thinking=thinking_enabled,
        thinking_budget_tokens=thinking_budget,
        timeout=getattr(host_agent.config, "request_timeout", 120.0),
        stop_sequences=cast(
            list[str],
            _sidecar_input_copy(getattr(host_agent.config, "stop_sequences", [])),
        ),
        cache_breakpoints=getattr(host_agent.config, "cache_breakpoints", None),
        cache_mode=getattr(host_agent.config, "cache_mode", "off"),
        model_capabilities=getattr(host_agent.config, "model_capabilities", None),
        thinking_level=(
            host_thinking if isinstance(host_thinking, ThinkingLevel) else None
        ),
        provider_request_max_chars=getattr(
            host_agent.config,
            "provider_request_proof_max_chars",
            0,
        ),
    )


def _optional_router_replay_string(event: Any, field_name: str) -> str | None:
    value = getattr(event, field_name, None)
    if value is None:
        return None
    if not isinstance(value, str):
        raise RuntimeError(f"router replay {field_name} must be a string or None")
    return value


def _validated_router_replay_event(event: Any) -> RouterControlReplayEvent:
    action = getattr(event, "action", "")
    if not isinstance(action, str):
        raise RuntimeError("router replay action must be a string")
    replay_depth = getattr(event, "replay_depth", 0)
    if not isinstance(replay_depth, int) or isinstance(replay_depth, bool):
        raise RuntimeError("router replay replay_depth must be an integer")
    if replay_depth < 0:
        raise RuntimeError("router replay replay_depth must be a non-negative integer")
    return RouterControlReplayEvent(
        action=action,
        target_tier=_optional_router_replay_string(event, "target_tier"),
        target_model=_optional_router_replay_string(event, "target_model"),
        target_provider=_optional_router_replay_string(event, "target_provider"),
        target_id=_optional_router_replay_string(event, "target_id"),
        replay_depth=replay_depth,
    )


def _tool_result_artifacts(result: Any) -> list[Any]:
    artifacts = getattr(result, "artifacts", [])
    if not isinstance(artifacts, list):
        raise RuntimeError("tool result artifacts must be a list")
    return artifacts


def _artifact_event_from_tool_artifact(artifact: Any) -> ArtifactEvent:
    from opensquilla.engine.agent import _artifact_event_kwargs

    payload = _artifact_event_kwargs(artifact)
    payload["kind"] = "artifact"
    for field_name in (
        "kind",
        "id",
        "sha256",
        "name",
        "mime",
        "session_id",
        "session_key",
        "source",
        "created_at",
        "download_url",
        "store",
    ):
        value = payload.get(field_name)
        if value is not None and not isinstance(value, str):
            raise RuntimeError(f"tool artifact {field_name} must be a string")
    size = payload.get("size")
    if size is not None and (not isinstance(size, int) or isinstance(size, bool)):
        raise RuntimeError("tool artifact size must be an integer")
    if isinstance(size, int) and size < 0:
        raise RuntimeError("tool artifact size must be a non-negative integer")
    return ArtifactEvent(**payload)


def _projected_tool_result_string(result: Any, field_name: str) -> str:
    if field_name == "content" and not hasattr(result, field_name):
        raise RuntimeError("projected tool result content is required")
    value = getattr(result, field_name, "")
    if not isinstance(value, str):
        raise RuntimeError(f"projected tool result {field_name} must be a string")
    return value


def _projected_tool_result_bool(result: Any, field_name: str) -> bool:
    value = getattr(result, field_name, False)
    if not isinstance(value, bool):
        raise RuntimeError(f"projected tool result {field_name} must be a boolean")
    return value


def _projected_tool_result_execution_status(result: Any) -> Any | None:
    value = getattr(result, "execution_status", None)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise RuntimeError(
            "projected tool result execution_status must be an object or None"
        )
    from opensquilla.execution_status import normalize_execution_status

    copied_value = _sidecar_json_input_copy(value)
    return normalize_execution_status(copied_value)


def _validate_projected_tool_result_arguments(result: Any) -> None:
    value = getattr(result, "arguments", None)
    if value is None:
        return
    if not isinstance(value, dict):
        raise RuntimeError(
            "projected tool result arguments must be an object or None"
        )
    _sidecar_json_input_copy(value)


def _tool_result_event_from_projection(result: Any, tool_call: ToolCall) -> ToolResultEvent:
    tool_use_id = _projected_tool_result_string(result, "tool_use_id")
    if not tool_use_id:
        raise RuntimeError("projected tool result tool_use_id must be non-empty")
    if tool_use_id != tool_call.tool_use_id:
        raise RuntimeError("projected tool result tool_use_id must match tool call")
    tool_name = _projected_tool_result_string(result, "tool_name")
    if not tool_name:
        raise RuntimeError("projected tool result tool_name must be non-empty")
    if tool_name != tool_call.tool_name:
        raise RuntimeError("projected tool result tool_name must match tool call")
    _validate_projected_tool_result_arguments(result)
    return ToolResultEvent(
        tool_use_id=tool_use_id,
        tool_name=tool_name,
        result=_projected_tool_result_string(result, "content"),
        is_error=_projected_tool_result_bool(result, "is_error"),
        arguments=tool_call.arguments,
        execution_status=_projected_tool_result_execution_status(result),
    )


def _intent_tool_call_id(payload: dict[str, Any]) -> str:
    for field_name in ("tool_call_id", "toolCallId", "id"):
        if field_name not in payload:
            continue
        raw = payload[field_name]
        if raw is None or not isinstance(raw, str):
            raise PiSidecarProtocolError(
                "Pi sidecar intent requires string tool_call_id"
            )
        tool_call_id = raw.strip()
        if not tool_call_id:
            raise PiSidecarProtocolError("Pi sidecar intent requires tool_call_id")
        return tool_call_id
    return ""


def _host_event_error(event: AgentEvent, field_name: str, expected: str) -> RuntimeError:
    return RuntimeError(
        f"KernelHostPorts returned malformed {type(event).__name__}: "
        f"{field_name} must be {expected}"
    )


def _host_event_string(event: AgentEvent, field_name: str) -> None:
    if not isinstance(getattr(event, field_name), str):
        raise _host_event_error(event, field_name, "a string")


def _host_event_non_empty_string(event: AgentEvent, field_name: str) -> None:
    value = getattr(event, field_name)
    if not isinstance(value, str) or not value.strip():
        raise _host_event_error(event, field_name, "a non-empty string")


def _host_event_optional_string(event: AgentEvent, field_name: str) -> None:
    value = getattr(event, field_name)
    if value is not None and not isinstance(value, str):
        raise _host_event_error(event, field_name, "a string or None")


def _host_event_int(event: AgentEvent, field_name: str) -> None:
    value = getattr(event, field_name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise _host_event_error(event, field_name, "an integer")


def _host_event_non_negative_int(event: AgentEvent, field_name: str) -> None:
    value = getattr(event, field_name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise _host_event_error(event, field_name, "a non-negative integer")


def _host_event_int_less_than_or_equal(
    event: AgentEvent,
    field_name: str,
    *,
    limit_field_name: str,
) -> None:
    value = getattr(event, field_name)
    limit = getattr(event, limit_field_name)
    if value > limit:
        raise _host_event_error(event, field_name, f"<= {limit_field_name}")


def _host_event_number(event: AgentEvent, field_name: str) -> None:
    value = getattr(event, field_name)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise _host_event_error(event, field_name, "a number")
    if not math.isfinite(float(value)):
        raise _host_event_error(event, field_name, "finite")


def _host_event_non_negative_number(event: AgentEvent, field_name: str) -> None:
    value = getattr(event, field_name)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise _host_event_error(event, field_name, "a number")
    if not math.isfinite(float(value)):
        raise _host_event_error(event, field_name, "finite")
    if float(value) < 0.0:
        raise _host_event_error(event, field_name, "a non-negative number")


def _host_event_probability(event: AgentEvent, field_name: str) -> None:
    _host_event_non_negative_number(event, field_name)
    if float(getattr(event, field_name)) > 1.0:
        raise _host_event_error(event, field_name, "a probability")


def _host_session_totals_non_negative_int(
    event: AgentEvent,
    field_name: str,
) -> None:
    session_totals = cast(SessionTotalsSnapshot, event.session_totals)
    value = getattr(session_totals, field_name)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise _host_event_error(
            event,
            f"session_totals.{field_name}",
            "a non-negative integer",
        )


def _host_session_totals_int_less_than_or_equal(
    event: AgentEvent,
    field_name: str,
    *,
    limit_field_name: str,
) -> None:
    session_totals = cast(SessionTotalsSnapshot, event.session_totals)
    value = getattr(session_totals, field_name)
    limit = getattr(session_totals, limit_field_name)
    if value > limit:
        raise _host_event_error(
            event,
            f"session_totals.{field_name}",
            f"<= session_totals.{limit_field_name}",
        )


def _host_session_totals_non_negative_number(
    event: AgentEvent,
    field_name: str,
) -> None:
    session_totals = cast(SessionTotalsSnapshot, event.session_totals)
    value = getattr(session_totals, field_name)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise _host_event_error(event, f"session_totals.{field_name}", "a number")
    if not math.isfinite(float(value)):
        raise _host_event_error(event, f"session_totals.{field_name}", "finite")
    if float(value) < 0.0:
        raise _host_event_error(
            event,
            f"session_totals.{field_name}",
            "a non-negative number",
        )


def _host_event_bool(event: AgentEvent, field_name: str) -> None:
    if not isinstance(getattr(event, field_name), bool):
        raise _host_event_error(event, field_name, "a boolean")


def _host_event_kind(event: AgentEvent, expected: str) -> None:
    if getattr(event, "kind", None) != expected:
        raise _host_event_error(event, "kind", repr(expected))


def _host_event_agent_state(event: AgentEvent, field_name: str) -> None:
    if not isinstance(getattr(event, field_name), AgentState):
        raise _host_event_error(event, field_name, "an AgentState")


def _validate_host_agent_event(event: AgentEvent) -> AgentEvent:
    for event_type, expected_kind in (
        (ThinkingEvent, "thinking"),
        (TextDeltaEvent, "text_delta"),
        (RunHeartbeatEvent, "run_heartbeat"),
        (ToolUseStartEvent, "tool_use_start"),
        (ToolUseEndEvent, "tool_use_end"),
        (ToolResultEvent, "tool_result"),
        (RouterControlReplayEvent, "router_control_replay"),
        (ArtifactEvent, "artifact"),
        (StateChangeEvent, "state_change"),
        (ErrorEvent, "error"),
        (DoneEvent, "done"),
        (CompactionEvent, "compaction"),
        (WarningEvent, "warning"),
        (RouterDecisionEvent, "router_decision"),
    ):
        if isinstance(event, event_type):
            _host_event_kind(event, expected_kind)
            break

    if isinstance(event, (ThinkingEvent, TextDeltaEvent)):
        _host_event_string(event, "text")
    elif isinstance(event, RunHeartbeatEvent):
        for field_name in ("phase", "message"):
            _host_event_string(event, field_name)
        for field_name in ("elapsed_ms", "idle_ms"):
            _host_event_non_negative_int(event, field_name)
    elif isinstance(event, ToolUseStartEvent):
        for field_name in ("tool_use_id", "tool_name"):
            _host_event_non_empty_string(event, field_name)
        _host_event_bool(event, "synthetic_from_text")
    elif isinstance(event, ToolUseEndEvent):
        for field_name in ("tool_use_id", "tool_name"):
            _host_event_non_empty_string(event, field_name)
        if not isinstance(event.arguments, dict):
            raise _host_event_error(event, "arguments", "an object")
        try:
            _sidecar_json_input_copy(event.arguments)
        except RuntimeError as exc:
            raise _host_event_error(event, "arguments", "JSON-safe") from exc
        _host_event_bool(event, "synthetic_from_text")
    elif isinstance(event, ToolResultEvent):
        for field_name in ("tool_use_id", "tool_name", "result"):
            if field_name in {"tool_use_id", "tool_name"}:
                _host_event_non_empty_string(event, field_name)
            else:
                _host_event_string(event, field_name)
        _host_event_bool(event, "is_error")
        if event.arguments is not None and not isinstance(event.arguments, dict):
            raise _host_event_error(event, "arguments", "an object or None")
        if event.arguments is not None:
            try:
                _sidecar_json_input_copy(event.arguments)
            except RuntimeError as exc:
                raise _host_event_error(event, "arguments", "JSON-safe") from exc
        if event.execution_status is not None and not isinstance(
            event.execution_status,
            dict,
        ):
            raise _host_event_error(
                event,
                "execution_status",
                "an object or None",
            )
        if event.execution_status is not None:
            try:
                _sidecar_json_input_copy(event.execution_status)
            except RuntimeError as exc:
                raise _host_event_error(event, "execution_status", "JSON-safe") from exc
    elif isinstance(event, RouterControlReplayEvent):
        _host_event_string(event, "action")
        for field_name in ("target_tier", "target_model", "target_provider", "target_id"):
            _host_event_optional_string(event, field_name)
        _host_event_non_negative_int(event, "replay_depth")
    elif isinstance(event, ArtifactEvent):
        for field_name in (
            "id",
            "sha256",
            "name",
            "mime",
            "session_id",
            "session_key",
            "source",
            "created_at",
            "download_url",
            "store",
        ):
            _host_event_string(event, field_name)
        _host_event_non_negative_int(event, "size")
    elif isinstance(event, StateChangeEvent):
        for field_name in ("from_state", "to_state"):
            _host_event_agent_state(event, field_name)
    elif isinstance(event, ErrorEvent):
        for field_name in ("message", "code"):
            _host_event_string(event, field_name)
    elif isinstance(event, DoneEvent):
        for field_name in (
            "text",
            "cost_source",
            "model",
            "routing_source",
            "baseline_model",
            "routed_model",
            "rollout_phase",
        ):
            _host_event_string(event, field_name)
        for field_name in ("runtime_context_hash", "routed_tier", "reasoning_content"):
            _host_event_optional_string(event, field_name)
        for field_name in (
            "input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "cached_tokens",
            "iterations",
            "runtime_context_chars",
            "cache_write_tokens",
        ):
            _host_event_non_negative_int(event, field_name)
        for field_name in ("cached_tokens", "cache_write_tokens"):
            _host_event_int_less_than_or_equal(
                event,
                field_name,
                limit_field_name="input_tokens",
            )
        for field_name in ("cost_usd", "billed_cost"):
            _host_event_non_negative_number(event, field_name)
        _host_event_probability(event, "routing_confidence")
        for field_name in (
            "savings_pct",
            "savings_usd",
            "total_savings_pct",
            "total_savings_usd",
        ):
            _host_event_non_negative_number(event, field_name)
        for field_name in ("cache_hit_active", "routing_applied"):
            _host_event_bool(event, field_name)
        if event.session_totals is not None and not isinstance(
            event.session_totals,
            SessionTotalsSnapshot,
        ):
            raise _host_event_error(
                event,
                "session_totals",
                "a SessionTotalsSnapshot or None",
            )
        if event.session_totals is not None:
            try:
                _sidecar_json_input_copy(event.session_totals)
            except RuntimeError as exc:
                raise _host_event_error(event, "session_totals", "JSON-safe") from exc
            for field_name in (
                "input_tokens",
                "output_tokens",
                "cache_read_tokens",
                "cache_write_tokens",
            ):
                _host_session_totals_non_negative_int(event, field_name)
            for field_name in ("cache_read_tokens", "cache_write_tokens"):
                _host_session_totals_int_less_than_or_equal(
                    event,
                    field_name,
                    limit_field_name="input_tokens",
                )
            for field_name in ("cost_usd", "billed_cost"):
                _host_session_totals_non_negative_number(event, field_name)
    elif isinstance(event, RouterDecisionEvent):
        for field_name in (
            "tier",
            "model",
            "baseline_model",
            "source",
            "thinking_mode",
            "prompt_policy",
            "rollout_phase",
        ):
            _host_event_string(event, field_name)
        _host_event_int(event, "tier_index")
        _host_event_probability(event, "confidence")
        _host_event_number(event, "savings_pct")
        if not isinstance(event.probs, list) or any(
            not isinstance(value, (int, float)) or isinstance(value, bool)
            or not math.isfinite(float(value))
            or float(value) < 0.0
            or float(value) > 1.0
            for value in event.probs
        ):
            raise _host_event_error(event, "probs", "a list of probabilities")
        for field_name in ("fallback", "routing_applied"):
            _host_event_bool(event, field_name)
    elif isinstance(event, WarningEvent):
        for field_name in ("code", "message"):
            _host_event_string(event, field_name)
    elif isinstance(event, CompactionEvent):
        _host_event_optional_string(event, "compaction_id")
        _host_event_string(event, "summary")
        if not isinstance(event.kept_entries, list) or any(
            not isinstance(entry, dict) for entry in event.kept_entries
        ):
            raise _host_event_error(
                event,
                "kept_entries",
                "a list of JSON-safe objects",
            )
        try:
            _sidecar_json_input_copy(event.kept_entries)
        except RuntimeError as exc:
            raise _host_event_error(
                event,
                "kept_entries",
                "a list of JSON-safe objects",
            ) from exc
        for field_name in ("kept_count", "removed_count"):
            _host_event_non_negative_int(event, field_name)
    return event


def _validate_host_port_event_session_scope(
    events: list[AgentEvent],
    *,
    session_key: str,
    port_name: str,
) -> None:
    for event in events:
        if isinstance(event, ArtifactEvent) and event.session_key != session_key:
            raise RuntimeError(
                f"KernelHostPorts.{port_name} returned ArtifactEvent "
                "for a different session_key"
            )


def _validate_host_port_tool_identity(
    events: list[AgentEvent],
    *,
    tool_call_id: str,
    tool_name: str,
    port_name: str,
) -> None:
    for event in events:
        if not isinstance(event, (ToolUseStartEvent, ToolUseEndEvent, ToolResultEvent)):
            continue
        event_name = event.__class__.__name__
        if event.tool_use_id != tool_call_id:
            raise RuntimeError(
                f"KernelHostPorts.{port_name} returned {event_name} "
                "for a different tool_use_id"
            )
        if event.tool_name != tool_name:
            raise RuntimeError(
                f"KernelHostPorts.{port_name} returned {event_name} "
                "for a different tool_name"
            )


def _validate_host_port_terminal_batch(
    events: list[AgentEvent],
    *,
    port_name: str,
) -> None:
    terminal_indexes = [
        index
        for index, event in enumerate(events)
        if isinstance(event, (DoneEvent, ErrorEvent))
    ]
    if len(terminal_indexes) > 1:
        raise RuntimeError(
            f"KernelHostPorts.{port_name} returned multiple terminal events"
        )
    if terminal_indexes and terminal_indexes[-1] != len(events) - 1:
        raise RuntimeError(
            f"KernelHostPorts.{port_name} returned events after terminal event"
        )


async def _coerce_host_port_events(result: Any) -> AsyncIterator[AgentEvent]:
    def _validated_event(event: Any) -> AgentEvent:
        if not isinstance(event, _AGENT_EVENT_TYPES):
            raise RuntimeError(
                "KernelHostPorts returned non-AgentEvent: "
                f"{type(event).__name__}"
            )
        return _validate_host_agent_event(cast(AgentEvent, event))

    if result is None:
        return
    if hasattr(result, "__aiter__"):
        async for event in result:
            yield _validated_event(event)
        return
    if isinstance(result, Iterable) and not isinstance(result, (str, bytes, dict)):
        for event in result:
            yield _validated_event(event)
        return
    yield _validated_event(result)


async def _close_async_iterator(stream: Any) -> None:
    aclose = getattr(stream, "aclose", None)
    if aclose is None:
        return
    result = aclose()
    if inspect.isawaitable(result):
        await result
