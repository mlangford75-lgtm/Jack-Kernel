import fs from "fs";
import http from "http";
import os from "os";
import path from "path";
import { randomUUID } from "crypto";

const HOST = "127.0.0.1";
const DEFAULT_CONTROL_PORT = 8011;
const CONFIG_PATH = path.join(os.homedir(), ".pi", "agent", "jack-kernel.json");
const CONTROL_MARKER_PREFIX = "\u2063JACK_CONTROL_RUN:";
const CONTROL_MARKER_SUFFIX = "\u2063";

function loadControlConfig() {
  try {
    if (fs.existsSync(CONFIG_PATH)) {
      const raw = fs.readFileSync(CONFIG_PATH, "utf-8");
      const parsed = JSON.parse(raw.charCodeAt(0) === 0xfeff ? raw.slice(1) : raw);
      const port = Number(parsed?.controlPort || DEFAULT_CONTROL_PORT);
      return {
        port: Number.isInteger(port) && port > 0 && port <= 65535 ? port : DEFAULT_CONTROL_PORT,
        token: typeof parsed?.controlToken === "string" ? parsed.controlToken : "",
      };
    }
  } catch (error) {
    console.error(`[pi-control] Failed to read ${CONFIG_PATH}:`, error);
  }
  return { port: DEFAULT_CONTROL_PORT, token: "" };
}

function json(res, statusCode, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
    "Cache-Control": "no-store",
  });
  res.end(body);
}

function parseJsonBody(req, limit = 1024 * 1024) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on("data", (chunk) => {
      size += chunk.length;
      if (size > limit) {
        reject(new Error("request body too large"));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => {
      try {
        const raw = Buffer.concat(chunks).toString("utf8");
        resolve(raw ? JSON.parse(raw) : {});
      } catch (error) {
        reject(error);
      }
    });
    req.on("error", reject);
  });
}

function taskIsActive(task) {
  return Boolean(task && ["queued", "running", "settling"].includes(task.status));
}

function taskCanCancel(task) {
  return Boolean(task && ["queued", "running"].includes(task.status));
}

function makeWirePrompt(runId, prompt) {
  return `${CONTROL_MARKER_PREFIX}${runId}${CONTROL_MARKER_SUFFIX}${prompt}`;
}

function decodeWirePrompt(text) {
  if (typeof text !== "string" || !text.startsWith(CONTROL_MARKER_PREFIX)) return null;
  const end = text.indexOf(CONTROL_MARKER_SUFFIX, CONTROL_MARKER_PREFIX.length);
  if (end < 0) return null;
  const runId = text.slice(CONTROL_MARKER_PREFIX.length, end);
  if (!runId) return null;
  return {
    runId,
    prompt: text.slice(end + CONTROL_MARKER_SUFFIX.length),
  };
}

function cloneBinding(binding) {
  if (!binding) return null;
  return {
    taskId: String(binding.taskId),
    runId: String(binding.runId),
    runEpoch: Number(binding.runEpoch || 1),
  };
}

function taskSnapshot(task, controlRun = null, activeRun = null) {
  if (!task) return { status: "idle" };
  const snapshot = {
    id: task.id,
    status: task.status,
    createdAt: task.createdAt,
    toolErrors: Array.isArray(task.toolErrors) ? [...task.toolErrors] : [],
    final: task.final ?? null,
    runId: controlRun?.runId ?? task.runId ?? null,
    runEpoch: activeRun?.runEpoch ?? controlRun?.lastEpoch ?? task.runEpoch ?? null,
    runOpen: Boolean(controlRun),
  };
  if (task.endedAt) snapshot.endedAt = task.endedAt;
  if (task.settledAt) snapshot.settledAt = task.settledAt;
  if (task.error) snapshot.error = task.error;
  return snapshot;
}

function assistantFailure(message) {
  if (!message || message.role !== "assistant") return null;
  if (message.errorMessage) return String(message.errorMessage);
  if (message.error) return typeof message.error === "string" ? message.error : JSON.stringify(message.error);
  if (message.stopReason === "error") return "assistant generation failed";
  return null;
}

export default async function (pi) {
  const { port, token } = loadControlConfig();
  let controlledTask = null;
  let activeCtx = null;
  let latestCtx = null;
  let shuttingDown = false;
  const sessionInstanceId = randomUUID();
  let sessionReady = false;
  let sessionTransitioning = false;
  let server = null;
  let serverListening = false;

  // Correlation state is deliberately separate from controlledTask. A task UUID
  // does not become event authority merely because it is the current task.
  //
  // pendingDispatch: POST /tasks accepted and a private marker was injected into
  // Pi's extension-originated user input. The marker is removed in the `input`
  // event before the prompt reaches templates, the session, or the model.
  //
  // awaitingAgentStart: the marked Pi input has been positively identified.
  // armedAgentStart: before_agent_start for that exact prompt flow has occurred.
  // controlRun: immutable controlled task/run binding lasting until agent_settled.
  // activeRun: one low-level Pi agent_start..agent_end epoch within controlRun.
  let pendingDispatch = null;
  let awaitingAgentStart = null;
  let armedAgentStart = null;
  let controlRun = null;
  let activeRun = null;

  const sseClients = new Set();

  function controlPlaneBusy() {
    return Boolean(
      sessionTransitioning ||
      taskIsActive(controlledTask) ||
      pendingDispatch ||
      awaitingAgentStart ||
      armedAgentStart ||
      controlRun ||
      activeRun
    );
  }

  function eventBinding() {
    return cloneBinding(activeRun);
  }

  function broadcast(eventName, payload, options = {}) {
    const at = new Date().toISOString();
    const binding = options.binding === undefined ? null : cloneBinding(options.binding);
    const taskId = options.taskId !== undefined
      ? options.taskId
      : binding?.taskId ?? null;
    const runId = options.runId !== undefined
      ? options.runId
      : binding?.runId ?? null;
    const runEpoch = options.runEpoch !== undefined
      ? options.runEpoch
      : binding?.runEpoch ?? null;
    const attribution = options.attribution || (binding ? "pi_run_bound" : "none");

    const wrapper = {
      type: eventName,
      task_id: taskId ?? null,
      run_id: runId ?? null,
      run_epoch: runEpoch ?? null,
      attribution,
      data: payload,
      at,
    };
    const frame = `event: ${eventName}\ndata: ${JSON.stringify(wrapper)}\n\n`;
    for (const res of [...sseClients]) {
      try {
        res.write(frame);
      } catch {
        sseClients.delete(res);
      }
    }
  }

  function emitTask(bindingOverride = undefined) {
    if (!controlledTask) return;
    const binding = bindingOverride === undefined
      ? (activeRun || (controlRun ? {
          taskId: controlRun.taskId,
          runId: controlRun.runId,
          runEpoch: controlRun.lastEpoch || 1,
        } : null))
      : bindingOverride;
    const snapshot = taskSnapshot(controlledTask, controlRun, activeRun);
    broadcast("task", snapshot, {
      taskId: controlledTask.id,
      runId: binding?.runId ?? snapshot.runId ?? null,
      runEpoch: binding?.runEpoch ?? snapshot.runEpoch ?? null,
      attribution: "task_state",
    });
  }

  function finishTask(status, error = undefined) {
    if (!controlledTask || ["completed", "failed", "cancelled"].includes(controlledTask.status)) return;
    controlledTask.status = status;
    controlledTask.endedAt = new Date().toISOString();
    if (error) controlledTask.error = String(error);
    emitTask();
  }

  function failCorrelation(reason) {
    if (controlledTask && !["completed", "failed", "cancelled"].includes(controlledTask.status)) {
      finishTask("failed", reason);
    }
    pendingDispatch = null;
    awaitingAgentStart = null;
    armedAgentStart = null;
  }


  function statusSnapshot() {
    const snapshot = controlledTask
      ? taskSnapshot(controlledTask, controlRun, activeRun)
      : { status: "idle" };

    return {
      ...snapshot,
      sessionReady,
      sessionTransitioning,
      sessionInstanceId,
    };
  }

  function ensureServerListening() {
    if (serverListening) return Promise.resolve();

    return new Promise((resolve, reject) => {
      const onError = (error) => {
        server.off("error", onError);
        reject(error);
      };

      server.once("error", onError);

      server.listen(port, HOST, () => {
        server.off("error", onError);
        serverListening = true;
        console.log(`[pi-control] Listening on http://${HOST}:${port}`);

        if (!token) {
          console.error(`[pi-control] controlToken is missing in ${CONFIG_PATH}; all HTTP requests will be unauthorized.`);
        }

        resolve();
      });
    });
  }

  pi.registerCommand("pi-control-new", {
    description: "Start a new Pi session for the local Jack orchestration bridge",
    handler: async (_args, ctx) => {
      try {
        const result = await ctx.newSession();

        // A cancelled replacement leaves this extension instance authoritative.
        // Reopen admission, but retain the same sessionInstanceId so a supervisor
        // cannot mistake cancellation for successful session replacement.
        if (result?.cancelled) {
          sessionTransitioning = false;
          sessionReady = true;
        }
      } catch (error) {
        sessionTransitioning = false;
        sessionReady = true;
        throw error;
      }
    },
  });

  pi.on("session_start", async (event, ctx) => {
    latestCtx = ctx;
    sessionTransitioning = false;

    // Pi binds extension action methods before this lifecycle boundary.
    // Do not expose the HTTP control listener during extension loading.
    await ensureServerListening();
    sessionReady = true;

    broadcast("session", event, { attribution: "none" });
  });

  // Pi 0.84.2 exposes input source="extension" for pi.sendUserMessage().
  // The private marker makes this specific dispatch distinguishable from every
  // other extension-originated message, even when the visible prompts are equal.
  pi.on("input", async (event, ctx) => {
    latestCtx = ctx;
    if (!pendingDispatch || event?.source !== "extension") return;

    const decoded = decodeWirePrompt(event?.text);
    if (!decoded || decoded.runId !== pendingDispatch.runId) return;

    const pending = pendingDispatch;
    pendingDispatch = null;

    // A queued task can be cancelled before Pi consumes its follow-up message.
    // In that case swallow only the exact privately-marked input. No model run
    // starts and the cancellation remains truthful.
    if (controlledTask?.id !== pending.taskId || controlledTask?.status === "cancelled") {
      return { action: "handled" };
    }

    if (decoded.prompt !== pending.prompt) {
      failCorrelation("controlled input correlation mismatch");
      return { action: "handled" };
    }

    awaitingAgentStart = {
      taskId: pending.taskId,
      runId: pending.runId,
      runEpoch: 1,
    };

    // Strip the private correlation marker before skill/template expansion,
    // persistence, system/context construction, and model inference.
    return { action: "transform", text: pending.prompt };
  });

  pi.on("before_agent_start", async (_event, ctx) => {
    latestCtx = ctx;
    if (!awaitingAgentStart) return;
    armedAgentStart = cloneBinding(awaitingAgentStart);
    awaitingAgentStart = null;
  });

  pi.on("agent_start", async (_event, ctx) => {
    latestCtx = ctx;
    activeCtx = ctx;

    if (armedAgentStart) {
      const binding = cloneBinding(armedAgentStart);
      armedAgentStart = null;
      if (controlledTask?.id !== binding.taskId || controlledTask?.status !== "queued") {
        failCorrelation("controlled task/run binding became invalid before agent_start");
        activeRun = null;
        return;
      }
      controlRun = {
        taskId: binding.taskId,
        runId: binding.runId,
        lastEpoch: 1,
      };
      activeRun = binding;
      controlledTask.runId = binding.runId;
      controlledTask.runEpoch = 1;
      controlledTask.status = "running";
      emitTask(binding);
      return;
    }

    // Automatic retry / compaction retry / queued continuation belonging to a
    // still-open controlled run receives a fresh low-level epoch under the same
    // immutable control-run identity. A new controlled task cannot overlap this.
    if (controlRun && controlledTask?.id === controlRun.taskId &&
        ["running", "settling", "cancelled"].includes(controlledTask.status)) {
      const nextEpoch = Number(controlRun.lastEpoch || 0) + 1;
      controlRun.lastEpoch = nextEpoch;
      activeRun = {
        taskId: controlRun.taskId,
        runId: controlRun.runId,
        runEpoch: nextEpoch,
      };
      controlledTask.runEpoch = nextEpoch;
      return;
    }

    // This is an unrelated Pi run. It gets no controlled task attribution.
    activeRun = null;
  });

  pi.on("message_update", async (event, ctx) => {
    latestCtx = ctx;
    const binding = eventBinding();
    broadcast("message", event, { binding });
  });

  pi.on("message_end", async (event, ctx) => {
    latestCtx = ctx;
    const binding = eventBinding();
    if (binding && controlledTask?.id === binding.taskId && event?.message?.role === "assistant") {
      controlledTask.final = event.message;
      const failure = assistantFailure(event.message);
      if (failure) {
        controlledTask.error = failure;
      } else if (["running", "settling"].includes(controlledTask.status)) {
        // Pi can retry the same controlled operation after a transient assistant
        // transport/generation failure. A later successful run-bound assistant
        // completion supersedes that earlier assistant failure. Deterministic
        // task-level failures are already terminal and therefore are not cleared.
        controlledTask.error = undefined;
      }
    }
    broadcast("message_end", event, { binding });
  });

  pi.on("tool_execution_start", async (event, ctx) => {
    latestCtx = ctx;
    const binding = eventBinding();
    broadcast("tool_start", event, { binding });
  });

  pi.on("tool_execution_update", async (event, ctx) => {
    latestCtx = ctx;
    const binding = eventBinding();
    broadcast("tool_update", event, { binding });
  });

  pi.on("tool_execution_end", async (event, ctx) => {
    latestCtx = ctx;
    const binding = eventBinding();
    if (binding && controlledTask?.id === binding.taskId && event?.isError) {
      controlledTask.toolErrors.push({
        name: event?.toolName ?? "unknown",
        result: event?.result ?? null,
      });
    }
    broadcast("tool_end", event, { binding });
  });

  pi.on("agent_end", async (_event, ctx) => {
    latestCtx = ctx;
    activeCtx = ctx;
    const endingBinding = eventBinding();

    if (endingBinding && controlRun?.runId === endingBinding.runId) {
      controlRun.lastEpoch = endingBinding.runEpoch;
      if (controlledTask?.id === endingBinding.taskId && controlledTask.status === "running") {
        controlledTask.status = "settling";
        emitTask(endingBinding);
      }
    }

    // Pi documents agent_end as the end of that low-level run. Clearing here is
    // what prevents a delayed/unowned event after agent_end from inheriting the
    // task ID merely because the higher-level controlled task has not settled.
    activeRun = null;
  });

  pi.on("agent_settled", async (_event, ctx) => {
    latestCtx = ctx;
    const settledRun = controlRun ? {
      taskId: controlRun.taskId,
      runId: controlRun.runId,
      runEpoch: controlRun.lastEpoch || 1,
    } : null;

    controlRun = null;
    activeRun = null;

    if (controlledTask && settledRun && controlledTask.id === settledRun.taskId) {
      controlledTask.settledAt = new Date().toISOString();
      if (controlledTask.status === "cancelled") {
        emitTask(settledRun);
      } else if (["running", "settling"].includes(controlledTask.status)) {
        if (controlledTask.error) {
          finishTask("failed", controlledTask.error);
        } else if (controlledTask.toolErrors.length > 0) {
          finishTask("failed", "one or more tool executions failed");
        } else {
          finishTask("completed");
        }
      }
    }

    activeCtx = null;
  });

  pi.on("session_shutdown", async (event, ctx) => {
    latestCtx = ctx;
    sessionReady = false;
    sessionTransitioning = true;
    broadcast("session", event, { attribution: "none" });
    if (shuttingDown) return;
    shuttingDown = true;
    for (const res of [...sseClients]) {
      try { res.end(); } catch {}
    }
    sseClients.clear();
    if (server && serverListening) {
      await new Promise((resolve) => server.close(() => resolve()));
      serverListening = false;
    }
  });

  server = http.createServer(async (req, res) => {
    try {
      const authorization = req.headers.authorization || "";
      if (!token || authorization !== `Bearer ${token}`) {
        json(res, 401, { error: "unauthorized" });
        return;
      }

      const requestUrl = new URL(req.url || "/", `http://${HOST}:${port}`);
      const pathname = requestUrl.pathname;

      if (req.method === "GET" && pathname === "/v1/status") {
        json(res, 200, statusSnapshot());
        return;
      }

      if (req.method === "GET" && pathname === "/v1/events") {
        res.writeHead(200, {
          "Content-Type": "text/event-stream; charset=utf-8",
          "Cache-Control": "no-cache, no-transform",
          "Connection": "keep-alive",
          "X-Accel-Buffering": "no",
        });
        const snapshot = statusSnapshot();
        res.write(`event: status\ndata: ${JSON.stringify(snapshot)}\n\n`);
        sseClients.add(res);
        const cleanup = () => sseClients.delete(res);
        req.on("close", cleanup);
        req.on("error", cleanup);
        return;
      }

      if (req.method === "POST" && pathname === "/v1/tasks") {
        let body;
        try {
          body = await parseJsonBody(req);
        } catch {
          json(res, 400, { error: "invalid JSON body" });
          return;
        }
        const prompt = typeof body?.prompt === "string" ? body.prompt.trim() : "";
        if (!prompt) {
          json(res, 400, { error: "prompt must be a non-empty string" });
          return;
        }
        if (!sessionReady || sessionTransitioning) {
          json(res, 409, {
            error: "Pi session transition in progress",
            sessionReady,
            sessionTransitioning,
            sessionInstanceId,
          });
          return;
        }
        if (controlPlaneBusy()) {
          json(res, 409, { error: "controlled task already active or prior run not yet settled" });
          return;
        }

        const taskId = randomUUID();
        const runId = randomUUID();
        controlledTask = {
          id: taskId,
          status: "queued",
          createdAt: new Date().toISOString(),
          endedAt: undefined,
          settledAt: undefined,
          toolErrors: [],
          final: null,
          error: undefined,
          runId: null,
          runEpoch: null,
        };
        pendingDispatch = {
          taskId,
          runId,
          prompt,
        };
        emitTask();

        try {
          pi.sendUserMessage(makeWirePrompt(runId, prompt), { deliverAs: "followUp" });
        } catch (error) {
          pendingDispatch = null;
          finishTask("failed", error instanceof Error ? error.message : String(error));
          json(res, 500, taskSnapshot(controlledTask, controlRun, activeRun));
          return;
        }

        json(res, 202, taskSnapshot(controlledTask, controlRun, activeRun));
        return;
      }

      if (req.method === "POST" && pathname === "/v1/tasks/cancel") {
        if (!taskCanCancel(controlledTask)) {
          json(res, 409, { error: "no active controlled task" });
          return;
        }
        try {
          activeCtx?.abort?.();
        } catch {}
        controlledTask.status = "cancelled";
        controlledTask.endedAt = new Date().toISOString();
        emitTask();
        json(res, 202, taskSnapshot(controlledTask, controlRun, activeRun));
        return;
      }

      if (req.method === "POST" && pathname === "/v1/session/new") {
        if (!sessionReady || sessionTransitioning) {
          json(res, 409, {
            error: "Pi session transition in progress",
            sessionReady,
            sessionTransitioning,
            sessionInstanceId,
          });
          return;
        }
        if (controlPlaneBusy() || (latestCtx?.isIdle && !latestCtx.isIdle())) {
          json(res, 409, { error: "Pi is not idle" });
          return;
        }

        const previousSessionInstanceId = sessionInstanceId;
        sessionReady = false;
        sessionTransitioning = true;

        try {
          pi.sendUserMessage("/pi-control-new", { expandPromptTemplates: true });
        } catch (error) {
          sessionTransitioning = false;
          sessionReady = true;
          json(res, 500, { error: error instanceof Error ? error.message : String(error) });
          return;
        }

        json(res, 202, {
          status: "starting",
          sessionReady: false,
          sessionTransitioning: true,
          previousSessionInstanceId,
        });
        return;
      }

      json(res, 404, { error: "not found" });
    } catch (error) {
      if (!res.headersSent) {
        json(res, 500, { error: error instanceof Error ? error.message : String(error) });
      } else {
        try { res.end(); } catch {}
      }
    }
  });

  server.on("error", (error) => {
    console.error(`[pi-control] Server error on ${HOST}:${port}:`, error);
  });

}
