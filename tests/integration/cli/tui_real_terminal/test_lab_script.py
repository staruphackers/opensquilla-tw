from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def _load_lab_script() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[4] / "scripts" / "tui_real_terminal_lab.py"
    )
    spec = importlib.util.spec_from_file_location("tui_real_terminal_lab", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_textual_lab_requires_explicit_live_env(monkeypatch: pytest.MonkeyPatch) -> None:
    lab = _load_lab_script()
    monkeypatch.delenv("OPENSQUILLA_TUI_LIVE_REAL", raising=False)

    with pytest.raises(SystemExit, match="OPENSQUILLA_TUI_LIVE_REAL=1"):
        lab._assert_live_backend_enabled("live-textual")

    monkeypatch.setenv("OPENSQUILLA_TUI_LIVE_REAL", "1")
    lab._assert_live_backend_enabled("live-textual")
    lab._assert_live_backend_enabled("textual")
