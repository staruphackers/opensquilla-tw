"""Chat command — interactive chat mode with Rich output.

Two modes:
- Default (gateway): Connect to running gateway daemon via WebSocket. Full features.
- --standalone: TurnRunner-based direct mode, no gateway daemon needed.
"""

from __future__ import annotations

from typing import Any

import typer

from opensquilla.cli.chat.launch import (
    ChatCommandLaunchOverrides as _ChatCommandLaunchOverrides,
)
from opensquilla.cli.chat.launch import ChatCommandRequest as _ChatCommandRequest
from opensquilla.cli.tui.chat_cmd_exports import (
    LEGACY_CHAT_CMD_EXPORT_NAMES,
    resolve_legacy_chat_cmd_export,
    resolve_legacy_chat_cmd_launch_overrides,
)

__all__ = tuple(
    sorted(
        {
            "run_chat",
            *(name for name in LEGACY_CHAT_CMD_EXPORT_NAMES if not name.startswith("_")),
        }
    )
)


def __dir__() -> list[str]:
    return sorted({*globals(), *LEGACY_CHAT_CMD_EXPORT_NAMES})


def __getattr__(name: str) -> Any:
    return resolve_legacy_chat_cmd_export(name)


def run_chat(
    model: str = typer.Option("", "--model", "-m", help="Model override (provider/model)"),
    session_id: str = typer.Option("", "--session", "-s", help="Resume session ID"),
    standalone: bool = typer.Option(False, "--standalone", help="Direct Agent without gateway"),
    workspace: str = typer.Option("", "--workspace", help="Workspace root for standalone tools"),
    workspace_strict: bool | None = typer.Option(
        None,
        "--workspace-strict/--no-workspace-strict",
        help="Restrict read-side file tools to --workspace in standalone mode",
    ),
    timeout: float | None = None,
) -> None:
    """Start interactive chat with the agent.

    Default: connects to the running gateway daemon for full features
    (tools, skills, session persistence). Use --standalone for direct
    TurnRunner mode without a gateway daemon.
    """
    module_globals = globals()
    launch_chat_command = (
        module_globals["_launch_chat_command"]
        if "_launch_chat_command" in module_globals
        else resolve_legacy_chat_cmd_export("_launch_chat_command")
    )
    launch_overrides: _ChatCommandLaunchOverrides = (
        resolve_legacy_chat_cmd_launch_overrides(module_globals)
    )
    launch_chat_command(
        _ChatCommandRequest(
            model=model,
            session_id=session_id,
            standalone=standalone,
            workspace=workspace,
            workspace_strict=workspace_strict,
            timeout=timeout,
        ),
        overrides=launch_overrides,
    )
