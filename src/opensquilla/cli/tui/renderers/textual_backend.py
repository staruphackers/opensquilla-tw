"""Experimental Textual renderer backend.

The module is intentionally importable without Textual installed. Runtime
construction checks the optional dependency only when this backend is selected.
"""

from __future__ import annotations

import importlib
import importlib.util
from dataclasses import dataclass, field
from typing import Any

from opensquilla.cli.tui.backend.transcript import ViewportProjection
from opensquilla.cli.tui.renderers.selection import (
    RendererBackendAvailability,
    RendererBackendUnavailableError,
)


@dataclass(frozen=True)
class TextualStructuredLayout:
    plugin_slots: tuple[str, ...]
    visible_items: int
    total_items: int
    total_rows: int


@dataclass
class TextualReplayRenderer:
    """Replay-friendly renderer facade used by benchmark evaluation.

    It keeps token streaming as append-only text while structured UI state is
    captured separately as layout summaries. A future live Textual app can
    consume the same data without turning every text delta into a full refresh.
    """

    buffer: str = ""
    flush_count: int = 0
    statuses: list[tuple[str, str]] = field(default_factory=list)
    tool_events: list[tuple[str, str | None]] = field(default_factory=list)
    layouts: list[TextualStructuredLayout] = field(default_factory=list)

    async def aappend_text(self, delta: str) -> None:
        self.buffer += delta
        self.flush_count += 1

    async def atool_start(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        tool_use_id: str | None = None,
    ) -> None:
        del args
        self.tool_events.append((f"start:{name}", tool_use_id))

    async def atool_finished(
        self,
        tool_use_id: str | None,
        *,
        success: bool,
        elapsed: float | None = None,
        error: str | None = None,
    ) -> None:
        del elapsed, error
        status = "done" if success else "error"
        self.tool_events.append((status, tool_use_id))

    async def astatus(self, message: str, *, style: str = "dim") -> None:
        self.statuses.append((message, style))

    async def aerror(self, message: str) -> None:
        self.statuses.append((message, "error"))

    async def afinalize(self, usage: Any | None = None, *, cancelled: bool = False) -> None:
        del usage
        if cancelled:
            self.statuses.append(("cancelled", "dim"))

    async def aclose(self) -> None:
        return None

    def render_structured_layout(
        self,
        *,
        plugin_snapshots: dict[str, object],
        transcript_projection: ViewportProjection,
    ) -> TextualStructuredLayout:
        layout = TextualStructuredLayout(
            plugin_slots=tuple(sorted(plugin_snapshots)),
            visible_items=len(transcript_projection.items),
            total_items=transcript_projection.total_items,
            total_rows=transcript_projection.total_rows,
        )
        self.layouts.append(layout)
        return layout


@dataclass(frozen=True)
class TextualRendererBackend:
    backend_id: str = "textual"
    supports_structured_ui: bool = True
    supports_streaming_fast_path: bool = True

    def is_available(self) -> RendererBackendAvailability:
        if importlib.util.find_spec("textual") is None:
            return RendererBackendAvailability(
                available=False,
                reason="Textual is not installed",
            )
        return RendererBackendAvailability(available=True)

    def create_renderer(self, **kwargs: Any) -> TextualReplayRenderer:
        del kwargs
        availability = self.is_available()
        if not availability.available:
            raise RendererBackendUnavailableError(
                availability.reason or "Textual unavailable"
            )
        # Verify the public Textual runtime modules lazily when the backend is
        # selected. The replay renderer itself remains lightweight and headless.
        importlib.import_module("textual.app")
        importlib.import_module("textual.widgets")
        return TextualReplayRenderer()
