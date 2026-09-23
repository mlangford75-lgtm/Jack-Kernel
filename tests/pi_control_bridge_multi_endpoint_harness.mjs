import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const bridgeTs = path.join(root, "Pi", "pi-control-bridge.ts");
const tempHome = fs.mkdtempSync(path.join(os.tmpdir(), "jack-pi-multi-endpoint-"));
const cfgDir = path.join(tempHome, ".pi", "agent");
const registryDir = path.join(cfgDir, "jack-kernel-bridges");
fs.mkdirSync(registryDir, { recursive: true });

process.env.HOME = tempHome;
process.env.USERPROFILE = tempHome;
process.env.JACK_PI_CONTROL_REGISTRY_DIR = registryDir;
process.env.JACK_PI_CONTROL_TOKEN = "multi-endpoint-token";
process.env.JACK_PI_CONTROL_BRIDGE_ID = "debug-worker";
process.env.JACK_PI_CONTROL_PORT_FALLBACK = "1";

const blocker = http.createServer((_req, res) => res.end("occupied"));
await new Promise((resolve) => blocker.listen(0, "127.0.0.1", resolve));
const preferredPort = blocker.address().port;
process.env.JACK_PI_CONTROL_PORT = String(preferredPort);

const bridgeMjs = path.join(tempHome, "pi-control-bridge.mjs");
fs.copyFileSync(bridgeTs, bridgeMjs);

const handlers = new Map();
function on(name, fn) {
  if (!handlers.has(name)) handlers.set(name, []);
  handlers.get(name).push(fn);
}
const context = {
  isIdle: () => true,
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
  sendUserMessage: () => {},
};

const { default: installBridge } = await import(pathToFileURL(bridgeMjs).href + `?v=${Date.now()}`);
await installBridge(pi);
await emit("session_start", { reason: "startup" });

let manifestPath = null;
for (let i = 0; i < 100; i++) {
  const files = fs.existsSync(registryDir)
    ? fs.readdirSync(registryDir).filter((name) => name.endsWith(".json"))
    : [];
  if (files.length === 1) {
    manifestPath = path.join(registryDir, files[0]);
    break;
  }
  await new Promise((resolve) => setTimeout(resolve, 10));
}
assert.ok(manifestPath, "bridge must publish exactly one runtime manifest");

const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
assert.equal(manifest.bridge_id, "debug-worker");
assert.equal(manifest.preferred_port, preferredPort);
assert.equal(manifest.fallback_enabled, true);
assert.equal(manifest.fallback_used, true);
assert.equal(manifest.fallback_reason, "EADDRINUSE");
assert.ok(Number.isInteger(manifest.actual_port));
assert.ok(manifest.actual_port > 0);
assert.notEqual(manifest.actual_port, preferredPort);

const headers = { Authorization: "Bearer multi-endpoint-token" };
const statusResponse = await fetch(`http://127.0.0.1:${manifest.actual_port}/v1/status`, { headers });
assert.equal(statusResponse.status, 200);
const status = await statusResponse.json();
assert.equal(status.bridgeId, "debug-worker");
assert.equal(status.preferredControlPort, preferredPort);
assert.equal(status.actualControlPort, manifest.actual_port);
assert.equal(status.controlPortFallbackEnabled, true);
assert.equal(status.controlPortFallbackUsed, true);
assert.equal(status.controlPortFallbackReason, "EADDRINUSE");
assert.ok(status.sessionInstanceId);

await emit("session_shutdown", { reason: "test-complete" });
await new Promise((resolve) => setTimeout(resolve, 10));
assert.equal(fs.existsSync(manifestPath), false, "bridge manifest must be removed on shutdown");

await new Promise((resolve) => blocker.close(resolve));

console.log("Pi multi-endpoint fallback harness: PASS");
