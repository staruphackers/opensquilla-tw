from __future__ import annotations

from pathlib import Path

HOST_SOURCE = (
    Path(__file__).resolve().parents[4]
    / "src"
    / "opensquilla"
    / "cli"
    / "tui"
    / "opentui"
    / "package"
    / "src"
    / "main.mjs"
)


def test_opentui_footer_uses_reference_plugin_layout_contract() -> None:
    source = HOST_SOURCE.read_text(encoding="utf-8")

    assert 'shouldFill: false' in source
    assert 'id: "composer-box"' in source
    assert 'bottomTitle: `${statusIcon()} ${turnStatus.label}`' in source
    assert 'id: "router-plugin"' in source
    assert 'position: "absolute"' in source
    assert 'right: 1' in source
    assert 'bottom: 0' in source
    assert 'title: " router "' in source


def test_opentui_host_locks_recommended_daily_visual_preset() -> None:
    source = HOST_SOURCE.read_text(encoding="utf-8")

    assert "OPENTUI_DAILY_THEME" in source
    assert 'preset: "daily"' in source
    assert 'frame: "card"' in source
    assert 'detailMode: "inline"' in source
    assert 'answerMode: "panel"' in source
    assert "#77B7FF" in source
    assert "decorateDailyTimelineScrollback" in source
    assert "classifyDailyTimelineLine" in source


def test_opentui_host_uses_lines_not_backgrounds_for_visual_separation() -> None:
    source = HOST_SOURCE.read_text(encoding="utf-8")

    assert "backgroundColor" not in source
    assert "routerBackground" not in source
