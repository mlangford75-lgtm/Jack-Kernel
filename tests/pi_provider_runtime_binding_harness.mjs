import assert from "node:assert/strict";
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
const server = http.createServer((req, res) => {
  res.setHeader("Content-Type", "application/json");
  if (req.url === "/health") {
    res.end(JSON.stringify({ runtime_id: healthRuntimeId }));
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

healthRuntimeId = "wrong-runtime";
for (const fn of handlers.get("before_agent_start") || []) {
  await fn({});
}
assert.equal(
  registrations.length,
  1,
  "provider must not re-register when the resolved endpoint reports the wrong runtime identity"
);

await new Promise((resolve) => server.close(resolve));
console.log("Pi provider runtime binding harness: PASS");
