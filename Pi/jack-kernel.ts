import crypto from "crypto";
import fs from "fs";
import os from "os";
import path from "path";

const PROVIDER_NAME = "jack-kernel";
const DEFAULT_JACK_URL = "http://127.0.0.1:8001";
// Pi's documented default output allowance. LM Studio's model-list API
// reports context capacity, not a separate generation-output ceiling.
const PI_DEFAULT_MAX_TOKENS = 16384;
const CONFIG_PATH = path.join(os.homedir(), ".pi", "agent", "jack-kernel.json");
const EXECUTOR_ADMISSION_PROTOCOL_VERSION = 1;
const STRUCTURED_PATH_TOOLS = new Set(["read", "edit", "write", "grep", "find", "ls"]);
const COMMAND_DIALECT_BY_TOOL = new Map([
  ["bash", "bash"],
  ["powershell", "powershell"],
  ["pwsh", "powershell"],
]);

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

async function postJson(url, token, payload, timeoutMs = 5000) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      method: "POST",
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(token),
      },
      body: JSON.stringify(payload),
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
  const root = String(url || DEFAULT_JACK_URL).replace(/\/+$/, "").replace(/\/v1$/, "");
  const health = await fetchJson(`${root}/health`, token);
  const actualRuntimeId = String(health?.runtime_id || "");
  if (!actualRuntimeId) {
    throw new Error("Jack runtime did not report runtime_id");
  }
  if (expectedRuntimeId && actualRuntimeId !== expectedRuntimeId) {
    throw new Error(
      `Jack runtime identity mismatch: expected ${expectedRuntimeId}, got ${actualRuntimeId || "unknown"}`
    );
  }
  return health;
}

// Pi's reasoning capability describes whether the active Jack cognition program
// uses native thinking. It is NOT the user-selected Pi thinking level: Jack's
// host-owned stage profiles continue to control actual inference effort.
function runtimeSupportsNativeThinking(health) {
  const identity = health?.runtime_identity;
  const stages = identity?.stage_controls;
  const flow = identity?.flow;
  if (Array.isArray(flow) && flow.length > 0 && stages && typeof stages === "object") {
    return flow.some((key) => stages[key]?.thinking === true);
  }

  // Compatibility with earlier Jack runtimes that expose only the display
  // label. Do not mistake the Agentic or native Medium/X-High modes for Off.
  const level = String(health?.reasoning_level || "").trim().toLowerCase();
  return level !== "" && level !== "off" && level !== "no reasoning";
}

// Pi hides xhigh/max unless each level is explicitly advertised by the model.
// Advertise xhigh only when a Jack-owned active stage actually uses xhigh.
// Jack has no distinct per-stage "max" effort, so do not advertise max.
function runtimeThinkingLevelMap(health) {
  const identity = health?.runtime_identity;
  const stages = identity?.stage_controls;
  const flow = identity?.flow;
  if (!Array.isArray(flow) || !stages || typeof stages !== "object") return {};
  const xhigh = flow.some((key) => {
    const stage = stages[key];
    return stage?.thinking === true &&
      String(stage?.reasoning_effort || "").trim().toLowerCase() === "xhigh";
  });
  return xhigh ? { xhigh: "xhigh" } : {};
}

async function fetchJackModels(url, token, health) {
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
      reasoning: runtimeSupportsNativeThinking(health),
      thinkingLevelMap: runtimeThinkingLevelMap(health),
      compat: { supportsDeveloperRole: false, supportsReasoningEffort: false },
      input: ["text"],
      cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
      contextWindow,
      // Pi maxTokens is an output allowance, not a context capacity.
      // Jack retains authority over actual stage generation limits.
      maxTokens: Math.min(contextWindow, PI_DEFAULT_MAX_TOKENS),
    };
  });
}

export default async function (pi) {
  let activeRuntimeBinding = null;
  // Unshared, high-entropy capability; rotate on every Pi session change.
  let tasSessionId = null;
  let tasSessionCapability = null;

  async function syncProvider() {
    const { url, token, expectedRuntimeId } = resolveJackTarget();
    activeRuntimeBinding = null;
    try {
      const health = await verifyRuntimeIdentity(url, token, expectedRuntimeId);
      const models = await fetchJackModels(url, token, health);
      if (!models.length) return;
      const root = String(url || DEFAULT_JACK_URL).replace(/\/+$/, "").replace(/\/v1$/, "");
      const runtimeId = String(health?.runtime_id || "");
      const laneId = String(health?.lane_id || "");
      if (!laneId) {
        throw new Error("Jack runtime did not report lane_id");
      }
      const provider = {
        baseUrl: `${root}/v1/`,
        api: "openai-completions",
        apiKey: token || "jack-kernel",
        models,
      };
      pi.registerProvider(PROVIDER_NAME, provider);
      activeRuntimeBinding = { root, token, runtimeId, laneId };
    } catch (error) {
      console.error("[jack-kernel] Context/model sync skipped:", error);
    }
  }

  await syncProvider();

  // Pi extensions may override built-in "edit" under the same name.
  // Never block by tool name alone: only a POSITIVE, exact Pi-origin match
  // to the native implementation authorizes hiding or denying it.
  const NATIVE_EDIT_ALTERNATIVE =
    "Pi's built-in edit tool is disabled by Jack. Read the existing file, use " +
    "the available write tool to save the complete updated contents or another " +
    "authorized patch/script tool, then read the file back to verify. Do not " +
    "retry Pi's built-in edit. Third-party replacement edit tools are allowed.";
  let editHiddenByJack = false;
  function editToolOrigin() {
    if (typeof pi.getAllTools !== "function") return "unknown";
    try {
      const registered = pi.getAllTools();
      if (!Array.isArray(registered)) return "unknown";
      const matches = registered.filter((entry) => entry?.name === "edit");
      if (matches.length === 0) return "absent";
      // Ambiguous registrations or unknown sources must NOT cause false
      // blocking of a custom/SDK edit override.
      if (matches.length !== 1) return "unknown";
      const source = matches[0]?.sourceInfo?.source;
      const rawPath = matches[0]?.sourceInfo?.path;
      const sourcePath = String(rawPath || "").replace(/^<|>$/g, "");
      return source === "builtin" && sourcePath === "builtin:edit"
        ? "builtin"
        : "other";
    } catch {
      // Failed introspection must never be used to ban third-party tools.
    }
    return "unknown";
  }

  function syncNativeEditGuidance(event, ctx) {
    // Pi's structured prompt can provide the alternative BEFORE tool use;
    // only when Pi positively identifies the editor as native.
    const guidelines = event?.systemPromptOptions?.promptGuidelines;
    if (!Array.isArray(guidelines)) return;
    const shouldGuide =
      String(ctx?.model?.provider || "") === PROVIDER_NAME &&
      editToolOrigin() === "builtin";
    const next = guidelines.filter((line) => line !== NATIVE_EDIT_ALTERNATIVE);
    if (shouldGuide) next.push(NATIVE_EDIT_ALTERNATIVE);
    guidelines.splice(0, guidelines.length, ...next);
  }

  function reconcileEditToolAvailability(ctx) {
    const provider = String(ctx?.model?.provider || "");
    if (!provider || typeof pi.getActiveTools !== "function" ||
        typeof pi.setActiveTools !== "function") return;
    const active = pi.getActiveTools();
    if (!Array.isArray(active)) return;
    const origin = editToolOrigin();
    if (provider === PROVIDER_NAME) {
      if (origin === "builtin" && active.includes("edit")) {
        pi.setActiveTools(active.filter((name) => name !== "edit"));
        editHiddenByJack = true;
      } else if (origin !== "builtin" && editHiddenByJack) {
        // Restore only the availability Jack previously suppressed.
        // SDK, extension and unknown-origin editors must not be blocked.
        if (origin !== "absent" && !active.includes("edit")) {
          pi.setActiveTools([...active, "edit"]);
        }
        editHiddenByJack = false;
      }
    } else if (editHiddenByJack) {
      // Do not change other providers' tool selection permanently.
      if (origin !== "absent" && !active.includes("edit")) {
        pi.setActiveTools([...active, "edit"]);
      }
      editHiddenByJack = false;
    }
  }

  // Live out-of-band host telemetry appears in Pi's existing footer only.
  // It does not enter the conversation, add a model request or open a window.
  // Polling errors have no effect on model generation or execution.
  const TELEMETRY_STATUS_KEY = "jack-live";
  let telemetryTimer = null;
  let telemetryGeneration = 0;
  let telemetryBusy = false;
  let telemetryLastLine = null;

  function formatJackLive(snapshot) {
    const active = Array.isArray(snapshot?.requests) ? snapshot.requests : [];
    const request = active.find((item) => item?.backend_request_active) || active[0];
    const capacity = Number(snapshot?.context_length);
    const availableCapacity = Number.isFinite(capacity) && capacity > 0
      ? Math.floor(capacity) : null;
    const total = request?.backend_total_tokens;
    const prompt = request?.backend_prompt_tokens;
    const previousTotal = request?.last_backend_total_tokens;
    const previousPrompt = request?.last_backend_prompt_tokens;
    const valid = (value) => typeof value === "number" && Number.isFinite(value) && value >= 0;
    // Prefer actual server-reported total context usage (prompt + output).
    // Otherwise identify prompt-only usage. Never substitute a host estimate.
    const currentNumber = valid(total) ? `${Math.floor(total).toLocaleString()}`
      : (valid(prompt) ? `${Math.floor(prompt).toLocaleString()} prompt` : null);
    const previousNumber = valid(previousTotal) ? `last ${Math.floor(previousTotal).toLocaleString()}`
      : (valid(previousPrompt) ? `last ${Math.floor(previousPrompt).toLocaleString()} prompt` : "—");
    const ctx = `ctx ${currentNumber || previousNumber}/${availableCapacity === null ? "?" : availableCapacity.toLocaleString()}`;
    const phase = String(request?.backend_stream_phase || (request ? "waiting_backend" : "idle"));
    const phaseLabel = ({
      reasoning: "reasoning", content: "answer",
      tool_arguments: "tool args buffered", waiting_backend: "waiting on model",
      unrecognized_chunk: "unrecognized stream", idle: "idle",
    })[phase] || phase;
    const bytes = request?.backend_stream_bytes || {};
    const observed = ["reasoning", "content", "tool_arguments"]
      .map((key) => Number(bytes[key]) || 0);
    const totalBytes = observed.reduce((a, b) => a + b, 0);
    const silence = Number(request?.seconds_since_recognized_output);
    const silenceLabel = request && Number.isFinite(silence) && silence > 3
      ? ` · ${Math.floor(silence)}s without recognized output` : "";
    const stage = request?.stage || "Jack";
    const lifecycle = snapshot?.tool_lifecycle;
    const count = Number(lifecycle?.active_unconfirmed);
    const age = Number(lifecycle?.longest_unconfirmed_seconds);
    const observedTools = Number.isInteger(count) && count > 0
      ? ` · ${count} tool execution${count === 1 ? "" : "s"} unconfirmed${Number.isFinite(age) && age >= 0 ? ` (${Math.floor(age)}s longest)` : ""}`
      : "";
    return `Jack ${stage} · ${phaseLabel} · ${ctx} · ${totalBytes.toLocaleString()} stream bytes${silenceLabel}${observedTools}`;
  }

  async function updateJackTelemetry(ctx, generation) {
    if (generation !== telemetryGeneration || telemetryBusy || !ctx?.hasUI) return;
    const binding = activeRuntimeBinding;
    if (!binding) return;
    telemetryBusy = true;
    try {
      const snapshot = await fetchJson(`${binding.root}/jack/runtime/status`, binding.token, 1200);
      if (generation !== telemetryGeneration || binding !== activeRuntimeBinding) return;
      if (snapshot?.runtime_id !== binding.runtimeId) return;
      const line = formatJackLive(snapshot);
      if (line !== telemetryLastLine) {
        ctx.ui.setStatus(TELEMETRY_STATUS_KEY, line);
        telemetryLastLine = line;
      }
    } catch {
      // The dashboard is observational. No retries, exceptions or control
      // side effects are introduced into the agent's execution.
    } finally {
      telemetryBusy = false;
    }
  }

  function startJackTelemetry(ctx) {
    stopJackTelemetry(ctx);
    if (!ctx?.hasUI || String(ctx?.model?.provider || "") !== PROVIDER_NAME) return;
    const generation = telemetryGeneration;
    telemetryLastLine = "Jack · waiting on backend telemetry";
    ctx.ui.setStatus(TELEMETRY_STATUS_KEY, telemetryLastLine);
    void updateJackTelemetry(ctx, generation);
    telemetryTimer = setInterval(() => {
      void updateJackTelemetry(ctx, generation);
    }, 1500);
    telemetryTimer.unref?.();
  }

  function stopJackTelemetry(ctx) {
    telemetryGeneration += 1;
    if (telemetryTimer !== null) {
      clearInterval(telemetryTimer);
      telemetryTimer = null;
    }
    telemetryLastLine = null;
    if (ctx?.hasUI) ctx.ui.setStatus(TELEMETRY_STATUS_KEY, undefined);
  }

  pi.on("agent_start", (_event, ctx) => startJackTelemetry(ctx));
  pi.on("agent_end", (_event, ctx) => stopJackTelemetry(ctx));
  pi.on("session_shutdown", (_event, ctx) => stopJackTelemetry(ctx));

  // Universal Jack lifecycle protocol; Pi is one best-effort reporting adapter.
  // Never delay tool execution, alter its outcome, or infer failure from silence.
  const lifecycleProgressAt = new Map();
  const lifecycleInFlight = new Set();
  const LIFECYCLE_MAX_IN_FLIGHT_REPORTS = 24;
  function reportToolLifecycle(event, ctx, kind) {
    const binding = activeRuntimeBinding;
    if (!binding || String(ctx?.model?.provider || "") !== PROVIDER_NAME) return;
    const owner = String(ctx?.sessionManager?.getSessionId?.() || "");
    const callId = String(event?.toolCallId || "");
    if (!owner || !callId) return;
    const key = owner + ":" + callId;
    const now = Date.now();
    if (kind === "PROGRESS") {
      if (now - (lifecycleProgressAt.get(key) || 0) < 5000) return;
      lifecycleProgressAt.set(key, now);
      if (lifecycleProgressAt.size > 512) {
        lifecycleProgressAt.delete(lifecycleProgressAt.keys().next().value);
      }
    } else if (kind === "END") {
      lifecycleProgressAt.delete(key);
    }
    if (lifecycleInFlight.size >= LIFECYCLE_MAX_IN_FLIGHT_REPORTS) return;
    const observed = kind === "END"
      ? (event?.isError === true ? "ERROR_REPORTED"
          : event?.isError === false ? "SUCCESS_REPORTED" : "UNKNOWN")
      : undefined;
    const body = {
      runtime_id: binding.runtimeId,
      lane_id: binding.laneId,
      adapter: "pi",
      owner,
      call_id: callId,
      event: kind,
      ...(kind === "END" ? { outcome: observed } : {}),
      ...(kind === "START" ? { capabilities: {
        start_end: true, progress: true,
        bounded_return: false, cancellation: false, detached_jobs: false,
      } } : {}),
    };
    const pending = postJson(`${binding.root}/jack/tool-lifecycle/observe`, binding.token, body, 1200);
    lifecycleInFlight.add(pending);
    void pending.catch(() => {
      // Telemetry loss must never alter executor behavior or tool outcomes.
    }).finally(() => lifecycleInFlight.delete(pending));
  }
  pi.on("tool_execution_start", (event, ctx) => reportToolLifecycle(event, ctx, "START"));
  pi.on("tool_execution_update", (event, ctx) => reportToolLifecycle(event, ctx, "PROGRESS"));
  pi.on("tool_execution_end", (event, ctx) => reportToolLifecycle(event, ctx, "END"));

  // Pi's executor knows both FAILED and SUCCESS. Preserve the existing
  // failure contract and send explicit successful receipts as well, so the
  // universal 25-failure ceiling resets only on actual executor success.
  // Both are observational and bound to tool-call ID and Pi session.
  const failedToolCalls = new Map();
  const successfulToolCalls = new Map();
  let outcomeSessionId = null;
  pi.on("tool_execution_end", (event, ctx) => {
    if (String(ctx?.model?.provider || "") !== PROVIDER_NAME) return;
    const callId = String(event?.toolCallId || "");
    const sessionId = String(ctx?.sessionManager?.getSessionId?.() || "");
    if (!callId || !sessionId) return;
    if (outcomeSessionId !== sessionId) {
      failedToolCalls.clear();
      successfulToolCalls.clear();
      outcomeSessionId = sessionId;
    }
    if (event?.isError === true) {
      successfulToolCalls.delete(callId);
      failedToolCalls.delete(callId);
      failedToolCalls.set(callId, sessionId);
    } else if (event?.isError === false) {
      failedToolCalls.delete(callId);
      successfulToolCalls.delete(callId);
      successfulToolCalls.set(callId, sessionId);
    } else {
      failedToolCalls.delete(callId);
      successfulToolCalls.delete(callId);
    }
    while (failedToolCalls.size > 128) {
      failedToolCalls.delete(failedToolCalls.keys().next().value);
    }
    while (successfulToolCalls.size > 128) {
      successfulToolCalls.delete(successfulToolCalls.keys().next().value);
    }
  });

  pi.on("before_provider_request", (event, ctx) => {
    if (!activeRuntimeBinding || String(ctx?.model?.provider || "") !== PROVIDER_NAME) return;
    const sessionId = String(ctx?.sessionManager?.getSessionId?.() || "");
    if (!sessionId || sessionId !== outcomeSessionId) return;
    const payload = event?.payload;
    if (!payload || typeof payload !== "object" || !Array.isArray(payload.messages)) return;
    let tagged = false;
    const messages = payload.messages.map((message) => {
      if (message?.role !== "tool") return message;
      const id = String(message.tool_call_id || "");
      if (!id) return message;
      if (failedToolCalls.get(id) === sessionId) {
        tagged = true;
        return { ...message, is_error: true };
      }
      if (successfulToolCalls.get(id) === sessionId) {
        tagged = true;
        return { ...message, is_error: false };
      }
      return message;
    });
    if (tagged) return { ...payload, messages };
    return undefined;
  });

  pi.on("before_provider_headers", (event, ctx) => {
    const binding = activeRuntimeBinding;
    if (!binding || String(ctx?.model?.provider || "") !== PROVIDER_NAME) {
      return;
    }

    event.headers["X-Jack-Executor-Admission-Version"] =
      String(EXECUTOR_ADMISSION_PROTOCOL_VERSION);
    event.headers["X-Jack-Executor-Runtime-Id"] = binding.runtimeId;
    event.headers["X-Jack-Executor-Lane-Id"] = binding.laneId;
    event.headers["X-Jack-Executor-Cwd"] = String(ctx?.cwd || "");
    event.headers["X-Jack-Executor-Platform"] = process.platform;
    event.headers["X-Jack-Executor-Adapter"] = "pi";

    const currentSessionId = String(ctx?.sessionManager?.getSessionId?.() || "");
    if (currentSessionId) {
      if (currentSessionId !== tasSessionId || !tasSessionCapability) {
        tasSessionId = currentSessionId;
        tasSessionCapability = crypto.randomBytes(32).toString("hex");
      }
      event.headers["X-Jack-TAS-Session-Capability"] = tasSessionCapability;
    } else {
      // Never reuse a capability when Pi cannot establish its current session.
      tasSessionId = null;
      tasSessionCapability = null;
    }
  });

  pi.on("tool_call", async (event, ctx) => {
    if (String(ctx?.model?.provider || "") !== PROVIDER_NAME) {
      return undefined;
    }

    const toolName = String(event?.toolName || "");
    if (toolName === "edit" && editToolOrigin() === "builtin") {
      // Guard stale native calls even if a model still has an old declaration.
      // Never deny SDK, third-party or unidentifiable editors by name alone.
      return { block: true, reason: NATIVE_EDIT_ALTERNATIVE };
    }
    const commandDialect = COMMAND_DIALECT_BY_TOOL.get(toolName) || null;
    if (!STRUCTURED_PATH_TOOLS.has(toolName) && !commandDialect) {
      return undefined;
    }

    const binding = activeRuntimeBinding;
    if (!binding) {
      return {
        block: true,
        reason: "Jack Phase-4 executor admission is unavailable.",
      };
    }

    try {
      const decision = await postJson(
        `${binding.root}/jack/security/path-admission`,
        binding.token,
        {
          protocol_version: EXECUTOR_ADMISSION_PROTOCOL_VERSION,
          runtime_id: binding.runtimeId,
          lane_id: binding.laneId,
          tool_call_id: String(event?.toolCallId || ""),
          tool_name: toolName,
          arguments: event?.input && typeof event.input === "object" ? event.input : {},
          executor_cwd: String(ctx?.cwd || ""),
          executor_platform: process.platform,
          ...(commandDialect ? { command_dialect: commandDialect } : {}),
        },
      );

      const outcome = String(decision?.outcome || "");
      if (decision?.contract_applied !== true) {
        return {
          block: true,
          reason: "Jack Phase-4 executor admission found no matching host-owned contract.",
        };
      }
      if (outcome === "ALLOW") {
        return undefined;
      }
      if (outcome === "HARD_INTERRUPT") {
        if (typeof ctx?.abort === "function") ctx.abort();
        return {
          block: true,
          reason: "Blocked by Jack Phase-4 restricted-path policy.",
          terminate: true,
        };
      }
      if (outcome === "DENY_AND_CONTINUE") {
        return {
          block: true,
          reason: "Blocked by Jack Phase-4 Workspace Lock.",
        };
      }
      return {
        block: true,
        reason: "Jack Phase-4 executor admission returned an unknown outcome.",
      };
    } catch (error) {
      console.error("[jack-kernel] Phase-4 executor admission failed:", error);
      return {
        block: true,
        reason: "Jack Phase-4 executor admission failed closed for this filesystem action.",
      };
    }
  });

  let refreshedThisTurn = false;
  pi.on("before_agent_start", async (event, ctx) => {
    reconcileEditToolAvailability(ctx);
    syncNativeEditGuidance(event, ctx);
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
