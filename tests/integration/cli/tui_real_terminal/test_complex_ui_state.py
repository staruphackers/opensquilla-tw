from __future__ import annotations

import pytest

from tui_real_terminal.scenarios import scenario_by_id

pytestmark = pytest.mark.tui_real_terminal


def test_complex_ui_state(run_real_terminal_scenario) -> None:
    result = run_real_terminal_scenario(scenario_by_id("complex_ui_state"))

    assert result.status == "pass"
    assert (result.run_dir / "frames").is_dir()
    assert (result.run_dir / "transcript.txt").exists()
