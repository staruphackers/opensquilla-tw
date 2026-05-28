from __future__ import annotations

import pytest

from tui_real_terminal.scenarios import scenario_by_id

pytestmark = pytest.mark.tui_real_terminal


def test_long_streaming_output(run_real_terminal_scenario) -> None:
    result = run_real_terminal_scenario(scenario_by_id("long_streaming"))

    assert result.status == "pass"
    assert (result.run_dir / "frames").is_dir()
    assert (result.run_dir / "transcript.txt").exists()
