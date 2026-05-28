from __future__ import annotations

import sys
from pathlib import Path

from tui_real_terminal.driver import TerminalSize
from tui_real_terminal.targets import TargetContext, build_tui_target


def test_terminal_target_builds_fake_app_command(tmp_path: Path) -> None:
    context = TargetContext(
        project_root=Path.cwd(),
        artifact_dir=tmp_path,
        scenario_id="launch_input_loop",
        size=TerminalSize(cols=100, rows=30),
    )

    target = build_tui_target("terminal", context)

    assert target.backend_id == "terminal"
    assert target.available is True
    assert target.command[:2] == [sys.executable, "-u"]
    assert target.command[2].endswith("fake_terminal_app.py")
    assert target.env["OPENSQUILLA_TUI_FAKE_SCENARIO"] == "launch_input_loop"
    assert target.env["OPENSQUILLA_TUI_READY_MARKER"] == "OPEN_SQUILLA_TUI_READY"
    assert target.readiness_markers == ("OPEN_SQUILLA_TUI_READY",)
    assert target.log_paths == (tmp_path / "app.log",)


def test_textual_target_is_explicitly_unavailable(tmp_path: Path) -> None:
    context = TargetContext(
        project_root=Path.cwd(),
        artifact_dir=tmp_path,
        scenario_id="launch_input_loop",
        size=TerminalSize(cols=100, rows=30),
    )

    target = build_tui_target("textual", context)

    assert target.backend_id == "textual"
    assert target.available is False
    assert target.skip_reason == "live Textual TUI target is not implemented"
