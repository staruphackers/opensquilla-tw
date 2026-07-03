"""Regression tests for CLI profile resolution before home .env loading."""

from __future__ import annotations

import os
from pathlib import Path

from typer.testing import CliRunner

from opensquilla.cli.main import app
from opensquilla.paths import default_opensquilla_home

runner = CliRunner()


def _write_profile(home: Path, name: str, env_lines: list[str]) -> Path:
    profile_dir = home / name
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / ".env").write_text("\n".join(env_lines) + "\n", encoding="utf-8")
    return profile_dir


def test_cli_profile_loads_selected_profile_env(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / "profiles"
    _write_profile(home, "default", ["PROFILE_MARK=loaded-default"])
    _write_profile(home, "coder", ["CODER_MARK=loaded-coder"])

    for key in (
        "OPENSQUILLA_HOME",
        "OPENSQUILLA_PROFILE",
        "OPENSQUILLA_STATE_DIR",
        "PROFILE_MARK",
        "CODER_MARK",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OPENSQUILLA_HOME", str(home))

    result = runner.invoke(app, ["--profile", "coder", "providers", "list", "--json"])

    assert result.exit_code == 0, result.output
    assert os.environ["OPENSQUILLA_PROFILE"] == "coder"
    assert os.environ["CODER_MARK"] == "loaded-coder"
    assert "PROFILE_MARK" not in os.environ
    assert default_opensquilla_home() == home / "coder"


def test_cli_without_profile_keeps_legacy_home(monkeypatch, tmp_path: Path) -> None:
    legacy_home = tmp_path / ".opensquilla"
    legacy_home.mkdir()
    (legacy_home / ".env").write_text("LEGACY_MARK=loaded\n", encoding="utf-8")

    for key in (
        "OPENSQUILLA_HOME",
        "OPENSQUILLA_PROFILE",
        "OPENSQUILLA_STATE_DIR",
        "LEGACY_MARK",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    result = runner.invoke(app, ["providers", "list", "--json"])

    assert result.exit_code == 0, result.output
    assert os.environ["LEGACY_MARK"] == "loaded"
    assert default_opensquilla_home() == legacy_home


def test_cli_rejects_invalid_profile(monkeypatch) -> None:
    monkeypatch.delenv("OPENSQUILLA_STATE_DIR", raising=False)

    result = runner.invoke(app, ["--profile", "../escape", "providers", "list"])

    assert result.exit_code != 0
    assert "lowercase letters" in result.output


def test_env_load_uses_provided_home(monkeypatch, tmp_path: Path) -> None:
    from opensquilla.env import load_env

    home = tmp_path / "custom"
    home.mkdir(parents=True)
    (home / ".env").write_text("CUSTOM_MARK=ok\n", encoding="utf-8")

    for key in (
        "OPENSQUILLA_HOME",
        "OPENSQUILLA_PROFILE",
        "OPENSQUILLA_STATE_DIR",
        "CUSTOM_MARK",
    ):
        monkeypatch.delenv(key, raising=False)

    assert load_env(home=home) >= 1
    assert os.environ["CUSTOM_MARK"] == "ok"
