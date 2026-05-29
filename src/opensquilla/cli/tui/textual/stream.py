"""Streaming helpers for the live Textual surface."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Protocol


class TextualStreamTarget(Protocol):
    def append_stream_output(self, payload: str) -> None: ...

    def flush_stream_output(self) -> None: ...


@asynccontextmanager
async def textual_stream_output(
    app: TextualStreamTarget,
) -> AsyncIterator[Callable[[str], None]]:
    buffered = ""

    def write(payload: str) -> None:
        nonlocal buffered
        if payload:
            buffered += payload
            while "\n" in buffered:
                line, buffered = buffered.split("\n", 1)
                app.append_stream_output(f"{line}\n")
            if len(buffered) >= 96:
                app.append_stream_output(f"{buffered.rstrip()}\n")
                buffered = ""

    try:
        yield write
    finally:
        if buffered:
            app.append_stream_output(buffered)
        app.flush_stream_output()
