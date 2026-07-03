"""Encoding helpers for subprocess stdout/stderr on non-UTF-8 consoles.

On Windows the console / ANSI code page is frequently a legacy multibyte code
page (e.g. CP936/GBK on Chinese systems, CP932 on Japanese systems).  Commands
launched by ``exec_command``, ``background_process`` and ``execute_code`` emit
their output in that code page, but the gateway historically decoded every
subprocess byte stream as UTF-8.  Non-ASCII text (Chinese, Japanese, ...) then
collapsed into U+FFFD replacement characters -- the "乱码" reported in issue #336.

This module centralises two fixes:

* :func:`decode_subprocess_output` -- decode captured bytes by trying strict
  UTF-8 first (which wins whenever the child already emitted UTF-8) and falling
  back to the Windows system code page when the bytes are not valid UTF-8.
* :func:`apply_utf8_child_env` -- force Python child processes to emit UTF-8 on
  Windows so the strict UTF-8 path is taken in the first place.

On POSIX both helpers preserve the previous behaviour byte-for-byte: decoding is
UTF-8 with replacement and no environment variables are injected.
"""

from __future__ import annotations

import codecs
import locale
import os


def _windows_system_encoding() -> str | None:
    """Return the Windows console/ANSI code page name, or ``None`` off Windows.

    Prefers the console output code page (what redirected console apps and the
    ``cmd.exe`` builtins write with), then the ANSI code page, then the locale's
    preferred encoding.  Best-effort: any failure yields ``None`` so callers fall
    back to plain UTF-8 handling.
    """
    if os.name != "nt":
        return None
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        code_page = int(kernel32.GetConsoleOutputCP()) or int(kernel32.GetACP())
        if code_page:
            return f"cp{code_page}"
    except Exception:
        pass
    preferred = locale.getpreferredencoding(False)
    return preferred or None


# Resolved once at import.  ``None`` on POSIX so decoding stays plain UTF-8 there.
_DEFAULT_FALLBACK_ENCODING = _windows_system_encoding()


def decode_subprocess_output(
    raw: bytes | None,
    *,
    fallback_encoding: str | None = _DEFAULT_FALLBACK_ENCODING,
) -> str:
    """Decode subprocess output bytes to text.

    Without a fallback encoding (POSIX, or the fallback explicitly disabled) this
    is exactly the historical behaviour: UTF-8 with replacement.

    With a fallback encoding (Windows) strict UTF-8 is attempted first -- so
    anything the child emitted as UTF-8 is preserved -- and only genuinely
    non-UTF-8 bytes fall through to the legacy code page (e.g. ``cp936``).

    Both attempts use an *incremental* decoder fed with ``final=False`` so that
    an incomplete multibyte sequence at the very end of the buffer -- which
    happens whenever output is truncated at a byte cap or read mid-stream -- is
    buffered and dropped rather than turned into replacement characters.  Without
    this, a single cut trailing byte would make a strict decode fail and collapse
    the *entire* buffer to garbled replacement text (issue #336).
    """
    if not raw:
        return ""
    if not fallback_encoding:
        return raw.decode("utf-8", errors="replace")
    try:
        return codecs.getincrementaldecoder("utf-8")("strict").decode(raw, final=False)
    except UnicodeDecodeError:
        pass
    try:
        return codecs.getincrementaldecoder(fallback_encoding)("replace").decode(raw, final=False)
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def apply_utf8_child_env(env: dict[str, str]) -> dict[str, str]:
    """Force UTF-8 stdio for Python child processes on Windows.

    Mutates and returns *env*.  Uses ``setdefault`` so an explicit value supplied
    by the caller or the user is never overridden.  No-op on POSIX, where the
    default locale is already UTF-8.
    """
    if os.name == "nt":
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
    return env
