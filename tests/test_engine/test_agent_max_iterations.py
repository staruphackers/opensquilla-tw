from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from opensquilla.engine import Agent, AgentConfig, ToolResult
from opensquilla.engine.subagent import SubagentSpec
from opensquilla.engine.types import ArtifactEvent
from opensquilla.provider import (
    ChatConfig,
    Message,
    ToolDefinition,
    ToolInputSchema,
)
from opensquilla.provider import (
    DoneEvent as ProviderDone,
)
from opensquilla.provider import (
    TextDeltaEvent as ProviderText,
)
from opensquilla.provider import (
    ToolUseEndEvent as ProviderToolUseEnd,
)
from opensquilla.provider import (
    ToolUseStartEvent as ProviderToolUseStart,
)


class _LoopingToolProvider:
    provider_name = "fake"

    def __init__(self, *, final_on_call: int | None = None) -> None:
        self.final_on_call = final_on_call
        self.calls: list[list[Message]] = []

    def chat(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
        config: ChatConfig | None = None,
    ) -> AsyncIterator[Any]:
        self.calls.append(messages)
        call_number = len(self.calls)
        return self._stream(call_number)

    async def _stream(self, call_number: int) -> AsyncIterator[Any]:
        if self.final_on_call == call_number:
            yield ProviderText(text="done")
            yield ProviderDone(stop_reason="stop", input_tokens=1, output_tokens=1)
            return

        tool_id = f"tool-{call_number}"
        yield ProviderToolUseStart(tool_use_id=tool_id, tool_name="echo")
        yield ProviderToolUseEnd(
            tool_use_id=tool_id,
            tool_name="echo",
            arguments={"value": "again"},
        )
        yield ProviderDone(stop_reason="tool_use", input_tokens=1, output_tokens=1)

    async def list_models(self) -> list[Any]:
        return []


async def _echo_tool(call: Any) -> ToolResult:
    return ToolResult(
        tool_use_id=call.tool_use_id,
        tool_name=call.tool_name,
        content="ok",
    )


def _echo_definition() -> ToolDefinition:
    return ToolDefinition(
        name="echo",
        description="Echo.",
        input_schema=ToolInputSchema(
            properties={"value": {"type": "string"}},
            required=["value"],
        ),
    )


def test_agent_iteration_defaults_are_raised_to_100() -> None:
    assert AgentConfig().max_iterations == 100
    assert SubagentSpec(task="check").max_iterations == 100


@pytest.mark.asyncio
async def test_agent_reports_max_iterations_when_tool_loop_needs_another_iteration() -> None:
    provider = _LoopingToolProvider()
    agent = Agent(
        provider=provider,
        config=AgentConfig(max_iterations=1),
        tool_definitions=[_echo_definition()],
        tool_handler=_echo_tool,
    )

    events = [event async for event in agent.run_turn("hello")]

    assert len(provider.calls) == 1
    assert any(event.kind == "error" and event.code == "max_iterations" for event in events)
    assert agent._history == []


@pytest.mark.asyncio
async def test_agent_allows_final_response_on_last_iteration() -> None:
    provider = _LoopingToolProvider(final_on_call=2)
    agent = Agent(
        provider=provider,
        config=AgentConfig(max_iterations=2),
        tool_definitions=[_echo_definition()],
        tool_handler=_echo_tool,
    )

    events = [event async for event in agent.run_turn("hello")]

    assert len(provider.calls) == 2
    assert not any(event.kind == "error" and event.code == "max_iterations" for event in events)
    assert any(event.kind == "done" and event.text == "done" for event in events)


@pytest.mark.asyncio
async def test_agent_emits_artifact_event_independent_of_tool_result_text() -> None:
    async def artifact_tool(call: Any) -> ToolResult:
        return ToolResult(
            tool_use_id=call.tool_use_id,
            tool_name=call.tool_name,
            content="tool text that may be compressed",
            artifacts=[
                {
                    "id": "art-1",
                    "name": "report.txt",
                    "mime": "text/plain",
                    "size": 12,
                    "sha256": "a" * 64,
                    "session_id": "session-1",
                    "session_key": "agent:main:webchat:session-1",
                    "source": "publish_artifact",
                    "created_at": "2026-05-06T12:00:00Z",
                    "download_url": "/api/v1/artifacts/art-1",
                }
            ],
        )

    provider = _LoopingToolProvider()
    agent = Agent(
        provider=provider,
        config=AgentConfig(max_iterations=1, tool_result_compression_mode="truncate"),
        tool_definitions=[_echo_definition()],
        tool_handler=artifact_tool,
    )

    events = [event async for event in agent.run_turn("hello")]

    artifact_events = [event for event in events if isinstance(event, ArtifactEvent)]
    assert len(artifact_events) == 1
    assert artifact_events[0].id == "art-1"
    assert artifact_events[0].download_url == "/api/v1/artifacts/art-1"
