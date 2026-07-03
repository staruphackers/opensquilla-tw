"""Tests for subprocess output decoding and UTF-8 child-env forcing (issue #336).

The Windows fallback path is exercised deterministically on any OS by passing an
explicit ``fallback_encoding`` and by monkeypatching ``os.name`` -- the CI hosts
are POSIX, so we cannot rely on the ambient code page.
"""

from __future__ import annotations

import pytest

from opensquilla import subprocess_encoding
from opensquilla.subprocess_encoding import apply_utf8_child_env, decode_subprocess_output

_HELLO = "你好世界"


class TestDecodeSubprocessOutput:
    def test_gbk_bytes_with_fallback_decode_correctly(self) -> None:
        raw = _HELLO.encode("gbk")
        assert decode_subprocess_output(raw, fallback_encoding="gbk") == _HELLO

    def test_utf8_bytes_win_over_fallback(self) -> None:
        # Strict UTF-8 is tried first, so genuine UTF-8 output is preserved even
        # when a legacy fallback encoding is configured.
        raw = _HELLO.encode("utf-8")
        assert decode_subprocess_output(raw, fallback_encoding="gbk") == _HELLO

    def test_no_fallback_matches_legacy_behavior(self) -> None:
        # POSIX / fallback disabled must behave exactly like the previous code:
        # UTF-8 with replacement.
        raw = _HELLO.encode("gbk")
        assert decode_subprocess_output(raw, fallback_encoding=None) == raw.decode(
            "utf-8", errors="replace"
        )

    def test_valid_utf8_with_no_fallback_is_exact(self) -> None:
        raw = _HELLO.encode("utf-8")
        assert decode_subprocess_output(raw, fallback_encoding=None) == _HELLO

    def test_empty_and_none(self) -> None:
        assert decode_subprocess_output(b"", fallback_encoding="gbk") == ""
        assert decode_subprocess_output(None, fallback_encoding="gbk") == ""

    def test_undecodable_in_both_never_raises(self) -> None:
        # 0xFF is invalid UTF-8 and (as a lone byte) invalid in utf-16 too; the
        # final replacement safety net must keep us from raising.
        result = decode_subprocess_output(b"\xff\xfe\x00bad", fallback_encoding="utf-16")
        assert isinstance(result, str)

    def test_bad_fallback_encoding_name_falls_back_to_replace(self) -> None:
        raw = _HELLO.encode("gbk")
        result = decode_subprocess_output(raw, fallback_encoding="not-a-real-codec")
        assert result == raw.decode("utf-8", errors="replace")

    def test_ascii_is_stable_across_paths(self) -> None:
        raw = b"exit_code=0\nhello\n"
        assert decode_subprocess_output(raw, fallback_encoding="gbk") == raw.decode()
        assert decode_subprocess_output(raw, fallback_encoding=None) == raw.decode()

    def test_chunk_boundary_split_reassembles(self) -> None:
        # Emulate the background_process fix: raw bytes are accumulated and the
        # whole buffer is decoded once, so a multibyte char split across a read
        # boundary is not garbled the way per-chunk decoding was.
        full = _HELLO.encode("gbk")
        first, second = full[:3], full[3:]  # splits a 2-byte GBK char
        per_chunk = first.decode("gbk", errors="replace") + second.decode("gbk", errors="replace")
        buffer = bytearray(first)
        buffer.extend(second)
        whole = decode_subprocess_output(bytes(buffer), fallback_encoding="gbk")
        assert whole == _HELLO
        assert per_chunk != _HELLO  # the old per-chunk approach was lossy


class TestApplyUtf8ChildEnv:
    def test_sets_vars_on_windows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(subprocess_encoding.os, "name", "nt")
        env: dict[str, str] = {}
        result = apply_utf8_child_env(env)
        assert result is env  # mutates and returns the same dict
        assert env["PYTHONUTF8"] == "1"
        assert env["PYTHONIOENCODING"] == "utf-8"

    def test_does_not_override_existing_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(subprocess_encoding.os, "name", "nt")
        env = {"PYTHONIOENCODING": "latin-1", "PYTHONUTF8": "0"}
        apply_utf8_child_env(env)
        assert env["PYTHONIOENCODING"] == "latin-1"
        assert env["PYTHONUTF8"] == "0"

    def test_noop_on_posix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(subprocess_encoding.os, "name", "posix")
        env: dict[str, str] = {}
        apply_utf8_child_env(env)
        assert env == {}
