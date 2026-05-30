"""Python side helpers for the OpenTUI footer host."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import shutil
from typing import Any

from opensquilla.cli.tui.backend.transcript import ViewportProjection
from opensquilla.cli.tui.renderers.selection import (
    RendererBackendAvailability,
    RendererBackendUnavailableError,
)

DEFAULT_HOST_PACKAGE_DIR = Path(__file__).resolve().parent / "package"


@dataclass(frozen=True)
class OpenTuiHostPaths:
    package_dir: Path = DEFAULT_HOST_PACKAGE_DIR
    main_script: Path = DEFAULT_HOST_PACKAGE_DIR / "src" / "main.mjs"

    @property
    def opentui_core_dir(self) -> Path:
        return self.package_dir / "node_modules" / "@opentui" / "core"


def check_opentui_host_available(
    *,
    package_dir: Path = DEFAULT_HOST_PACKAGE_DIR,
    runtime_bin: str | None = None,
    node_bin: str | None = None,
) -> RendererBackendAvailability:
    """Check whether the local Node/OpenTUI host can be launched."""

    resolved_runtime = runtime_bin or node_bin or shutil.which("bun")
    if not resolved_runtime:
        return RendererBackendAvailability(
            available=False,
            reason="Bun is not installed or is not on PATH",
        )

    paths = OpenTuiHostPaths(package_dir=package_dir)
    if not paths.opentui_core_dir.exists():
        return RendererBackendAvailability(
            available=False,
            reason=(
                "OpenTUI host dependency @opentui/core is not installed. "
                f"Run: npm install --prefix {package_dir}"
            ),
        )
    if not paths.main_script.exists():
        return RendererBackendAvailability(
            available=False,
            reason=f"OpenTUI host entrypoint is missing: {paths.main_script}",
        )
    return RendererBackendAvailability(available=True)


@dataclass
class OpenTuiReplayRenderer:
    """Headless renderer facade used for backend contract tests and evaluation."""

    buffer: str = ""
    flush_count: int = 0
    statuses: list[tuple[str, str]] = field(default_factory=list)
    tool_events: list[tuple[str, str | None]] = field(default_factory=list)

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
        result: object | None = None,
    ) -> None:
        del elapsed, error, result
        self.tool_events.append(("done" if success else "error", tool_use_id))

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
    ) -> dict[str, int | tuple[str, ...]]:
        return {
            "plugin_slots": tuple(sorted(plugin_snapshots)),
            "visible_items": len(transcript_projection.items),
            "total_items": transcript_projection.total_items,
            "total_rows": transcript_projection.total_rows,
        }


@dataclass(frozen=True)
class OpenTuiRendererBackend:
    backend_id: str = "opentui"
    supports_structured_ui: bool = True
    supports_streaming_fast_path: bool = True

    def is_available(self) -> RendererBackendAvailability:
        return check_opentui_host_available()

    def create_renderer(self, **kwargs: Any) -> OpenTuiReplayRenderer:
        del kwargs
        availability = self.is_available()
        if not availability.available:
            raise RendererBackendUnavailableError(
                availability.reason or "OpenTUI host unavailable"
            )
        return OpenTuiReplayRenderer()
