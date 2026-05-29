from __future__ import annotations

import pytest

from tui_real_terminal.scenarios import scenario_by_id

pytestmark = pytest.mark.tui_real_terminal


def test_complex_ui_state(run_real_terminal_scenario) -> None:
    result = run_real_terminal_scenario(scenario_by_id("complex_ui_state"))

    assert result.status == "pass"
    assert (result.run_dir / "frames").is_dir()
    assert (result.run_dir / "transcript.txt").exists()
    last_frame = sorted((result.run_dir / "frames").glob("*.txt"))[-1].read_text(
        encoding="utf-8"
    )
    if result.backend_id == "textual":
        router_lines = [line for line in last_frame.splitlines() if "Router:" in line]
        assert "Router:" in last_frame
        assert "fake-terminal" in last_frame
        assert "save 42%" in last_frame
        assert any("fake-terminal" in line and "save 42%" in line for line in router_lines)
