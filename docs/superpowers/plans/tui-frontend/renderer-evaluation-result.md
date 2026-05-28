# TUI Renderer Evaluation Result

Date: 2026-05-28

## Recommendation

Keep the terminal renderer as the production default. Keep Textual as an
optional experimental backend scaffold for later evaluation, but do not promote
it and do not add it as a dependency in this phase.

The local environment does not have Textual installed, so the relative Textual
thresholds could not be evaluated. The explicit Textual path now skips cleanly
with `Textual is not installed`, which is enough to preserve optional-dependency
behavior without changing the default CLI surface.

## Evidence

Commands run:

```bash
uv run python scripts/bench_tui_replay.py --renderer terminal --fixture long-stream --summary-json .artifacts/tui/terminal-long-stream.json
uv run python scripts/bench_tui_replay.py --renderer textual --fixture long-stream --summary-json .artifacts/tui/textual-long-stream.json
uv run python scripts/bench_tui_replay.py --renderer terminal --fixture dense-history --summary-json .artifacts/tui/terminal-dense-history.json
uv run python scripts/bench_tui_replay.py --renderer textual --fixture dense-history --summary-json .artifacts/tui/textual-dense-history.json
```

Local JSON summaries:

- `.artifacts/tui/terminal-long-stream.json`: available, 4,011 events,
  160,000 text chars, 86 flushes, coalescing ratio 0.02,
  max buffer 2,040 chars, rendered text matched, 0 plugin errors, 0 errors.
- `.artifacts/tui/terminal-dense-history.json`: available, 624 events,
  624 transcript items, 30 visible items, 20 expanded tools,
  projection wall time 0.146 ms, 0 plugin errors, 0 errors.
- `.artifacts/tui/textual-long-stream.json`: unavailable, skipped with
  `Textual is not installed`, 0 errors.
- `.artifacts/tui/textual-dense-history.json`: unavailable, skipped with
  `Textual is not installed`, 0 errors.

## Threshold Assessment

- Long-stream terminal replay preserved final text exactly.
- Terminal coalescing stayed bounded at 86 flushes for 4,000 text deltas.
- Dense-history projection stayed bounded to 30 visible items from 624
  transcript items.
- No replay summary reported plugin dispatch errors.
- Textual import and availability checks are lazy, so existing prompt-toolkit
  behavior is unchanged when Textual is absent.

Textual promotion remains blocked until it is installed in an evaluation
environment and passes the same long-stream and dense-history thresholds against
the terminal baseline.
