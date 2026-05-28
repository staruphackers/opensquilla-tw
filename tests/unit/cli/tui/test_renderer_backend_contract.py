from __future__ import annotations

import asyncio
import sys

import pytest

from opensquilla.cli.tui.backend.transcript import (
    MessageItem,
    TranscriptStore,
    ViewportRequest,
    project_viewport,
)
from opensquilla.cli.tui.plugins.router_hud import RouterHudSnapshot
from opensquilla.cli.tui.renderers.selection import (
    RendererBackendUnavailableError,
    get_renderer_backend,
    select_renderer_backend,
)
from opensquilla.cli.tui.renderers.textual_backend import (
    TextualRendererBackend,
    TextualReplayRenderer,
)


def test_terminal_backend_is_default_and_preserves_fast_streaming_path() -> None:
    backend = select_renderer_backend()

    assert backend.backend_id == "terminal"
    assert backend.supports_streaming_fast_path is True
    assert backend.supports_structured_ui is False
    assert backend.is_available().available is True
    assert hasattr(backend.create_renderer(title="test"), "aappend_text")


def test_renderer_backend_lookup_rejects_unknown_ids() -> None:
    with pytest.raises(KeyError):
        get_renderer_backend("unknown")


def test_textual_backend_imports_textual_only_when_selected() -> None:
    sys.modules.pop("textual.app", None)

    backend = select_renderer_backend("textual")

    assert backend.backend_id == "textual"
    assert "textual.app" not in sys.modules


def test_textual_backend_reports_unavailable_without_required_dependency() -> None:
    backend = TextualRendererBackend()
    availability = backend.is_available()

    if availability.available:
        assert hasattr(backend.create_renderer(), "aappend_text")
    else:
        assert availability.reason == "Textual is not installed"
        with pytest.raises(RendererBackendUnavailableError):
            backend.create_renderer()


def test_textual_replay_renderer_keeps_streaming_and_structured_state_separate() -> None:
    renderer = TextualReplayRenderer()
    store = TranscriptStore()
    store.append(MessageItem(role="user", text="hello", run_id=None, timestamp_ms=1))
    projection = project_viewport(
        store.snapshot(),
        ViewportRequest(scroll_offset=0, viewport_height=5),
    )
    snapshot = RouterHudSnapshot(
        tier="t2",
        tier_index=2,
        model="anthropic/claude-sonnet-4.6",
        baseline_model="anthropic/claude-opus-4.7",
        source="router",
        confidence=0.71,
        savings_pct=64.0,
        fallback=False,
        thinking_mode="balanced",
        prompt_policy="default",
        routing_applied=True,
        rollout_phase="full",
        label="route t2 -> claude-sonnet-4.6 71% save 64%",
        style="normal",
    )

    asyncio.run(renderer.aappend_text("hello"))
    layout = renderer.render_structured_layout(
        plugin_snapshots={"router_hud": snapshot},
        transcript_projection=projection,
    )

    assert renderer.buffer == "hello"
    assert renderer.flush_count == 1
    assert layout.plugin_slots == ("router_hud",)
    assert layout.visible_items == 1
    assert layout.total_items == 1
