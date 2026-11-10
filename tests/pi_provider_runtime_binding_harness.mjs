import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = path.join(root, "Pi", "jack-kernel.ts");
const tempHome = fs.mkdtempSync(path.join(os.tmpdir(), "jack-pi-provider-binding-"));
const cfgDir = path.join(tempHome, ".pi", "agent");
const runtimeRegistry = path.join(tempHome, "runtimes");
fs.mkdirSync(cfgDir, { recursive: true });
fs.mkdirSync(runtimeRegistry, { recursive: true });

process.env.HOME = tempHome;
process.env.USERPROFILE = tempHome;
process.env.JACK_PI_JACK_RUNTIME_REGISTRY_DIR = runtimeRegistry;
process.env.JACK_PI_JACK_RUNTIME_ID = "runtime-agentic-01";
delete process.env.JACK_PI_JACK_URL;
delete process.env.JACK_PI_JACK_TOKEN;

fs.writeFileSync(
  path.join(cfgDir, "jack-kernel.json"),
  JSON.stringify({ url: "http://127.0.0.1:65530" }),
  "utf8"
);

let healthRuntimeId = "runtime-agentic-01";
let activeThinking = true;
let activeMode = "agentic";
let activeEffort = "xhigh";
let mockLoadedContext = 16384;
let mockMaxContext = 32768;
let validCommitDigests = [];
let mockStage2Thinking = false;
const server = http.createServer((req, res) => {
  res.setHeader("Content-Type", "application/json");
  if (req.url === "/health") {
    res.end(JSON.stringify({
      runtime_id: healthRuntimeId,
      lane_id: "lane-agentic-01",
      reasoning_level: activeMode === "agentic" ? "Agentic" : activeMode,
      runtime_identity: {
        mode: activeMode,
        flow: ["extended_initial"],
        stage_controls: { extended_initial: { thinking: activeThinking, reasoning_effort: activeEffort } },
      },
    }));
    return;
  }
  if (req.url === "/jack/runtime/status") {
    res.end(JSON.stringify({runtime_id: healthRuntimeId, completed_agentic_digests: validCommitDigests, agentic_stage2_native_thinking: mockStage2Thinking}));
    return;
  }
  if (req.url === "/api/v1/models") {
    res.end(JSON.stringify({
      models: [{
        key: "test-model",
        display_name: "Test Model",
        max_context_length: mockMaxContext,
        loaded_instances: [{ config: { context_length: mockLoadedContext } }],
      }],
    }));
    return;
  }
  res.statusCode = 404;
  res.end(JSON.stringify({ error: "not found" }));
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const actualPort = server.address().port;

fs.writeFileSync(
  path.join(runtimeRegistry, "runtime-agentic-01.json"),
  JSON.stringify({
    runtime_id: "runtime-agentic-01",
    status: "stale",
    endpoint: {
      actual_host: "127.0.0.1",
      actual_port: actualPort,
    },
  }),
  "utf8"
);

const modulePath = path.join(tempHome, "jack-kernel.mjs");
fs.copyFileSync(source, modulePath);

const handlers = new Map();
const registrations = [];
const pi = {
  registerProvider(name, provider) {
    registrations.push({ name, provider });
  },
  on(name, fn) {
    if (!handlers.has(name)) handlers.set(name, []);
    handlers.get(name).push(fn);
  },
};

const { default: installProvider } = await import(pathToFileURL(modulePath).href + `?v=${Date.now()}`);
await installProvider(pi);

assert.equal(registrations.length, 1);
assert.equal(registrations[0].name, "jack-kernel");
assert.equal(
  registrations[0].provider.baseUrl,
  `http://127.0.0.1:${actualPort}/v1/`
);
assert.equal(registrations[0].provider.models[0].contextWindow, 16384);
assert.equal(registrations[0].provider.models[0].maxTokens, 16384,
  "Output allowance must not inherit the theoretical 32768-token context maximum");
assert.equal(registrations[0].provider.models[0].reasoning, true,
  "Agentic must advertise native thinking to stock Pi");
assert.equal(registrations[0].provider.models[0].thinkingLevelMap.xhigh, "xhigh",
  "Agentic xhigh must appear in the stock Pi thinking selector");
assert.equal(registrations[0].provider.models[0].thinkingLevelMap.max, undefined,
  "Do not advertise a distinct max stage effort Jack does not support");
assert.equal(registrations[0].provider.models[0].compat.supportsDeveloperRole, false);
assert.equal(registrations[0].provider.models[0].compat.supportsReasoningEffort, false);

// Provider refresh follows host-owned stage capability, not display label.
activeThinking = false;
activeMode = "off";
for (const fn of handlers.get("before_agent_start") || []) await fn({});
assert.equal(registrations.at(-1).provider.models[0].reasoning, false,
  "Off must not advertise thinking");
assert.equal(registrations.at(-1).provider.models[0].thinkingLevelMap.xhigh, undefined);

activeThinking = true;
activeMode = "x-high";
for (const fn of handlers.get("before_agent_start") || []) await fn({});
assert.equal(registrations.at(-1).provider.models[0].reasoning, true,
  "Native X-High must advertise thinking");
assert.equal(registrations.at(-1).provider.models[0].thinkingLevelMap.xhigh, "xhigh");

activeMode = "medium";
activeEffort = "medium";
for (const fn of handlers.get("before_agent_start") || []) await fn({});
assert.equal(registrations.at(-1).provider.models[0].reasoning, true);
assert.equal(registrations.at(-1).provider.models[0].thinkingLevelMap.xhigh, undefined,
  "Medium mode must not claim to support a host xhigh stage");

// The matching model may not be registered if the runtime identity changes.

healthRuntimeId = "wrong-runtime";
for (const fn of handlers.get("before_agent_start") || []) {
  await fn({});
}
assert.equal(
  registrations.length,
  4,
  "provider must not re-register when the resolved endpoint reports the wrong runtime identity"
);

// Context-size boundary tests. Restore the matching runtime after the
// intentionally rejected runtime-identity test above.
healthRuntimeId = "runtime-agentic-01";
activeThinking = true;
activeMode = "agentic";
activeEffort = "xhigh";

for (const scenario of [
  { loaded: 4096, theoretical: 32768, context: 4096, output: 4096 },
  { loaded: 8192, theoretical: 32768, context: 8192, output: 8192 },
  { loaded: 65536, theoretical: 131072, context: 65536, output: 16384 },
  { loaded: 0, theoretical: 32768, context: 32768, output: 16384 },
  { loaded: 0, theoretical: 4096, context: 4096, output: 4096 },
]) {
  mockLoadedContext = scenario.loaded;
  mockMaxContext = scenario.theoretical;

  const previousCount = registrations.length;
  for (const fn of handlers.get("before_agent_start") || []) {
    await fn({});
  }

  assert.equal(registrations.length, previousCount + 1,
    "Expected provider registration for valid context metadata");

  const model = registrations.at(-1).provider.models[0];

  assert.equal(model.contextWindow, scenario.context);
  assert.equal(model.maxTokens, scenario.output);
  assert.ok(model.maxTokens <= model.contextWindow);
}

// Pi should prune only authenticated, successfully committed Agentic tool
// exchanges after the turn is complete, never user or final answer entries.
const committedResponse = "Verified working memory\\n\\nFrozen answer";
validCommitDigests = [crypto.createHash("sha256").update(committedResponse).digest("hex")];
const finalMessage = {
  role: "assistant", stopReason: "stop", content: [
    {type: "thinking", thinking: "Transient native Stage 1 draft"},
    {type: "text", text: committedResponse},
  ],
};
const branch = [
  {type: "message", id: "before-user", message: {role: "assistant", content: [{type: "text", text: "older"}]}},
  {type: "message", id: "user-current", message: {role: "user", content: "Do work"}},
  {type: "message", id: "tool-assistant", message: {role: "assistant", content: [{type: "toolCall", id: "call", name: "bash", arguments: {command: "ls"}}]}},
  {type: "message", id: "tool-result", message: {role: "toolResult", toolCallId: "call", content: [{type: "text", text: "files"}]}},
  {type: "message", id: "final-response", message: finalMessage},
];
const context = {
  model: {provider: "jack-kernel"},
  sessionManager: {getBranch: () => branch},
};
const event = {
  outcome: "completed",
  toolResults: [],
  message: finalMessage,
  messageEntryId: "final-response",
  entries: [{type: "custom", customType: "existing", data: 1}],
};
const results = await Promise.all((handlers.get("turn_end") || []).map(fn => fn(event, context)));
assert.equal(results.length, 1);
assert.deepEqual(results[0]?.entries.map(x => x.type), ["custom", "context_edit", "context_edit", "context_edit"]);
assert.deepEqual(results[0].entries.slice(1).map(x => x.targetId), ["tool-assistant", "tool-result", "final-response"]);
assert.equal(results[0].entries.at(-1).replacement, committedResponse,
  "Thinking-OFF memory stage must remove obsolete native reasoning from Pi's next context");
mockStage2Thinking = true;
const thinkingOn = await handlers.get("turn_end")[0](event, context);
assert.deepEqual(thinkingOn.entries.slice(1).map(x => x.targetId), ["tool-assistant", "tool-result"],
  "Thinking-ON Stage 2 bridge must remain intact");
mockStage2Thinking = false;
assert.equal(results[0]?.continue, undefined, "Context synchronization must not cause an inference");
assert.equal((await handlers.get("turn_end")[0]({...event, outcome: "failed"}, context)), undefined);
validCommitDigests = [];
assert.equal((await handlers.get("turn_end")[0](event, context)), undefined,
  "No digest receipt must preserve all caller context");
validCommitDigests = [crypto.createHash("sha256").update(committedResponse).digest("hex")];
assert.equal((await handlers.get("turn_end")[0]({...event, toolResults: [{}]}, context)), undefined,
  "Tool-suspension boundary must not compact caller protocol");
const noEdits = {
  ...context, sessionManager: {getBranch: () => [
    ...branch.slice(0, 2),
    {type: "context_edit", targetId: "tool-assistant", replacement: null},
    {type: "context_edit", targetId: "tool-result", replacement: null},
    {type: "context_edit", targetId: "final-response", replacement: committedResponse},
    ...branch.slice(2),
  ]},
};
assert.equal((await handlers.get("turn_end")[0](event, noEdits)), undefined,
  "Previously omitted tool protocol must not produce duplicate edits");
console.log("Pi committed Agentic context synchronization: PASS");

// Missing both context measurements must fail closed.
mockLoadedContext = 0;
mockMaxContext = 0;
const previousCount = registrations.length;

for (const fn of handlers.get("before_agent_start") || []) {
  await fn({});
}

assert.equal(registrations.length, previousCount,
  "Missing context metadata must not register an invalid model");

console.log("Pi context boundary tests: PASS");
await new Promise((resolve) => server.close(resolve));
console.log("Pi provider runtime binding harness: PASS");
