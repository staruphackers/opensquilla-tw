from __future__ import annotations

import asyncio

import pytest
from textual.events import Paste
from textual.widgets import Static

from opensquilla.cli.tui.backend.contracts import TuiOutputHandle, TuiSurface
from opensquilla.cli.tui.textual import (
    CHAT_INPUT_PLACEHOLDER,
    ROUTER_HUD_DEFAULT,
    USER_ECHO_LABEL,
    ChatInput,
    TextualChatApp,
    TextualOutputHandle,
    TextualSurface,
    classify_textual_output_line,
    format_router_hud_label,
    normalize_pasted_chat_text,
    normalize_textual_output_payload,
    render_textual_output_line,
    render_textual_output_payload,
)
from opensquilla.engine.commands import Surface


@pytest.mark.asyncio
async def test_textual_surface_exposes_submitted_lines_and_eof() -> None:
    app = TextualChatApp(
        model="fake-model",
        session_id="fake-session",
        ready_marker=None,
        print_ready_marker=False,
    )
    surface = TextualSurface(app, approval_surface=Surface.CLI_GATEWAY)

    assert isinstance(surface, TuiSurface)

    app.submit_text("hello textual")

    assert await surface.next_line() == "hello textual"

    surface.emit_eof()

    assert await surface.next_line() is None


@pytest.mark.asyncio
async def test_textual_shutdown_action_delegates_eof_to_registered_callback() -> None:
    app = TextualChatApp(
        model="fake-model",
        session_id="fake-session",
        ready_marker=None,
        print_ready_marker=False,
    )
    shutdown_calls: list[str] = []

    def _shutdown() -> None:
        shutdown_calls.append("shutdown")
        app.emit_eof()

    app.set_shutdown_callback(_shutdown)
    app.action_request_shutdown()

    assert shutdown_calls == ["shutdown"]
    assert await app.next_submitted_line() is None

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(app.next_submitted_line(), timeout=0.01)


@pytest.mark.asyncio
async def test_textual_output_handle_writes_and_streams_to_transcript() -> None:
    app = TextualChatApp(
        model="fake-model",
        session_id="fake-session",
        ready_marker=None,
        print_ready_marker=False,
    )
    output = TextualOutputHandle(app, approval_surface=Surface.CLI_GATEWAY)

    assert isinstance(output, TuiOutputHandle)
    assert output.approval_surface is Surface.CLI_GATEWAY

    await output.write_through("one-shot payload")
    async with output.stream_output() as write:
        write("chunk-a")
        assert "chunk-a" in app.transcript_text
        assert app.active_stream_text == "chunk-a"
        write("chunk-b")
        assert app.active_stream_text == "chunk-achunk-b"

    assert "one-shot payload" in app.transcript_text
    assert "chunk-achunk-b" in app.transcript_text
    assert app.active_stream_text == ""


@pytest.mark.asyncio
async def test_textual_stream_region_hides_after_stream_flush() -> None:
    app = TextualChatApp(
        model="fake-model",
        session_id="fake-session",
        ready_marker=None,
        print_ready_marker=False,
    )

    async with app.run_test() as pilot:
        stream_widget = app.query_one("#active-stream", Static)
        assert stream_widget.display is False

        app.append_stream_output("terminal-change-response CJK混合ASCII")
        await pilot.pause()

        assert stream_widget.display is True
        assert app.active_stream_text == "terminal-change-response CJK混合ASCII"

        app.flush_stream_output()
        await pilot.pause()

        assert "terminal-change-response CJK混合ASCII" in app.transcript_text
        assert app.active_stream_text == ""
        assert stream_widget.display is False


def test_textual_output_toolbar_updates_router_hud_without_status_spam() -> None:
    app = TextualChatApp(
        model="fake-model",
        session_id="fake-session",
        ready_marker=None,
        print_ready_marker=False,
    )
    output = TextualOutputHandle(app, approval_surface=Surface.CLI_GATEWAY)

    output.set_toolbar("router_hud", "route standard -> fake-textual 99% save 42%")
    output.set_toolbar("router_hud_style", "normal")
    output.invalidate()

    assert app.status_text == "model fake-model | session fake-session"
    assert app.router_hud_text == "Router: fake-textual | 99% | save 42%"
    assert app.router_hud_style == "normal"

    output.set_toolbar("router_hud", None)
    output.invalidate()

    assert app.router_hud_text == ROUTER_HUD_DEFAULT
    assert app.router_hud_style == "dim"


def test_textual_router_hud_label_compacts_model_confidence_and_savings() -> None:
    assert format_router_hud_label(None) == ROUTER_HUD_DEFAULT
    assert format_router_hud_label("") == ROUTER_HUD_DEFAULT
    assert format_router_hud_label("route t2 -> claude-sonnet-4.6 71% save 64%") == (
        "Router: claude-sonnet-4.6 | 71% | save 64%"
    )


@pytest.mark.parametrize(
    ("line", "kind"),
    [
        (USER_ECHO_LABEL, "user_label"),
        ("thinking through a plan", "thinking"),
        ("router route standard -> fake-terminal 99% save 42%", "thinking"),
        ("▸ read_file fixture.txt", "tool_call"),
        ("tool_output read_file 198 lines", "tool_detail"),
        ("198 lines", "tool_detail"),
        ("fake-terminal · 0.0s", "usage"),
        ("1 in / 2 out", "usage"),
        ("✗ fake_tool: bad", "error"),
    ],
)
def test_textual_output_lines_are_classified_for_semantic_rendering(
    line: str,
    kind: str,
) -> None:
    assert classify_textual_output_line(line) == kind


def test_textual_output_line_styles_distinguish_tool_thinking_and_error_content() -> None:
    assert "#38bdf8" in str(render_textual_output_line("▸ fake_tool").style)
    assert "#c9964b" in str(render_textual_output_line("thinking...").style)
    assert "#7d8794" in str(render_textual_output_line("tool_output 3 lines").style)
    assert "#ef6461" in str(render_textual_output_line("error: denied").style)


def test_textual_payload_rendering_keeps_user_text_visually_distinct() -> None:
    rendered = [
        item
        for item in render_textual_output_payload(
            f"\n{USER_ECHO_LABEL}\nfirst line 中文输入 CJK混合ASCII\n\n◢ squilla\nfake-response"
        )
        if item.plain
    ]
    styles = {item.plain: str(item.style) for item in rendered}

    assert "#ff8a4c" in styles[USER_ECHO_LABEL]
    assert "#ffd08a" in styles["first line 中文输入 CJK混合ASCII"]
    assert "#e7edf4" in styles["fake-response"]


def test_textual_layout_uses_custom_bilingual_chat_surface() -> None:
    assert "输入消息" in CHAT_INPUT_PLACEHOLDER
    assert USER_ECHO_LABEL == "你 / you"
    assert "#shell" in TextualChatApp.CSS
    assert "#workspace" in TextualChatApp.CSS
    assert "#composer" in TextualChatApp.CSS
    assert "#router-hud" in TextualChatApp.CSS
    assert "#status" in TextualChatApp.CSS


def test_textual_paste_normalizes_multiline_cjk_without_truncation() -> None:
    pasted = "first line\nsecond line CJK混合ASCII"

    assert normalize_pasted_chat_text(pasted) == "first line second line CJK混合ASCII"


@pytest.mark.asyncio
async def test_textual_chat_input_inserts_normalized_cjk_paste() -> None:
    app = TextualChatApp(
        model="fake-model",
        session_id="fake-session",
        ready_marker=None,
        print_ready_marker=False,
    )

    async with app.run_test():
        input_widget = app.query_one("#input", ChatInput)
        input_widget.on_paste(Paste("first line\nsecond line CJK混合ASCII"))

        assert input_widget.value == "first line second line CJK混合ASCII"


def test_textual_output_normalizes_rich_capture_padding() -> None:
    assert normalize_textual_output_payload("fake-terminal · 0.0s     \nnext") == (
        "fake-terminal · 0.0s\nnext"
    )
