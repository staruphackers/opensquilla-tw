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


def test_textual_target_builds_fake_live_app_command(tmp_path: Path) -> None:
    context = TargetContext(
        project_root=Path.cwd(),
        artifact_dir=tmp_path,
        scenario_id="launch_input_loop",
        size=TerminalSize(cols=100, rows=30),
    )

    target = build_tui_target("textual", context)

    assert target.backend_id == "textual"
    assert target.available is True
    assert target.skip_reason is None
    assert target.command[:2] == [sys.executable, "-u"]
    assert target.command[2].endswith("fake_textual_app.py")
    assert target.env["OPENSQUILLA_TUI_FAKE_SCENARIO"] == "launch_input_loop"
    assert target.env["OPENSQUILLA_TUI_READY_MARKER"] == "OPEN_SQUILLA_TUI_READY"
    assert target.env["OPENSQUILLA_TUI_BACKEND"] == "textual"
    assert target.readiness_markers == ("OPEN_SQUILLA_TUI_READY",)
    assert target.log_paths == (tmp_path / "textual-app.log",)
    assert "live-textual-app" in target.capability_requirements
    assert "missing-live-app" not in target.capability_requirements


def test_live_textual_target_builds_real_cli_command(tmp_path: Path) -> None:
    context = TargetContext(
        project_root=Path.cwd(),
        artifact_dir=tmp_path,
        scenario_id="live_architecture_prompt",
        size=TerminalSize(cols=112, rows=34),
    )

    target = build_tui_target("live-textual", context)

    assert target.backend_id == "live-textual"
    assert target.command[:3] == [sys.executable, "-u", "-m"]
    assert target.command[3:6] == ["opensquilla.cli.main", "chat", "--standalone"]
    assert "--workspace" in target.command
    assert str(Path.cwd()) in target.command
    assert "--workspace-strict" in target.command
    assert target.env["OPENSQUILLA_TUI_BACKEND"] == "textual"
    assert target.env["OPENSQUILLA_TUI_READY_MARKER"] == "OPEN_SQUILLA_TUI_READY"
    assert "real-cli" in target.capability_requirements
    assert "tmux" in target.capability_requirements
    assert "fake-provider" not in target.capability_requirements
