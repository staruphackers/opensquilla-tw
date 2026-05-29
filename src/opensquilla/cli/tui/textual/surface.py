"""TUI backend surface adapter for the live Textual app."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from opensquilla.cli.tui.backend.contracts import TuiSurface
from opensquilla.cli.tui.textual.app import (
    ROUTER_HUD_DEFAULT,
    TextualChatApp,
    format_router_hud_label,
    normalize_textual_output_payload,
    write_inline_terminal_payload,
)
from opensquilla.cli.tui.textual.stream import textual_stream_output
from opensquilla.engine.commands import Surface


class TextualOutputHandle:
    """Typed output bridge over the live Textual chat app."""

    def __init__(
        self,
        app: TextualChatApp,
        *,
        approval_surface: Surface,
    ) -> None:
        self._app = app
        self.approval_surface = approval_surface
        self._toolbar: dict[str, object] = {}

    async def write_through(self, payload: str) -> None:
        self._app.append_output(payload)

    def stream_output(self) -> AbstractAsyncContextManager[Callable[[str], None]]:
        return textual_stream_output(self._app)

    def set_toolbar(self, key: str, value: object | None) -> None:
        if value is None:
            self._toolbar.pop(key, None)
            return
        self._toolbar[key] = value

    def invalidate(self) -> None:
        router_hud = self._toolbar.get("router_hud")
        router_hud_style = self._toolbar.get("router_hud_style")
        self._app.set_router_hud(
            str(router_hud) if router_hud is not None else None,
            style=str(router_hud_style) if router_hud_style is not None else None,
        )


class TextualSurface:
    """Adapter exposing `TextualChatApp` through `TuiSurface`."""

    def __init__(
        self,
        app: TextualChatApp,
        *,
        approval_surface: Surface = Surface.CLI_GATEWAY,
    ) -> None:
        self._app = app
        self._output_handle = TextualOutputHandle(
            app,
            approval_surface=approval_surface,
        )

    async def next_line(self) -> str | None:
        return await self._app.next_submitted_line()

    @property
    def output_handle(self) -> TextualOutputHandle:
        return self._output_handle

    @property
    def redraw_callback(self) -> Callable[[], None]:
        return self._app.refresh_ui

    def set_cancel_callback(self, cb: Callable[[], None] | None) -> None:
        self._app.set_cancel_callback(cb)

    def set_shutdown_callback(self, cb: Callable[[], None] | None) -> None:
        self._app.set_shutdown_callback(cb)

    def emit_eof(self) -> None:
        self._app.emit_eof()

    async def write_through(self, payload: str) -> None:
        await self._output_handle.write_through(payload)


class InlineTextualOutputHandle:
    """Append-only output bridge for inline Textual prompt sessions."""

    def __init__(
        self,
        surface: InlineTextualSurface,
        *,
        approval_surface: Surface,
    ) -> None:
        self._surface = surface
        self.approval_surface = approval_surface
        self._toolbar: dict[str, object] = {}

    async def write_through(self, payload: str) -> None:
        self._surface.append_output(payload)

    def stream_output(self) -> AbstractAsyncContextManager[Callable[[str], None]]:
        return textual_stream_output(self._surface)

    def set_toolbar(self, key: str, value: object | None) -> None:
        if value is None:
            self._toolbar.pop(key, None)
            return
        self._toolbar[key] = value

    def invalidate(self) -> None:
        router_hud = self._toolbar.get("router_hud")
        router_hud_style = self._toolbar.get("router_hud_style")
        self._surface.set_router_hud(
            str(router_hud) if router_hud is not None else None,
            style=str(router_hud_style) if router_hud_style is not None else None,
        )


class InlineTextualSurface:
    """Line-oriented Textual surface: Textual for input, terminal for output."""

    def __init__(
        self,
        *,
        surface: Surface,
        model: str | None,
        session_id: str | None,
        ready_marker: str | None,
        print_ready_marker: bool,
        inline: bool,
        inline_no_clear: bool,
    ) -> None:
        self.model = model
        self.session_id = session_id
        self.ready_marker = ready_marker
        self.print_ready_marker = print_ready_marker
        self.inline = inline
        self.inline_no_clear = inline_no_clear
        self._ready_emitted = False
        self._current_app: TextualChatApp | None = None
        self._cancel_callback: Callable[[], None] | None = None
        self._shutdown_callback: Callable[[], None] | None = None
        self._eof_emitted = False
        self._router_hud_text = ROUTER_HUD_DEFAULT
        self._router_hud_style = "dim"
        self._transcript_text = ""
        self._output_handle = InlineTextualOutputHandle(
            self,
            approval_surface=surface,
        )

    @property
    def output_handle(self) -> InlineTextualOutputHandle:
        return self._output_handle

    @property
    def redraw_callback(self) -> Callable[[], None]:
        return self.refresh_ui

    @property
    def transcript_text(self) -> str:
        return self._transcript_text

    async def next_line(self) -> str | None:
        if self._eof_emitted:
            return None

        app = TextualChatApp(
            model=self.model,
            session_id=self.session_id,
            ready_marker=self.ready_marker if not self._ready_emitted else None,
            print_ready_marker=self.print_ready_marker,
        )
        app.set_router_hud(
            self._router_hud_text if self._router_hud_text != ROUTER_HUD_DEFAULT else None,
            style=self._router_hud_style,
        )
        app.set_cancel_callback(self._cancel_callback)
        app.set_shutdown_callback(self._shutdown_callback)
        self._current_app = app
        self._ready_emitted = True

        run_task = asyncio.create_task(
            app.run_async(inline=self.inline, inline_no_clear=self.inline_no_clear)
        )
        line_task = asyncio.create_task(app.next_submitted_line())
        try:
            done, _pending = await asyncio.wait(
                {run_task, line_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if line_task in done:
                return line_task.result()
            if run_task in done and not line_task.done():
                await asyncio.sleep(0)
            if line_task.done():
                return line_task.result()
            return None
        finally:
            if not line_task.done():
                line_task.cancel()
            app.exit()
            await run_task
            self._current_app = None

    async def write_through(self, payload: str) -> None:
        self.append_output(payload)

    def append_output(self, payload: str) -> None:
        payload = normalize_textual_output_payload(payload)
        self._transcript_text += payload
        if not write_inline_terminal_payload(payload):
            print(payload, end="", flush=True)

    def append_stream_output(self, payload: str) -> None:
        self.append_output(payload)

    def flush_stream_output(self) -> None:
        return None

    def refresh_ui(self) -> None:
        app = self._current_app
        if app is not None:
            app.refresh_ui()

    def set_cancel_callback(self, cb: Callable[[], None] | None) -> None:
        self._cancel_callback = cb
        if self._current_app is not None:
            self._current_app.set_cancel_callback(cb)

    def set_shutdown_callback(self, cb: Callable[[], None] | None) -> None:
        self._shutdown_callback = cb
        if self._current_app is not None:
            self._current_app.set_shutdown_callback(cb)

    def emit_eof(self) -> None:
        self._eof_emitted = True
        if self._current_app is not None:
            self._current_app.emit_eof()
            self._current_app.exit()

    def set_router_hud(self, label: str | None = None, *, style: str | None = None) -> None:
        self._router_hud_text = format_router_hud_label(label)
        self._router_hud_style = "dim" if label is None else _normalize_router_hud_style(style)
        if self._current_app is not None:
            self._current_app.set_router_hud(label, style=style)


def _normalize_router_hud_style(style: str | None) -> str:
    if style in {"dim", "normal", "warning"}:
        return style
    return "dim" if style is None else "normal"


@asynccontextmanager
async def open_textual_surface(
    *,
    surface: Surface,
    model: str | None = None,
    session_id: str | None = None,
    ready_marker: str | None = "OPEN_SQUILLA_TUI_READY",
    print_ready_marker: bool = True,
    inline: bool = True,
    inline_no_clear: bool = True,
) -> AsyncIterator[TuiSurface]:
    if inline:
        yield InlineTextualSurface(
            surface=surface,
            model=model,
            session_id=session_id,
            ready_marker=ready_marker,
            print_ready_marker=print_ready_marker,
            inline=inline,
            inline_no_clear=inline_no_clear,
        )
        return

    app = TextualChatApp(
        model=model,
        session_id=session_id,
        ready_marker=ready_marker,
        print_ready_marker=print_ready_marker,
    )
    run_task = asyncio.create_task(
        app.run_async(inline=inline, inline_no_clear=inline_no_clear)
    )
    try:
        await asyncio.sleep(0)
        yield TextualSurface(app, approval_surface=surface)
    finally:
        app.exit()
        await run_task
