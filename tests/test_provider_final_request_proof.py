from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from opensquilla.provider.anthropic import AnthropicProvider
from opensquilla.provider.openai import OpenAIProvider
from opensquilla.provider.types import ChatConfig, ErrorEvent, Message


def test_openai_final_request_proof_blocks_oversized_send(monkeypatch: Any) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def patched_async_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr("opensquilla.provider.openai.httpx.AsyncClient", patched_async_client)
    provider = OpenAIProvider(api_key="test", model="gpt-test")

    async def run() -> list[Any]:
        return [
            event
            async for event in provider.chat(
                [Message(role="user", content="x" * 5000)],
                config=ChatConfig(provider_request_max_chars=1000),
            )
        ]

    events = asyncio.run(run())

    assert requests == []
    assert isinstance(events[0], ErrorEvent)
    assert events[0].code == "provider_request_budget_exhausted"
    proof = json.loads(events[0].message)
    assert proof["fits"] is False
    assert proof["retry_count"] == 1
    assert proof["top_contributors"][0]["chars"] == 5000


def test_anthropic_final_request_proof_blocks_oversized_send(monkeypatch: Any) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(500)

    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def patched_async_client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr("opensquilla.provider.anthropic.httpx.AsyncClient", patched_async_client)
    provider = AnthropicProvider(api_key="test", model="claude-test")

    async def run() -> list[Any]:
        return [
            event
            async for event in provider.chat(
                [Message(role="user", content="x" * 5000)],
                config=ChatConfig(provider_request_max_chars=1000),
            )
        ]

    events = asyncio.run(run())

    assert requests == []
    assert isinstance(events[0], ErrorEvent)
    assert events[0].code == "provider_request_budget_exhausted"
    proof = json.loads(events[0].message)
    assert proof["fits"] is False
    assert proof["retry_count"] == 1
