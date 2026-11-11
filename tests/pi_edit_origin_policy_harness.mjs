import assert from "node:assert/strict";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const home = fs.mkdtempSync(path.join(os.tmpdir(), "jack-pi-edit-policy-"));
const registry = path.join(home, "registry");
fs.mkdirSync(path.join(home, ".pi", "agent"), { recursive: true });
fs.mkdirSync(registry, { recursive: true });
process.env.HOME = home;
process.env.USERPROFILE = home;
process.env.JACK_PI_JACK_RUNTIME_REGISTRY_DIR = registry;
process.env.JACK_PI_JACK_RUNTIME_ID = "runtime-edit-policy";
delete process.env.JACK_PI_JACK_URL;
delete process.env.JACK_PI_JACK_TOKEN;

const admission = [];
const server = http.createServer(async (req, res) => {
  res.setHeader("Content-Type", "application/json");
  if (req.url === "/health") {
    res.end(JSON.stringify({ runtime_id: "runtime-edit-policy", lane_id: "lane-edit-policy" }));
  } else if (req.url === "/api/v1/models") {
    res.end(JSON.stringify({ models: [{
      key: "test-model", display_name: "Test Model", max_context_length: 32768,
      loaded_instances: [{ config: { context_length: 16384 } }],
    }] }));
  } else if (req.url === "/jack/security/path-admission") {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    admission.push(JSON.parse(Buffer.concat(chunks).toString("utf8")));
    res.end(JSON.stringify({ outcome: "ALLOW", contract_applied: true }));
  } else { res.statusCode = 404; res.end("{}"); }
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
fs.writeFileSync(path.join(registry, "runtime-edit-policy.json"),
  JSON.stringify({runtime_id:"runtime-edit-policy", endpoint: {
    actual_host:"127.0.0.1", actual_port:server.address().port}}));

const modulePath = path.join(home, "jack-kernel.mjs");
fs.copyFileSync(path.join(root, "Pi", "jack-kernel.ts"), modulePath);
const handlers = new Map();
let active = ["read", "edit", "write", "bash"];
let toolSource = "builtin";
let toolPath = "<builtin:edit>";
const pi = {
  registerProvider() {},
  on(name, handler) { const group = handlers.get(name) || []; group.push(handler); handlers.set(name, group); },
  getActiveTools() { return [...active]; },
  setActiveTools(tools) { active = [...tools]; },
  getAllTools() { return [{name:"edit", sourceInfo:{source:toolSource, path:toolPath}}]; },
};
const { default: install } = await import(pathToFileURL(modulePath).href);
await install(pi);
const start = handlers.get("before_agent_start")[0];
const call = handlers.get("tool_call")[0];
const jackCtx = {model:{provider:"jack-kernel"},cwd:"D:\\Projects"};
const otherCtx = {model:{provider:"other"},cwd:"D:\\Projects"};
const editRequest = {toolName:"edit",toolCallId:"edit-1",input:{path:"file.py",oldText:"a",newText:"b"}};

await start({},jackCtx);
assert.equal(active.includes("edit"),false,"builtin edit must be removed from active tools");
let result=await call(editRequest,jackCtx);
assert.equal(result?.block,true);
assert.match(result.reason,/different authorized method/);
assert.equal(admission.length,0,"rejected builtin must not reach executor admission");

await start({},otherCtx);
assert.equal(active.includes("edit"),true,"non-Jack provider's original tool selection must be restored");

toolSource="extension";
toolPath="~/.pi/agent/extensions/alternative-editor.ts";
await start({},jackCtx);
assert.equal(active.includes("edit"),true,"extension override must stay exposed");
result=await call(editRequest,jackCtx);
assert.equal(result,undefined,"extension override goes through normal admission");
assert.equal(admission.length,1);
assert.equal(admission[0].tool_name,"edit");

toolSource="sdk";
toolPath="sdk:edit";
await start({},jackCtx);
assert.equal(active.includes("edit"),false,"SDK source is not automatically trusted as extension");
result=await call(editRequest,jackCtx);
assert.equal(result?.block,true);
assert.equal(admission.length,1);

toolSource="extension";
toolPath="~/.pi/agent/extensions/alternative-editor.ts";
await start({},jackCtx);
assert.equal(active.includes("edit"),true,"verified override restores a tool hidden by Jack");
await new Promise(resolve=>server.close(resolve));
console.log("Pi edit source policy harness: PASS");
