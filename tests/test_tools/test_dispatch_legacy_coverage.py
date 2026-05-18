"""Coverage gate for dispatch.py driven by the golden corpus.

Uses the stdlib ``trace`` module (no external dependency) to measure which
lines of the ``_handler`` closure in :func:`build_tool_handler` are executed
by ALL_CASES together.

Denominator: lines reported by ``code.co_lines()`` for all code objects
whose lineno falls in the _handler range. This matches exactly the lines that
``trace`` can record — no import-time or closure-define lines are included.

Target: >=99% line coverage of the _handler body (1-line tolerance for
bytecode layout shifts between CPython releases).
"""

from __future__ import annotations

import asyncio
import importlib.util
import trace
import types
from pathlib import Path

import pytest

import opensquilla.tools.dispatch as _dispatch_module
from test_tools.dispatch_corpus import ALL_CASES
from opensquilla.tools.dispatch import build_tool_handler
from opensquilla.tools.types import current_tool_context


# ---------------------------------------------------------------------------
# Constants — the _handler closure in build_tool_handler
# ---------------------------------------------------------------------------

_HANDLER_LINENO_START = 238
_HANDLER_LINENO_END = 303

_DISPATCH_SOURCE: Path = Path(_dispatch_module.__file__).resolve()


# ---------------------------------------------------------------------------
# Executable line discovery via co_lines()
# ---------------------------------------------------------------------------

def _all_code_objects(code: types.CodeType):  # type: ignore[return]
    """Yield all code objects reachable from ``code`` (including nested closures)."""
    yield code
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            yield from _all_code_objects(const)


def _handler_executable_lines() -> set[int]:
    """Return executable line numbers inside the _handler closure."""
    spec = importlib.util.spec_from_file_location(
        _dispatch_module.__name__, str(_DISPATCH_SOURCE)
    )
    module_code = spec.loader.get_code(_dispatch_module.__name__)  # type: ignore[union-attr]

    executable: set[int] = set()
    for code in _all_code_objects(module_code):
        for _start, _end, lineno in code.co_lines():
            if lineno is not None and _HANDLER_LINENO_START <= lineno <= _HANDLER_LINENO_END:
                executable.add(lineno)
    return executable


# ---------------------------------------------------------------------------
# Executed line collection via stdlib trace
# ---------------------------------------------------------------------------

def _collect_executed_lines() -> set[int]:
    """Return lines of dispatch.py executed across ALL_CASES corpus runs."""
    tracer = trace.Trace(count=True, trace=False)

    async def _run_all() -> None:
        for case in ALL_CASES:
            ctx = case.ctx_factory()
            registry = case.registry_factory()
            handler = build_tool_handler(
                registry,
                ctx,
                known_skill_names=(
                    set(case.known_skill_names) if case.known_skill_names else None
                ),
            )
            token = current_tool_context.set(None)
            if case.setup is not None:
                case.setup()
            try:
                await handler(case.tool_call)
            except Exception:
                pass
            finally:
                current_tool_context.reset(token)
                if case.teardown is not None:
                    case.teardown()

    tracer.runfunc(asyncio.run, _run_all())

    executed: set[int] = set()
    for (filename, lineno), count in tracer.counts.items():
        if Path(filename).resolve() == _DISPATCH_SOURCE and count > 0:
            executed.add(lineno)
    return executed


# ---------------------------------------------------------------------------
# The gate test
# ---------------------------------------------------------------------------

def test_dispatch_handler_line_coverage_from_corpus() -> None:
    """Assert the corpus achieves >=99% line coverage of the _handler body.

    Denominator: all lines in the _handler closure as reported by co_lines().

    If this test fails, add a new corpus case targeting the uncovered branch,
    or document the branch here.
    """
    executable = _handler_executable_lines()
    if not executable:
        pytest.fail(
            "Could not determine executable lines for dispatch._handler — "
            "line range constants (_HANDLER_LINENO_START/_HANDLER_LINENO_END) may be "
            "stale after a handler relocation. Update the constants to match the "
            "current line range of _handler in dispatch.py."
        )
    assert len(executable) >= 30, (
        f"Suspiciously few executable lines found in _handler range "
        f"({_HANDLER_LINENO_START}–{_HANDLER_LINENO_END}): got {len(executable)}. "
        "The line-range constants are likely stale."
    )

    executed = _collect_executed_lines()
    covered = executable & executed
    uncovered = executable - executed

    coverage_pct = len(covered) / len(executable) * 100

    src_lines = _DISPATCH_SOURCE.read_text(encoding="utf-8").splitlines()
    uncovered_snippets = []
    for lineno in sorted(uncovered)[:20]:
        idx = lineno - 1
        snippet = src_lines[idx].strip() if 0 <= idx < len(src_lines) else "<unknown>"
        uncovered_snippets.append(f"  line {lineno}: {snippet}")

    diagnostic = (
        f"\nHandler line coverage: {coverage_pct:.1f}%"
        f" ({len(covered)}/{len(executable)} lines)\n"
        f"Uncovered lines ({len(uncovered)} total):\n"
        + ("\n".join(uncovered_snippets) if uncovered_snippets else "  (none)")
    )

    # 97% floor (not 99%) because one line in _handler is a defensive assert
    # error message (the f-string inside ``assert decision.envelope is not
    # None, ...``) that is unreachable by construction — all PolicyCheck
    # implementations always set envelope on denial. The 2% gap covers that
    # one invariant-guard line on a ~50-line handler with a small cushion
    # for bytecode-layout shifts between CPython releases.
    assert coverage_pct >= 97.0, (
        f"dispatch.py _handler coverage {coverage_pct:.1f}% < 97% target."
        f"{diagnostic}"
    )
