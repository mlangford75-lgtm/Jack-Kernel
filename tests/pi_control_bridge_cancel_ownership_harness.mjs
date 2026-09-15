import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const bridgeTs = path.join(root, "Pi", "pi-control-bridge.ts");
const tempHome = fs.mkdtempSync(path.join(os.tmpdir(), "jack-pi-cancel-owner-"));
const port = 20000 + (process.pid % 1000);
const token = "cancel-ownership-test-token";
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
let controlledAbortCount = 0;

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
  abort: () => { controlledAbortCount += 1; },
  newSession: async () => {},
};

const pi = {
  on,
  registerCommand: () => {},
  sendUserMessage: (content, options) => sent.push({ content, options }),
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
  // Scenario 1: an unrelated Pi run is active. A controlled task is accepted as
  // queued but remains bridge-owned and is never injected into Pi. Cancelling it
  // must not abort the unrelated active Pi context, and the cancelled prompt must
  // remain undispatched even after the unrelated run settles.
  idle = false;
  await emit("agent_start", {}, unrelatedContext);

  const queuedSubmit = await fetch(`http://127.0.0.1:${port}/v1/tasks`, {
    method: "POST",
    headers,
    body: JSON.stringify({ prompt: "cancel while unrelated run is active" }),
  });
  assert.equal(queuedSubmit.status, 202);
  const queuedTask = await queuedSubmit.json();
  assert.equal(queuedTask.status, "queued");
  assert.equal(queuedTask.runOpen, false);
  assert.equal(sent.length, 0, "bridge-owned queued task must not be injected into Pi while unrelated work is active");

  const queuedCancel = await fetch(`http://127.0.0.1:${port}/v1/tasks/cancel`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  assert.equal(queuedCancel.status, 202);
  const queuedCancelled = await queuedCancel.json();
  assert.equal(queuedCancelled.status, "cancelled");
  assert.equal(queuedCancelled.runOpen, false);
  assert.equal(
    unrelatedAbortCount,
    0,
    "queued controlled cancellation must not abort an unrelated active Pi context",
  );
  assert.equal(sent.length, 0, "cancelled bridge-owned queued task must not be dispatched");

  await emit("agent_end", { messages: [] }, unrelatedContext);
  idle = true;
  await emit("agent_settled", {}, idleContext);
  await new Promise((resolve) => setTimeout(resolve, 10));

  assert.equal(unrelatedAbortCount, 0);
  assert.equal(sent.length, 0, "cancelled queued task must remain undispatched after unrelated settlement");

  // Scenario 2: a positively-bound controlled run is active. With Pi idle, the
  // controlled task is dispatched immediately, positively bound at agent_start,
  // and cancelling it must abort that exact controlled context once while
  // retaining run-open semantics until physical settlement.
  const runningSubmit = await fetch(`http://127.0.0.1:${port}/v1/tasks`, {
    method: "POST",
    headers,
    body: JSON.stringify({ prompt: "cancel the bound controlled run" }),
  });
  assert.equal(runningSubmit.status, 202);
  assert.equal(sent.length, 1);

  const transformed = await emit("input", {
    text: sent[0].content,
    source: "extension",
    streamingBehavior: "followUp",
  }, controlledContext);
  assert.equal(transformed?.action, "transform");

  idle = false;
  await emit("before_agent_start", { prompt: transformed.text }, controlledContext);
  await emit("agent_start", {}, controlledContext);

  const runningCancel = await fetch(`http://127.0.0.1:${port}/v1/tasks/cancel`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  assert.equal(runningCancel.status, 202);
  const runningCancelled = await runningCancel.json();
  assert.equal(runningCancelled.status, "cancelled");
  assert.equal(runningCancelled.runOpen, true);
  assert.equal(controlledAbortCount, 1, "controlled running cancellation must abort its bound context exactly once");
  assert.equal(unrelatedAbortCount, 0);

  // While the cancelled run is still physically open, admission must remain
  // closed. This deterministic check avoids the live-test race where Pi may
  // settle between the cancellation response and a subsequent HTTP request.
  const overlapSubmit = await fetch(`http://127.0.0.1:${port}/v1/tasks`, {
    method: "POST",
    headers,
    body: JSON.stringify({ prompt: "must remain blocked before settlement" }),
  });
  assert.equal(
    overlapSubmit.status,
    409,
    "new controlled work must be rejected while cancelled runOpen is still true",
  );

  await emit("agent_end", { messages: [] }, controlledContext);
  idle = true;
  await emit("agent_settled", {}, idleContext);

  const finalStatusResponse = await fetch(`http://127.0.0.1:${port}/v1/status`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const finalStatus = await finalStatusResponse.json();
  assert.equal(finalStatus.status, "cancelled");
  assert.equal(finalStatus.runOpen, false);
  assert.ok(finalStatus.settledAt);

  console.log("PI CONTROL BRIDGE CANCEL OWNERSHIP: PASS");
} finally {
  await emit("session_shutdown", { reason: "test-complete" }, idleContext);
}
