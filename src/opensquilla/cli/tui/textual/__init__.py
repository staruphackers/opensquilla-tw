"""Live Textual TUI surface primitives."""

from __future__ import annotations

from opensquilla.cli.tui.textual.app import (
    CHAT_INPUT_PLACEHOLDER,
    COMPLETED_OUTPUT_PREFIX,
    ROUTER_HUD_DEFAULT,
    RUNNING_OUTPUT_PREFIX,
    USER_ECHO_LABEL,
    ChatInput,
    TextualChatApp,
    classify_textual_output_line,
    format_router_hud_label,
    normalize_pasted_chat_text,
    normalize_textual_output_payload,
    render_textual_output_line,
    render_textual_output_payload,
)
from opensquilla.cli.tui.textual.surface import (
    TextualOutputHandle,
    TextualSurface,
    open_textual_surface,
)

__all__ = [
    "CHAT_INPUT_PLACEHOLDER",
    "COMPLETED_OUTPUT_PREFIX",
    "ROUTER_HUD_DEFAULT",
    "RUNNING_OUTPUT_PREFIX",
    "USER_ECHO_LABEL",
    "ChatInput",
    "TextualChatApp",
    "TextualOutputHandle",
    "TextualSurface",
    "classify_textual_output_line",
    "format_router_hud_label",
    "normalize_textual_output_payload",
    "normalize_pasted_chat_text",
    "open_textual_surface",
    "render_textual_output_line",
    "render_textual_output_payload",
]
