import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = path.join(root, "Pi", "jack-kernel.ts");
const tempHome = fs.mkdtempSync(path.join(os.tmpdir(), "jack-pi-phase4-admission-"));
const runtimeRegistry = path.join(tempHome, "runtimes");
fs.mkdirSync(path.join(tempHome, ".pi", "agent"), { recursive: true });
fs.mkdirSync(runtimeRegistry, { recursive: true });

process.env.HOME = tempHome;
process.env.USERPROFILE = tempHome;
process.env.JACK_PI_JACK_RUNTIME_REGISTRY_DIR = runtimeRegistry;
process.env.JACK_PI_JACK_RUNTIME_ID = "runtime-phase4-01";
delete process.env.JACK_PI_JACK_URL;
delete process.env.JACK_PI_JACK_TOKEN;

let outcome = "ALLOW";
const admissionCalls = [];

const server = http.createServer(async (req, res) => {
  res.setHeader("Content-Type", "application/json");

  if (req.url === "/health") {
    res.end(JSON.stringify({ runtime_id: "runtime-phase4-01", lane_id: "lane-phase4-01" }));
    return;
  }

  if (req.url === "/api/v1/models") {
    res.end(JSON.stringify({
      models: [{
        key: "test-model",
        display_name: "Test Model",
        max_context_length: 32768,
        loaded_instances: [{ config: { context_length: 16384 } }],
      }],
    }));
    return;
  }

  if (req.url === "/jack/security/path-admission" && req.method === "POST") {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    admissionCalls.push(body);
    res.end(JSON.stringify({
      protocol_version: 1,
      runtime_id: "runtime-phase4-01",
      lane_id: "lane-phase4-01",
      tool_call_id: body.tool_call_id,
      outcome,
      contract_applied: true,
    }));
    return;
  }

  res.statusCode = 404;
  res.end(JSON.stringify({ error: "not found" }));
});

await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const actualPort = server.address().port;

fs.writeFileSync(
  path.join(runtimeRegistry, "runtime-phase4-01.json"),
  JSON.stringify({
    runtime_id: "runtime-phase4-01",
    status: "ready",
    endpoint: { actual_host: "127.0.0.1", actual_port: actualPort },
  }),
  "utf8"
);

const modulePath = path.join(tempHome, "jack-kernel.mjs");
fs.copyFileSync(source, modulePath);

const handlers = new Map();
const pi = {
  registerProvider() {},
  on(name, fn) {
    if (!handlers.has(name)) handlers.set(name, []);
    handlers.get(name).push(fn);
  },
};

const { default: installProvider } = await import(
  pathToFileURL(modulePath).href + `?v=${Date.now()}`
);
await installProvider(pi);

const headerHandlers = handlers.get("before_provider_headers") || [];
assert.equal(headerHandlers.length, 1);
const headerEvent = { headers: {} };
headerHandlers[0](headerEvent, {
  cwd: "D:\\Projects\\Jack",
  model: { provider: "jack-kernel" },
});
assert.equal(headerEvent.headers["X-Jack-Executor-Admission-Version"], "1");
assert.equal(headerEvent.headers["X-Jack-Executor-Runtime-Id"], "runtime-phase4-01");
assert.equal(headerEvent.headers["X-Jack-Executor-Lane-Id"], "lane-phase4-01");
assert.equal(headerEvent.headers["X-Jack-Executor-Cwd"], "D:\\Projects\\Jack");
assert.equal(headerEvent.headers["X-Jack-Executor-Platform"], process.platform);
assert.equal(headerEvent.headers["X-Jack-Executor-Adapter"], "pi");

const toolHandlers = handlers.get("tool_call") || [];
assert.equal(toolHandlers.length, 1);
const toolCall = toolHandlers[0];

let abortCount = 0;
const ctx = {
  cwd: "D:\\Projects\\Jack",
  model: { provider: "jack-kernel" },
  abort() { abortCount += 1; },
};

outcome = "ALLOW";
let result = await toolCall({
  toolCallId: "call-allow",
  toolName: "read",
  input: { path: "src\\engine.py" },
}, ctx);
assert.equal(result, undefined);
assert.equal(admissionCalls.length, 1);
assert.equal(admissionCalls[0].runtime_id, "runtime-phase4-01");
assert.equal(admissionCalls[0].lane_id, "lane-phase4-01");
assert.equal(admissionCalls[0].tool_name, "read");
assert.equal(admissionCalls[0].executor_cwd, "D:\\Projects\\Jack");
assert.equal(admissionCalls[0].executor_platform, process.platform);

outcome = "DENY_AND_CONTINUE";
result = await toolCall({
  toolCallId: "call-deny",
  toolName: "ls",
  input: {},
}, { ...ctx, cwd: "D:\\OtherProject" });
assert.equal(result?.block, true);
assert.equal(result?.terminate, undefined);
assert.match(result?.reason || "", /Workspace Lock/);

outcome = "HARD_INTERRUPT";
result = await toolCall({
  toolCallId: "call-hard",
  toolName: "read",
  input: { path: "..\\Sensitive\\secret.txt" },
}, ctx);
assert.equal(result?.block, true);
assert.equal(result?.terminate, true);
assert.equal(abortCount, 1);

const callsBeforeBash = admissionCalls.length;
outcome = "ALLOW";
result = await toolCall({
  toolCallId: "call-bash",
  toolName: "bash",
  input: { command: "git status" },
}, ctx);
assert.equal(result, undefined);
assert.equal(admissionCalls.length, callsBeforeBash + 1);
assert.equal(admissionCalls.at(-1).command_dialect, "bash");

const callsBeforePowerShell = admissionCalls.length;
outcome = "DENY_AND_CONTINUE";
result = await toolCall({
  toolCallId: "call-powershell",
  toolName: "powershell",
  input: { command: "Get-Content ..\\Outside\\secret.txt" },
}, ctx);
assert.equal(result?.block, true);
assert.equal(admissionCalls.length, callsBeforePowerShell + 1);
assert.equal(admissionCalls.at(-1).command_dialect, "powershell");

await new Promise((resolve) => server.close(resolve));
console.log("Pi Phase-4 executor admission harness: PASS");
