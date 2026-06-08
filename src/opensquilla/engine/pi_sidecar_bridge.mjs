#!/usr/bin/env node
import { readFile } from "node:fs/promises";
import { createInterface } from "node:readline";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { stdin, stderr, stdout } from "node:process";
import { pathToFileURL } from "node:url";

const DEFAULT_RUNTIME_PACKAGE = "@earendil-works/pi-agent-core";
const DEFAULT_AI_PACKAGE = "@earendil-works/pi-ai";
const PROTOCOL = process.env.OPENSQUILLA_AGENT_CORE_PROTOCOL || "opensquilla.agent_core.v1";
const STDOUT_FRAME_MAX_BYTES = 24_000;
const STDOUT_FRAME_CHUNK_CHARS = 18_000;
const SUPPORTED_INTENT_RESULT_TYPES = new Set([
  "provider.request",
  "tool.call.prepare",
  "tool.call.execute",
  "session.write.enqueue",
  "queue.poll",
  "savepoint.request",
  "yield.request",
  "telemetry.emit",
]);
const SUPPORTED_INTENT_RESULT_EVENT_KINDS = new Set([
  "agent_start",
  "agent_end",
  "artifact",
  "auto_retry_end",
  "auto_retry_start",
  "compaction",
  "compaction_end",
  "compaction_start",
  "done",
  "error",
  "message_end",
  "message_start",
  "message_update",
  "provider.done",
  "provider.request",
  "provider_done",
  "provider_request",
  "queue_update",
  "queue.poll",
  "router_control_replay",
  "router_decision",
  "run_heartbeat",
  "session.write",
  "session.write.enqueue",
  "savepoint.request",
  "state_change",
  "text_delta",
  "telemetry.emit",
  "thinking",
  "tool.call.execute",
  "tool.call.prepare",
  "tool.result",
  "tool_result",
  "tool_use_delta",
  "tool_use_end",
  "tool_use_start",
  "tool_execution_end",
  "tool_execution_start",
  "tool_execution_update",
  "turn_start",
  "turn_end",
  "warning",
  "yield",
  "yield.request",
]);

function parseArgs(argv) {
  const args = {
    runtimePackage: DEFAULT_RUNTIME_PACKAGE,
    aiPackage: DEFAULT_AI_PACKAGE,
    moduleRoot: "",
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const next = argv[index + 1];
    if (
      arg === "--runtime" ||
      arg === "--runtime-package" ||
      arg === "--runtime_package" ||
      arg === "--pi-runtime" ||
      arg === "--pi_runtime" ||
      arg === "--piRuntime"
    ) {
      if (!next) throw new Error(`${arg} requires a package specifier`);
      args.runtimePackage = next;
      index += 1;
      continue;
    }
    if (arg.startsWith("--runtime=")) {
      args.runtimePackage = arg.slice("--runtime=".length);
      continue;
    }
    if (arg.startsWith("--runtime-package=")) {
      args.runtimePackage = arg.slice("--runtime-package=".length);
      continue;
    }
    if (arg === "--ai-package") {
      if (!next) throw new Error("--ai-package requires a package specifier");
      args.aiPackage = next;
      index += 1;
      continue;
    }
    if (arg === "--module-root") {
      if (!next) throw new Error("--module-root requires a directory");
      args.moduleRoot = next;
      index += 1;
      continue;
    }
    if (arg.startsWith("--module-root=")) {
      args.moduleRoot = arg.slice("--module-root=".length);
      continue;
    }
  }
  return args;
}

function isPathLikeSpecifier(specifier) {
  return (
    specifier.startsWith("/") ||
    specifier.startsWith("./") ||
    specifier.startsWith("../") ||
    specifier.startsWith("file:")
  );
}

function splitPackageSpecifier(specifier) {
  const parts = specifier.split("/");
  if (specifier.startsWith("@")) {
    if (parts.length < 2 || !parts[0] || !parts[1]) {
      throw new Error(`invalid package specifier: ${specifier}`);
    }
    return {
      packageName: `${parts[0]}/${parts[1]}`,
      exportKey: parts.length > 2 ? `./${parts.slice(2).join("/")}` : ".",
    };
  }
  if (!parts[0]) throw new Error(`invalid package specifier: ${specifier}`);
  return {
    packageName: parts[0],
    exportKey: parts.length > 1 ? `./${parts.slice(1).join("/")}` : ".",
  };
}

function importTargetFromExportValue(exportValue) {
  if (typeof exportValue === "string") return exportValue;
  if (Array.isArray(exportValue)) {
    for (const candidate of exportValue) {
      const target = importTargetFromExportValue(candidate);
      if (target) return target;
    }
    return null;
  }
  if (!exportValue || typeof exportValue !== "object") return null;
  for (const condition of ["import", "node", "default"]) {
    const target = importTargetFromExportValue(exportValue[condition]);
    if (target) return target;
  }
  return null;
}

function importTargetFromPackageExports(packageExports, exportKey) {
  if (packageExports === undefined) return null;
  if (
    typeof packageExports === "string" ||
    Array.isArray(packageExports) ||
    packageExports.import !== undefined ||
    packageExports.node !== undefined ||
    packageExports.default !== undefined
  ) {
    return exportKey === "." ? importTargetFromExportValue(packageExports) : null;
  }
  return importTargetFromExportValue(packageExports[exportKey]);
}

async function resolveBridgeModuleUrl(specifier, moduleRoot) {
  const requireFromModuleRoot = createRequire(
    pathToFileURL(resolve(moduleRoot, "package.json")),
  );
  try {
    return pathToFileURL(requireFromModuleRoot.resolve(specifier)).href;
  } catch (resolveError) {
    const { packageName, exportKey } = splitPackageSpecifier(specifier);
    let packageJsonPath;
    try {
      packageJsonPath = requireFromModuleRoot.resolve(`${packageName}/package.json`);
    } catch {
      packageJsonPath = resolve(
        moduleRoot,
        "node_modules",
        ...packageName.split("/"),
        "package.json",
      );
    }
    let packageJson;
    try {
      packageJson = JSON.parse(await readFile(packageJsonPath, "utf8"));
    } catch {
      throw resolveError;
    }
    const importTarget =
      importTargetFromPackageExports(packageJson.exports, exportKey) ||
      (exportKey === "." ? packageJson.module || packageJson.main : null);
    if (!importTarget) throw resolveError;
    return pathToFileURL(resolve(dirname(packageJsonPath), importTarget)).href;
  }
}

async function importBridgeModule(specifier, moduleRoot) {
  if (!moduleRoot || isPathLikeSpecifier(specifier)) return import(specifier);
  return import(await resolveBridgeModuleUrl(specifier, moduleRoot));
}

let nextChunkId = 0;

function writeFrame(frame) {
  const serialized = JSON.stringify({ protocol: PROTOCOL, ...frame });
  if (Buffer.byteLength(serialized, "utf8") <= STDOUT_FRAME_MAX_BYTES) {
    stdout.write(`${serialized}\n`);
    return;
  }
  const encoded = Buffer.from(serialized, "utf8").toString("base64");
  const total = Math.ceil(encoded.length / STDOUT_FRAME_CHUNK_CHARS);
  const chunkId = `stdout-${Date.now()}-${nextChunkId}`;
  nextChunkId += 1;
  for (let index = 0; index < total; index += 1) {
    stdout.write(
      `${JSON.stringify({
        protocol: PROTOCOL,
        kind: "chunk",
        chunk_id: chunkId,
        index,
        total,
        encoding: "base64-json",
        data: encoded.slice(
          index * STDOUT_FRAME_CHUNK_CHARS,
          (index + 1) * STDOUT_FRAME_CHUNK_CHARS,
        ),
      })}\n`,
    );
  }
}

function writeProtocolError(message, code = "pi_bridge_error") {
  writeFrame({
    kind: "event",
    type: "error",
    payload: { message: String(message), code },
  });
}

function jsonObject(value, fieldName) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${fieldName} must be a JSON object`);
  }
  return value;
}

function stringValue(value, fieldName) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`${fieldName} must be a non-empty string`);
  }
  return value;
}

function intentResultType(value) {
  if (typeof value !== "string") {
    throw new Error("intent_result type must be a string");
  }
  if (value.trim() === "") {
    throw new Error("intent_result type must be non-empty");
  }
  if (value.trim() !== value) {
    throw new Error("intent_result type must not contain surrounding whitespace");
  }
  if (!SUPPORTED_INTENT_RESULT_TYPES.has(value)) {
    throw new Error(`Unsupported Pi sidecar intent_result '${value}'`);
  }
  return value;
}

function intentResultSessionKey(value, expectedSessionKey) {
  if (typeof value !== "string") {
    throw new Error("intent_result session_key must be a string");
  }
  if (value.trim() === "") {
    throw new Error("intent_result session_key must be non-empty");
  }
  if (value !== expectedSessionKey) {
    throw new Error("intent_result session_key must match current turn session_key");
  }
  return value;
}

function eventStringValue(event, fieldName) {
  const value = event?.[fieldName];
  if (typeof value !== "string") {
    throw new Error(`${event?.kind ?? "event"} ${fieldName} must be a string`);
  }
  return value;
}

function optionalDoneNonNegativeInteger(doneEvent, fieldName) {
  const value = doneEvent?.[fieldName];
  if (value === undefined) return 0;
  if (!Number.isInteger(value) || value < 0) {
    throw new Error(`done ${fieldName} must be a non-negative integer`);
  }
  return value;
}

function optionalDoneFiniteNonNegativeNumber(doneEvent, fieldName) {
  const value = doneEvent?.[fieldName];
  if (value === undefined) return 0;
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    throw new Error(`done ${fieldName} must be a finite non-negative number`);
  }
  return value;
}

function contentText(content) {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content
    .filter((block) => block && block.type === "text" && typeof block.text === "string")
    .map((block) => block.text)
    .join("");
}

function jsonString(value) {
  return JSON.stringify(value ?? {});
}

function toolCallArguments(block) {
  const value = block?.arguments;
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return value;
}

function hostToolCallsFromPiContent(content) {
  if (!Array.isArray(content)) return [];
  const toolCalls = [];
  for (const block of content) {
    if (!block || block.type !== "toolCall") continue;
    const id = stringValue(block.id, "assistant toolCall id");
    const name = stringValue(block.name, "assistant toolCall name");
    toolCalls.push({
      id,
      type: "function",
      function: {
        name,
        arguments: jsonString(toolCallArguments(block)),
      },
    });
  }
  return toolCalls;
}

function hostToolResultContentFromPi(content) {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    const text = contentText(content);
    return text || jsonString(content);
  }
  if (content === null || content === undefined) return "";
  if (typeof content === "object") return jsonString(content);
  return String(content);
}

function hostAssistantMessageFromPi(message) {
  const hostMessage = { role: "assistant", content: contentText(message.content) };
  const toolCalls = hostToolCallsFromPiContent(message.content);
  if (toolCalls.length > 0) hostMessage.tool_calls = toolCalls;
  return hostMessage;
}

function hostToolResultMessageFromPi(message) {
  const toolCallId = stringValue(
    message.toolCallId ?? message.tool_call_id ?? message.id,
    "toolResult toolCallId",
  );
  return {
    role: "user",
    content: [
      {
        type: "tool_result",
        tool_use_id: toolCallId,
        content: hostToolResultContentFromPi(message.content),
        is_error: Boolean(message.isError ?? message.is_error),
      },
    ],
  };
}

function hostMessagesFromPi(messages) {
  if (!Array.isArray(messages)) return [];
  const hostMessages = [];
  for (const message of messages) {
    if (!message || typeof message !== "object") continue;
    if (message.role === "user") {
      hostMessages.push({ role: "user", content: contentText(message.content) });
    } else if (message.role === "assistant") {
      hostMessages.push(hostAssistantMessageFromPi(message));
    } else if (message.role === "toolResult") {
      hostMessages.push(hostToolResultMessageFromPi(message));
    }
  }
  return hostMessages;
}

function piMessagesFromHost(messages) {
  if (!Array.isArray(messages)) return [];
  return messages
    .filter(
      (message) =>
        message &&
        typeof message === "object" &&
        (message.role === "user" || message.role === "assistant"),
    )
    .map((message) => ({
      role: message.role,
      content: [{ type: "text", text: contentText(message.content) }],
      timestamp: Date.now(),
    }));
}

function normalizeToolParameters(tool) {
  if (tool && typeof tool.input_schema === "object" && tool.input_schema) return tool.input_schema;
  if (tool && typeof tool.parameters === "object" && tool.parameters) return tool.parameters;
  return { type: "object", properties: {}, additionalProperties: true };
}

function yieldPayloadFromParams(params) {
  if (params && Object.prototype.hasOwnProperty.call(params, "reason")) {
    return { reason: params.reason };
  }
  if (params && Object.prototype.hasOwnProperty.call(params, "message")) {
    return { message: params.message };
  }
  return {};
}

function toolResultText(
  events,
  toolCallId,
  toolName,
  { intentType = "tool.call.execute", requireResult = true } = {},
) {
  if (!Array.isArray(events)) {
    throw new Error(`${intentType} events must be a JSON array`);
  }
  let terminalSeen = false;
  for (const event of events) {
    if (!event || typeof event !== "object" || Array.isArray(event)) {
      throw new Error(`${intentType} events entries must be JSON objects`);
    }
    if (typeof event.kind !== "string") {
      throw new Error(`${intentType} events entries must include string kind`);
    }
    if (event.kind.trim() === "") {
      throw new Error(`${intentType} events entries kind must be non-empty`);
    }
    if (!SUPPORTED_INTENT_RESULT_EVENT_KINDS.has(event.kind)) {
      throw new Error(`Unsupported Pi sidecar intent_result event kind '${event.kind}'`);
    }
    if (event.kind === "done" || event.kind === "error") {
      if (terminalSeen) {
        throw new Error("intent_result events returned multiple terminal events");
      }
      terminalSeen = true;
    } else if (terminalSeen) {
      throw new Error("intent_result events returned events after terminal event");
    }
  }
  const result = events.find(
    (event) =>
      event &&
      event.kind === "tool_result" &&
      (event.tool_use_id === toolCallId || event.tool_call_id === toolCallId) &&
      event.tool_name === toolName,
  );
  if (!result) {
    if (requireResult) throw new Error(`${intentType} must return matching tool_result`);
    return { text: "", isError: false };
  }
  return {
    text: typeof result.result === "string" ? result.result : JSON.stringify(result.result ?? ""),
    isError: result.is_error === true,
    details: result,
  };
}

function usageFromDone(doneEvent) {
  const hostInputTokens = optionalDoneNonNegativeInteger(doneEvent, "input_tokens");
  const outputTokens = optionalDoneNonNegativeInteger(doneEvent, "output_tokens");
  const reasoningTokens = optionalDoneNonNegativeInteger(doneEvent, "reasoning_tokens");
  const cacheReadTokens = optionalDoneNonNegativeInteger(doneEvent, "cached_tokens");
  const cacheWriteTokens = optionalDoneNonNegativeInteger(doneEvent, "cache_write_tokens");
  if (cacheReadTokens > hostInputTokens) {
    throw new Error("done cached_tokens must be <= input_tokens");
  }
  if (cacheWriteTokens > hostInputTokens) {
    throw new Error("done cache_write_tokens must be <= input_tokens");
  }
  const billedCost = optionalDoneFiniteNonNegativeNumber(doneEvent, "billed_cost");
  const inputTokens = Math.max(0, hostInputTokens - cacheReadTokens);
  return {
    input: inputTokens,
    output: outputTokens,
    cacheRead: cacheReadTokens,
    cacheWrite: cacheWriteTokens,
    totalTokens:
      inputTokens + outputTokens + cacheReadTokens + cacheWriteTokens + reasoningTokens,
    cost: {
      input: 0,
      output: 0,
      cacheRead: 0,
      cacheWrite: 0,
      total: billedCost,
    },
  };
}

function emptyUsage() {
  return usageFromDone(undefined);
}

function assistantMessageFromContent(model, content, usage, stopReason = "stop", errorMessage = undefined) {
  return {
    role: "assistant",
    content,
    api: typeof model?.api === "string" ? model.api : "opensquilla-agent-core",
    provider: typeof model?.provider === "string" ? model.provider : "opensquilla",
    model: typeof model?.id === "string" ? model.id : "opensquilla",
    usage,
    stopReason,
    errorMessage,
    timestamp: Date.now(),
  };
}

function assistantMessage(model, text, usage, stopReason = "stop", errorMessage = undefined) {
  return assistantMessageFromContent(
    model,
    text ? [{ type: "text", text }] : [],
    usage,
    stopReason,
    errorMessage,
  );
}

function pushAssistantResult(stream, model, events) {
  const content = [];
  let textIndex = -1;
  let doneEvent;
  let errorEvent;
  const toolStarts = new Map();
  const toolFragments = new Map();
  const start = assistantMessageFromContent(model, [], emptyUsage());
  stream.push({ type: "start", partial: start });
  const supportedProviderEventKinds = new Set([
    "text_delta",
    "tool_use_start",
    "tool_use_delta",
    "tool_use_end",
    "done",
    "error",
  ]);

  function partialMessage(usage = emptyUsage(), stopReason = "stop") {
    return assistantMessageFromContent(
      model,
      content.map((block) => ({ ...block })),
      usage,
      stopReason,
    );
  }

  function appendText(delta) {
    if (textIndex < 0) {
      textIndex = content.length;
      content.push({ type: "text", text: "" });
      stream.push({ type: "text_start", contentIndex: textIndex, partial: partialMessage() });
    }
    content[textIndex].text += delta;
    stream.push({ type: "text_delta", contentIndex: textIndex, delta, partial: partialMessage() });
  }

  if (!Array.isArray(events)) {
    throw new Error("provider.request events must be a JSON array");
  }

  let terminalSeen = false;
  for (const event of events) {
    if (!event || typeof event !== "object" || Array.isArray(event)) {
      throw new Error("provider.request events entries must be JSON objects");
    }
    if (typeof event.kind !== "string") {
      throw new Error("provider.request events entries must include string kind");
    }
    if (event.kind.trim() === "") {
      throw new Error("provider.request events entries kind must be non-empty");
    }
    if (!supportedProviderEventKinds.has(event.kind)) {
      throw new Error(`unsupported provider.request event kind ${String(event.kind)}`);
    }
    if (event.kind === "done" || event.kind === "error") {
      if (terminalSeen) {
        throw new Error("intent_result events returned multiple terminal events");
      }
      terminalSeen = true;
    } else if (terminalSeen) {
      throw new Error("intent_result events returned events after terminal event");
    }
    if (event.kind === "text_delta") {
      appendText(eventStringValue(event, "text"));
    }
    if (event.kind === "tool_use_start") {
      const toolCallId = stringValue(
        event.tool_use_id ?? event.tool_call_id,
        "tool_use_start tool_use_id",
      );
      const toolName = stringValue(event.tool_name, "tool_use_start tool_name");
      if (toolStarts.has(toolCallId)) {
        throw new Error("duplicate tool_use_start tool_use_id");
      }
      toolStarts.set(toolCallId, { name: toolName });
      toolFragments.set(toolCallId, []);
      stream.push({
        type: "toolcall_start",
        contentIndex: content.length,
        partial: partialMessage(),
      });
    }
    if (event.kind === "tool_use_delta") {
      const toolCallId = stringValue(
        event.tool_use_id ?? event.tool_call_id,
        "tool_use_delta tool_use_id",
      );
      const fragments = toolFragments.get(toolCallId);
      if (!fragments) {
        throw new Error("tool_use_delta requires matching tool_use_start");
      }
      fragments.push(stringValue(event.json_fragment, "tool_use_delta json_fragment"));
    }
    if (event.kind === "tool_use_end") {
      const toolCallId = stringValue(
        event.tool_use_id ?? event.tool_call_id,
        "tool_use_end tool_use_id",
      );
      const startEvent = toolStarts.get(toolCallId);
      const fragments = toolFragments.get(toolCallId);
      if (!startEvent || !fragments) {
        throw new Error("tool_use_end requires matching tool_use_start");
      }
      const toolName = stringValue(
        event.tool_name ?? startEvent?.name,
        "tool_use_end tool_name",
      );
      if (toolName !== startEvent.name) {
        throw new Error("tool_use_end tool_name must match start tool_name");
      }
      let args =
        "arguments" in event ? jsonObject(event.arguments, "tool_use_end arguments") : {};
      if (fragments.length > 0 && Object.keys(args).length === 0) {
        try {
          args = JSON.parse(fragments.join(""));
        } catch {
          throw new Error("provider.request provider tool-use arguments must decode to an object");
        }
        if (!args || typeof args !== "object" || Array.isArray(args)) {
          throw new Error("provider.request provider tool-use arguments must decode to an object");
        }
      }
      toolStarts.delete(toolCallId);
      toolFragments.delete(toolCallId);
      const toolCall = {
        type: "toolCall",
        id: toolCallId,
        name: toolName,
        arguments: args,
      };
      content.push(toolCall);
      stream.push({
        type: "toolcall_end",
        contentIndex: content.length - 1,
        toolCall,
        partial: partialMessage(),
      });
    }
    if (event.kind === "done") {
      if ("text" in event) eventStringValue(event, "text");
      doneEvent = event;
    }
    if (event.kind === "error") {
      eventStringValue(event, "message");
      errorEvent = event;
    }
  }
  if (toolStarts.size > 0) {
    const pending = Array.from(toolStarts.keys()).sort().join(", ");
    throw new Error(`provider.request ended with pending provider tool-use streams: ${pending}`);
  }
  if (errorEvent) {
    const errorMessage = eventStringValue(errorEvent, "message");
    stream.push({
      type: "error",
      reason: "error",
      error: assistantMessage(
        model,
        "",
        emptyUsage(),
        "error",
        errorMessage,
      ),
    });
    return;
  }
  const finalText = typeof doneEvent?.text === "string" && doneEvent.text ? doneEvent.text : "";
  if (finalText && (textIndex < 0 || content[textIndex]?.text !== finalText)) {
    appendText(finalText);
  }
  if (textIndex >= 0) {
    stream.push({
      type: "text_end",
      contentIndex: textIndex,
      content: content[textIndex].text,
      partial: partialMessage(),
    });
  }
  const stopReason = content.some((block) => block.type === "toolCall") ? "toolUse" : "stop";
  stream.push({
    type: "done",
    reason: stopReason,
    message: partialMessage(usageFromDone(doneEvent), stopReason),
  });
}

class JsonlBridge {
  constructor() {
    this.pending = [];
    this.readline = createInterface({ input: stdin, crlfDelay: Infinity });
    this.iterator = this.readline[Symbol.asyncIterator]();
  }

  async readTurnStart() {
    const item = await this.iterator.next();
    if (item.done) throw new Error("missing turn_start frame");
    const frame = jsonObject(JSON.parse(item.value), "turn_start frame");
    if (frame.protocol !== PROTOCOL) throw new Error("turn_start protocol mismatch");
    if (frame.kind !== "turn_start") throw new Error("first frame must be turn_start");
    const payload = jsonObject(frame.payload, "turn_start payload");
    return {
      prompt: stringValue(payload.prompt, "turn_start prompt"),
      kwargs: jsonObject(payload.kwargs ?? {}, "turn_start kwargs"),
    };
  }

  startFeedbackReader(expectedSessionKey) {
    this.feedbackReader = (async () => {
      for await (const line of this.readline) {
        if (!line.trim()) continue;
        const frame = jsonObject(JSON.parse(line), "intent_result frame");
        if (frame.protocol !== PROTOCOL) throw new Error("intent_result protocol mismatch");
        if (frame.kind !== "intent_result") throw new Error("expected intent_result frame");
        frame.type = intentResultType(frame.type);
        frame.session_key = intentResultSessionKey(frame.session_key, expectedSessionKey);
        jsonObject(frame.payload, "intent_result payload");
        const index = this.pending.findIndex((pending) => pending.matches(frame));
        if (index < 0) {
          stderr.write(`unmatched intent_result frame for ${String(frame.type)}\n`);
          continue;
        }
        const [pending] = this.pending.splice(index, 1);
        pending.resolve(frame);
      }
      for (const pending of this.pending.splice(0)) {
        if (pending.resolveOnClose) {
          pending.resolve({
            kind: "intent_result",
            type: pending.type,
            payload: pending.payload,
            events: [],
          });
        } else {
          pending.reject(new Error("stdin closed before intent_result"));
        }
      }
    })().catch((error) => {
      for (const pending of this.pending.splice(0)) pending.reject(error);
    });
  }

  sendIntent(type, payload, matches = () => true, options = {}) {
    const response = new Promise((resolve, reject) => {
      this.pending.push({
        type,
        payload,
        resolve,
        reject,
        resolveOnClose: options.resolveOnClose === true,
        matches: (frame) => frame.type === type && matches(frame),
      });
    });
    writeFrame({ kind: "intent", type, payload });
    return response;
  }

  close() {
    this.readline.close();
  }
}

function buildPiTools(toolDefinitions, bridge, sessionKey) {
  if (!Array.isArray(toolDefinitions)) return [];
  const pendingToolExecutions = new Set();

  async function waitForPendingToolExecutions() {
    await Promise.resolve();
    while (pendingToolExecutions.size > 0) {
      await Promise.allSettled([...pendingToolExecutions]);
    }
  }

  return toolDefinitions
    .filter((tool) => tool && typeof tool === "object" && typeof tool.name === "string")
    .map((tool) => ({
      name: tool.name,
      label: typeof tool.name === "string" ? tool.name : "OpenSquilla tool",
      description: typeof tool.description === "string" ? tool.description : "",
      parameters: normalizeToolParameters(tool),
      execute: async (toolCallId, params) => {
        if (tool.name === "sessions_yield") {
          await waitForPendingToolExecutions();
          const payload = {
            session_key: sessionKey,
            tool_call_id: toolCallId,
            ...yieldPayloadFromParams(params),
          };
          const feedback = await bridge.sendIntent(
            "yield.request",
            payload,
            (frame) => frame.payload?.tool_call_id === toolCallId || frame.payload?.toolCallId === toolCallId,
            { resolveOnClose: true },
          );
          const result = toolResultText(feedback.events, toolCallId, tool.name, {
            intentType: "yield.request",
            requireResult: false,
          });
          if (result.isError) throw new Error(result.text || `${tool.name} failed`);
          return { content: [{ type: "text", text: result.text }], details: result.details ?? {} };
        }

        const payload = {
          session_key: sessionKey,
          tool_call_id: toolCallId,
          tool_name: tool.name,
          arguments: params && typeof params === "object" ? params : {},
        };
        const execution = (async () => {
          await bridge.sendIntent(
            "tool.call.prepare",
            payload,
            (frame) => frame.payload?.tool_call_id === toolCallId || frame.payload?.toolCallId === toolCallId,
          );
          const feedback = await bridge.sendIntent(
            "tool.call.execute",
            payload,
            (frame) => frame.payload?.tool_call_id === toolCallId || frame.payload?.toolCallId === toolCallId,
          );
          const result = toolResultText(feedback.events, toolCallId, tool.name, {
            intentType: "tool.call.execute",
            requireResult: true,
          });
          if (result.isError) throw new Error(result.text || `${tool.name} failed`);
          return { content: [{ type: "text", text: result.text }], details: result.details ?? {} };
        })();
        pendingToolExecutions.add(execution);
        try {
          return await execution;
        } finally {
          pendingToolExecutions.delete(execution);
        }
      },
    }));
}

function providerStreamFn(bridge, StreamCtor, sessionKey) {
  return (model, context, options) => {
    const stream = new StreamCtor();
    (async () => {
      const messages = hostMessagesFromPi(context?.messages);
      const payload = {
        session_key: sessionKey,
        messages,
        prompt: messages.length > 0 ? undefined : "",
        tools: Array.isArray(context?.tools) ? context.tools : [],
        config: {
          model_id: typeof model?.id === "string" ? model.id : undefined,
          thinking_level: options?.reasoning,
        },
      };
      const feedback = await bridge.sendIntent("provider.request", payload);
      pushAssistantResult(stream, model, feedback.events);
    })().catch((error) => {
      const message = assistantMessage(undefined, "", emptyUsage(), "error", String(error.message || error));
      stream.push({ type: "error", reason: "error", error: message });
    });
    return stream;
  };
}

function modelFromSnapshot(snapshot) {
  const modelId = typeof snapshot?.model_id === "string" && snapshot.model_id ? snapshot.model_id : "opensquilla";
  return {
    id: modelId,
    name: modelId,
    api: "opensquilla-agent-core",
    provider: "opensquilla",
    baseUrl: "",
    reasoning: false,
    input: [],
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    contextWindow: 0,
    maxTokens: 0,
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const runtime = await importBridgeModule(args.runtimePackage, args.moduleRoot);
  const ai = await importBridgeModule(args.aiPackage, args.moduleRoot);
  const Agent = runtime.Agent;
  const StreamCtor = ai.AssistantMessageEventStream;
  if (typeof Agent !== "function") throw new Error(`${args.runtimePackage} does not export Agent`);
  if (typeof StreamCtor !== "function") {
    throw new Error(`${args.aiPackage} does not export AssistantMessageEventStream`);
  }

  const bridge = new JsonlBridge();
  const turnStart = await bridge.readTurnStart();

  const snapshot = jsonObject(turnStart.kwargs.turn_snapshot ?? {}, "turn_snapshot");
  const sessionKey = stringValue(
    turnStart.kwargs.session_key ?? snapshot.session_key,
    "turn_start session_key",
  );
  bridge.startFeedbackReader(sessionKey);
  const systemPrompt = typeof snapshot.system_prompt === "string" ? snapshot.system_prompt : "";
  const history = piMessagesFromHost(turnStart.kwargs.history);
  const tools = buildPiTools(snapshot.tool_definitions, bridge, sessionKey);
  const agent = new Agent({
    initialState: {
      systemPrompt,
      messages: history,
      tools,
      model: modelFromSnapshot(snapshot),
      thinkingLevel: typeof snapshot.metadata?.thinking_level === "string" ? snapshot.metadata.thinking_level : "off",
    },
    sessionId: typeof turnStart.kwargs.session_id === "string" ? turnStart.kwargs.session_id : sessionKey,
    streamFn: providerStreamFn(bridge, StreamCtor, sessionKey),
  });

  agent.subscribe((event) => {
    const assistantEvent = event?.assistantMessageEvent;
    if (assistantEvent?.type === "text_delta" && typeof assistantEvent.delta === "string") {
      writeFrame({
        kind: "event",
        type: "text.delta",
        payload: { text: assistantEvent.delta },
      });
    }
  });

  try {
    await agent.prompt(turnStart.prompt);
    await agent.waitForIdle();
  } finally {
    bridge.close();
  }
}

main().catch((error) => {
  writeProtocolError(error?.message || error);
  process.exitCode = 1;
});
