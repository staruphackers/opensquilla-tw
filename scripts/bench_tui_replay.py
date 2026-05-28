from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from opensquilla.cli.tui.backend.streaming import StreamingPlane
from opensquilla.cli.tui.terminal.renderer import TerminalRenderer

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = PROJECT_ROOT / "tests" / "unit" / "cli" / "tui" / "replay_fixtures.py"


@dataclass(frozen=True)
class ReplaySummary:
    renderer: str
    fixture: str
    event_count: int
    text_chars: int
    tool_count: int
    router_decision_count: int
    wall_ms: float
    flush_count: int
    max_buffer_chars: int
    coalescing_ratio: float
    errors: list[str]


class _ReplayStreamOutput:
    def __init__(self, output_handle: _ReplayOutputHandle) -> None:
        self._output_handle = output_handle

    async def __aenter__(self):
        return self._output_handle.write

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _ReplayOutputHandle:
    def __init__(self) -> None:
        self.flush_count = 0
        self.max_payload_chars = 0

    def write(self, payload: str) -> None:
        self.flush_count += 1
        self.max_payload_chars = max(self.max_payload_chars, len(payload))

    async def write_through(self, payload: str) -> None:
        self.write(payload)

    def stream_output(self) -> _ReplayStreamOutput:
        return _ReplayStreamOutput(self)


def _load_fixture_module() -> Any:
    spec = importlib.util.spec_from_file_location("tui_replay_fixtures", FIXTURE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load replay fixtures from {FIXTURE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _build_events(fixture: str) -> list[Any]:
    fixtures = _load_fixture_module()
    if fixture == "long-stream":
        return list(fixtures.build_long_stream_events())
    if fixture == "dense-history":
        return list(fixtures.build_dense_history_events())
    raise ValueError(f"Unsupported fixture: {fixture}")


def _text_chars_for(event: Any) -> int:
    payload = event.payload
    if event.kind == "text_delta":
        return len(str(payload.get("text", "")))
    if event.kind == "history_message":
        return len(str(payload.get("content", "")))
    if event.kind == "tool_card":
        return len(str(payload.get("summary", "")))
    return 0


async def _flush_streaming_plane(
    renderer: TerminalRenderer,
    streaming_plane: StreamingPlane,
) -> None:
    flush = streaming_plane.finish()
    if flush is not None:
        await renderer.aappend_text(flush.text)


async def _render_event(
    renderer: TerminalRenderer,
    streaming_plane: StreamingPlane,
    event: Any,
) -> None:
    payload = event.payload
    if event.kind == "text_delta":
        flush = streaming_plane.append(str(payload.get("text", "")))
        if flush is not None:
            await renderer.aappend_text(flush.text)
    elif event.kind == "tool_start":
        await _flush_streaming_plane(renderer, streaming_plane)
        args = payload.get("args")
        await renderer.atool_start(
            str(payload.get("name", "tool")),
            args if isinstance(args, dict) else None,
            str(payload.get("tool_use_id", "")),
        )
    elif event.kind == "tool_finished":
        await _flush_streaming_plane(renderer, streaming_plane)
        elapsed = payload.get("elapsed")
        await renderer.atool_finished(
            str(payload.get("tool_use_id", "")),
            success=bool(payload.get("success", True)),
            elapsed=elapsed if isinstance(elapsed, float) else None,
            error=str(payload["error"]) if "error" in payload else None,
        )
    elif event.kind == "router_decision":
        await _flush_streaming_plane(renderer, streaming_plane)
        await renderer.astatus(
            "route: "
            f"{payload.get('tier')} -> {payload.get('model')} "
            f"(baseline {payload.get('baseline_model')})",
            style="cyan",
        )
    elif event.kind == "history_message":
        await _flush_streaming_plane(renderer, streaming_plane)
        await renderer.astatus(
            f"{payload.get('role')}: {str(payload.get('content', ''))[:120]}",
            style="dim",
        )
    elif event.kind == "tool_card":
        await _flush_streaming_plane(renderer, streaming_plane)
        await renderer.astatus(
            f"tool: {payload.get('name')} {payload.get('summary')}",
            style="magenta",
        )
    elif event.kind == "done":
        await _flush_streaming_plane(renderer, streaming_plane)
        await renderer.afinalize()


async def run_replay(renderer: str, fixture: str, *, repeat: int = 1) -> ReplaySummary:
    if repeat < 1:
        raise ValueError("--repeat must be >= 1")
    if renderer != "terminal":
        raise ValueError(f"Unsupported renderer: {renderer}")

    errors: list[str] = []
    event_count = 0
    text_chars = 0
    tool_count = 0
    router_decision_count = 0
    text_delta_count = 0
    streaming_flush_count = 0
    flush_count = 0
    max_buffer_chars = 0
    started_at = time.perf_counter()

    for _ in range(repeat):
        events = _build_events(fixture)
        output_handle = _ReplayOutputHandle()
        terminal_renderer = TerminalRenderer(title="tui-replay", output_handle=output_handle)
        streaming_plane = StreamingPlane()
        for event in events:
            event_count += 1
            text_chars += _text_chars_for(event)
            if event.kind == "text_delta":
                text_delta_count += 1
            if event.kind in {"tool_start", "tool_card"}:
                tool_count += 1
            if event.kind == "router_decision":
                router_decision_count += 1
            try:
                await _render_event(terminal_renderer, streaming_plane, event)
            except Exception as exc:  # pragma: no cover - summarized for CLI evidence.
                errors.append(f"{event.kind}: {exc}")
            max_buffer_chars = max(
                max_buffer_chars,
                streaming_plane.max_buffer_chars,
            )
        await terminal_renderer.aclose()
        streaming_flush_count += streaming_plane.flush_count
        flush_count += output_handle.flush_count

    wall_ms = (time.perf_counter() - started_at) * 1_000
    coalescing_ratio = (
        round(streaming_flush_count / text_delta_count, 6)
        if text_delta_count > 0
        else 0.0
    )
    return ReplaySummary(
        renderer=renderer,
        fixture=fixture,
        event_count=event_count,
        text_chars=text_chars,
        tool_count=tool_count,
        router_decision_count=router_decision_count,
        wall_ms=round(wall_ms, 3),
        flush_count=flush_count,
        max_buffer_chars=max_buffer_chars,
        coalescing_ratio=coalescing_ratio,
        errors=errors,
    )


def write_summary(summary: ReplaySummary, summary_json: Path) -> None:
    summary_json.parent.mkdir(parents=True, exist_ok=True)
    summary_json.write_text(json.dumps(asdict(summary), indent=2, sort_keys=True) + "\n")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Replay synthetic TUI events.")
    parser.add_argument("--renderer", choices=("terminal",), required=True)
    parser.add_argument("--fixture", choices=("long-stream", "dense-history"), required=True)
    parser.add_argument("--summary-json", type=Path, required=True)
    parser.add_argument("--repeat", type=int, default=1)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    summary = asyncio.run(
        run_replay(args.renderer, args.fixture, repeat=args.repeat),
    )
    write_summary(summary, args.summary_json)
    return 1 if summary.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
