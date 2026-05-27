"""TUI-owned default bridge for shared turn streaming.

This module binds the shared chat turn stream to terminal presentation defaults
such as renderers, approval handling, image input, and output panels.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import opensquilla.cli.tui.input_bridge as _input_bridge
import opensquilla.cli.tui.terminal_bridge as _terminal_bridge
from opensquilla.cli.chat import turn_stream as _turn_stream
from opensquilla.cli.chat.turn import TurnResult, UsageSummary
from opensquilla.cli.tui.approval_adapter import maybe_handle_approval
from opensquilla.cli.tui.contracts import TuiOutputHandle
from opensquilla.cli.tui.terminal_renderer import TerminalRenderer
from opensquilla.cli.ui import console, error_panel
from opensquilla.engine.commands import Surface

TurnStreamDependencies = _turn_stream.TurnStreamDependencies

ORIGINAL_TURN_STREAM_WRAP = _turn_stream.wrap_cli_turn_stream
DEFAULT_STREAM_HEARTBEAT_INTERVAL_SECONDS = (
    _turn_stream._DEFAULT_STREAM_HEARTBEAT_INTERVAL_SECONDS
)
DEFAULT_STREAM_IDLE_TIMEOUT_SECONDS = _turn_stream._DEFAULT_STREAM_IDLE_TIMEOUT_SECONDS


def tool_result_success_from_status(status: Any, *, legacy_is_error: bool) -> bool:
    return _turn_stream._tool_result_success_from_status(
        status,
        legacy_is_error=legacy_is_error,
    )


def turn_stream_error_message(event: Any) -> str:
    return _turn_stream.turn_stream_error_message(event)


def timeout_exception_message(exc: BaseException) -> str:
    return _turn_stream.timeout_exception_message(exc)


def optional_positive_config_float(config_source: Any, attr: str, default: float) -> float | None:
    return _turn_stream.optional_positive_config_float(config_source, attr, default)


def wrap_cli_turn_stream(stream: Any, config_source: Any) -> Any:
    return ORIGINAL_TURN_STREAM_WRAP(stream, config_source)


def is_approval_or_blocked_result(result: Any) -> bool:
    return _turn_stream.is_approval_or_blocked_result(result)


def approval_surface_for_tui_output(
    tui_output: TuiOutputHandle | None,
    default: Surface,
) -> Surface:
    resolved = _turn_stream.approval_surface_for_tui_output(tui_output, default)
    if isinstance(resolved, Surface):
        return resolved
    return default


def _approval_surface_for_terminal_output(
    tui_output: TuiOutputHandle | None,
    default: object | None,
) -> object | None:
    if not isinstance(default, Surface):
        return default
    return approval_surface_for_tui_output(tui_output, default)


def image_prompt_and_attachments(command: str) -> tuple[str, list[dict[str, str]]]:
    return _input_bridge.image_prompt_and_attachments(command)


def default_turn_stream_dependencies(
    *,
    renderer_factory: Callable[..., Any] | None = None,
    stream_wrapper: Callable[[Any, Any], Any] | None = None,
    approval_handler: Callable[..., Awaitable[None]] | None = None,
    cancel_clearer: Callable[[], None] | None = None,
    image_attachment_builder: Callable[[str], tuple[str, list[dict[str, str]]]]
    | None = None,
    output_console: Any | None = None,
    error_panel_factory: Callable[[str], Any] | None = None,
) -> TurnStreamDependencies:
    return _turn_stream.default_turn_stream_dependencies(
        renderer_factory=(
            TerminalRenderer if renderer_factory is None else renderer_factory
        ),
        stream_wrapper=stream_wrapper,
        approval_handler=(
            maybe_handle_approval if approval_handler is None else approval_handler
        ),
        cancel_clearer=(
            _terminal_bridge.clear_current_cancel
            if cancel_clearer is None
            else cancel_clearer
        ),
        image_attachment_builder=(
            image_prompt_and_attachments
            if image_attachment_builder is None
            else image_attachment_builder
        ),
        output_console=console if output_console is None else output_console,
        error_panel_factory=(
            error_panel if error_panel_factory is None else error_panel_factory
        ),
        gateway_approval_surface=Surface.CLI_GATEWAY,
        standalone_approval_surface=Surface.CLI_STANDALONE,
        approval_surface_resolver=_approval_surface_for_terminal_output,
    )


def render_gateway_task_group_status(
    event_name: str,
    event: dict[str, Any],
    renderer: Any,
    *,
    deps: TurnStreamDependencies | None = None,
) -> None:
    _turn_stream.render_gateway_task_group_status(
        event_name,
        event,
        renderer,
        deps=deps,
    )


def gateway_task_group_status(
    event_name: str,
    event: dict[str, Any],
) -> tuple[str, str] | None:
    return _turn_stream.gateway_task_group_status(event_name, event)


async def arender_gateway_task_group_status(
    event_name: str,
    event: dict[str, Any],
    renderer: Any,
    *,
    deps: TurnStreamDependencies | None = None,
) -> None:
    await _turn_stream.arender_gateway_task_group_status(
        event_name,
        event,
        renderer,
        deps=deps,
    )


async def renderer_status(
    renderer: Any,
    message: str,
    *,
    style: str = "dim",
    deps: TurnStreamDependencies | None = None,
) -> None:
    await _turn_stream.renderer_status(
        renderer,
        message,
        style=style,
        deps=deps,
    )


async def renderer_tool_start(
    renderer: Any,
    name: str,
    args: dict | None,
    tool_use_id: str | None,
) -> None:
    await _turn_stream.renderer_tool_start(renderer, name, args, tool_use_id)


async def renderer_tool_finished(
    renderer: Any,
    tool_use_id: str | None,
    *,
    success: bool,
) -> None:
    await _turn_stream.renderer_tool_finished(
        renderer,
        tool_use_id,
        success=success,
    )


async def renderer_error(renderer: Any, message: str) -> None:
    await _turn_stream.renderer_error(renderer, message)


async def renderer_finalize(
    renderer: Any,
    usage: UsageSummary | None = None,
    *,
    cancelled: bool = False,
) -> None:
    await _turn_stream.renderer_finalize(renderer, usage, cancelled=cancelled)


async def renderer_close(renderer: Any) -> None:
    await _turn_stream.renderer_close(renderer)


def artifact_event_payload(event: Any) -> dict[str, Any]:
    return _turn_stream.artifact_event_payload(event)


def artifact_status_line(artifact: dict[str, Any]) -> str:
    return _turn_stream.artifact_status_line(artifact)


async def stream_response_gateway(
    client: Any,
    session_key: str,
    message: str,
    elevated_state: dict[str, str | None] | None = None,
    attachments: list[dict] | None = None,
    *,
    tui_output: TuiOutputHandle | None = None,
    deps: TurnStreamDependencies | None = None,
) -> TurnResult:
    return await _turn_stream.stream_response_gateway(
        client,
        session_key,
        message,
        elevated_state,
        attachments=attachments,
        tui_output=tui_output,
        deps=deps,
    )


def local_approval_resolver() -> Callable[..., Awaitable[None]]:
    return _turn_stream.local_approval_resolver()


async def stream_response_turnrunner(
    turn_runner: object,
    session_key: str,
    tool_ctx: object,
    message: str,
    model: str | None = None,
    svc: object = None,
    timeout: float | None = None,
    *,
    tui_output: TuiOutputHandle | None = None,
    deps: TurnStreamDependencies | None = None,
) -> TurnResult:
    return await _turn_stream.stream_response_turnrunner(
        turn_runner,
        session_key,
        tool_ctx,
        message,
        model=model,
        svc=svc,
        timeout=timeout,
        tui_output=tui_output,
        deps=deps,
    )


async def handle_image_command_turnrunner(
    turn_runner: object,
    session_key: str,
    tool_ctx: object,
    command: str,
    model: str | None = None,
    svc: object = None,
    timeout: float | None = None,
    *,
    tui_output: TuiOutputHandle | None = None,
    deps: TurnStreamDependencies | None = None,
) -> TurnResult:
    return await _turn_stream.handle_image_command_turnrunner(
        turn_runner,
        session_key,
        tool_ctx,
        command,
        model=model,
        svc=svc,
        timeout=timeout,
        tui_output=tui_output,
        deps=deps,
    )
