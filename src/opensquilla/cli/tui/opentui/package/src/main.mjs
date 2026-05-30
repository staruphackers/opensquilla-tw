#!/usr/bin/env node

import fs from "node:fs";
import process from "node:process";
import readline from "node:readline";

const HELP = `OpenSquilla OpenTUI footer host

Usage:
  bun src/main.mjs

IPC:
  reads Python JSON lines from fd 3 and writes host JSON lines to fd 4.
`;

if (process.argv.includes("--help") || process.argv.includes("-h")) {
  process.stdout.write(HELP);
  process.exit(0);
}

const FROM_PYTHON_FD = Number(process.env.OPENSQUILLA_OPENTUI_FROM_PYTHON_FD ?? "3");
const TO_PYTHON_FD = Number(process.env.OPENSQUILLA_OPENTUI_TO_PYTHON_FD ?? "4");
const FOOTER_HEIGHT = 6;

let renderer;
let root;
let Box;
let Text;
let TextRenderable;
let createCliRenderer;
let inputText = "";

const composer = {
  placeholder: "send a message",
  text: "",
  disabled: false,
};

const routerState = {
  model: "routing...",
  route: "route pending",
  saving: "saving pending",
  context: "ctx pending",
  style: "dim",
};

const turnStatus = {
  phase: "idle",
  label: "ready",
  active: false,
  style: "dim",
};

function sendHostMessage(message) {
  fs.writeSync(TO_PYTHON_FD, `${JSON.stringify(message)}\n`, "utf8");
}

function writeError(error) {
  const message = error instanceof Error ? error.message : String(error);
  try {
    sendHostMessage({ type: "error", message });
  } catch {
    process.stderr.write(`${message}\n`);
  }
}

function colorForStyle(style) {
  if (style === "warning") return "#F6C177";
  if (style === "error") return "#EB6F92";
  if (style === "dim") return "#6E7581";
  return "#9CCFD8";
}

function statusIcon() {
  if (!turnStatus.active) return "✓";
  if (turnStatus.phase === "tool") return "◌";
  if (turnStatus.phase === "output") return "◇";
  return "∙";
}

function renderFooterTree() {
  const composerLine = inputText || composer.text;
  const visibleComposer = composerLine || composer.placeholder;
  const composerColor = composerLine ? "#E6EDF3" : "#7D8590";
  const statusColor = colorForStyle(turnStatus.style);
  const routerColor = colorForStyle(routerState.style);

  return Box(
    {
      id: "opentui-footer-root",
      width: "100%",
      height: "100%",
      flexDirection: "row",
      backgroundColor: "#0B0F14",
    },
    Box(
      {
        id: "composer-wrap",
        flexGrow: 1,
        height: "100%",
        paddingLeft: 1,
        paddingRight: 1,
        flexDirection: "column",
        justifyContent: "center",
      },
      Box(
        {
          id: "composer-box",
          width: "100%",
          height: 4,
          borderStyle: "rounded",
          borderColor: composer.disabled ? "#3A3F47" : "#7AA2F7",
          paddingLeft: 1,
          paddingRight: 1,
          flexDirection: "column",
          justifyContent: "center",
          backgroundColor: "#0B0F14",
        },
        Text({
          id: "composer-placeholder",
          content: "send a message",
          fg: "#7D8590",
        }),
        Text({
          id: "composer-text",
          content: visibleComposer,
          fg: composerColor,
        }),
      ),
      Text({
        id: "turn-status",
        content: `${statusIcon()} ${turnStatus.label}`,
        fg: statusColor,
      }),
    ),
    Box(
      {
        id: "router-plugin",
        width: 27,
        height: 5,
        marginRight: 1,
        marginTop: 1,
        borderStyle: "rounded",
        borderColor: routerColor,
        paddingLeft: 1,
        paddingRight: 1,
        flexDirection: "column",
        backgroundColor: "#10161F",
      },
      Text({ id: "router-model", content: `model  ${routerState.model}`, fg: "#E6EDF3" }),
      Text({ id: "router-route", content: `route  ${routerState.route}`, fg: "#C4B5FD" }),
      Text({ id: "router-saving", content: `save   ${routerState.saving}`, fg: "#8BD5CA" }),
      Text({ id: "router-context", content: `ctx    ${routerState.context}`, fg: "#F6C177" }),
    ),
  );
}

function rerenderFooter() {
  if (!renderer) return;
  if (root) {
    renderer.root.remove("opentui-footer-root");
  }
  root = renderFooterTree();
  renderer.root.add(root);
  renderer.requestRender?.();
}

function writePlainScrollback(text) {
  renderer.writeToScrollback((ctx) => {
    const root = new TextRenderable(ctx.renderContext, {
      id: `scrollback-${Date.now()}`,
      position: "absolute",
      left: 0,
      top: 0,
      width: ctx.width,
      height: Math.max(1, text.split("\n").length),
      content: text,
      fg: "#E6EDF3",
    });
    return {
      root,
      width: ctx.width,
      height: Math.max(1, text.split("\n").length),
      startOnNewLine: false,
      trailingNewline: false,
    };
  });
}

function handlePythonMessage(message) {
  switch (message.type) {
    case "router.update":
      Object.assign(routerState, {
        model: String(message.model ?? routerState.model),
        route: String(message.route ?? routerState.route),
        saving: String(message.saving ?? routerState.saving),
        context: String(message.context ?? routerState.context),
        style: String(message.style ?? routerState.style),
      });
      rerenderFooter();
      return;
    case "composer.set":
      Object.assign(composer, {
        placeholder: String(message.placeholder ?? composer.placeholder),
        text: String(message.text ?? composer.text),
        disabled: Boolean(message.disabled ?? composer.disabled),
      });
      inputText = composer.text;
      rerenderFooter();
      return;
    case "turn.status":
      Object.assign(turnStatus, {
        phase: String(message.phase ?? turnStatus.phase),
        label: String(message.label ?? turnStatus.label),
        active: Boolean(message.active ?? turnStatus.active),
        style: String(message.style ?? turnStatus.style),
      });
      rerenderFooter();
      return;
    case "scrollback.write":
      writePlainScrollback(String(message.text ?? ""));
      return;
    case "shutdown":
      renderer.destroy();
      process.exit(0);
      return;
    default:
      writeError(new Error(`Unknown Python message type: ${message.type}`));
  }
}

function submitInput() {
  const text = inputText;
  inputText = "";
  composer.text = "";
  sendHostMessage({ type: "input.submit", text });
  rerenderFooter();
}

function installKeyboardHandlers() {
  renderer.keyInput.on("keypress", (key) => {
    if (key.ctrl && key.name === "c") {
      sendHostMessage({ type: "input.cancel" });
      return;
    }
    if (key.ctrl && key.name === "d") {
      sendHostMessage({ type: "input.eof" });
      return;
    }
    if (key.name === "return") {
      submitInput();
      return;
    }
    if (key.name === "backspace") {
      inputText = inputText.slice(0, -1);
      rerenderFooter();
      return;
    }
    const printable = key.sequence ?? key.name ?? "";
    if (printable.length > 0 && !key.ctrl && !key.meta && key.name !== "space") {
      inputText += printable;
      rerenderFooter();
    } else if (key.name === "space") {
      inputText += " ";
      rerenderFooter();
    }
  });

  const decoder = new TextDecoder();
  renderer.keyInput.on("paste", (event) => {
    inputText += decoder.decode(event.bytes);
    rerenderFooter();
  });
}

async function main() {
  ({ Box, Text, TextRenderable, createCliRenderer } = await import("@opentui/core"));

  renderer = await createCliRenderer({
    screenMode: "split-footer",
    footerHeight: FOOTER_HEIGHT,
    externalOutputMode: "capture-stdout",
    exitOnCtrlC: false,
  });

  rerenderFooter();
  installKeyboardHandlers();
  sendHostMessage({ type: "ready" });

  const input = fs.createReadStream(null, {
    fd: FROM_PYTHON_FD,
    encoding: "utf8",
    autoClose: false,
  });
  const lines = readline.createInterface({ input, crlfDelay: Infinity });
  lines.on("line", (line) => {
    if (!line.trim()) return;
    try {
      handlePythonMessage(JSON.parse(line));
    } catch (error) {
      writeError(error);
    }
  });
  lines.on("close", () => {
    renderer.destroy();
    process.exit(0);
  });
}

main().catch((error) => {
  writeError(error);
  process.exit(1);
});
