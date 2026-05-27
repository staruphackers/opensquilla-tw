"""Typed launch contracts shared by chat entrypoints and frontends."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

type ChatCommandRunner = Callable[..., Coroutine[Any, Any, None]]
type ChatCommandLauncher = Callable[..., None]


@dataclass(frozen=True)
class ChatCommandRequest:
    model: str
    session_id: str
    standalone: bool
    workspace: str
    workspace_strict: bool | None
    timeout: float | None


@dataclass(frozen=True)
class ChatCommandLaunchOverrides:
    launch_chat: ChatCommandLauncher | None = None
    standalone_runner: ChatCommandRunner | None = None
    gateway_runner: ChatCommandRunner | None = None
