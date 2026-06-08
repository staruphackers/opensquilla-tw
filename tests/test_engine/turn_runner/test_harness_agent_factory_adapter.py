"""Tests for TurnRunner harness adapters."""

from __future__ import annotations

import contextlib
from types import SimpleNamespace
from typing import Any

import pytest

from opensquilla.engine.turn_runner.harness import (
    _coerce_flush_triggers,
    _TurnRunnerAgentFactoryAdapter,
    _TurnRunnerAgentRunAdapter,
    _TurnRunnerHistoryLoaderAdapter,
)
from opensquilla.engine.types import DoneEvent, TextDeltaEvent


def test_harness_flush_triggers_normalize_comma_delimited_aliases() -> None:
    assert _coerce_flush_triggers("reset, inline_overflow") == [
        "session_reset",
        "pre_compaction",
    ]


def test_harness_flush_triggers_reject_unknown_aliases() -> None:
    with pytest.raises(ValueError, match="unknown flush trigger"):
        _coerce_flush_triggers(["manual", "bogus"])


def test_agent_factory_adapter_passes_runner_tool_registry(monkeypatch) -> None:
    """Meta-skill execution needs the per-runner registry on constructed Agents."""

    captured: dict[str, Any] = {}

    class RecordingAgent:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    import opensquilla.engine.agent as agent_module

    monkeypatch.setattr(agent_module, "Agent", RecordingAgent)

    registry = object()
    runner = SimpleNamespace(
        _tool_registry=registry,
        _usage_tracker=None,
        _session_flush_service=None,
    )
    adapter = _TurnRunnerAgentFactoryAdapter(runner)

    adapter.build(
        provider=object(),
        config=object(),
        tool_definitions=[],
        tool_handler=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        tool_context=None,
    )

    assert captured["tool_registry"] is registry


@pytest.mark.asyncio
async def test_history_loader_adapter_forwards_provider_kind() -> None:
    calls: list[dict[str, Any]] = []

    class Runner:
        async def _load_history(
            self,
            agent: Any,
            session_key: str,
            *,
            trim_last_user: bool,
            provider_kind: str,
        ) -> str | None:
            calls.append(
                {
                    "agent": agent,
                    "session_key": session_key,
                    "trim_last_user": trim_last_user,
                    "provider_kind": provider_kind,
                }
            )
            return "SUMMARY"

    agent = SimpleNamespace(set_history=lambda _history: None)
    adapter = _TurnRunnerHistoryLoaderAdapter(Runner())

    result = await adapter.load(
        agent=agent,
        session_key="agent:main:test",
        trim_last_user=False,
        provider_kind="host-provider",
    )

    assert result == "SUMMARY"
    assert calls == [
        {
            "agent": agent,
            "session_key": "agent:main:test",
            "trim_last_user": False,
            "provider_kind": "host-provider",
        }
    ]


@pytest.mark.asyncio
async def test_agent_run_adapter_always_forwards_semantic_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import opensquilla.engine.runtime as runtime_module

    calls: list[dict[str, Any]] = []

    class Kernel:
        async def run_turn(
            self,
            turn_input: str,
            *,
            extra_messages: list[Any] | None = None,
            semantic_message: str | None = None,
        ):
            calls.append(
                {
                    "turn_input": turn_input,
                    "extra_messages": extra_messages,
                    "semantic_message": semantic_message,
                }
            )
            yield TextDeltaEvent(text="ok")

    monkeypatch.setattr(
        runtime_module,
        "_accepts_keyword_arg",
        lambda _callable, _name: False,
    )

    events = [
        event
        async for event in _TurnRunnerAgentRunAdapter().run_turn(
            Kernel(),
            turn_input="hello",
            extra_messages=[{"role": "user", "content": "extra"}],
            semantic_message="semantic input",
        )
    ]

    assert events == [TextDeltaEvent(text="ok")]
    assert calls == [
        {
            "turn_input": "hello",
            "extra_messages": [{"role": "user", "content": "extra"}],
            "semantic_message": "semantic input",
        }
    ]


@pytest.mark.asyncio
async def test_agent_factory_adapter_selects_pi_kernel_from_config(monkeypatch) -> None:
    """The kernel switch is below TurnRunner, so CLI/TUI contracts stay unchanged."""

    captured: dict[str, Any] = {}

    class RecordingAgent:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            assert message == "hello"
            yield {
                "protocol": "opensquilla.agent_core.v1",
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "from pi"},
            }

    import opensquilla.engine.agent as agent_module

    monkeypatch.setattr(agent_module, "Agent", RecordingAgent)

    runner = SimpleNamespace(
        _tool_registry=object(),
        _usage_tracker=None,
        _session_flush_service=None,
        _config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_client=FakePiRpcClient(),
            allow_test_pi_rpc_client=True,
        ),
    )
    adapter = _TurnRunnerAgentFactoryAdapter(runner)

    agent = adapter.build(
        provider=object(),
        config=SimpleNamespace(model_id="pi-model"),
        tool_definitions=[],
        tool_handler=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        tool_context=None,
    )

    events = [event async for event in agent.run_turn("hello", extra_messages=None)]

    assert events == [
        TextDeltaEvent(text="from pi"),
        DoneEvent(text="from pi", model="pi-model", cost_source="unavailable"),
    ]
    assert agent.__class__.__name__ == "PiSidecarKernelRuntime"
    assert captured["tool_registry"] is runner._tool_registry


@pytest.mark.asyncio
async def test_agent_factory_adapter_wires_pi_session_write_host_port(monkeypatch) -> None:
    """Pi session writes must go through the TurnRunner-owned session port."""

    class RecordingAgent:
        def __init__(self, **kwargs: Any) -> None:
            pass

    class FakePiRpcClient:
        async def stream_prompt(self, message: str, **kwargs):
            yield {
                "protocol": "opensquilla.agent_core.v1",
                "kind": "intent",
                "type": "session.write.enqueue",
                "payload": {
                    "role": "assistant",
                    "content": "sidecar state",
                },
            }
            yield {
                "protocol": "opensquilla.agent_core.v1",
                "kind": "event",
                "type": "text.delta",
                "payload": {"text": "done"},
            }

    class FakeSessionManager:
        def __init__(self) -> None:
            self.messages: list[tuple[str, dict[str, Any]]] = []

        async def append_message(self, session_key: str, **kwargs: Any) -> None:
            self.messages.append((session_key, kwargs))

    context_entries: list[str] = []

    @contextlib.asynccontextmanager
    async def write_context(session_key: str):
        context_entries.append(session_key)
        yield

    import opensquilla.engine.agent as agent_module

    monkeypatch.setattr(agent_module, "Agent", RecordingAgent)

    session_manager = FakeSessionManager()
    runner = SimpleNamespace(
        _tool_registry=object(),
        _usage_tracker=None,
        _session_flush_service=None,
        _session_manager=session_manager,
        _session_write_context_factory=lambda session_key: write_context(session_key),
        _config=SimpleNamespace(
            agent_kernel="pi",
            pi_agent_rpc_client=FakePiRpcClient(),
                allow_test_pi_rpc_client=True,
        ),
    )
    adapter = _TurnRunnerAgentFactoryAdapter(runner)

    agent = adapter.build(
        provider=object(),
        config=SimpleNamespace(model_id="pi-model"),
        tool_definitions=[],
        tool_handler=None,
        session_key="agent:main:test",
        turn_call_logger=None,
        memory_sync_manager=None,
        tool_context=None,
    )

    events = [event async for event in agent.run_turn("hello", extra_messages=None)]

    assert events == [
        TextDeltaEvent(text="done"),
        DoneEvent(text="done", model="pi-model", cost_source="unavailable"),
    ]
    assert context_entries == ["agent:main:test"]
    assert session_manager.messages == [
        (
            "agent:main:test",
            {
                "role": "assistant",
                "content": "sidecar state",
                "tool_calls": None,
                "reasoning_content": None,
                "turn_usage": None,
                "token_count": None,
            },
        )
    ]
