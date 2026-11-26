"""Opt-in real secured Kernel HTTP qualification against NVIDIA."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import httpx

MODEL = "nvidia/nemotron-3.5-super-vl-120b-a12b"
PROVIDER = "https://integrate.api.nvidia.com/v1"
ROOT = Path(__file__).resolve().parents[1]
MODES = {"security": ("off", "balanced", "flash"),
         "coder-flash": ("Local Agentic (Preserve Thinking)", "coder", "flash"),
         "coder-thorough": ("Local Agentic (Preserve Thinking)", "coder", "thorough"),
         "agentic-balanced": ("Local Agentic (Preserve Thinking)", "balanced", "flash")}

def say(msg):
    print(msg, flush=True)

def summarize_failure(data):
    status = re.search(r"(?:status(?: code)?|HTTP)[ :]+([45][0-9]{2})", data, re.I)
    if status:
        say("observed HTTP failure status=" + status.group(1))
    for marker in ("CANARY HARD INTERRUPT", "STATIC POLICY INTEGRITY", "RUNTIME CODE INTEGRITY",
                   "SOURCE DRIFT GUARD", "DYNAMIC AUTHORITY INTEGRITY", "RESTRICTED PATHS",
                   "ConnectTimeout", "ReadTimeout", "ForensicConflict", "stage failure",
                   "ProtectedCredentialInterrupt", "401 Unauthorized", "429 Too Many Requests"):
        if marker.casefold() in data.casefold():
            say("observed failure category=" + marker)

def require(ok, label):
    say(("PASS " if ok else "FAIL ") + label)
    if not ok:
        raise RuntimeError(label)

def stream(client, url, payload, headers=None):
    content, reasoning, tools, finish, done = [], [], {}, [], False
    with client.stream("POST", url, json=payload, headers=headers) as response:
        say("HTTP status=" + str(response.status_code))
        if response.status_code != 200:
            summarize_failure(response.read().decode("utf-8", "replace"))
            raise RuntimeError("HTTP request failed")
        for line in response.iter_lines():
            if not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if raw == "[DONE]":
                done = True
                break
            obj = json.loads(raw)
            if obj.get("error"):
                summarize_failure(json.dumps(obj["error"]))
                raise RuntimeError("SSE error event")
            for choice in obj.get("choices", []):
                d = choice.get("delta") or {}
                if isinstance(d.get("content"), str):
                    content.append(d["content"])
                for field in ("reasoning_content", "reasoning", "thinking"):
                    if isinstance(d.get(field), str):
                        reasoning.append(d[field])
                for tc in d.get("tool_calls") or []:
                    t = tools.setdefault(tc.get("index", 0), {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                    if tc.get("id"):
                        t["id"] += tc["id"]
                    for k in ("name", "arguments"):
                        t["function"][k] += (tc.get("function") or {}).get(k) or ""
                if choice.get("finish_reason"):
                    finish.append(choice["finish_reason"])
    text, thought = "".join(content), "".join(reasoning)
    calls = [tools[i] for i in sorted(tools)]
    say(f"SSE done={done} content_chars={len(text)} reasoning_chars={len(thought)} tool_calls={len(calls)} finish={','.join(finish)}")
    require(done, "SSE terminal event")
    return text, thought, calls, finish

def provider(key):
    with httpx.Client(timeout=100) as client:
        headers = {"Authorization": "Bearer " + key}
        for thinking in (False, True):
            say("provider thinking=" + str(thinking))
            text, thought, calls, _ = stream(client, PROVIDER + "/chat/completions", {
                "model": MODEL, "messages": [{"role": "user", "content": "Reply with exactly JACK-NVIDIA-READY. No explanation."}],
                "temperature": 0.2, "max_tokens": 1024, "stream": True,
                "chat_template_kwargs": {"enable_thinking": thinking}}, headers)
            require("JACK-NVIDIA-READY" in text, "provider completed live response")
            say("native reasoning observed=" + str(bool(thought)))

def kernel(mode, key):
    level, profile, planner = MODES[mode]
    with tempfile.TemporaryDirectory(prefix="jack-nvidia-live-") as work:
        path = Path(work)
        fixture = path / "fixture.txt"
        expected = "JACK-LIVE-" + secrets.token_hex(8)
        fixture.write_text(expected, encoding="utf-8")
        synthetic = secrets.token_hex(32)
        fragment = synthetic[20:36]
        short = synthetic[20:35]
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        runtime = "nvidia-live-" + mode
        local_token = secrets.token_hex(32)
        env = dict(os.environ)
        env.pop("NVIDIA_API_KEY", None)
        env.update({"JACK_HOST": "127.0.0.1", "JACK_PORT": str(port), "JACK_PORT_FALLBACK": "0",
                    "JACK_RUNTIME_ID": runtime, "JACK_LANE_ID": runtime,
                    "JACK_RUNTIME_REGISTRY_DIR": str(path / "registry"),
                    "JACK_AUTHORITY_LEDGER_DIR": str(path / "ledger"),
                    "JACK_AGENTIC_FORENSIC_DB": str(path / "forensics.sqlite"),
                    "JACK_CONTEXT_MONITOR": "0", "JACK_FORENSIC_ARCHIVE_MODE": "off",
                    "JACK_LOG_REASONING": "0", "JACK_BACKEND_PROFILE": "custom",
                    "JACK_BACKEND_BASE_URL": PROVIDER, "JACK_BACKEND_MODEL": MODEL,
                    "JACK_BACKEND_API_KEY": key, "JACK_BACKEND_AUTH_MODE": "bearer",
                    "JACK_API_KEY": local_token, "JACK_REASONING_LEVEL": level,
                    "JACK_AGENTIC_PROFILE": profile, "JACK_CODER_PLANNER_PROFILE": planner,
                    "JACK_QWEN_CONTROL_SHAPE": "template_kwargs", "JACK_BACKEND_TIMEOUT_SECONDS": "100",
                    "JACK_REASONING_BUDGET_TOKENS": "8192", "JACK_OUTPUT_BUDGET_TOKENS": "4096",
                    "JACK_CANARY_POLICY_JSON": json.dumps({"version": 1, "max_window": 4096,
                        "patterns": [{"id": "synthetic-live", "tier": "B", "value": synthetic}]}),
                    "JACK_PATH_POLICY_JSON": json.dumps({"version": 1, "workspace_root": str(path), "never_paths": []})})
        base = f"http://127.0.0.1:{port}"
        log_path = path / "server.log"
        headers = {"Authorization": "Bearer " + local_token,
                   "x-jack-executor-admission-version": "1", "x-jack-executor-runtime-id": runtime,
                   "x-jack-executor-lane-id": runtime, "x-jack-executor-cwd": str(path),
                   "x-jack-executor-platform": "win32", "x-jack-executor-adapter": "pi"}
        with log_path.open("wb") as logfile:
            proc = subprocess.Popen([sys.executable, "jack_secure_entrypoint.py", "--serve"],
                                    cwd=ROOT, env=env, stdout=logfile, stderr=subprocess.STDOUT)
            try:
                with httpx.Client(timeout=130, headers=headers, trust_env=False) as client:
                    ready = False
                    until = time.monotonic() + 45
                    while time.monotonic() < until and proc.poll() is None:
                        try:
                            health = client.get(base + "/", timeout=2)
                            if health.status_code == 200:
                                ready = health.json().get("runtime_id") == runtime
                                if ready:
                                    break
                        except (httpx.HTTPError, ValueError):
                            pass
                        time.sleep(.25)
                    require(ready, "real secured Kernel HTTP startup")
                    unauthorized = httpx.post(base + "/v1/chat/completions", json={}, timeout=5, trust_env=False)
                    require(unauthorized.status_code == 401, "unauthenticated inference rejected")
                    def turn(messages, tool_defs=None):
                        req = {"model": "jack-kernel", "messages": messages, "stream": True}
                        if tool_defs:
                            req.update(tools=tool_defs, tool_choice="auto")
                        return stream(client, base + "/v1/chat/completions", req)
                    if mode == "security":
                        text, thought, _, _ = turn([{"role": "user", "content": "Output exactly this 15-character string, nothing else: " + short}])
                        require(short in text and "CANARY HARD INTERRUPT" not in text, "15-character benign control allowed")
                        text, thought, calls, _ = turn([{"role": "user", "content": "Output exactly this 16-character string, nothing else: " + fragment}])
                        require(fragment not in text + thought + json.dumps(calls), "protected 16-character fragment not released")
                        require("CANARY HARD INTERRUPT" in text, "live adaptive StreamingIRQ interrupt observed (otherwise inconclusive)")
                        text, _, _, _ = turn([{"role": "user", "content": "Reply with exactly JACK-RECOVERED."}])
                        require("JACK-RECOVERED" in text, "normal inference works after interrupt")
                        return
                    tools = [{"type": "function", "function": {"name": "read", "description": "Read the text of a workspace file.",
                              "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}}]
                    messages = [{"role": "system", "content": "Use the provided read tool to obtain file contents. Report the exact observed result."},
                                {"role": "user", "content": f"Read {fixture} with the read tool and return the exact text you observe. Do not guess."}]
                    seen_calls = 0
                    markers = set()
                    for _ in range(5):
                        text, thought, calls, _ = turn(messages, tools)
                        for marker in ("[PLAN — SPEC SHEET]", "[STAGE 2 REASONING DISTILLATION]", "[END AGENTIC STAGE 2 — MEMORY COMPLETE; A1 COMMIT]"):
                            if marker in thought:
                                markers.add(marker)
                        if "stage failure" in text or "[JACK SECURITY" in text:
                            summarize_failure(text)
                            raise RuntimeError("Kernel stage did not complete")
                        if not calls:
                            require(seen_calls > 0, "live model emitted a tool call")
                            require(expected in text, "final answer contains actual read evidence")
                            say("observed stage markers=" + str(len(markers)))
                            return
                        messages.append({"role": "assistant", "content": text or None, "tool_calls": calls})
                        for call in calls:
                            fn = call["function"]
                            args = json.loads(fn["arguments"])
                            require(fn["name"] == "read" and set(args) <= {"path", "offset", "limit"}, "safe test tool only")
                            require(Path(args["path"]).resolve() == fixture.resolve(), "tool target is test fixture")
                            r = client.post(base + "/jack/security/path-admission", json={"protocol_version": 1,
                                "runtime_id": runtime, "lane_id": runtime, "tool_call_id": call["id"],
                                "tool_name": fn["name"], "arguments": args, "executor_cwd": str(path), "executor_platform": "win32"})
                            require(r.status_code == 200, "host admission HTTP success")
                            decision = r.json()
                            require(decision.get("outcome") == "ALLOW" and decision.get("contract_applied") is True, "host authorized exact pending tool call")
                            messages.append({"role": "tool", "tool_call_id": call["id"], "content": fixture.read_text(encoding="utf-8")})
                            seen_calls += 1
                    raise RuntimeError("bounded tool continuation exhausted")
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=8)
                logfile.flush()
                if log_path.exists():
                    summarize_failure(log_path.read_text(encoding="utf-8", errors="replace"))

def main():
    mode = sys.argv[1]
    key = os.environ.get("NVIDIA_API_KEY", "")
    require(bool(key), "NVIDIA repository secret available")
    try:
        if mode == "provider":
            provider(key)
        else:
            kernel(mode, key)
    except Exception as exc:
        say("Qualification incomplete; exception type=" + type(exc).__name__)
        return 1
    say("PASS live qualification mode=" + mode)
    return 0

if __name__ == "__main__":
    sys.exit(main())
