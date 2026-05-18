"""Concrete :class:`PolicyCheck` implementations.

Each check mirrors a single branch from the legacy waterfall in
``opensquilla.tools.dispatch_legacy``. The line ranges referenced in the
docstrings point at the canonical legacy contract.

Behaviour notes shared across the checks:

* ``ctx is None`` always allows — the legacy code guards every policy
  with ``if effective_ctx and ...``.
* Denial envelopes are constructed via :func:`_denial_envelope`, which
  centralises the ``ToolResult`` shape used by the legacy
  ``_build_envelope_result`` helper for ``policy_denial=True``.
* The structured log event returned alongside an envelope is emitted by
  the orchestrator at WARN level — keeping I/O out of the checks
  themselves.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from opensquilla.execution_status import normalize_execution_status
from opensquilla.safety.permission_matrix import Principal, is_tool_allowed
from opensquilla.tool_boundary import ToolCall, ToolResult
from opensquilla.tools.envelope import build_tool_failure_envelope
from opensquilla.tools.policy.types import DispatchInput, PolicyDecision
from opensquilla.tools.policy_helpers import private_memory_read_tool_denied
from opensquilla.tools.types import CallerKind, ToolContext


def _denial_envelope(
    tool_call: ToolCall,
    *,
    exc: Exception,
    error_class_override: str,
    user_message_override: str,
) -> ToolResult:
    """Build the ``ToolResult`` returned for a policy-denial outcome.

    Mirrors :func:`opensquilla.tools.dispatch_legacy._build_envelope_result`
    when ``policy_denial=True``.
    """
    status = {
        "version": 1,
        "status": "error",
        "exit_code": None,
        "timed_out": False,
        "truncated": False,
        "reason": "denied",
        "source": "tool_runtime",
        "preservation_class": "diagnostic",
    }
    return ToolResult(
        tool_use_id=tool_call.tool_use_id,
        tool_name=tool_call.tool_name,
        content=json.dumps(
            build_tool_failure_envelope(
                exc,
                tool_call.tool_name,
                policy_denial=True,
                error_class_override=error_class_override,
                user_message_override=user_message_override,
            )
        ),
        is_error=True,
        execution_status=normalize_execution_status(status),
    )


def _block_log_event(
    tool_call: ToolCall,
    ctx: ToolContext | None,
    *,
    event: str,
    reason: str,
) -> dict[str, Any]:
    """Construct the ``dispatch.defense_in_depth_block`` log payload.

    Field order and key names match the legacy ``log.warning`` calls so
    the equivalence harness sees identical structured-log records.
    """
    return {
        "event": event,
        "tool": tool_call.tool_name,
        "reason": reason,
        "tool_use_id": tool_call.tool_use_id,
        "agent_id": ctx.agent_id if ctx else None,
        "session_key": ctx.session_key if ctx else None,
    }


# ---------------------------------------------------------------------------
# Owner-only — legacy lines 215–231
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OwnerOnlyPolicy:
    """Reject ``owner_only`` tools when ``ctx.is_owner`` is False."""

    name: str = "owner_only"

    def evaluate(self, d: DispatchInput) -> PolicyDecision:
        ctx = d.ctx
        if ctx and d.registered.spec.owner_only and not ctx.is_owner:
            envelope = _denial_envelope(
                d.tool_call,
                exc=PermissionError("owner-only tool"),
                error_class_override="OwnerOnly",
                user_message_override=(
                    f"Tool '{d.tool_call.tool_name}' restricted to owner."
                ),
            )
            log_event = _block_log_event(
                d.tool_call,
                ctx,
                event="dispatch.defense_in_depth_block",
                reason="owner_only",
            )
            return PolicyDecision(allowed=False, envelope=envelope, log_event=log_event)
        return PolicyDecision(allowed=True)


# ---------------------------------------------------------------------------
# Deny list — legacy lines 233–251
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DenyListPolicy:
    """Reject tools that appear in ``ctx.denied_tools``."""

    name: str = "denied"

    def evaluate(self, d: DispatchInput) -> PolicyDecision:
        ctx = d.ctx
        if ctx and d.tool_call.tool_name in ctx.denied_tools:
            envelope = _denial_envelope(
                d.tool_call,
                exc=PermissionError("tool blocked"),
                error_class_override="PolicyDenied",
                user_message_override=(
                    f"Tool '{d.tool_call.tool_name}' not available in this context."
                ),
            )
            log_event = _block_log_event(
                d.tool_call,
                ctx,
                event="dispatch.defense_in_depth_block",
                reason="denied",
            )
            return PolicyDecision(allowed=False, envelope=envelope, log_event=log_event)
        return PolicyDecision(allowed=True)


# ---------------------------------------------------------------------------
# Private memory scope — legacy lines 253–270
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PrivateMemoryScopePolicy:
    """Reject private-memory reads from contexts that may not access them."""

    name: str = "private_memory_scope"

    def evaluate(self, d: DispatchInput) -> PolicyDecision:
        ctx = d.ctx
        if private_memory_read_tool_denied(ctx, d.tool_call.tool_name):
            envelope = _denial_envelope(
                d.tool_call,
                exc=PermissionError("private memory blocked"),
                error_class_override="PolicyDenied",
                user_message_override=(
                    f"Tool '{d.tool_call.tool_name}' not available in this context."
                ),
            )
            log_event = _block_log_event(
                d.tool_call,
                ctx,
                event="dispatch.defense_in_depth_block",
                reason="private_memory_scope",
            )
            return PolicyDecision(allowed=False, envelope=envelope, log_event=log_event)
        return PolicyDecision(allowed=True)


# ---------------------------------------------------------------------------
# Allow list — legacy lines 272–293
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AllowListPolicy:
    """Reject tools absent from a non-None ``ctx.allowed_tools``."""

    name: str = "allowlist"

    def evaluate(self, d: DispatchInput) -> PolicyDecision:
        ctx = d.ctx
        if (
            ctx
            and ctx.allowed_tools is not None
            and d.tool_call.tool_name not in ctx.allowed_tools
        ):
            envelope = _denial_envelope(
                d.tool_call,
                exc=PermissionError("tool blocked"),
                error_class_override="PolicyDenied",
                user_message_override=(
                    f"Tool '{d.tool_call.tool_name}' not available in this context."
                ),
            )
            log_event = _block_log_event(
                d.tool_call,
                ctx,
                event="dispatch.defense_in_depth_block",
                reason="not_allowed",
            )
            return PolicyDecision(allowed=False, envelope=envelope, log_event=log_event)
        return PolicyDecision(allowed=True)


# ---------------------------------------------------------------------------
# Profile — legacy lines 295–315
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProfilePolicy:
    """Reject tools the resolved tool profile does not allow."""

    name: str = "profile"

    def evaluate(self, d: DispatchInput) -> PolicyDecision:
        # Imported lazily — opensquilla.tools.registry imports
        # opensquilla.tools.policy at module-load time, so a top-level
        # import here would create a circular dependency.
        from opensquilla.tools.registry import profile_allows_tool, resolve_profile

        ctx = d.ctx
        if ctx and not profile_allows_tool(
            d.tool_call.tool_name,
            resolve_profile(ctx),
            explicitly_allowed=ctx.allowed_tools,
        ):
            envelope = _denial_envelope(
                d.tool_call,
                exc=PermissionError("tool blocked by profile"),
                error_class_override="PolicyDenied",
                user_message_override=(
                    f"Tool '{d.tool_call.tool_name}' not available in this context."
                ),
            )
            log_event = {
                "event": "dispatch.profile_block",
                "tool": d.tool_call.tool_name,
                "tool_use_id": d.tool_call.tool_use_id,
                "agent_id": ctx.agent_id,
                "session_key": ctx.session_key,
            }
            return PolicyDecision(allowed=False, envelope=envelope, log_event=log_event)
        return PolicyDecision(allowed=True)


# ---------------------------------------------------------------------------
# Permission matrix — legacy lines 317–340
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PermissionMatrixPolicy:
    """Run the channel permission matrix when ``caller_kind == CHANNEL``."""

    name: str = "permission_matrix"

    def evaluate(self, d: DispatchInput) -> PolicyDecision:
        ctx = d.ctx
        if ctx and ctx.caller_kind is CallerKind.CHANNEL:
            # Defense-in-depth: CHANNEL callers must never reach operator role
            # regardless of is_owner. Owner promotion happens upstream in the
            # owner-resolver, not here, so an is_owner=True leak from a future
            # ctx constructor must not silently widen channel permissions.
            principal = Principal(
                role="user",
                channel_id=ctx.session_key,
            )
            decision = is_tool_allowed(d.tool_call.tool_name, "dm", principal)
            if not decision.allowed:
                envelope = _denial_envelope(
                    d.tool_call,
                    exc=PermissionError("tool denied"),
                    error_class_override="UnsupportedSurface",
                    user_message_override=(
                        f"Tool '{d.tool_call.tool_name}' denied: {decision.reason}."
                    ),
                )
                log_event = {
                    "event": "dispatch.permission_matrix_block",
                    "tool": d.tool_call.tool_name,
                    "reason": decision.reason,
                    "tool_use_id": d.tool_call.tool_use_id,
                    "agent_id": ctx.agent_id if ctx else None,
                    "session_key": ctx.session_key if ctx else None,
                }
                return PolicyDecision(
                    allowed=False, envelope=envelope, log_event=log_event
                )
        return PolicyDecision(allowed=True)
