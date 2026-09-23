import fs from "fs";
import os from "os";
import path from "path";

const PROVIDER_NAME = "jack-kernel";
const DEFAULT_JACK_URL = "http://127.0.0.1:8001";
const CONFIG_PATH = path.join(os.homedir(), ".pi", "agent", "jack-kernel.json");

function resolveValue(value) {
  if (typeof value !== "string") return value;
  if (value.startsWith("$")) return process.env[value.slice(1)] ?? value;
  return value;
}

function safeRuntimeId(value) {
  return String(value || "")
    .trim()
    .replace(/[^A-Za-z0-9._-]+/g, "-")
    .replace(/^[-._]+|[-._]+$/g, "")
    .slice(0, 96);
}

function defaultRuntimeRegistryDir() {
  const override = String(process.env.JACK_PI_JACK_RUNTIME_REGISTRY_DIR || "").trim();
  if (override) return path.resolve(override);
  if (process.platform === "win32" && process.env.APPDATA) {
    return path.join(process.env.APPDATA, "JackKernel", "runtimes");
  }
  return path.join(os.homedir(), ".jack-kernel", "runtimes");
}

function loadConfig() {
  let parsed = {};
  try {
    if (fs.existsSync(CONFIG_PATH)) {
      const raw = fs.readFileSync(CONFIG_PATH, "utf-8");
      parsed = JSON.parse(raw.charCodeAt(0) === 0xfeff ? raw.slice(1) : raw);
    }
  } catch (error) {
    console.error(`[jack-kernel] Failed to read ${CONFIG_PATH}:`, error);
    parsed = {};
  }

  const envUrl = String(process.env.JACK_PI_JACK_URL || "").trim();
  const envToken = process.env.JACK_PI_JACK_TOKEN;
  const runtimeId = String(process.env.JACK_PI_JACK_RUNTIME_ID || "").trim();

  return {
    url: resolveValue(envUrl || parsed.url || DEFAULT_JACK_URL),
    token: envToken !== undefined
      ? resolveValue(String(envToken))
      : (parsed.token ? resolveValue(parsed.token) : undefined),
    runtimeId,
    runtimeRegistryDir: defaultRuntimeRegistryDir(),
  };
}

function runtimeUrlFromRegistry(runtimeId, registryDir) {
  const safeId = safeRuntimeId(runtimeId);
  if (!safeId) throw new Error("JACK_PI_JACK_RUNTIME_ID is invalid");

  const manifestPath = path.join(registryDir, `${safeId}.json`);
  if (!fs.existsSync(manifestPath)) {
    throw new Error(`Jack runtime manifest not found for ${runtimeId}: ${manifestPath}`);
  }

  const raw = fs.readFileSync(manifestPath, "utf-8");
  const manifest = JSON.parse(raw.charCodeAt(0) === 0xfeff ? raw.slice(1) : raw);
  if (String(manifest?.runtime_id || "") !== runtimeId) {
    throw new Error(`Jack runtime manifest identity mismatch for ${runtimeId}`);
  }
  if (String(manifest?.status || "") !== "ready") {
    throw new Error(`Jack runtime ${runtimeId} is not ready`);
  }

  const endpoint = manifest?.endpoint || {};
  let host = String(endpoint.actual_host || "").trim();
  const port = Number(endpoint.actual_port || 0);
  if (!host || !(Number.isInteger(port) && port > 0 && port <= 65535)) {
    throw new Error(`Jack runtime ${runtimeId} has no usable actual endpoint`);
  }
  if (["0.0.0.0", "::", "[::]"].includes(host)) host = "127.0.0.1";
  if (host.includes(":") && !host.startsWith("[")) host = `[${host}]`;

  return `http://${host}:${port}`;
}

function resolveJackTarget() {
  const config = loadConfig();
  if (config.runtimeId) {
    return {
      url: runtimeUrlFromRegistry(config.runtimeId, config.runtimeRegistryDir),
      token: config.token,
      expectedRuntimeId: config.runtimeId,
    };
  }
  return {
    url: String(config.url || DEFAULT_JACK_URL),
    token: config.token,
    expectedRuntimeId: null,
  };
}

function authHeaders(token) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

async function fetchJson(url, token, timeoutMs = 5000) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      signal: controller.signal,
      headers: authHeaders(token),
    });
    if (!response.ok) {
      throw new Error(`Jack Kernel HTTP status ${response.status}: ${await response.text()}`);
    }
    return await response.json();
  } finally {
    clearTimeout(timeoutId);
  }
}

async function verifyRuntimeIdentity(url, token, expectedRuntimeId) {
  if (!expectedRuntimeId) return;
  const root = String(url || DEFAULT_JACK_URL).replace(/\/+$/, "").replace(/\/v1$/, "");
  const health = await fetchJson(`${root}/health`, token);
  if (String(health?.runtime_id || "") !== expectedRuntimeId) {
    throw new Error(
      `Jack runtime identity mismatch: expected ${expectedRuntimeId}, got ${health?.runtime_id || "unknown"}`
    );
  }
}

async function fetchJackModels(url, token) {
  const root = String(url || DEFAULT_JACK_URL).replace(/\/+$/, "").replace(/\/v1$/, "");
  const payload = await fetchJson(`${root}/api/v1/models`, token);
  const models = Array.isArray(payload?.models) ? payload.models : [];
  return models.map((model) => {
    const loadedContext = Number(model?.loaded_instances?.[0]?.config?.context_length || 0);
    const maxContext = Number(model?.max_context_length || 0);
    const contextWindow = loadedContext > 0 ? loadedContext : maxContext;
    if (!(contextWindow > 0)) {
      throw new Error(`Jack model ${model?.key || "unknown"} did not advertise a usable context length`);
    }
    return {
      id: model.key,
      name: model.display_name || model.key,
      reasoning: false,
      input: ["text"],
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
      contextWindow,
      // Jack owns generation ceilings by mode. Pi requires a maxTokens value;
      // use the advertised backend context ceiling rather than a guessed static value.
      maxTokens: maxContext > 0 ? maxContext : contextWindow,
    };
  });
}

export default async function (pi) {
  async function syncProvider() {
    const { url, token, expectedRuntimeId } = resolveJackTarget();
    try {
      await verifyRuntimeIdentity(url, token, expectedRuntimeId);
      const models = await fetchJackModels(url, token);
      if (!models.length) return;
      const root = String(url || DEFAULT_JACK_URL).replace(/\/+$/, "").replace(/\/v1$/, "");
      const provider = {
        baseUrl: `${root}/v1/`,
        api: "openai-completions",
        apiKey: token || "jack-kernel",
        models,
      };
      pi.registerProvider(PROVIDER_NAME, provider);
    } catch (error) {
      console.error("[jack-kernel] Context/model sync skipped:", error);
    }
  }

  await syncProvider();

  let refreshedThisTurn = false;
  pi.on("before_agent_start", async () => {
    refreshedThisTurn = false;
    await syncProvider();
  });
  pi.on("message_end", async (event) => {
    if (event?.message?.role === "assistant" && !refreshedThisTurn) {
      refreshedThisTurn = true;
      await syncProvider();
    }
  });
}
