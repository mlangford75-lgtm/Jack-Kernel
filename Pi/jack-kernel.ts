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

function loadConfig() {
  try {
    if (fs.existsSync(CONFIG_PATH)) {
      const raw = fs.readFileSync(CONFIG_PATH, "utf-8");
      const parsed = JSON.parse(raw.charCodeAt(0) === 0xfeff ? raw.slice(1) : raw);
      return {
        url: resolveValue(parsed.url || DEFAULT_JACK_URL),
        token: parsed.token ? resolveValue(parsed.token) : undefined,
      };
    }
  } catch (error) {
    console.error(`[jack-kernel] Failed to read ${CONFIG_PATH}:`, error);
  }
  return { url: DEFAULT_JACK_URL, token: undefined };
}

async function fetchJackModels(url, token) {
  const root = String(url || DEFAULT_JACK_URL).replace(/\/+$/, "").replace(/\/v1$/, "");
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 5000);
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;

  try {
    const response = await fetch(`${root}/api/v1/models`, {
      signal: controller.signal,
      headers,
    });
    if (!response.ok) {
      throw new Error(`Jack Kernel HTTP status ${response.status}: ${await response.text()}`);
    }
    const payload = await response.json();
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
  } finally {
    clearTimeout(timeoutId);
  }
}

export default async function (pi) {
  async function syncProvider() {
    const { url, token } = loadConfig();
    try {
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
  pi.on("agent_start", async () => {
    refreshedThisTurn = false;
  });
  pi.on("message_end", async (event) => {
    if (event?.message?.role === "assistant" && !refreshedThisTurn) {
      refreshedThisTurn = true;
      await syncProvider();
    }
  });
}
