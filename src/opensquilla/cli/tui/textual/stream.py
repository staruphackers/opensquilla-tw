"""Streaming helpers for the live Textual surface."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from opensquilla.cli.tui.textual.app import TextualChatApp


@asynccontextmanager
async def textual_stream_output(
    app: TextualChatApp,
) -> AsyncIterator[Callable[[str], None]]:
    def write(payload: str) -> None:
        if payload:
            app.append_stream_output(payload)

    try:
        yield write
    finally:
        app.flush_stream_output()
