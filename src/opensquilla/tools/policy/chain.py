"""Ordered chain of policy checks.

The chain order is the legacy waterfall order — owner_only fires before
denied_tools, denied_tools before private_memory_scope, and so on. The
:func:`run_chain` function returns the first denying decision (the
"first denial wins" contract codified in
``test_dispatch_properties.test_first_denial_wins_*``).
"""

from __future__ import annotations

from opensquilla.tools.policy.checks import (
    AllowListPolicy,
    DenyListPolicy,
    OwnerOnlyPolicy,
    PermissionMatrixPolicy,
    PrivateMemoryScopePolicy,
    ProfilePolicy,
)
from opensquilla.tools.policy.types import DispatchInput, PolicyCheck, PolicyDecision

POLICY_CHAIN: tuple[PolicyCheck, ...] = (
    OwnerOnlyPolicy(),
    DenyListPolicy(),
    PrivateMemoryScopePolicy(),
    AllowListPolicy(),
    ProfilePolicy(),
    PermissionMatrixPolicy(),
)


def run_chain(d: DispatchInput) -> PolicyDecision:
    """Run the chain in order; return the first denial or an allow."""
    for check in POLICY_CHAIN:
        decision = check.evaluate(d)
        if not decision.allowed:
            return decision
    return PolicyDecision(allowed=True)
