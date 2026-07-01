import assert from "node:assert/strict";
import test from "node:test";

import {
  copySelectionToClipboard,
  osClipboardWrite,
  writeOsc52Clipboard,
} from "./primitives.mjs";

// Copy priority: local OS clipboard command (reliable, terminal-agnostic) →
// OpenTUI native OSC52 → direct OSC52 emit (SSH / probe-declined terminals).
// OpenTUI gated its OSC52 on a capability probe many terminals fail, so copy
// silently did nothing; these lock the layered fallback that makes it work.

const b64 = (s) => Buffer.from(s, "utf8").toString("base64");

function fakeSpawn(record, { status = 0, error = null } = {}) {
  return (cmd, args, opts) => {
    record.push({ cmd, args, input: opts?.input });
    return { status, error };
  };
}

// ── osClipboardWrite (platform command) ──────────────────────────────────────

test("osClipboardWrite uses pbcopy on macOS", () => {
  const calls = [];
  const ok = osClipboardWrite("hello", {
    platform: "darwin",
    env: {},
    spawn: fakeSpawn(calls),
  });
  assert.equal(ok, true);
  assert.deepEqual(calls, [{ cmd: "pbcopy", args: [], input: "hello" }]);
});

test("osClipboardWrite tries wl-copy then xclip on Linux until one succeeds", () => {
  const calls = [];
  const spawn = (cmd, args, opts) => {
    calls.push(cmd);
    return { status: cmd === "wl-copy" ? 1 : 0, error: null }; // wl-copy fails, xclip works
  };
  const ok = osClipboardWrite("x", { platform: "linux", env: {}, spawn });
  assert.equal(ok, true);
  assert.deepEqual(calls, ["wl-copy", "xclip"]);
});

test("osClipboardWrite is skipped over SSH (prefer OSC52 to the local machine)", () => {
  const calls = [];
  const ok = osClipboardWrite("x", {
    platform: "darwin",
    env: { SSH_TTY: "/dev/ttys001" },
    spawn: fakeSpawn(calls),
  });
  assert.equal(ok, false);
  assert.equal(calls.length, 0);
});

test("osClipboardWrite returns false on an unknown platform", () => {
  assert.equal(osClipboardWrite("x", { platform: "win32", env: {}, spawn: () => ({ status: 0 }) }), false);
});

// ── writeOsc52Clipboard (escape sequence) ────────────────────────────────────

test("writeOsc52Clipboard emits a bare OSC52 sequence outside tmux", () => {
  const writes = [];
  const ok = writeOsc52Clipboard("hello", { env: {}, out: { write: (s) => writes.push(s) } });
  assert.equal(ok, true);
  assert.equal(writes[0], `\x1b]52;c;${b64("hello")}\x07`);
});

test("writeOsc52Clipboard wraps the sequence in tmux passthrough under TMUX", () => {
  const writes = [];
  writeOsc52Clipboard("hi", { env: { TMUX: "/tmp/t,1,0" }, out: { write: (s) => writes.push(s) } });
  assert.equal(writes[0], `\x1bPtmux;\x1b\x1b]52;c;${b64("hi")}\x07\x1b\\`);
});

// ── copySelectionToClipboard (layered) ───────────────────────────────────────

test("copy over SSH with a probe-declined terminal falls back to direct OSC52", () => {
  // Force the SSH branch so the OS-clipboard command is skipped, and a probe that
  // reports unsupported — the old code copied nothing here.
  const restoreEnv = process.env.SSH_TTY;
  const restoreWrite = process.stdout.write.bind(process.stdout);
  const writes = [];
  process.env.SSH_TTY = "/dev/ttys001";
  process.stdout.write = (s) => (writes.push(s), true);
  try {
    const ok = copySelectionToClipboard(
      { isOsc52Supported: () => false, copyToClipboardOSC52: () => true },
      { getSelectedText: () => "grep foo" },
    );
    assert.equal(ok, true);
  } finally {
    process.stdout.write = restoreWrite;
    if (restoreEnv === undefined) delete process.env.SSH_TTY;
    else process.env.SSH_TTY = restoreEnv;
  }
  assert.equal(writes[0], `\x1b]52;c;${b64("grep foo")}\x07`);
});

test("copy is a no-op for an empty selection", () => {
  const renderer = { isOsc52Supported: () => true, copyToClipboardOSC52: () => true };
  assert.equal(copySelectionToClipboard(renderer, { getSelectedText: () => "" }), false);
});
