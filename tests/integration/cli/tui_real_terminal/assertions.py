from __future__ import annotations

import re

from tui_real_terminal.driver import TerminalFrame

_ANSI_RE = re.compile(
    r"\x1b(?:"
    r"\[[0-?]*[ -/]*[@-~]"
    r"|\][^\x07\x1b]*(?:\x07|\x1b\\)"
    r"|P[^\x1b]*\x1b\\"
    r"|[@-Z\\-_]"
    r")"
)
_PROMPT_PLACEHOLDERS = ("send a message", "send a massage")


def assert_visible_text(frame: TerminalFrame, expected: str) -> None:
    if expected not in frame.text:
        raise AssertionError(
            f"{frame.checkpoint}: expected visible text {expected!r}; screen was:\n"
            f"{frame.text}"
        )


def assert_prompt_ready(frame: TerminalFrame) -> None:
    if "you" not in frame.text and not any(
        placeholder in frame.text for placeholder in _PROMPT_PLACEHOLDERS
    ):
        raise AssertionError(f"{frame.checkpoint}: prompt is not visibly ready:\n{frame.text}")


def assert_no_inline_prompt_chrome_collision(frame: TerminalFrame) -> None:
    for line in frame.text.splitlines():
        if re.match(r"^\s*│\s+s(?:[#|*⠋✓✗]|[\u4e00-\u9fff])", line):
            raise AssertionError(
                f"{frame.checkpoint}: inline prompt chrome overlapped output:\n{frame.text}"
            )
        resize_checkpoint = "narrow" in frame.checkpoint or "wide" in frame.checkpoint
        if (
            sum(line.count(placeholder) for placeholder in _PROMPT_PLACEHOLDERS) > 1
            and not resize_checkpoint
        ):
            raise AssertionError(
                f"{frame.checkpoint}: inline prompt chrome was duplicated:\n{frame.text}"
            )


def assert_no_traceback(frame: TerminalFrame) -> None:
    forbidden = (
        "Traceback (most recent call last)",
        "RuntimeError:",
        "Unhandled exception",
    )
    for marker in forbidden:
        if marker in frame.text:
            raise AssertionError(f"{frame.checkpoint}: unexpected error marker {marker!r}")


def assert_no_raw_ansi_leakage(frame: TerminalFrame) -> None:
    match = _ANSI_RE.search(frame.text)
    if match:
        raise AssertionError(
            f"{frame.checkpoint}: raw terminal escape leaked at offset {match.start()}"
        )
