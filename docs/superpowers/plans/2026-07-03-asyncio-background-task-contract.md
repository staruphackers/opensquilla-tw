# Asyncio Background Task Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair `create_background_task` so its test-friendly coroutine-close contract is explicit, tested, and exception-safe.

**Architecture:** Keep `opensquilla.asyncio_utils` as the single owner of this helper contract. Add direct tests for normal runtime behavior, stubbed non-task returns, and task-creation exceptions. Avoid changing gateway, scheduler, heartbeat, or channel call sites.

**Tech Stack:** Python 3.12, asyncio, pytest, pytest-asyncio via project `uv run`.

---

## File Structure

- Modify: `src/opensquilla/asyncio_utils.py`
  - Responsibility: create background tasks and close still-unconsumed coroutines for test stubs or task-creation failures.
- Create: `tests/test_asyncio_utils.py`
  - Responsibility: direct contract tests for `create_background_task`.

### Task 1: Add Direct Asyncio Helper Contract Tests

**Files:**
- Create: `tests/test_asyncio_utils.py`

- [x] **Step 1: Write the failing tests**

```python
from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

import pytest

from opensquilla.asyncio_utils import create_background_task


async def _return_value(value: str) -> str:
    return value


@pytest.mark.asyncio
async def test_create_background_task_returns_real_task() -> None:
    task = create_background_task(_return_value("done"))

    assert isinstance(task, asyncio.Task)
    assert await task == "done"


@pytest.mark.asyncio
async def test_create_background_task_closes_unconsumed_coroutine_for_stubbed_non_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = object()

    def fake_create_task(coro: Coroutine[Any, Any, Any]) -> object:
        return sentinel

    monkeypatch.setattr(asyncio, "create_task", fake_create_task)

    coro = _return_value("unused")
    assert coro.cr_frame is not None

    result = create_background_task(coro)

    assert result is sentinel
    assert coro.cr_frame is None


@pytest.mark.asyncio
async def test_create_background_task_closes_unconsumed_coroutine_when_create_task_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CreateTaskError(RuntimeError):
        pass

    def fake_create_task(coro: Coroutine[Any, Any, Any]) -> object:
        raise CreateTaskError("task creation failed")

    monkeypatch.setattr(asyncio, "create_task", fake_create_task)

    coro = _return_value("unused")
    assert coro.cr_frame is not None

    with pytest.raises(CreateTaskError, match="task creation failed"):
        create_background_task(coro)

    assert coro.cr_frame is None
```

- [x] **Step 2: Run the tests to verify RED**

Run:

```bash
uv run pytest tests/test_asyncio_utils.py -q
```

Expected: two tests pass and
`test_create_background_task_closes_unconsumed_coroutine_when_create_task_raises`
fails because `coro.cr_frame` remains live after `asyncio.create_task` raises.

### Task 2: Make Task Creation Exception-Safe

**Files:**
- Modify: `src/opensquilla/asyncio_utils.py`
- Test: `tests/test_asyncio_utils.py`

- [x] **Step 1: Implement minimal helper cleanup**

Replace the function body with:

```python
def create_background_task(coro: Coroutine[Any, Any, Any]) -> Any:
    """Create a background task and close unconsumed coroutines in tests."""
    try:
        task = asyncio.create_task(coro)
    except Exception:
        frame = getattr(coro, "cr_frame", None)
        if frame is not None:
            coro.close()
        raise
    frame = getattr(coro, "cr_frame", None)
    if frame is not None and not isinstance(task, asyncio.Task):
        coro.close()
    return task
```

- [x] **Step 2: Run the focused tests to verify GREEN**

Run:

```bash
uv run pytest tests/test_asyncio_utils.py -q
```

Expected: all three tests pass.

### Task 3: Final Verification and Commit

**Files:**
- Stage: `src/opensquilla/asyncio_utils.py`
- Stage: `tests/test_asyncio_utils.py`
- Stage: `docs/superpowers/plans/2026-07-03-asyncio-background-task-contract.md`

- [x] **Step 1: Run formatting and whitespace checks**

Run:

```bash
git diff --check
```

Expected: no output and exit code 0.

- [x] **Step 2: Run focused verification**

Run:

```bash
uv run pytest tests/test_asyncio_utils.py -q
```

Expected: `3 passed`.

- [x] **Step 3: Review the final diff**

Run:

```bash
git diff -- src/opensquilla/asyncio_utils.py tests/test_asyncio_utils.py
git diff -- docs/superpowers/plans/2026-07-03-asyncio-background-task-contract.md
```

Expected: diff only includes the planned helper change, new direct tests, and this plan.

- [x] **Step 4: Commit the implementation**

Run:

```bash
git add src/opensquilla/asyncio_utils.py tests/test_asyncio_utils.py
git add -f docs/superpowers/plans/2026-07-03-asyncio-background-task-contract.md
git commit -m "fix: close unconsumed background task coroutines"
```

Expected: commit succeeds on `fix/asyncio-background-task-contract`.
