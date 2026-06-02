"""Agent re-emit hop: provider ReasoningDeltaEvent -> engine ThinkingEvent.

The agent layer translates provider-level stream events into engine-level
events. Reasoning must cross this hop as a first-class ThinkingEvent (not folded
into assistant text), so the TUI can render it as a distinct thinking stream.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from opensquilla.engine import Agent, AgentConfig
from opensquilla.engine.types import ThinkingEvent
from opensquilla.provider import ChatConfig, Message
from opensquilla.provider import DoneEvent as ProviderDone
from opensquilla.provider import ReasoningDeltaEvent as ProviderReasoning
from opensquilla.provider import TextDeltaEvent as ProviderText


class _ReasoningProvider:
    provider_name = "fake"

    def chat(
        self,
        messages: list[Message],
        tools: list[Any] | None = None,
        config: ChatConfig | None = None,
    ) -> AsyncIterator[Any]:
        return self._stream()

    async def _stream(self) -> AsyncIterator[Any]:
        yield ProviderReasoning(text="Let me ")
        yield ProviderReasoning(text="think.")
        yield ProviderText(text="The answer.")
        yield ProviderDone(
            stop_reason="stop",
            input_tokens=5,
            output_tokens=3,
            reasoning_content="Let me think.",
        )

    async def list_models(self) -> list[Any]:
        return []


def test_agent_reemits_reasoning_as_thinking_event() -> None:
    import asyncio

    async def run() -> list[Any]:
        agent = Agent(provider=_ReasoningProvider(), config=AgentConfig(max_iterations=1))
        return [event async for event in agent.run_turn("hi")]

    events = asyncio.run(run())

    thinking = [e for e in events if isinstance(e, ThinkingEvent)]
    assert [t.text for t in thinking] == ["Let me ", "think."]

    # reasoning must NOT be folded into the assistant answer text
    answer = "".join(
        e.text for e in events if type(e).__name__ == "TextDeltaEvent"
    )
    assert answer == "The answer."
    assert "think" not in answer
