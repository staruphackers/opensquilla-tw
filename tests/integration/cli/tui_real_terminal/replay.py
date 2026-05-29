from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from opensquilla.cli.chat.turn import UsageSummary  # type: ignore[import-untyped]

ARCHITECTURE_PROMPT_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "fixtures"
    / "tui"
    / "architecture_prompt_replay.json"
)


async def replay_architecture_prompt(renderer: Any, output: Any) -> UsageSummary:
    fixture = json.loads(ARCHITECTURE_PROMPT_FIXTURE.read_text(encoding="utf-8"))
    usage = UsageSummary(model="fake-terminal", input_tokens=1, output_tokens=2)

    for event in fixture["events"]:
        kind = event["kind"]
        payload = event.get("payload", {})
        if kind == "toolbar":
            _set_toolbar(output, "router_hud", payload.get("router_hud"))
            _set_toolbar(output, "router_hud_style", payload.get("router_hud_style"))
            _invalidate(output)
        elif kind == "status":
            await renderer.astatus(str(payload.get("message", "")))
            for detail in _details_from_payload(payload):
                await renderer.astatus(detail)
        elif kind == "tool_start":
            args = payload.get("args")
            await renderer.atool_start(
                str(payload.get("name", "tool")),
                args if isinstance(args, dict) else None,
                str(payload.get("tool_use_id", "")),
            )
        elif kind == "tool_finished":
            elapsed = payload.get("elapsed")
            await renderer.atool_finished(
                str(payload.get("tool_use_id", "")),
                success=bool(payload.get("success", True)),
                elapsed=elapsed if isinstance(elapsed, float | int) else None,
                error=str(payload["error"]) if "error" in payload else None,
            )
        elif kind == "tool_output":
            await renderer.astatus(_tool_output_summary(payload))
            for detail in _tool_output_details(payload):
                await renderer.astatus(detail)
        elif kind == "text_delta":
            await renderer.aappend_text(str(payload.get("text", "")))
        elif kind == "done":
            usage_payload = payload.get("usage", {})
            if isinstance(usage_payload, dict):
                usage = UsageSummary(
                    model=str(usage_payload.get("model", "fake-terminal")),
                    input_tokens=int(usage_payload.get("input_tokens", 0)),
                    output_tokens=int(usage_payload.get("output_tokens", 0)),
                )
    return usage


def _details_from_payload(payload: dict[str, Any]) -> list[str]:
    details = payload.get("detail", [])
    if isinstance(details, list):
        return [str(detail) for detail in details]
    return []


def _tool_output_summary(payload: dict[str, Any]) -> str:
    name = str(payload.get("name", "tool"))
    line_count = int(payload.get("line_count", 0))
    summary = str(payload.get("summary", "")).strip()
    suffix = f" — {summary}" if summary else ""
    truncated = " truncated" if payload.get("truncated") else ""
    return f"tool_output {name} {line_count} lines{truncated}{suffix}"


def _tool_output_details(payload: dict[str, Any]) -> list[str]:
    details: list[str] = []
    stdout = payload.get("stdout", [])
    stderr = payload.get("stderr", [])
    if isinstance(stdout, list) and stdout:
        details.append("│ stdout:")
        details.extend(f"│   {line}" for line in stdout[:8])
    if isinstance(stderr, list) and stderr:
        details.append("│ stderr:")
        details.extend(f"│   {line}" for line in stderr[:8])
    if payload.get("truncated"):
        details.append(f"│ omitted: {payload.get('line_count', 0)} total lines in fixture")
    return details


def _set_toolbar(output: Any, key: str, value: object | None) -> None:
    setter = getattr(output, "set_toolbar", None)
    if callable(setter):
        setter(key, value)


def _invalidate(output: Any) -> None:
    invalidate = getattr(output, "invalidate", None)
    if callable(invalidate):
        invalidate()
