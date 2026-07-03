from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR = ROOT / "scripts" / "supervisor"


def test_supervisor_scripts_are_windows_profile_scoped() -> None:
    scripts = {
        "lib.ps1",
        "start-all.ps1",
        "stop-all.ps1",
        "status.ps1",
        "install-autostart.ps1",
        "uninstall-autostart.ps1",
    }
    for name in scripts:
        assert (SUPERVISOR / name).is_file()

    combined = "\n".join((SUPERVISOR / name).read_text(encoding="utf-8") for name in scripts)
    assert r"D:\ai\opensquilla" not in combined
    assert "OPENSQUILLA_HOME" in combined
    assert "--profile" in combined
    assert "^[a-z0-9][a-z0-9_-]{0,63}$" in combined


def test_task_scheduler_registration_uses_encoded_command() -> None:
    text = (SUPERVISOR / "install-autostart.ps1").read_text(encoding="utf-8")

    assert "-EncodedCommand" in text
    assert "ConvertTo-PowerShellSingleQuotedLiteral" in text
    assert "ConvertTo-XmlEscapedText" in text
