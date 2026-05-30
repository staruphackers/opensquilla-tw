from __future__ import annotations

import json
from pathlib import Path

import pytest

from tui_real_terminal.scenarios import scenario_by_id

pytestmark = pytest.mark.tui_real_terminal

ARCHITECTURE_PROMPT = "帮我分析这个代码长的架构 /Users/cwan0785/opensquilla"
ARCHITECTURE_REPLAY_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "fixtures"
    / "tui"
    / "architecture_prompt_replay.json"
)


def test_architecture_prompt_replay_fixture_is_saved_for_render_only_runs() -> None:
    fixture = json.loads(ARCHITECTURE_REPLAY_FIXTURE.read_text(encoding="utf-8"))
    events = fixture["events"]
    kinds = [event["kind"] for event in events]

    assert fixture["source_prompt"] == ARCHITECTURE_PROMPT
    assert "toolbar" in kinds
    assert "tool_start" in kinds
    assert "tool_finished" in kinds
    assert "tool_output" in kinds
    assert "text_delta" in kinds
    assert events[-1]["kind"] == "done"
    tool_outputs = [event["payload"] for event in events if event["kind"] == "tool_output"]
    assert tool_outputs
    assert all("stdout" in payload for payload in tool_outputs)
    assert any(payload.get("truncated") for payload in tool_outputs)
    assert any(
        "architecture-analysis-complete" in event["payload"].get("text", "")
        for event in events
        if event["kind"] == "text_delta"
    )


def test_architecture_prompt_renders_tools_and_chinese_output(
    run_real_terminal_scenario,
) -> None:
    result = run_real_terminal_scenario(scenario_by_id("architecture_prompt"))

    assert result.status == "pass"
    transcript = (result.run_dir / "transcript.txt").read_text(encoding="utf-8")
    scrollback = (result.run_dir / "scrollback.txt").read_text(encoding="utf-8")
    rendered_output = f"{transcript}\n{scrollback}"
    app_log_name = (
        "textual-app.log"
        if result.backend_id == "textual"
        else "opentui-app.log"
        if result.backend_id == "opentui"
        else "app.log"
    )
    app_events = [
        json.loads(line)
        for line in (result.run_dir / app_log_name).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    submitted = [
        event["payload"].get("input", "")
        for event in app_events
        if event["event"] == "dispatch"
    ]

    assert any(ARCHITECTURE_PROMPT in item for item in submitted)
    assert ARCHITECTURE_PROMPT in rendered_output or result.backend_id == "textual"
    assert "read_file" in rendered_output
    assert "tool_output" in rendered_output
    assert "stdout:" in rendered_output
    assert "truncated" in rendered_output
    assert "router.reason" in rendered_output
    assert "架构" in rendered_output
    assert "architecture-analysis-complete" in rendered_output
    assert "Traceback" not in rendered_output
    assert "\x1b[" not in rendered_output
