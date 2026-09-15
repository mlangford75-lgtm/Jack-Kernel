import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const bridgeTs = path.join(root, "Pi", "pi-control-bridge.ts");
const tempHome = fs.mkdtempSync(path.join(os.tmpdir(), "jack-pi-deferred-dispatch-"));
const port = 21000 + (process.pid % 1000);
const token = "deferred-dispatch-test-token";
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
let unrelatedAbortCount = 0;

function on(name, fn) {
  if (!handlers.has(name)) handlers.set(name, []);
  handlers.get(name).push(fn);
}

async function emit(name, event = {}, ctx) {
  let result;
  for (const fn of handlers.get(name) || []) {
    const next = await fn(event, ctx);
    if (next !== undefined) result = next;
  }
  return result;
}

const idleContext = {
  isIdle: () => idle,
  abort: () => {},
  newSession: async () => {},
};

const unrelatedContext = {
  isIdle: () => false,
  abort: () => { unrelatedAbortCount += 1; },
  newSession: async () => {},
};

const controlledContext = {
  isIdle: () => false,
  abort: () => {},
  newSession: async () => {},
};

const pi = {
  on,
  registerCommand: () => {},
  sendUserMessage: (content, options) => {
    sent.push({ content, options });
  },
};

const { default: installBridge } = await import(
  pathToFileURL(bridgeMjs).href + `?v=${Date.now()}`
);
await installBridge(pi);
await emit("session_start", { reason: "startup" }, idleContext);

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
  // Live Pi 0.85.1 showed that input preflight for a follow-up can occur while an
  // unrelated run is still active, before the supervisor has time to cancel the
  // queued controlled task. Once that input is accepted into Pi's queue, a later
  // bridge cancellation cannot truthfully claim the prompt was swallowed.
  //
  // Therefore the bridge must own the queue while unrelated Pi work is active:
  // accept the controlled task as queued, but do not inject its private wire
  // prompt into Pi until Pi has physically settled and the task is still queued.
  idle = false;
  await emit("agent_start", {}, unrelatedContext);

  const cancelledSubmit = await fetch(`http://127.0.0.1:${port}/v1/tasks`, {
    method: "POST",
    headers,
    body: JSON.stringify({ prompt: "cancel before deferred dispatch" }),
  });
  assert.equal(cancelledSubmit.status, 202);
  const cancelledQueued = await cancelledSubmit.json();
  assert.equal(cancelledQueued.status, "queued");
  assert.equal(cancelledQueued.runOpen, false);
  assert.equal(
    sent.length,
    0,
    "controlled wire prompt must not be injected into Pi while unrelated Pi work is active",
  );

  const queuedCancel = await fetch(`http://127.0.0.1:${port}/v1/tasks/cancel`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  assert.equal(queuedCancel.status, 202);
  const queuedCancelled = await queuedCancel.json();
  assert.equal(queuedCancelled.status, "cancelled");
  assert.equal(queuedCancelled.runOpen, false);
  assert.equal(unrelatedAbortCount, 0);
  assert.equal(sent.length, 0);

  await emit("agent_end", { messages: [] }, unrelatedContext);
  idle = true;
  await emit("agent_settled", {}, idleContext);
  await new Promise((resolve) => setTimeout(resolve, 10));

  assert.equal(
    sent.length,
    0,
    "cancelled bridge-owned queued task must never be injected into Pi after unrelated settlement",
  );

  // Preserve usefulness: a queued controlled task that is not cancelled should
  // remain accepted while unrelated work runs, then dispatch exactly once after
  // that unrelated work physically settles.
  idle = false;
  await emit("agent_start", {}, unrelatedContext);

  const deferredSubmit = await fetch(`http://127.0.0.1:${port}/v1/tasks`, {
    method: "POST",
    headers,
    body: JSON.stringify({ prompt: "dispatch after unrelated settlement" }),
  });
  assert.equal(deferredSubmit.status, 202);
  const deferredQueued = await deferredSubmit.json();
  assert.equal(deferredQueued.status, "queued");
  assert.equal(deferredQueued.runOpen, false);
  assert.equal(sent.length, 0);

  await emit("agent_end", { messages: [] }, unrelatedContext);
  idle = true;
  await emit("agent_settled", {}, idleContext);
  await new Promise((resolve) => setTimeout(resolve, 10));

  assert.equal(sent.length, 1, "queued controlled task must dispatch exactly once after unrelated settlement");
  assert.equal(sent[0].options?.deliverAs, "followUp");

  const transformed = await emit("input", {
    text: sent[0].content,
    source: "extension",
    streamingBehavior: "followUp",
  }, controlledContext);
  assert.equal(transformed?.action, "transform");
  assert.equal(transformed?.text, "dispatch after unrelated settlement");

  idle = false;
  await emit("before_agent_start", { prompt: transformed.text }, controlledContext);
  await emit("agent_start", {}, controlledContext);
  await emit("message_end", {
    message: { role: "assistant", content: "done", stopReason: "stop" },
  }, controlledContext);
  await emit("agent_end", { messages: [] }, controlledContext);
  idle = true;
  await emit("agent_settled", {}, idleContext);

  const finalResponse = await fetch(`http://127.0.0.1:${port}/v1/status`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const finalStatus = await finalResponse.json();
  assert.equal(finalStatus.status, "completed");
  assert.equal(finalStatus.runOpen, false);
  assert.ok(finalStatus.settledAt);

  console.log("PI CONTROL BRIDGE DEFERRED DISPATCH: PASS");
} finally {
  await emit("session_shutdown", { reason: "test-complete" }, idleContext);
}
