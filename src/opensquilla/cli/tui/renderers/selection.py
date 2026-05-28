"""Renderer backend registry for TUI evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from opensquilla.cli.tui.terminal.renderer import TerminalRenderer


@dataclass(frozen=True)
class RendererBackendAvailability:
    available: bool
    reason: str | None = None


class RendererBackendUnavailableError(RuntimeError):
    """Raised when a selected renderer backend cannot be constructed."""


class TuiRendererBackend(Protocol):
    @property
    def backend_id(self) -> str: ...

    @property
    def supports_structured_ui(self) -> bool: ...

    @property
    def supports_streaming_fast_path(self) -> bool: ...

    def is_available(self) -> RendererBackendAvailability: ...

    def create_renderer(self, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class TerminalRendererBackend:
    backend_id: str = "terminal"
    supports_structured_ui: bool = False
    supports_streaming_fast_path: bool = True

    def is_available(self) -> RendererBackendAvailability:
        return RendererBackendAvailability(available=True)

    def create_renderer(self, **kwargs: Any) -> TerminalRenderer:
        return TerminalRenderer(**kwargs)


def renderer_backends() -> dict[str, TuiRendererBackend]:
    from opensquilla.cli.tui.renderers.textual_backend import TextualRendererBackend

    backends: list[TuiRendererBackend] = [
        TerminalRendererBackend(),
        TextualRendererBackend(),
    ]
    return {backend.backend_id: backend for backend in backends}


def get_renderer_backend(backend_id: str) -> TuiRendererBackend:
    return renderer_backends()[backend_id]


def select_renderer_backend(backend_id: str | None = None) -> TuiRendererBackend:
    return get_renderer_backend("terminal" if backend_id is None else backend_id)
