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
