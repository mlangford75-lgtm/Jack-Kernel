"""Jack Context Monitor: independent, observational Windows telemetry window.

No inference requests, agent actions, output/token heuristics, or model-context
changes. Only reads Jack's already authenticated /jack/runtime/status endpoint.
The monitor is a separate process: closing/crashing it cannot stop the Kernel.

Backend usage from streamed Chat Completions is typically reported at EOS.
Those numbers describe a completed request, NOT exact live KV-cache occupancy.
"""
from __future__ import annotations

import json
import math
import os
import queue
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple


POLL_MS = 1500
HTTP_TIMEOUT_SECONDS = 1.1
MAX_STATUS_BYTES = 262144
BACKGROUND = "#101925"
SURFACE = "#1A2838"
TEXT = "#E9F2FA"
MUTED = "#9CB0C2"
ACCENT = "#55C7DC"
GOOD = "#77C4A3"
WARN = "#EAC078"


def _nonnegative(value: Any) -> Optional[int]:
    """Reject booleans and fabricated string/floating-point token counts."""
    return value if type(value) is int and value >= 0 else None


def _usage_from(entry: Any) -> Optional[Tuple[str, int]]:
    if not isinstance(entry, dict):
        return None
    for key, kind in (
        ("backend_total_tokens", "request total"),
        ("backend_prompt_tokens", "prompt only"),
        ("last_backend_total_tokens", "request total"),
        ("last_backend_prompt_tokens", "prompt only"),
    ):
        n = _nonnegative(entry.get(key))
        if n is not None:
            return kind, n
    return None


def interpret_status(
    payload: Dict[str, Any], previous: Optional[Dict[str, Any]] = None,
    *, observed_at: Optional[float] = None,
) -> Dict[str, Any]:
    """Pure, monotonic presentation: never pass an estimate off as server usage."""
    if not isinstance(payload, dict):
        raise ValueError("Jack status must be an object")
    now = time.time() if observed_at is None else float(observed_at)
    capacity = _nonnegative(payload.get("context_length"))
    if capacity == 0:
        capacity = None
    requests = payload.get("requests")
    if not isinstance(requests, list):
        requests = []
    active = next(
        (x for x in requests if isinstance(x, dict) and x.get("backend_request_active") is True),
        None,
    )
    if active is None:
        active = next((x for x in requests if isinstance(x, dict)), None)
    last_request = payload.get("last_request")
    if not isinstance(last_request, dict):
        last_request = None

    current = _usage_from(active)
    last = _usage_from(last_request)
    kind = None
    tokens = None
    measured_at = None
    origin = "unknown"
    if current is not None:
        kind, tokens = current
        if isinstance(active, dict) and (
            _nonnegative(active.get("backend_total_tokens")) is not None
            or _nonnegative(active.get("backend_prompt_tokens")) is not None
        ):
            measured_at = now
            origin = "this request"
        else:
            # A resumed backend call may retain the prior generation's final
            # usage inside last_backend_*. That is historical, not live.
            measured_at = previous.get("measured_at") if isinstance(previous, dict) else None
            origin = "previous backend request"
    elif last is not None:
        kind, tokens = last
        measured_at = last_request.get("ended_at_unix")
        if not isinstance(measured_at, (int, float)) or not math.isfinite(measured_at):
            measured_at = now
        origin = "last completed request"
    elif isinstance(previous, dict) and _nonnegative(previous.get("tokens")) is not None:
        kind = previous.get("kind")
        tokens = previous["tokens"]
        measured_at = previous.get("measured_at")
        origin = "last confirmed reading"

    status = "active" if active is not None else "idle"
    phase = str((active or {}).get("backend_stream_phase") or "idle")
    stage = str((active or {}).get("stage") or "—")
    if status == "active" and phase == "waiting_backend":
        phase = "waiting on model"
    reason = str(payload.get("telemetry_status") or "unknown")
    return {
        "runtime_id": str(payload.get("runtime_id") or ""),
        "model": str(payload.get("backend_model") or "Not yet resolved"),
        "profile": str(payload.get("reasoning_level") or "—"),
        "capacity": capacity,
        "capacity_source": str(payload.get("context_length_source") or "unknown"),
        "source": str(payload.get("context_usage_source") or "unknown"),
        "status": status,
        "phase": phase,
        "stage": stage,
        "telemetry": reason,
        "kind": kind,
        "tokens": tokens,
        "origin": origin,
        "measured_at": measured_at,
    }


def _status_url_and_token(environ: Dict[str, str]) -> Tuple[str, str, str]:
    """Fixed loopback URL; no user-controlled remote telemetry destinations."""
    raw_port = str(environ.get("JACK_CONTEXT_MONITOR_PORT", ""))
    if not raw_port.isascii() or not raw_port.isdecimal():
        raise ValueError("Monitor port must be numeric")
    port = int(raw_port)
    if not (1 <= port <= 65535):
        raise ValueError("Monitor port is outside the TCP range")
    runtime_id = str(environ.get("JACK_CONTEXT_MONITOR_RUNTIME_ID") or "").strip()
    if not runtime_id:
        raise ValueError("Monitor runtime identity is required")
    return f"http://127.0.0.1:{port}/jack/runtime/status", (
        str(environ.get("JACK_CONTEXT_MONITOR_TOKEN") or "")
    ), runtime_id


def read_status(url: str, token: str, expected_runtime_id: str) -> Dict[str, Any]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers, method="GET")
    # Never forward the local Jack credential through a configured proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        raw = response.read(MAX_STATUS_BYTES + 1)
    if len(raw) > MAX_STATUS_BYTES:
        raise ValueError("Jack status response exceeded monitor telemetry limit")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("Jack status did not contain an object")
    if payload.get("runtime_id") != expected_runtime_id:
        raise ValueError("Jack runtime identity mismatch; refusing telemetry")
    return payload


def format_number(value: Optional[int]) -> str:
    return f"{value:,}" if value is not None else "—"


def create_window(*, url: str, token: str, runtime_id: str) -> None:
    # Import GUI dependencies only in the child monitor process. Kernel and
    # headless test runners never import tkinter.
    import tkinter as tk

    root = tk.Tk()
    root.title("Jack — LLM Context Monitor")
    root.geometry("560x400")
    root.minsize(500, 370)
    root.configure(bg=BACKGROUND)
    root.attributes("-topmost", False)

    def label(parent, text, size=11, fg=TEXT, weight="normal"):
        return tk.Label(parent, text=text, bg=BACKGROUND, fg=fg,
                        font=("Segoe UI", size, weight), anchor="w")

    pad = tk.Frame(root, bg=BACKGROUND, padx=24, pady=18)
    pad.pack(fill="both", expand=True)
    label(pad, "JACK  /  LLM CONTEXT MONITOR", 13, ACCENT, "bold").pack(anchor="w")
    model = label(pad, "Waiting for Jack...", 11, MUTED)
    model.pack(anchor="w", pady=(8, 14))
    usage_text = label(pad, "— / — tokens", 25, TEXT, "bold")
    usage_text.pack(anchor="w")
    status_text = label(pad, "Awaiting server telemetry", 10, MUTED)
    status_text.pack(anchor="w", pady=(0, 12))
    bar = tk.Canvas(pad, height=15, bg=SURFACE, highlightthickness=0, bd=0)
    bar.pack(fill="x")
    detail = label(pad, "Not a live KV-cache occupancy measurement", 9, MUTED)
    detail.pack(anchor="w", pady=(7, 16))
    stage_label = label(pad, "Stage: —", 10)
    stage_label.pack(anchor="w", pady=3)
    source_label = label(pad, "Capacity source: unknown", 10, MUTED)
    source_label.pack(anchor="w", pady=3)
    fresh_label = label(pad, "Last confirmed usage: —", 10, MUTED)
    fresh_label.pack(anchor="w", pady=3)
    connectivity = label(pad, "Connecting...", 10, WARN)
    connectivity.pack(anchor="w", pady=(13, 0))
    label(pad, "Read-only · Close this window without affecting Jack",
          9, MUTED).pack(anchor="w", pady=(9, 0))

    updates: queue.SimpleQueue = queue.SimpleQueue()
    stop = threading.Event()
    busy = False
    last_confirmed: Optional[Dict[str, Any]] = None
    width = 480
    latest_fraction = 0.0

    def paint(event=None):
        nonlocal width
        if event is not None:
            width = max(1, int(event.width))
        bar.delete("all")
        bar.create_rectangle(0, 0, width, 15, fill=SURFACE, outline=SURFACE)
        if latest_fraction > 0:
            bar.create_rectangle(0, 0, int(width * latest_fraction), 15,
                                 fill=ACCENT, outline=ACCENT)
    bar.bind("<Configure>", paint)

    def render(reading: Dict[str, Any]) -> None:
        nonlocal latest_fraction
        tokens = reading["tokens"]
        capacity = reading["capacity"]
        model.configure(text=reading["model"][:95] + "  ·  " + reading["profile"][:45])
        usage_text.configure(text=f"{format_number(tokens)} / {format_number(capacity)}")
        if tokens is None:
            status_text.configure(text="Current context usage unavailable")
            latest_fraction = 0.0
        else:
            status_text.configure(
                text=f"Backend-reported {reading['kind']} · {reading['origin']}"
            )
            latest_fraction = min(1.0, tokens / capacity) if capacity else 0.0
        paint()
        stage_label.configure(
            text=f"Activity: {reading['status']} · {reading['stage']} · {reading['phase']}"
        )
        source_label.configure(
            text=f"Capacity source: {reading['capacity_source']}  |  Usage: {reading['source']}"
        )
        measured_at = reading.get("measured_at")
        if isinstance(measured_at, (int, float)) and math.isfinite(measured_at):
            age = max(0, int(time.time() - measured_at))
            fresh_label.configure(text=f"Last confirmed usage: {age}s ago")
        else:
            fresh_label.configure(text="Last confirmed usage: unavailable")
        connectivity.configure(
            text="Connected · actual backend values when supplied",
            fg=GOOD if reading["telemetry"] == "ok" else WARN,
        )

    def fetch_once():
        try:
            updates.put(("ok", read_status(url, token, runtime_id)))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            updates.put(("error", type(exc).__name__))
        except Exception:
            updates.put(("error", "Telemetry unavailable"))

    def tick():
        nonlocal busy, last_confirmed
        if stop.is_set():
            return
        try:
            while True:
                kind, payload = updates.get_nowait()
                busy = False
                if kind == "ok":
                    reading = interpret_status(payload, last_confirmed)
                    last_confirmed = reading if reading.get("tokens") is not None else last_confirmed
                    render(reading)
                else:
                    connectivity.configure(text=f"Telemetry offline ({payload}) · Jack unaffected", fg=WARN)
        except queue.Empty:
            pass
        if not busy:
            busy = True
            threading.Thread(target=fetch_once, daemon=True, name="JackContextMonitorPoll").start()
        root.after(POLL_MS, tick)

    def close():
        stop.set()
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", close)
    root.after(100, tick)
    root.mainloop()


def main() -> int:
    url, token, runtime_id = _status_url_and_token(dict(os.environ))
    create_window(url=url, token=token, runtime_id=runtime_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
