import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const bridgeTs = path.join(root, "Pi", "pi-control-bridge.ts");
const tempHome = fs.mkdtempSync(path.join(os.tmpdir(), "jack-pi-v2-"));
const port = 18000 + (process.pid % 1000);
const token = "v2-test-token";
const cfgDir = path.join(tempHome, ".pi", "agent");
fs.mkdirSync(cfgDir, { recursive: true });
fs.writeFileSync(path.join(cfgDir, "jack-kernel.json"), JSON.stringify({ controlPort: port, controlToken: token }));
process.env.HOME = tempHome;
process.env.USERPROFILE = tempHome;

// Node does not load .ts directly in this harness; the bridge intentionally uses
// JavaScript-compatible TypeScript, so import an exact-byte .mjs copy.
const bridgeMjs = path.join(tempHome, "pi-control-bridge.mjs");
fs.copyFileSync(bridgeTs, bridgeMjs);

const handlers = new Map();
const sent = [];
let idle = true;
let aborted = false;

function on(name, fn) {
  if (!handlers.has(name)) handlers.set(name, []);
  handlers.get(name).push(fn);
}

async function emit(name, event = {}, ctx = context) {
  let result;
  for (const fn of handlers.get(name) || []) {
    const next = await fn(event, ctx);
    if (next !== undefined) result = next;
  }
  return result;
}

const context = {
  isIdle: () => idle,
  abort: () => { aborted = true; },
  newSession: async () => {},
};

const pi = {
  on,
  registerCommand: () => {},
  sendUserMessage: (content, options) => {
    sent.push({ content, options });
  },
};

const { default: installBridge } = await import(pathToFileURL(bridgeMjs).href + `?v=${Date.now()}`);
await installBridge(pi);
await emit("session_start", { reason: "startup" });

const headers = { Authorization: `Bearer ${token}` };

async function waitForServer() {
  for (let i = 0; i < 100; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/v1/status`, { headers });
      if (r.status === 200) return;
    } catch {}
    await new Promise((r) => setTimeout(r, 10));
  }
  throw new Error("bridge server did not start");
}

function createSseCollector(response) {
  const events = [];
  let buffer = "";
  let stopped = false;
  const decoder = new TextDecoder();
  const reader = response.body.getReader();
  const pump = (async () => {
    while (!stopped) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      while (buffer.includes("\n\n")) {
        const idx = buffer.indexOf("\n\n");
        const frame = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const type = frame.split("\n").find((l) => l.startsWith("event: "))?.slice(7) || "message";
        const dataLine = frame.split("\n").find((l) => l.startsWith("data: "));
        if (!dataLine) continue;
        events.push({ type, data: JSON.parse(dataLine.slice(6)) });
      }
    }
  })();
  return {
    events,
    stop: async () => {
      stopped = true;
      try { await reader.cancel(); } catch {}
      await pump.catch(() => {});
    },
  };
}

await waitForServer();
const sseResponse = await fetch(`http://127.0.0.1:${port}/v1/events`, { headers });
assert.equal(sseResponse.status, 200);
const collector = createSseCollector(sseResponse);

const prompt = "Say hi.";
const submit = await fetch(`http://127.0.0.1:${port}/v1/tasks`, {
  method: "POST",
  headers: { ...headers, "Content-Type": "application/json" },
  body: JSON.stringify({ prompt }),
});
assert.equal(submit.status, 202);
const queued = await submit.json();
assert.equal(queued.status, "queued");
assert.equal(sent.length, 1);
assert.ok(sent[0].content.includes("JACK_CONTROL_RUN:"));

// The exact private marker proves this is the bridge-injected Pi input. The input
// hook must strip it before before_agent_start/model-visible prompt processing.
const inputResult = await emit("input", {
  text: sent[0].content,
  source: "extension",
  streamingBehavior: "followUp",
});
assert.equal(inputResult.action, "transform");
assert.equal(inputResult.text, prompt);
assert.ok(!inputResult.text.includes("JACK_CONTROL_RUN:"));

idle = false;
await emit("before_agent_start", { prompt: inputResult.text });
await emit("agent_start", {});
await emit("message_end", { message: { role: "user", content: prompt } });
await emit("message_update", {
  message: { role: "assistant" },
  assistantMessageEvent: { type: "text_delta", delta: "Hi" },
});
await emit("message_end", { message: { role: "assistant", content: "Hi" } });
await emit("agent_end", { messages: [] });

// This intentionally occurs after agent_end. It must NOT inherit the controlled
// task merely because that task has not reached agent_settled yet.
await emit("message_end", { message: { role: "assistant", content: "stale" } });

idle = true;
await emit("agent_settled", {});
await new Promise((r) => setTimeout(r, 50));

const taskEvents = collector.events.filter((e) => e.type === "task");
const messageEnds = collector.events.filter((e) => e.type === "message_end");
const messageUpdates = collector.events.filter((e) => e.type === "message");
assert.ok(taskEvents.some((e) => e.data.status === undefined ? false : true) || taskEvents.length > 0);

const runningTask = taskEvents.map((e) => e.data).find((e) => e.data?.status === "running");
const completedTask = taskEvents.map((e) => e.data).find((e) => e.data?.status === "completed");
assert.ok(runningTask, "running task event missing");
assert.ok(completedTask, "completed task event missing");
assert.equal(completedTask.data.runOpen, false, "terminal completed SSE task snapshot must close runOpen");
assert.ok(completedTask.data.settledAt, "terminal completed SSE task snapshot must include settledAt");
const taskId = runningTask.task_id;
const runId = runningTask.run_id;
assert.equal(taskId, queued.id);
assert.ok(runId);
assert.equal(runningTask.attribution, "task_state");

const attributedEnds = messageEnds.filter((e) => e.data.task_id === taskId);
assert.equal(attributedEnds.length, 2); // user + assistant message_end for this run
assert.ok(attributedEnds.every((e) => e.data.run_id === runId));
assert.ok(attributedEnds.every((e) => e.data.attribution === "pi_run_bound"));
assert.equal(messageUpdates.length, 1);
assert.equal(messageUpdates[0].data.task_id, taskId);
assert.equal(messageUpdates[0].data.run_id, runId);

const stale = messageEnds.find((e) => e.data.data?.message?.content === "stale");
assert.ok(stale, "post-agent_end stale event missing");
assert.equal(stale.data.task_id, null);
assert.equal(stale.data.run_id, null);
assert.equal(stale.data.attribution, "none");

const finalStatus = await fetch(`http://127.0.0.1:${port}/v1/status`, { headers });
const final = await finalStatus.json();
assert.equal(final.status, "completed");
assert.equal(final.runOpen, false);
assert.equal(final.runId, runId);
assert.ok(final.settledAt);
assert.equal(aborted, false);

// Automatic retry/continuation must retain run_id and advance run_epoch.
const retryPrompt = "Retry correlation test.";
const retrySubmit = await fetch(`http://127.0.0.1:${port}/v1/tasks`, {
  method: "POST",
  headers: { ...headers, "Content-Type": "application/json" },
  body: JSON.stringify({ prompt: retryPrompt }),
});
assert.equal(retrySubmit.status, 202);
const retryQueued = await retrySubmit.json();
const retryWire = sent.at(-1).content;
const retryInput = await emit("input", { text: retryWire, source: "extension", streamingBehavior: "followUp" });
assert.equal(retryInput.text, retryPrompt);
idle = false;
await emit("before_agent_start", { prompt: retryInput.text });
await emit("agent_start", {});
await emit("message_end", { message: { role: "user", content: retryPrompt } });
await emit("agent_end", { messages: [], willRetry: true });
// Pi retry/continuation agent_start has no new controlled input marker.
await emit("agent_start", {});
await emit("message_end", { message: { role: "assistant", content: "retry success" } });
await emit("agent_end", { messages: [], willRetry: false });
idle = true;
await emit("agent_settled", {});
await new Promise((r) => setTimeout(r, 50));

const retryEvents = collector.events.filter((e) => e.data?.task_id === retryQueued.id && e.data?.run_id);
assert.ok(retryEvents.length > 0);
const retryRunIds = new Set(retryEvents.map((e) => e.data.run_id));
assert.equal(retryRunIds.size, 1);
const retryMessageEnds = retryEvents.filter((e) => e.type === "message_end");
assert.ok(retryMessageEnds.some((e) => e.data.run_epoch === 1));
assert.ok(retryMessageEnds.some((e) => e.data.run_epoch === 2));

// A running cancellation is terminal immediately but cannot overlap a new
// controlled task until the underlying Pi run actually settles.
const cancelPrompt = "Long cancellation test.";
const cancelEventStart = collector.events.length;
const cancelSubmit = await fetch(`http://127.0.0.1:${port}/v1/tasks`, {
  method: "POST",
  headers: { ...headers, "Content-Type": "application/json" },
  body: JSON.stringify({ prompt: cancelPrompt }),
});
assert.equal(cancelSubmit.status, 202);
const cancelWire = sent.at(-1).content;
const cancelInput = await emit("input", { text: cancelWire, source: "extension", streamingBehavior: "followUp" });
idle = false;
await emit("before_agent_start", { prompt: cancelInput.text });
await emit("agent_start", {});
const cancelResponse = await fetch(`http://127.0.0.1:${port}/v1/tasks/cancel`, { method: "POST", headers });
assert.equal(cancelResponse.status, 202);
const cancelled = await cancelResponse.json();
assert.equal(cancelled.status, "cancelled");
assert.equal(cancelled.runOpen, true);
assert.equal(aborted, true);
const overlap = await fetch(`http://127.0.0.1:${port}/v1/tasks`, {
  method: "POST",
  headers: { ...headers, "Content-Type": "application/json" },
  body: JSON.stringify({ prompt: "must not overlap" }),
});
assert.equal(overlap.status, 409);
await emit("agent_end", { messages: [] });
idle = true;
await emit("agent_settled", {});
const cancelledStatusResponse = await fetch(`http://127.0.0.1:${port}/v1/status`, { headers });
const cancelledStatus = await cancelledStatusResponse.json();
assert.equal(cancelledStatus.status, "cancelled");
assert.equal(cancelledStatus.runOpen, false);
assert.ok(cancelledStatus.settledAt);
const cancelTaskEvents = collector.events.slice(cancelEventStart).filter((e) => e.type === "task");
const cancelledTerminalEvent = cancelTaskEvents
  .map((e) => e.data)
  .find((e) => e.data?.status === "cancelled" && e.data?.settledAt);
assert.ok(cancelledTerminalEvent, "terminal cancelled SSE task snapshot missing");
assert.equal(cancelledTerminalEvent.run_id, cancelled.runId, "terminal cancelled SSE task snapshot must retain run ID");
assert.equal(cancelledTerminalEvent.data.runOpen, false, "terminal cancelled SSE task snapshot must close runOpen");

// A queued cancellation is swallowed at the exact private input marker and does
// not begin a controlled model run.
const queuedCancelSubmit = await fetch(`http://127.0.0.1:${port}/v1/tasks`, {
  method: "POST",
  headers: { ...headers, "Content-Type": "application/json" },
  body: JSON.stringify({ prompt: "cancel before start" }),
});
assert.equal(queuedCancelSubmit.status, 202);
const queuedCancelWire = sent.at(-1).content;
const queuedCancelResponse = await fetch(`http://127.0.0.1:${port}/v1/tasks/cancel`, { method: "POST", headers });
assert.equal(queuedCancelResponse.status, 202);
const swallowed = await emit("input", { text: queuedCancelWire, source: "extension", streamingBehavior: "followUp" });
assert.equal(swallowed.action, "handled");

await collector.stop();
await emit("session_shutdown", { reason: "quit" });
fs.rmSync(tempHome, { recursive: true, force: true });
console.log("PI_CONTROL_BRIDGE_V2_RUN_CORRELATION: PASS");
