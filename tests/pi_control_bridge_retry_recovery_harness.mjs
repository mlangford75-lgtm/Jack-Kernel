import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const bridgeTs = path.join(root, "Pi", "pi-control-bridge.ts");
const tempHome = fs.mkdtempSync(path.join(os.tmpdir(), "jack-pi-retry-recovery-"));
const port = 19000 + (process.pid % 1000);
const token = "retry-recovery-test-token";
const cfgDir = path.join(tempHome, ".pi", "agent");
fs.mkdirSync(cfgDir, { recursive: true });
fs.writeFileSync(
  path.join(cfgDir, "jack-kernel.json"),
  JSON.stringify({ controlPort: port, controlToken: token }),
);
process.env.HOME = tempHome;
process.env.USERPROFILE = tempHome;

const bridgeMjs = path.join(tempHome, "pi-control-bridge.mjs");
fs.copyFileSync(bridgeTs, bridgeMjs);

const handlers = new Map();
const sent = [];
let idle = true;

function on(name, fn) {
  if (!handlers.has(name)) handlers.set(name, []);
  handlers.get(name).push(fn);
}

const context = {
  isIdle: () => idle,
  abort: () => {},
  newSession: async () => {},
};

async function emit(name, event = {}, ctx = context) {
  let result;
  for (const fn of handlers.get(name) || []) {
    const next = await fn(event, ctx);
    if (next !== undefined) result = next;
  }
  return result;
}

const pi = {
  on,
  registerCommand: () => {},
  sendUserMessage: (content, options) => sent.push({ content, options }),
};

const { default: installBridge } = await import(
  pathToFileURL(bridgeMjs).href + `?v=${Date.now()}`
);
await installBridge(pi);
await emit("session_start", { reason: "startup" });

const headers = {
  Authorization: `Bearer ${token}`,
  "Content-Type": "application/json",
};

async function waitForServer() {
  for (let i = 0; i < 100; i++) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/v1/status`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.status === 200) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
  throw new Error("bridge server did not start");
}

await waitForServer();

try {
  const prompt = "Retry recovery should finish completed.";
  const submit = await fetch(`http://127.0.0.1:${port}/v1/tasks`, {
    method: "POST",
    headers,
    body: JSON.stringify({ prompt }),
  });
  assert.equal(submit.status, 202);
  const queued = await submit.json();
  assert.equal(queued.status, "queued");
  assert.equal(sent.length, 1);

  const input = await emit("input", {
    text: sent[0].content,
    source: "extension",
    streamingBehavior: "followUp",
  });
  assert.equal(input.action, "transform");
  assert.equal(input.text, prompt);

  idle = false;
  await emit("before_agent_start", { prompt: input.text });
  await emit("agent_start", {});

  // Epoch 1 ends with a transient assistant transport failure. Pi is allowed to
  // retry the same controlled operation before agent_settled.
  await emit("message_end", {
    message: {
      role: "assistant",
      content: [],
      stopReason: "error",
      errorMessage: "Connection error.",
    },
  });
  await emit("agent_end", { messages: [], willRetry: true });

  // The automatic retry opens epoch 2 under the same immutable run id and
  // succeeds. The recovered final assistant outcome must supersede the transient
  // epoch-1 assistant error for terminal task disposition.
  await emit("agent_start", {});
  await emit("message_end", {
    message: {
      role: "assistant",
      content: "retry recovered",
      stopReason: "stop",
    },
  });
  await emit("agent_end", { messages: [], willRetry: false });

  idle = true;
  await emit("agent_settled", {});

  const statusResponse = await fetch(`http://127.0.0.1:${port}/v1/status`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  assert.equal(statusResponse.status, 200);
  const status = await statusResponse.json();

  assert.equal(status.status, "completed");
  assert.equal(status.runOpen, false);
  assert.equal(status.runEpoch, 2);
  assert.ok(status.settledAt);
  assert.equal(status.error, undefined);
  assert.equal(status.final?.content, "retry recovered");

  console.log("PI CONTROL BRIDGE RETRY RECOVERY: PASS");
} finally {
  await emit("session_shutdown", { reason: "test-complete" });
}
