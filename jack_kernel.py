#!/usr/bin/env python3
"""
Jack Kernel
===========

Jack Kernel is a deterministic inference-control runtime between an agent/client
and an OpenAI-compatible model backend. The agent chooses the task and workflow;
the model supplies probabilistic cognition; Jack controls the inference
environment: stage topology, reasoning/sampling, tool authority, context
projection, commit/freeze authority, retention, and host-side execution policy.
The bundled modes are reference programs, not the product boundary.

Deep Research is a three-stage Preserve-Thinking think-longer program intended especially
for smaller, short-reasoning, flash-class, or drift-prone models. Thesis plans
at X-High @ 0.85 with no tool surface. Antithesis asks only the strongest
material adversarial questions at Medium @ 0.70 with tools off. Synthesis runs
at X-High @ 0.70, receives caller tools when supplied, decides independently,
and is the sole authoritative reasoning/execution/final-answer stage. Full
active cognition is preserved through Synthesis; only Stage-1/Stage-2 native
reasoning is retired on later re-entry. Deep Research emits no Jack XML.

Agentic is the Qwen-oriented Preserve-Thinking semantic-consolidation program.
Stage 1 receives full native cognition and caller tools, produces A1, and freezes
that exact answer. Stage 2 has tools off and zero answer authority; while the
immediately preceding Stage-1 reasoning/tool episode is still preserved, it
re-encodes the future-relevant epistemic residue into strongly semantic
grounding/verification/challenge/audit Jack XML. The durable turn is exact user
message + Jack XML + exact frozen A1; completed raw native cognition and consumed
tool protocol are retired. Preserve Thinking is the short-lived Stage-1 ->
Stage-2 bridge, not the cross-turn memory mechanism, and semantic capability is
required in addition to transport compatibility.

Code Debugging is a separate user-guided intake plus five-pass fresh-context forensic audit loop.
Before Pass 1, Jack records the user's request in a tools-off diagnostic intake. The intake is non-blocking by default:
user-supplied information is sufficient, optional clarification may occur when materially useful, and any instruction
to proceed immediately closes intake. Native intake reasoning and visible output use the normal live streaming surface,
but only user-origin intake becomes durable Pass 0; assistant intake dialogue and native intake reasoning are pruned at
the boundary. Each configured-effort pass then reads the bundled Debugging instructions,
receives the exact user-origin Pass 0 intake on every fresh pass plus, for Passes 2-5, a bounded host-derived
registry of all already committed prior findings, independently inspects the unchanged target code, surveys the same full
professional code-review category set, and then audits exactly one candidate problem. Full prior handoffs,
repair guidance, residual observations, and raw cognition remain disk-only between completed passes; only the
compact host-derived registry of already committed findings crosses for duplicate avoidance. Categories are not assigned to pass numbers: every pass may search correctness/runtime
behavior; security/trust boundaries; state/lifecycle/concurrency/error handling; performance/resources/
reliability; and interfaces/data integrity/integration/maintainability/testability. The fresh-pass temperature
cascade is the control mechanism that changes search behavior. A pass locks onto one candidate, classifies
it LOW, MEDIUM, HIGH, or CRITICAL when a real finding exists, and does not pivot to a second problem after
that candidate is selected. Code Debugging
is report-only: it does not patch the target project. A live pass may pause to ask the
user a targeted diagnostic question about that same candidate when runtime observations,
reproduction details, environment, or other clarification would materially improve the
audit; Jack preserves that same pass for the reply and always presents a reminder that
the debugger remains bound by its primary Debugging instructions. Jack strips explicitly identified direct file-mutation tools from the pass tool surface. Every debugging
invocation receives its own date/time-named report under Debugging/Reports; the bundled Instructions.md,
User_Instructions.md, and Debugging_Report.md template are never overwritten at runtime. Jack appends every
completed pass summary to that run-specific report immediately and discards all pass reasoning/tool context
before the next pass. Preserve Thinking exists only inside one active pass for
diagnostic tool or user-dialogue continuation. After Pass 5, a fresh tools-off reporting
instance receives the complete durable Pass 0..5 report from disk, reads all saved
summaries, and produces a severity-ranked work-agent repair specification that Jack also
saves to disk.

Run the Windows launcher with start.bat. LM Studio is the default backend;
Ollama, Jan.ai, llama.cpp, and custom OpenAI-compatible endpoints are supported.
"""

from __future__ import annotations

import asyncio
import base64
import copy
import getpass
import html
import re
from contextlib import asynccontextmanager
import contextlib
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from dataclasses import dataclass, replace
from typing import Any, AsyncIterator, Dict, Iterable, List, Optional, Tuple

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

PUBLIC_VERSION = "v.0.1.1"
CONFIG_SCHEMA_VERSION = 1


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


BACKEND_PRESETS: Dict[str, Dict[str, str]] = {
    "lmstudio": {
        "label": "LM Studio (Default)",
        "short_label": "LM Studio",
        "base_url": "http://127.0.0.1:1234/v1",
        "auth_mode": "none",
        "control_shape": "template_kwargs",
    },
    "ollama": {
        "label": "Ollama",
        "short_label": "Ollama",
        "base_url": "http://127.0.0.1:11434/v1",
        "auth_mode": "none",
        "control_shape": "ollama_openai",
    },
    "jan": {
        "label": "Jan.ai",
        "short_label": "Jan.ai",
        "base_url": "http://127.0.0.1:1337/v1",
        "auth_mode": "none",
        "control_shape": "template_kwargs",
    },
    "llamacpp": {
        "label": "llama.cpp (raw llama-server)",
        "short_label": "llama.cpp",
        "base_url": "http://127.0.0.1:8080/v1",
        "auth_mode": "none",
        "control_shape": "template_kwargs",
    },
    "custom": {
        "label": "Custom OpenAI-compatible",
        "short_label": "Custom",
        "base_url": "http://127.0.0.1:8000/v1",
        "auth_mode": "none",
        "control_shape": "template_kwargs",
    },
}

_BACKEND_PROFILE_ALIASES = {
    "lm": "lmstudio",
    "lm-studio": "lmstudio",
    "lm_studio": "lmstudio",
    "ollama-local": "ollama",
    "jan.ai": "jan",
    "janai": "jan",
    "llama.cpp": "llamacpp",
    "llama-cpp": "llamacpp",
    "llama_cpp": "llamacpp",
    "raw": "llamacpp",
    "openai": "custom",
    "vllm": "custom",
}

def _normalize_backend_profile(value: str) -> str:
    key = (value or "lmstudio").strip().lower()
    key = _BACKEND_PROFILE_ALIASES.get(key, key)
    return key if key in BACKEND_PRESETS else "lmstudio"

def _profile_env_base_url(profile: str) -> str:
    aliases = {
        "lmstudio": "JACK_LMSTUDIO_BASE_URL",
        "ollama": "JACK_OLLAMA_BASE_URL",
        "jan": "JACK_JAN_BASE_URL",
        "llamacpp": "JACK_LLAMACPP_BASE_URL",
    }
    name = aliases.get(profile)
    return os.getenv(name, "").strip() if name else ""

def _profile_env_api_key(profile: str) -> str:
    aliases = {
        "lmstudio": "JACK_LMSTUDIO_API_KEY",
        "ollama": "JACK_OLLAMA_API_KEY",
        "jan": "JACK_JAN_API_KEY",
        "llamacpp": "JACK_LLAMACPP_API_KEY",
    }
    name = aliases.get(profile)
    return os.getenv(name, "") if name else ""


@dataclass(frozen=True)
class KernelConfig:
    # Wrapper endpoint.
    host: str = os.getenv("JACK_HOST", "127.0.0.1")
    port: int = int(os.getenv("JACK_PORT", "8001"))
    api_key: str = os.getenv("JACK_API_KEY", "")

    # Agent-facing URL advertised by the Kernel. This is intentionally
    # separate from the bind host so Jack may listen on 0.0.0.0 while agents
    # connect through a LAN hostname/IP, tunnel, container address, etc.
    agent_base_url_override: str = os.getenv("JACK_AGENT_BASE_URL", "").strip().rstrip("/")

    @property
    def agent_base_url(self) -> str:
        if self.agent_base_url_override:
            url = self.agent_base_url_override
            return url if url.endswith("/v1") else url + "/v1"
        display_host = self.host
        if display_host in {"0.0.0.0", "::", "[::]"}:
            display_host = "127.0.0.1"
        if ":" in display_host and not display_host.startswith("["):
            display_host = f"[{display_host}]"
        return f"http://{display_host}:{self.port}/v1"

    # Selectable local backend preset. LM Studio remains the default.
    backend_profile: str = _normalize_backend_profile(
        os.getenv("JACK_BACKEND_PROFILE", "lmstudio")
    )
    backend_base_url: str = (
        os.getenv("JACK_BACKEND_BASE_URL")
        or _profile_env_base_url(_normalize_backend_profile(os.getenv("JACK_BACKEND_PROFILE", "lmstudio")))
        or BACKEND_PRESETS[_normalize_backend_profile(os.getenv("JACK_BACKEND_PROFILE", "lmstudio"))]["base_url"]
    ).strip().rstrip("/")
    backend_model: str = os.getenv("JACK_BACKEND_MODEL", "")

    # Authentication is backend-owned configuration, separate from the optional
    # Jack Kernel access key used by calling agents. Local presets default to no
    # authentication but can enable Bearer/API-key authentication when configured.
    backend_api_key: str = (
        os.getenv("JACK_BACKEND_API_KEY")
        or _profile_env_api_key(_normalize_backend_profile(os.getenv("JACK_BACKEND_PROFILE", "lmstudio")))
        or ""
    )
    backend_auth_mode: str = os.getenv(
        "JACK_BACKEND_AUTH_MODE",
        "bearer" if (os.getenv("JACK_BACKEND_API_KEY") or _profile_env_api_key(_normalize_backend_profile(os.getenv("JACK_BACKEND_PROFILE", "lmstudio")))) else BACKEND_PRESETS[_normalize_backend_profile(os.getenv("JACK_BACKEND_PROFILE", "lmstudio"))]["auth_mode"],
    ).strip().lower()
    backend_header_name: str = os.getenv("JACK_BACKEND_HEADER_NAME", "").strip()
    backend_header_value: str = os.getenv("JACK_BACKEND_HEADER_VALUE", "")
    backend_username: str = os.getenv("JACK_BACKEND_USERNAME", "")
    backend_password: str = os.getenv("JACK_BACKEND_PASSWORD", "")
    backend_authorization_value: str = os.getenv("JACK_BACKEND_AUTHORIZATION_VALUE", "")
    backend_extra_headers_json: str = os.getenv("JACK_BACKEND_EXTRA_HEADERS", "{}").strip() or "{}"

    @property
    def backend_extra_headers(self) -> Dict[str, str]:
        try:
            data = json.loads(self.backend_extra_headers_json)
        except Exception as exc:
            raise RuntimeError("JACK_BACKEND_EXTRA_HEADERS must be a JSON object") from exc
        if not isinstance(data, dict):
            raise RuntimeError("JACK_BACKEND_EXTRA_HEADERS must be a JSON object")
        return {str(k): str(v) for k, v in data.items() if str(k).strip()}

    # Virtual model exposed to calling agents. The calling agent cannot switch
    # the actual backend model by changing its OpenAI model field.
    virtual_model: str = os.getenv("JACK_VIRTUAL_MODEL", "jack-kernel")


    # Named Jack reasoning profile. X-High is the default.
    # Profiles are resolved below into Qwen per-stage native-thinking controls.
    reasoning_level: str = os.getenv("JACK_REASONING_LEVEL", "x-high").strip().lower()

    # Human-configurable Qwen preserve-thinking policy. Calling agents cannot
    # override this value; it is owned by the Jack Kernel runtime.
    preserve_thinking: bool = os.getenv("JACK_PRESERVE_THINKING", "1").strip().lower() not in {
        "0", "false", "no", "off"
    }

    # Long local reasoning can take a while. This is an HTTP transport timeout,
    # not a promise or task deadline.
    backend_timeout_seconds: float = float(
        os.getenv("JACK_BACKEND_TIMEOUT_SECONDS", "1800")
    )

    # Optional observability-only context metadata. Zero/empty means unknown.
    # Jack never changes the backend overflow policy from these fields.
    backend_context_length: int = int(os.getenv("JACK_BACKEND_CONTEXT_LENGTH", "0") or "0")

    # One local 27B model is generally best served serially unless the backend
    # has explicitly been configured for parallel inference.
    max_concurrent_requests: int = int(os.getenv("JACK_MAX_CONCURRENT", "1"))

    # Optional deterministic seed. Empty = let backend choose.
    seed: str = os.getenv("JACK_SEED", "")

    # Qwen control shape. LM Studio defaults to "template_kwargs" so every
    # Jack stage stays on /v1/chat/completions with the real assistant history.
    # Qwen3.8 non-thinking mode is selected per request through the model's
    # official chat-template variable: enable_thinking=false.
    qwen_control_shape: str = os.getenv(
        "JACK_QWEN_CONTROL_SHAPE",
        BACKEND_PRESETS[_normalize_backend_profile(os.getenv("JACK_BACKEND_PROFILE", "lmstudio"))]["control_shape"],
    ).strip().lower()

    # Logging. Native model reasoning is NOT logged unless explicitly enabled.
    log_level: str = os.getenv("JACK_LOG_LEVEL", "INFO").upper()
    log_reasoning: bool = os.getenv("JACK_LOG_REASONING", "0") == "1"

    # Optional local forensic checkpointing is host-owned and never model context.
    # ``stage`` archives the completed Agentic Stage-1 trajectory only after Stage 2
    # succeeds; ``off`` disables it. The archive is written atomically at the full
    # turn commit boundary before request-local cognition is discarded.
    forensic_archive_mode: str = os.getenv("JACK_FORENSIC_ARCHIVE_MODE", "stage").strip().lower()
    forensic_archive_dir: str = os.getenv("JACK_FORENSIC_ARCHIVE_DIR", "").strip()


CFG = KernelConfig()

logging.basicConfig(
    level=getattr(logging, CFG.log_level, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
# Keep third-party HTTP client request traces out of the branded Jack CLI and
# ordinary runtime output. Jack's own observability remains controlled by
# JACK_LOG_LEVEL; dependency request logs stay warning-or-higher.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
LOG = logging.getLogger("jack-kernel")

if CFG.qwen_control_shape not in {"template_kwargs", "top_level", "hybrid", "ollama_openai"}:
    raise RuntimeError(
        "JACK_QWEN_CONTROL_SHAPE must be template_kwargs, top_level, hybrid, or ollama_openai"
    )
if CFG.backend_auth_mode not in {
    "none", "bearer", "header", "basic", "authorization"
}:
    raise RuntimeError(
        "JACK_BACKEND_AUTH_MODE must be none, bearer, header, basic, or authorization"
    )
if CFG.forensic_archive_mode not in {"off", "stage"}:
    raise RuntimeError("JACK_FORENSIC_ARCHIVE_MODE must be off or stage")
# Reasoning-mode taxonomy.
# Agentic: raw Stage 1 -> XML-only Stage 2; A1 remains authoritative and native
# cognition/tool protocol is pruned between completed turns.
# Deep Research: grounded Thesis -> narrow Antithesis -> tool-enabled Synthesis. The complete
# active Thesis/Antithesis trajectory is preserved through authoritative Synthesis; on later
# history preparation, Stage-1/Stage-2 native reasoning is retired while durable outputs remain eligible.
# Off, Medium, and X-High remain plain native controls. Low remains disabled.
REASONING_PROFILES: Dict[str, Dict[str, Any]] = {
    "off": {"label": "Off", "mode": "native", "answer": "off", "disabled": False},
    "low": {"label": "Low (Disabled)", "mode": "native", "answer": "low", "disabled": True},
    "medium": {"label": "Medium", "mode": "native", "answer": "medium", "disabled": False},
    "x-high": {"label": "X-High (Default)", "mode": "native", "answer": "xhigh", "disabled": False},
    "ultra": {
        "label": "Deep Research",
        "mode": "ultra",
        "answer": "xhigh",
        "pass1": "xhigh",
        "pass2": "medium",
        "pass3": "xhigh",
        "disabled": False,
    },
    "agentic": {
        "label": "Agentic",
        "mode": "agentic",
        "answer": "xhigh",
        "pass1": "xhigh",
        "pass2": "xhigh",
        "disabled": False,
    },
    "code-debugging": {
        "label": "Code Debugging",
        "mode": "code_debugging",
        "answer": "medium",
        "debugging": "medium",
        "disabled": False,
    },
    "code-debugging-deep": {
        "label": "Code Debugging (Deep)",
        "mode": "code_debugging",
        "answer": "xhigh",
        "debugging": "xhigh",
        "disabled": False,
    },
}

# Accepted aliases for reasoning-level input.
_REASONING_LEVEL_ALIASES = {
    "xhigh": "x-high",
    "x_high": "x-high",
    "x high": "x-high",
    "standard": "medium",
    "default": "x-high",
    "recommended": "x-high",
    "flash": "off",
    "high": "x-high",
    "deep-research": "ultra",
    "deep_research": "ultra",
    "deep research": "ultra",
    "deepresearch": "ultra",
    "extreme": "ultra",
    "max": "ultra",
    "debug": "code-debugging",
    "debugging": "code-debugging",
    "code_debugging": "code-debugging",
    "code debugging": "code-debugging",
    "code-debugging-deep": "code-debugging-deep",
    "code_debugging_deep": "code-debugging-deep",
    "code debugging deep": "code-debugging-deep",
    "debugging deep": "code-debugging-deep",
    "deep debugging": "code-debugging-deep",
    "debug-deep": "code-debugging-deep",
}
_reasoning_level = _REASONING_LEVEL_ALIASES.get(CFG.reasoning_level, CFG.reasoning_level)
if _reasoning_level not in REASONING_PROFILES:
    raise RuntimeError("JACK_REASONING_LEVEL must be off, medium, x-high, deep-research, agentic, code-debugging, or code-debugging-deep; low is listed but disabled")
if REASONING_PROFILES[_reasoning_level].get("disabled"):
    raise RuntimeError("JACK_REASONING_LEVEL=low is disabled in Jack Kernel v0.1.1. Choose off, medium, x-high, deep-research, agentic, code-debugging, or code-debugging-deep.")
ACTIVE_REASONING_PROFILE = REASONING_PROFILES[_reasoning_level]
AGENTIC_MODE = ACTIVE_REASONING_PROFILE["mode"] == "agentic"
ULTRA_MODE = ACTIVE_REASONING_PROFILE["mode"] == "ultra"
CODE_DEBUGGING_MODE = ACTIVE_REASONING_PROFILE["mode"] == "code_debugging"
SELF_ADVERSARIAL_MODE = AGENTIC_MODE or ULTRA_MODE


# ---------------------------------------------------------------------------
# Jack 2.x stage continuations and prompts.
# ---------------------------------------------------------------------------

_STAGE_CONTINUATIONS = {
    "Native answer": "Continue the original user request.",
    "Agentic native pass 1": "Continue the current user turn.",
    "Agentic native pass 2": (
        "[JACK RUNTIME STAGE CONTINUATION — NOT USER CONTENT — SAME USER TURN]\n"
        "Generate Jack XML now."
    ),
}


def _stage_continuation(
    profile: "StageProfile", messages: Optional[Iterable[Dict[str, Any]]] = None
) -> str:
    return _STAGE_CONTINUATIONS.get(
        profile.name,
        "Continue the requested task using the preceding conversation.",
    )


ULTRA_STAGE2_TRANSITION_BRIDGE = "THESIS COMPLETE. PROCEED TO ANTITHESIS."
ULTRA_STAGE3_TRANSITION_BRIDGE = "ANTITHESIS COMPLETE. PROCEED TO SYNTHESIS."
ULTRA_USER_REQUEST_REMINDER = "As a reminder, this was the user request:"
ULTRA_STAGE_REMINDER_DISCLAIMER = (
    "This Jack-generated transport message is not a new user request and does not modify or replace the active user request."
)
ULTRA_STAGE2_THESIS_IDENTITY = (
    "The assistant response immediately before this Jack transition is the THESIS.\n"
    "Evaluate that THESIS against the exact user request."
)
ULTRA_STAGE3_INPUT_IDENTITY = (
    "The assistant response immediately before this Jack transition is the ANTITHESIS.\n"
    "The assistant response immediately before the prior Jack transition is the THESIS.\n"
    "Produce the final response to the exact user request."
)


def _ultra_transition_reminder(
    stage_bridge: str, messages: Iterable[Dict[str, Any]]
) -> str:
    """Build the minimal Jack-owned stage bridge with explicit input identity.

    The bridge is a transport turn required by assistant-ended chat templates. It
    names the stage transition, quotes the actual response target as a reminder,
    identifies which prior assistant response is the stage input, and explicitly
    says the reminder is not a new request. No model-output parsing, retry, or
    semantic judgment is involved.
    """
    target = active_response_target(messages)
    request_text = str((target or {}).get("content") or "").strip()
    if not request_text:
        request_text = "[current user request unavailable]"
    if stage_bridge == ULTRA_STAGE2_TRANSITION_BRIDGE:
        identity = ULTRA_STAGE2_THESIS_IDENTITY
    elif stage_bridge == ULTRA_STAGE3_TRANSITION_BRIDGE:
        identity = ULTRA_STAGE3_INPUT_IDENTITY
    else:
        identity = ""
    identity_block = f"\n\n{identity}" if identity else ""
    return (
        f"{stage_bridge}\n\n"
        f"{ULTRA_USER_REQUEST_REMINDER}\n"
        f"{request_text}"
        f"{identity_block}\n\n"
        f"{ULTRA_STAGE_REMINDER_DISCLAIMER}"
    )


def _stage_generation_trigger(
    profile: "StageProfile", messages: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Return the generation-opening turn required by staged chat templates.

    Qwen/LM Studio can return an empty generation when stage context ends in an
    assistant message. Deep Research uses a small Jack-owned transition reminder that keeps
    the actual current user request immediately salient without presenting that
    request as a fresh user command.
    """
    if profile.name == "Deep Research Antithesis pass 2":
        return {
            "role": "user",
            "content": _ultra_transition_reminder(ULTRA_STAGE2_TRANSITION_BRIDGE, messages),
        }
    if profile.name == "Deep Research Synthesis pass 3":
        return {
            "role": "user",
            "content": _ultra_transition_reminder(ULTRA_STAGE3_TRANSITION_BRIDGE, messages),
        }
    return {"role": "user", "content": _stage_continuation(profile, messages)}


def _append_ultra_stage_generation_trigger(
    history: List[Dict[str, Any]], stage_key: str
) -> Dict[str, Any]:
    """Persist one Jack-owned Deep Research stage boundary in the active transaction.

    A boundary that actually opens Antithesis or Synthesis is causal transaction
    state, not disposable prompt scaffolding. Keeping it through Synthesis makes
    Thesis and Antithesis structurally distinguishable while active_response_target()
    continues to ignore the Jack-owned user-role transport turn.
    """
    for item in history:
        if (
            isinstance(item, dict)
            and item.get("_jack_internal_stage_generation_trigger")
            and item.get("_jack_stage_key") == stage_key
        ):
            return item
    trigger = _stage_generation_trigger(STAGES[stage_key], history)
    trigger["_jack_internal_stage_generation_trigger"] = True
    trigger["_jack_stage_key"] = stage_key
    history.append(trigger)
    return trigger


def _stage_requires_user_continuation(profile: "StageProfile") -> bool:
    """Return whether an assistant-ended stage view needs a generation-opening turn."""
    return True


# Plain native and Agentic Stage-1 cognition intentionally carry no Jack-authored cognitive prompt.
THESIS_PROMPT = ""

ULTRA_STAGE1_THESIS_PROMPT = """You are Thesis.

Reason exceptionally thoroughly from First Principles and produce a concentrated plan for Synthesis to fulfill the exact user request.

You have no tools in this stage. Synthesis may receive the caller's tools and is the execution stage, so plan required tool use, file operations, artifact changes, verification, and other execution for Synthesis with that capability in mind. Plan tool use by required capability only; do not invent specific tool names or schemas you have not been shown. Do not execute the plan or claim that execution occurred.

Output only the plan."""

AGENTIC_36_STAGE2_PROMPT = """Your only task in this stage is to construct a compact, high-signal Jack XML checkpoint for this completed current turn.

The exact current user message is already retained deterministically by the Jack host outside Jack XML. Stage 1 has already produced:
- that exact active user message,
- native reasoning,
- the frozen model answer,
- and any actual tool calls/results.

Jack preserves completed Agentic turns as exact user message + compact Jack XML + exact frozen Stage-1 answer. Jack XML must not become a synthetic workspace truth source. Use fewer semantic surfaces with stronger meaning. Preserve evidence, deterministic verification, adversarial pressure, and concrete discovered output mistakes; leave broad state reconstruction to future reasoning and fresh tools.

Do not call tools.
Do not generate or modify the frozen answer.
Do not invent evidence.
Do not reconstruct, summarize, or declare the current workspace state.
Do not create anchor facts, operative-state summaries, persistent-constraint ledgers, dependency ledgers, open-loop ledgers, or superseded-state ledgers.
Do not quote, reproduce, or summarize the current user message merely to preserve it; the host already preserves it exactly outside Jack XML.
Do not treat prior Jack XML, Stage-1 reasoning, or the frozen Stage-1 answer as independent evidence.
When fresh current-turn tool evidence conflicts with prior model-authored state, prefer the fresh tool evidence and record only the evidential conflict needed for calibration.

<Prime_Directive>
- The exact host-retained user message remains authoritative for what the user requested.
- Actual user-provided evidence, established conversation evidence, and actual tool results retain evidential status.
- Prior Jack XML is working memory/attention context, not an independent source of truth.
- Stage-1 reasoning and frozen A1 are working cognition and claims to evaluate, not evidence.
- Premise != fact.
- Requested conclusion != evidence.
- A deterministic check establishes only what it actually tested.
- Absence of evidence != evidence of safety, success, harm, or failure.
- User preference does not change truth conditions.
- Prefer specific evidence and narrow verification over broad semantic summaries.
</Prime_Directive>

Build exactly four semantic blocks inside <Jack XML>, in this order:

<grounding>
Observed:
Not Observed:
</grounding>

For <grounding>:
- Record only evidence actually available in the completed current turn.
- Be concrete: identify the source or tool result when material.
- Do not convert inference, prior Jack XML, Stage-1 reasoning, or A1 into evidence.
- If a material fact was not observed, place it under Not Observed rather than inferring it.
- Do not describe the whole workspace, task history, or future plan.

<verification>
Verified:
Scope:
Not Verified:
</verification>

For <verification>:
- Include only claims directly established by an actual deterministic Stage-1 tool/result.
- State the exact narrow scope of the verification.
- Never generalize syntax, file presence, grep, tests, or inspection into broader success.
- If no deterministic tool verification occurred, use exactly:
Verified: NONE
Scope: No deterministic tool verification occurred during Stage 1.
Not Verified: Any claim requiring deterministic verification.

<challenge>
PREMISE
Question: What must be true for the Stage-1 answer to satisfy the exact user request?
Answer:

INVALIDATION
Question: What material fact, counterexample, or failure condition would invalidate the Stage-1 answer?
Answer:

HIDDEN ASSUMPTION
Question: What material assumption is the Stage-1 answer relying on?
Answer:
</challenge>

For <challenge>:
- Materially test the frozen Stage-1 answer against the exact current user request and available evidence.
- Do not introduce requirements or success criteria the user did not ask for.
- Do not manufacture uncertainty, alternative interpretations, failure modes, hypothetical edge cases, or assumptions merely to populate a lens. If no material issue exists for a lens, write NONE.
- Do not create a replacement answer, corrective plan, or workspace summary.
- Do not treat unverified claims as established facts.

<audit>
Uncovered Output Mistakes:
</audit>

For <audit>:
- Audit is retrospective and diagnostic. Generate it last, after grounding, verification, and challenge.
- After completing Grounding, Verification, and Challenge, inspect the frozen Stage-1 answer one final time against the exact user request and the evidence established above.
- Record only concrete mistakes actually present in frozen A1. Eligible mistakes include direct arithmetic or logical contradictions, contradictions between different parts of A1, contradictions with deterministic evidence, materially incorrect stated values, and required outputs from the exact user request that A1 actually omitted.
- A mistake must be supported by the exact user request, available user or conversation evidence, an actual deterministic tool/result, or a direct logical, arithmetic, or internal contradiction in A1.
- Challenge identifies what may make A1 wrong. Audit records only errors that Stage 2 determined are actually present. Do not copy a challenge item into Audit unless the error is established.
- Do not record hypothetical risks, possible counterexamples, possible failure modes, hidden assumptions, unverified suspicions, stylistic preferences, suggested improvements, future actions, or a replacement answer.
- Audit is model-authored diagnostic memory, not independent evidence and not deterministic verification. Future reasoning must not treat an Audit item as established truth solely because it appears in Jack XML.
- Keep each mistake precise and concise. If no concrete output mistake was uncovered, use exactly:
Uncovered Output Mistakes: NONE

Output exactly:
<Jack XML>
<grounding>...</grounding>
<verification>...</verification>
<challenge>...</challenge>
<audit>...</audit>
</Jack XML>

Rules:
- Output Jack XML only.
- Use NONE or NOT OBSERVED when warranted rather than inventing content.
- Each semantic block must contribute distinct information. Do not repeat the same limitation, fact, or caution across multiple blocks unless the distinction materially changes its meaning. Prefer sparse, high-signal output.
- Preserve only material evidence, verification scope, adversarial cautions, and concrete discovered output mistakes that could improve downstream reasoning.
- Do not copy the user request into XML merely for retention.
- Do not rewrite the frozen answer.
"""

ULTRA_STAGE2_ANTITHESIS_PROMPT = """You are Antithesis.

Introduce friction by asking strong adversarial questions about the THESIS's premises or its alignment with the user's request.

The THESIS is intentionally a plan for Synthesis. Evaluate it as a plan for Synthesis, not as the user-facing final answer. Thesis has no tools, but Synthesis may receive caller tools and execute the plan. Do not criticize Thesis merely for being a plan, for withholding final-answer presentation, or for not executing work reserved for Synthesis.

Challenge material assumptions, incorrect premises, weaknesses, omissions, or failure points in the THESIS. Identify the strongest material adversarial questions and stop. Question whether the THESIS is aligned with the user request when there is a material basis to do so.

Ask only materially relevant questions. Do not solve the task."""

ULTRA_STAGE3_SYNTHESIS_PROMPT = """You are Synthesis, the authoritative reasoning and execution stage.

Fulfill the exact user request. Use the THESIS as a proposed plan and the ANTITHESIS as adversarial questions, but decide independently.

You have access to the tools supplied to this stage. When the request requires implementation, file or artifact changes, verification, or other execution and an appropriate tool is available, carry out the work with the tools rather than merely describing what the user should do.

Only actual host-returned tool results establish that tool execution occurred. Ground execution-state claims in those results.

Return the final response."""

DEBUGGING_PASS_COUNT = 5
DEBUGGING_PASS_TEMPERATURES = {1: 1.0, 2: 0.8, 3: 0.7, 4: 0.6, 5: 0.5}
DEBUGGING_REVIEW_CATEGORIES = (
    "Functional correctness and runtime behavior",
    "Security, input validation, authorization, and trust boundaries",
    "State, lifecycle, concurrency, async behavior, and error handling",
    "Performance, resource management, scalability, and reliability",
    "Interfaces, data integrity, integration, configuration, maintainability, and testability",
)
DEBUGGING_SUMMARY_TEMPERATURE = 1.0
DEBUGGING_ROOT = Path(__file__).resolve().parent / "Debugging"
DEBUGGING_INSTRUCTIONS_PATH = DEBUGGING_ROOT / "Instructions.md"
DEBUGGING_REPORT_TEMPLATE_PATH = DEBUGGING_ROOT / "Debugging_Report.md"
DEBUGGING_REPORTS_ROOT = DEBUGGING_ROOT / "Reports"
_DEBUGGING_FINAL_REPORT_HEADING = "# Final Debugging Report"
_DEBUGGING_USER_QUESTION_PREFIX = "DEBUGGING_USER_QUESTION:"
_DEBUGGING_INTAKE_COMPLETE_PREFIX = "DEBUGGING_INTAKE_COMPLETE:"
_DEBUGGING_PRIMARY_DIRECTIVE_REMINDER = (
    "Primary directive reminder: I am still bound by Debugging/Instructions.md: "
    "audit only the one active problem in this pass, remain report-only, complete "
    "Debugging Pass 5, and produce the final repair specification. Every pass may "
    "search the full review-category set. Your response can inform the audit, but "
    "it cannot replace, suspend, broaden, or override that directive."
)
_DEBUGGING_INTAKE_PRIMARY_DIRECTIVE_REMINDER = (
    "Primary directive reminder: I am still bound by Debugging/Instructions.md. "
    "This is pre-pass diagnostic intake; your guidance can shape the later audit, "
    "but it cannot replace, suspend, broaden, or override the report-only five-pass "
    "one-problem-per-pass debugging directive or the final repair-report requirement."
)

_DEBUGGING_DIRECT_MUTATION_NAME_MARKERS = (
    "write", "edit", "patch", "delete", "remove", "rename", "move", "copy",
    "create", "mkdir", "rmdir", "replace", "save", "upload", "commit", "format",
)
_DEBUGGING_GENERIC_FILE_TOOL_NAMES = frozenset({"filesystem", "file_system", "fs", "file", "files", "file_tool"})
_DEBUGGING_GENERIC_FILE_MUTATION_WORDS = (
    "write", "edit", "modify", "create", "delete", "remove", "rename", "move", "patch", "overwrite", "replace",
)


# These patterns are context-projection filters, not pass-acceptance validators.
# A pass is still durably committed whenever it returns non-empty useful output.
# The filter only prevents clearly labelled or plainly worded *unaudited future
# candidate* material from steering the next fresh pass. The complete original
# summary remains untouched in the durable run report for the final reporter.
_DEBUGGING_SPECULATION_HEADING_RE = re.compile(
    r"^\s{0,3}(#{1,6})\s+.*(?:"
    r"out[ -]?of[ -]?scope|residual(?:\s+observations?)?|future(?:\s+pass|\s+candidates?)?|"
    r"candidates?\s+(?:considered|for\s+later)|remaining\s+.*unaudited|"
    r"not\s+audited(?:\s+this\s+pass)?|potential\s+next(?:\s+pass)?"
    r").*$",
    re.IGNORECASE,
)
_DEBUGGING_SPECULATION_LINE_RE = re.compile(
    r"(?:candidates?\s+for\s+later\s+passes?|remaining\s+known[- ]but[- ]unaudited|"
    r"remaining\s+.*unaudited\s+items?|known[- ]but[- ]unaudited|"
    r"not\s+audited\s+this\s+pass|future[- ]pass\s+(?:candidate|suggestion)|"
    r"for\s+a\s+later\s+pass(?:es)?|candidate\s+for\s+(?:a\s+)?later\s+pass(?:es)?|"
    r"remaining\s+items\s+above\s+are\s+residual\s+observations\s+only|"
    r"residual\s+observations\s+only.*(?:not\s+audited|final\s+report))",
    re.IGNORECASE,
)


def _debugging_tool_name(tool: Dict[str, Any]) -> str:
    function = tool.get("function") if isinstance(tool, dict) else None
    if not isinstance(function, dict):
        return ""
    return str(function.get("name") or "").strip()


def _debugging_tool_is_direct_mutator(tool: Dict[str, Any]) -> bool:
    """Reject caller tools whose advertised surface directly mutates project files.

    Generic command-execution tools are intentionally not classified here because
    they can be useful for non-mutating diagnostics and cannot be made safe by name
    filtering alone. The Debugging system contract restricts those tools to
    non-mutating diagnostic use; Jack does not claim command-level sandboxing.
    """
    name = _debugging_tool_name(tool).lower()
    if any(marker in name for marker in _DEBUGGING_DIRECT_MUTATION_NAME_MARKERS):
        return True
    function = tool.get("function") if isinstance(tool, dict) else None
    description = str((function or {}).get("description") or "").lower()
    if name in _DEBUGGING_GENERIC_FILE_TOOL_NAMES:
        return any(word in description for word in _DEBUGGING_GENERIC_FILE_MUTATION_WORDS)
    return False


def _debugging_report_only_tool_surface(
    tools: Optional[List[Dict[str, Any]]], tool_choice: Any
) -> Tuple[List[Dict[str, Any]], Any]:
    """Project a caller tool surface suitable for report-only Code Debugging."""
    if not tools:
        raise HTTPException(
            status_code=400,
            detail="Code Debugging requires caller-provided inspection tools.",
        )
    kept = [copy.deepcopy(tool) for tool in tools if not _debugging_tool_is_direct_mutator(tool)]
    removed = [_debugging_tool_name(tool) or "<unnamed>" for tool in tools if _debugging_tool_is_direct_mutator(tool)]
    if removed:
        LOG.info("Code Debugging report-only policy removed direct mutation tools: %s", ", ".join(removed))
    if not kept:
        raise HTTPException(
            status_code=400,
            detail=(
                "Code Debugging report-only mode requires at least one non-mutation inspection tool; "
                "the caller supplied only direct mutation tools."
            ),
        )
    normalized_choice = _normalize_agent_tool_choice(tool_choice, kept)
    if isinstance(tool_choice, dict) and normalized_choice is None:
        normalized_choice = "auto"
    return kept, normalized_choice

# Code Debugging deliberately uses a fresh backend context for every pass. Exact
# user-origin Pass 0 authority is re-projected into every fresh pass. For Passes
# 2-5, Jack additionally projects only a compact host-derived duplicate-avoidance
# registry distilled from already committed outcomes; full model-authored handoffs
# remain durable on disk for the final reporter but never become live next-pass
# context. Active-pass cognition/tool protocol is retained until the pass summary
# is durably committed. Every debugging invocation owns a unique durable report
# file; bundled Debugging core files are immutable runtime inputs/templates.
@dataclass
class DebuggingRunState:
    run_id: str
    report_path: Path
    created_at: str
    initial_request: str
    intake_history: List[Dict[str, str]]
    summaries: Dict[int, str]
    intake_frozen: bool = False
    final_report_committed: bool = False
    final_report: str = ""


_DEBUGGING_RUNS: Dict[str, DebuggingRunState] = {}


def _debugging_retire_run(run: DebuggingRunState) -> None:
    if _DEBUGGING_RUNS.get(run.run_id) is run:
        _DEBUGGING_RUNS.pop(run.run_id, None)


def _debugging_user_requests_new_run(text: str) -> bool:
    value = re.sub(r"\s+", " ", str(text or "").strip().lower())
    if not value:
        return False
    patterns = (
        r"\brun\s+(?:jack\s+)?code\s+debugging\b",
        r"\bstart\s+(?:a\s+)?new\s+(?:jack\s+)?code\s+debugging\b",
        r"\bbegin\s+(?:a\s+)?new\s+(?:jack\s+)?code\s+debugging\b",
        r"\brun\s+(?:the\s+)?debugger\s+(?:again|against|on)\b",
        r"\bstart\s+(?:the\s+)?debugger\s+(?:again|against|on)\b",
    )
    return any(re.search(pattern, value) is not None for pattern in patterns)


def _debugging_completed_run_for_history(
    messages: Iterable[Dict[str, Any]],
) -> Optional[DebuggingRunState]:
    """Positive-match a follow-up to an exact completed final report in history."""
    items = [item for item in messages if isinstance(item, dict)]
    target = active_response_target(items)
    current_user = _content_to_text((target or {}).get("content")).strip()
    if _debugging_user_requests_new_run(current_user):
        return None

    completed = [
        run for run in _DEBUGGING_RUNS.values()
        if run.final_report_committed and str(run.final_report or "").strip()
    ]
    for item in reversed(items):
        if item.get("role") != "assistant":
            continue
        assistant_content = _content_to_text(item.get("content")).strip()
        if not assistant_content:
            continue
        for run in reversed(completed):
            if assistant_content == run.final_report.strip():
                return run
    return None


def _debugging_followup_history(
    run: DebuggingRunState, messages: Iterable[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Keep completed-work conversation and inject exact host-owned run metadata."""
    history = [copy.deepcopy(item) for item in messages if isinstance(item, dict)]
    last_user_index: Optional[int] = None
    for index in range(len(history) - 1, -1, -1):
        if history[index].get("role") == "user":
            last_user_index = index
            break
    if last_user_index is None:
        raise HTTPException(status_code=400, detail="Code Debugging follow-up requires an active user message.")

    exact_user = _content_to_text(history[last_user_index].get("content")).strip()
    if not exact_user:
        raise HTTPException(status_code=400, detail="Code Debugging follow-up user message is empty.")

    projected = dict(history[last_user_index])
    projected["content"] = (
        "[JACK RUNTIME CONTEXT — NOT USER CONTENT]\n"
        "This is conversational follow-up to a completed Code Debugging run, not a new five-pass audit.\n"
        f"Completed Run ID: {run.run_id}\n"
        f"Saved Report Path: {run.report_path}\n"
        "Use the preceding completed final debugging report and conversation history to answer the user's follow-up. "
        "Do not restart Pass 1 unless the user explicitly requests a new debugging run.\n\n"
        "[EXACT USER FOLLOW-UP]\n"
        f"{exact_user}"
    )
    projected["_jack_internal_debugging_followup"] = True
    history[last_user_index] = projected
    return history


def _debugging_initial_request(messages: Iterable[Dict[str, Any]]) -> str:
    target = active_response_target(messages)
    if not target:
        raise RuntimeError("Code Debugging could not resolve the active user request")
    text = str(target.get("content") or "").strip()
    if not text:
        raise RuntimeError("Code Debugging active user request is empty")
    return text


def _debugging_new_report_path() -> Path:
    DEBUGGING_REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
    micros = (time.time_ns() // 1000) % 1_000_000
    suffix = uuid.uuid4().hex[:8]
    return DEBUGGING_REPORTS_ROOT / f"Debugging_Report_{stamp}_{micros:06d}_{suffix}.md"


def _debugging_create_run(initial_request: str) -> DebuggingRunState:
    DEBUGGING_ROOT.mkdir(parents=True, exist_ok=True)
    DEBUGGING_REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    if not DEBUGGING_INSTRUCTIONS_PATH.is_file():
        raise RuntimeError(f"Missing Code Debugging instructions: {DEBUGGING_INSTRUCTIONS_PATH}")
    if not DEBUGGING_REPORT_TEMPLATE_PATH.is_file():
        raise RuntimeError(f"Missing Code Debugging report template: {DEBUGGING_REPORT_TEMPLATE_PATH}")
    run_id = f"jack-debug-{uuid.uuid4().hex}"
    created_at = time.strftime("%Y-%m-%d %H:%M:%S %z", time.localtime())
    run = DebuggingRunState(
        run_id=run_id,
        report_path=_debugging_new_report_path(),
        created_at=created_at,
        initial_request=initial_request.strip(),
        intake_history=[{"role": "user", "content": initial_request.strip()}],
        summaries={},
    )
    _DEBUGGING_RUNS[run_id] = run
    _debugging_write_open_intake_report(run)
    LOG.info("Created Code Debugging run %s report=%s", run.run_id, run.report_path)
    return run


def _debugging_get_run(run_id: Optional[str]) -> DebuggingRunState:
    if not run_id or run_id not in _DEBUGGING_RUNS:
        raise HTTPException(status_code=500, detail="Code Debugging run state is unavailable or expired.")
    return _DEBUGGING_RUNS[run_id]


def _debugging_append_intake_turn(run: DebuggingRunState, role: str, content: str) -> None:
    if run.intake_frozen:
        raise HTTPException(status_code=409, detail="Code Debugging diagnostic intake is already frozen.")
    text = str(content or "").strip()
    if not text:
        return
    run.intake_history.append({"role": role, "content": text})
    _debugging_write_open_intake_report(run)


def _debugging_render_intake_transcript(
    run: DebuggingRunState, *, user_only: bool = False
) -> str:
    """Render intake dialogue, optionally projecting only user-origin information.

    Pre-pass assistant dialogue is ephemeral same-stage scaffolding. Durable Pass 0
    and the run report intentionally retain only user-origin diagnostic input.
    """
    lines: List[str] = []
    for item in run.intake_history:
        raw_role = str(item.get("role") or "unknown").lower()
        if user_only and raw_role != "user":
            continue
        role = raw_role.upper()
        content = str(item.get("content") or "").strip()
        if content:
            lines.append(f"### {role}\n\n{content}")
    return "\n\n".join(lines).strip()


def _debugging_render_open_intake_report(run: DebuggingRunState) -> str:
    return (
        "# Jack Code Debugging Report\n\n"
        f"Run ID: `{run.run_id}`\n\n"
        f"Created: {run.created_at}\n\n"
        "Status: PRE-PASS DIAGNOSTIC INTAKE\n\n"
        "## Pre-Pass Diagnostic Intake\n\n"
        f"{_debugging_render_intake_transcript(run, user_only=True)}\n"
    )


def _debugging_write_open_intake_report(run: DebuggingRunState) -> None:
    run.report_path.parent.mkdir(parents=True, exist_ok=True)
    run.report_path.write_text(_debugging_render_open_intake_report(run), encoding="utf-8")


def _debugging_pass0_summary(run: DebuggingRunState) -> str:
    transcript = _debugging_render_intake_transcript(run, user_only=True)
    return (
        "User-origin pre-pass diagnostic intake:\n\n"
        f"{transcript}\n\n"
        "Evidence rule: user descriptions are user-reported diagnostic observations until independently verified by a live audit pass."
    )


def _debugging_render_handoff(pass_number: int, summary: str) -> str:
    return f"# Jack Code Debugging Handoff\n\n## Debugging Pass {pass_number}\n\n{summary.strip()}\n"


def _debugging_render_report_through(run: DebuggingRunState, pass_number: int) -> str:
    expected = list(range(0, pass_number + 1))
    missing = [number for number in expected if number not in run.summaries]
    if missing:
        raise RuntimeError(f"Code Debugging host state is missing summaries: {missing}")
    parts = [
        "# Jack Code Debugging Report",
        "",
        f"Run ID: `{run.run_id}`",
        "",
        f"Created: {run.created_at}",
        "",
        f"Report File: `{run.report_path.name}`",
        "",
    ]
    for number in expected:
        parts.append(f"## Debugging Pass {number}")
        parts.append("")
        parts.append(run.summaries[number].strip())
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def _debugging_freeze_intake(run: DebuggingRunState) -> None:
    """Freeze user-origin intake as durable Pass 0 before fresh Pass 1 begins.

    Native pre-stage reasoning is never promoted into Pass 0. Visible assistant
    intake dialogue is same-stage scaffolding only and is pruned at the boundary.
    """
    if run.intake_frozen:
        return
    run.summaries.clear()
    run.summaries[0] = _debugging_pass0_summary(run)
    run.intake_history = [
        {"role": "user", "content": str(item.get("content") or "").strip()}
        for item in run.intake_history
        if str(item.get("role") or "").lower() == "user" and str(item.get("content") or "").strip()
    ]
    run.intake_frozen = True
    run.report_path.write_text(_debugging_render_report_through(run, 0), encoding="utf-8")
    _debugging_validate_report_through(run, 0)
    LOG.info("Code Debugging user-origin intake frozen as Pass 0: run=%s report=%s", run.run_id, run.report_path)


def _debugging_report_text(run: DebuggingRunState) -> str:
    if not run.report_path.is_file():
        raise RuntimeError(f"Missing Code Debugging run report: {run.report_path}")
    return run.report_path.read_text(encoding="utf-8")


def _debugging_validate_report_through(run: DebuggingRunState, expected_pass: int) -> str:
    """Require this run's unique disk report to contain exact durable Pass 0..N state."""
    if not run.intake_frozen:
        raise HTTPException(status_code=409, detail="Code Debugging pass validation requested before intake freeze.")
    expected_numbers = list(range(0, expected_pass + 1))
    missing = [number for number in expected_numbers if number not in run.summaries]
    if missing:
        raise HTTPException(status_code=500, detail=f"Code Debugging host state is missing summaries: {missing}.")
    report = _debugging_report_text(run)
    expected_text = _debugging_render_report_through(run, expected_pass)
    if report != expected_text:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Code Debugging durable report through Pass {expected_pass} changed outside Jack's commit boundary. "
                "Completed pass summaries are host-owned durable state."
            ),
        )
    return report


def _debugging_exact_user_authority_projection(run: DebuggingRunState) -> str:
    """Project the exact user-origin intake directly into every fresh pass.

    This is authoritative request/diagnostic context, not a model-authored summary.
    Pre-stage assistant chatter and native reasoning were already removed at freeze.
    """
    transcript = _debugging_render_intake_transcript(run, user_only=True).strip()
    if not transcript:
        raise HTTPException(status_code=500, detail="Code Debugging user-origin Pass 0 intake is empty.")
    return (
        "# EXACT USER-ORIGIN DEBUGGING INTAKE — AUTHORITATIVE\n\n"
        f"{transcript}\n\n"
        "This block is direct user authority. Preserve its exact requirements and constraints even if a later "
        "model-authored handoff omits, compresses, or paraphrases them. User-reported observations remain "
        "user-reported until independently verified."
    )


def _debugging_section(summary: str, heading: str) -> str:
    """Extract one Markdown section without projecting unrelated handoff material."""
    text = str(summary or "")
    pattern = re.compile(
        rf"(?ims)^\s{{0,3}}#{{2,6}}\s+{re.escape(heading)}\s*$\n(.*?)(?=^\s{{0,3}}#{{2,6}}\s+|\Z)"
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def _debugging_compact_text(value: str, limit: int) -> str:
    text = re.sub(r"[`*_>#]", "", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip(" -:\t\r\n")
    return text[:limit].rstrip()


def _debugging_first_material_line(value: str, limit: int = 700) -> str:
    for raw in str(value or "").splitlines():
        cleaned = _debugging_compact_text(raw, limit)
        if cleaned:
            return cleaned
    return ""


def _debugging_inline_field(text: str, labels: Tuple[str, ...], limit: int = 900) -> str:
    """Tolerantly read a one-line semantic field after Markdown decoration is removed.

    Pass handoffs are intentionally not schema-bound. Models commonly emit fields as
    headings, bold inline labels, bullets, or plain text. This helper extracts only a
    named established field and never makes formatting compliance a pass condition.
    """
    label_pattern = "|".join(re.escape(label) for label in labels)
    for raw in str(text or "").splitlines():
        cleaned = _debugging_compact_text(raw, max(limit + 160, 400))
        if not cleaned:
            continue
        match = re.match(rf"(?i)^(?:{label_pattern})\s*[:—-]\s*(.+)$", cleaned)
        if match:
            return _debugging_compact_text(match.group(1), limit)
    return ""


def _debugging_section_or_inline(text: str, heading: str, *, aliases: Tuple[str, ...] = (), limit: int = 900) -> str:
    section = _debugging_section(text, heading)
    if section:
        value = _debugging_first_material_line(section, limit)
        if value:
            return value
    return _debugging_inline_field(text, (heading,) + aliases, limit)


def _debugging_host_registry_record(pass_number: int, summary: str) -> str:
    """Deterministically derive bounded duplicate-avoidance state from a committed handoff.

    Extraction is deliberately tolerant because useful model output is semantic rather
    than schema-bound. Only established-outcome fields are eligible. Repair instructions,
    preservation advice, verification plans, residual observations, future-candidate
    suggestions, and the rest of the model-authored handoff are never projected forward.
    """
    text = str(summary or "")

    primary_heading = re.search(
        r"(?ims)^\s{0,3}#{1,6}\s+(?:Primary\s+)?Finding(?:\s+(?:—|-)\s+ID\s+`?([A-Z][A-Z0-9_.:-]{2,119})`?)?\s*$\n(.*?)(?=^\s{0,3}#{1,6}\s+|\Z)",
        text,
    )
    heading_finding_id = primary_heading.group(1) if primary_heading else ""
    established = _debugging_first_material_line(primary_heading.group(2), 900) if primary_heading else ""
    if established and re.match(r"(?i)^Finding\s+ID\s*[:—-]", established):
        established = ""
    if not established:
        established = _debugging_inline_field(
            text,
            ("Primary Finding", "Finding", "Primary Problem", "Finding Summary"),
            900,
        )
    if not established:
        established = _debugging_section_or_inline(
            text,
            "Observed Behavior",
            aliases=("Observed", "Problem", "Problem/Outcome"),
            limit=900,
        )

    finding_id = _debugging_inline_field(text, ("Finding ID", "Finding Id", "ID"), 120)
    if not finding_id and heading_finding_id:
        finding_id = heading_finding_id
    if not finding_id and established:
        lead_id = re.match(r"^([A-Z][A-Z0-9_.:-]{2,119})\s*(?:—|-|:)", established)
        if lead_id:
            finding_id = lead_id.group(1)
    if not finding_id:
        handoff_id = re.search(
            r"(?im)^\s{0,3}#{1,6}\s+[^\n]*?Handoff\s*(?:—|-)\s*`?([A-Z][A-Z0-9_.:-]{2,119})`?\s*$",
            text,
        )
        if handoff_id:
            finding_id = handoff_id.group(1)
    finding_id = _debugging_compact_text(finding_id, 120)

    category = _debugging_section_or_inline(
        text,
        "Review Category",
        aliases=("Category",),
        limit=300,
    )
    location = _debugging_section_or_inline(
        text,
        "Exact Location",
        aliases=("Location", "File"),
        limit=500,
    )

    severity_raw = _debugging_section_or_inline(text, "Severity", limit=120)
    sev = re.search(r"(?i)\b(CRITICAL|HIGH|MEDIUM|LOW)\b", severity_raw)
    if not sev:
        sev = re.search(r"(?i)\bSeverity\b[^\n]{0,32}\b(CRITICAL|HIGH|MEDIUM|LOW)\b", _debugging_compact_text(text, 6000))
    severity = sev.group(1).upper() if sev else "UNSPECIFIED"

    status_raw = _debugging_section_or_inline(text, "Status", limit=120)
    status_known = re.search(
        r"(?i)\b(CONFIRMED|REJECTED|UNRESOLVED|SUSPECTED|COMPLETED|NO MATERIAL FINDING|NO FINDING)\b",
        status_raw,
    )
    if status_known:
        status_text = status_known.group(1).upper()
    elif status_raw:
        status_text = _debugging_compact_text(status_raw, 60).upper()
    else:
        status_match = re.search(r"(?i)\bStatus\b[^\n]{0,20}[:—-]\s*([A-Za-z][A-Za-z _/-]{1,40})", text)
        status_text = _debugging_compact_text(status_match.group(1), 60).upper() if status_match else "COMPLETED"

    evidence_section = _debugging_section(text, "Evidence")
    evidence_lines: List[str] = []
    if evidence_section:
        for raw in evidence_section.splitlines():
            cleaned = _debugging_compact_text(raw, 420)
            if cleaned:
                evidence_lines.append(cleaned)
            if len(evidence_lines) >= 2:
                break
    if not evidence_lines:
        inline_evidence = _debugging_inline_field(text, ("Evidence", "Evidence Basis"), 800)
        if inline_evidence:
            evidence_lines.append(inline_evidence)
    evidence = " | ".join(evidence_lines)[:800]

    fields = [f"PASS {pass_number} CONFIRMED PRIOR OUTCOME"]
    if finding_id:
        fields.append(f"Finding ID: {finding_id}")
    if category:
        fields.append(f"Category: {category}")
    fields.append(f"Severity: {severity}")
    fields.append(f"Status: {status_text}")
    if location:
        fields.append(f"Location: {location}")
    if established:
        fields.append(f"Established problem/outcome: {established}")
    if evidence:
        fields.append(f"Evidence basis: {evidence}")

    # Loss-resistant fallback: if a committed pass cannot be parsed into preferred
    # fields, retain one bounded material sentence from the handoff rather than reducing
    # the prior outcome to an identity-less placeholder. Exclude known future-search or
    # repair-only sections by taking the first material line before those headings.
    if not established:
        safe_prefix = re.split(
            r"(?im)^\s{0,3}#{1,6}\s+(?:Required Correction|Repair Direction|Preservation Constraints|Verification Steps|Post-Patch Verification|Out-of-Scope|Residual Observations)\b",
            text,
            maxsplit=1,
        )[0]
        fallback = _debugging_first_material_line(safe_prefix, 900)
        if fallback:
            fields.append(f"Established problem/outcome: {fallback}")

    return "\n".join(fields)

def _debugging_prior_registry_projection(run: DebuggingRunState, previous_pass: int) -> str:
    """Build the complete host-derived prior-outcome registry for Pass N."""
    records = [
        _debugging_host_registry_record(number, run.summaries[number])
        for number in range(1, previous_pass + 1)
    ]
    return (
        "# HOST-DERIVED CONFIRMED PRIOR-FINDING REGISTRY — DUPLICATE AVOIDANCE ONLY\n\n"
        + "\n\n".join(records)
        + "\n\nThis registry is host-derived from already committed outcomes. It is not repair authority, "
          "not a future-search suggestion, and not a replacement for a fresh independent scan of the current target. "
          "Do not re-audit a registered outcome unless new current evidence materially invalidates it."
    )


def _debugging_fresh_pass_history(run: DebuggingRunState, pass_number: int) -> List[Dict[str, Any]]:
    """Build a fresh pass from exact user authority plus compact host-derived prior state.

    Pass 1 receives only exact user-origin Pass 0 intake. Passes 2-5 receive that same
    exact intake plus a deterministic duplicate-avoidance registry distilled from all
    already committed prior outcomes. No prior raw cognition/tool traffic or complete
    model-authored handoff is restored.
    """
    previous_pass = pass_number - 1
    _debugging_validate_report_through(run, previous_pass)
    history: List[Dict[str, Any]] = [
        {"role": "user", "content": _debugging_exact_user_authority_projection(run)}
    ]
    if previous_pass >= 1:
        history.append(
            {"role": "user", "content": _debugging_prior_registry_projection(run, previous_pass)}
        )
    return history

def _debugging_intake_complete_from_result(stage: Dict[str, Any]) -> bool:
    choice = (stage.get("choices") or [{}])[0] or {}
    msg = choice.get("message") or {}
    content = str(msg.get("content") or "").strip()
    return content.startswith(_DEBUGGING_INTAKE_COMPLETE_PREFIX)


def _debugging_intake_public_content(stage: Dict[str, Any]) -> str:
    """Return intake content without Jack's internal completion control prefix."""
    choice = (stage.get("choices") or [{}])[0] or {}
    msg = choice.get("message") or {}
    content = str(msg.get("content") or "").strip()
    if content.startswith(_DEBUGGING_INTAKE_COMPLETE_PREFIX):
        content = content[len(_DEBUGGING_INTAKE_COMPLETE_PREFIX):].lstrip()
    return content


def _debugging_user_requests_intake_close(text: str) -> bool:
    """Recognize user control that means: stop asking intake questions and proceed.

    This is deliberately a user-control convenience, not a semantic-output validator.
    A user never has to provide additional diagnostic facts in order to start Pass 1.
    """
    value = re.sub(r"\s+", " ", str(text or "").strip().lower())
    if not value:
        return False
    patterns = (
        r"^(?:start|begin|proceed|continue|go ahead|run(?: the)? debugger|debug it|start debugging)[.! ]*$",
        r"^(?:just )?(?:do|follow) (?:your|the) (?:directive|instructions?)[.! ]*$",
        r"^(?:just )?(?:do it|go|carry on|use what you have|work with what you have)[.! ]*$",
        r"^(?:that'?s all|nothing else|no more(?: info(?:rmation)?)?|skip(?: the)? questions?)[.! ]*$",
    )
    return any(re.fullmatch(pattern, value) is not None for pattern in patterns)


def _debugging_intake_visible_content(stage: Dict[str, Any]) -> str:
    choice = (stage.get("choices") or [{}])[0] or {}
    msg = choice.get("message") or {}
    content = str(msg.get("content") or "").strip()
    if not content:
        content = "I have recorded your debugging request. Additional diagnostic detail is optional; tell me to proceed at any time."
    return f"{content}\n\n{_DEBUGGING_INTAKE_PRIMARY_DIRECTIVE_REMINDER}"


def _debugging_user_question_from_result(stage: Dict[str, Any]) -> Optional[str]:
    """Recognize the explicit model-to-user clarification interrupt contract."""
    choice = (stage.get("choices") or [{}])[0] or {}
    msg = choice.get("message") or {}
    content = str(msg.get("content") or "").strip()
    if not content.startswith(_DEBUGGING_USER_QUESTION_PREFIX):
        return None
    question = content[len(_DEBUGGING_USER_QUESTION_PREFIX):].strip()
    if not question:
        raise HTTPException(status_code=502, detail="Code Debugging emitted an empty user clarification request.")
    return question


def _debugging_render_user_question(question: str) -> str:
    return f"{question.strip()}\n\n{_DEBUGGING_PRIMARY_DIRECTIVE_REMINDER}"


def _debugging_pass_summary_from_result(pass_number: int, stage: Dict[str, Any]) -> str:
    """Return any non-empty pass handoff exactly as the model produced it.

    Code Debugging does not parse or reject useful forensic output for harmless
    formatting variance. The prompt strongly requests review category, finding,
    severity, status, evidence, and repair guidance, but those are semantic
    instructions rather than a host-enforced serialization schema.
    """
    choice = (stage.get("choices") or [{}])[0] or {}
    msg = choice.get("message") or {}
    summary = str(msg.get("content") or "").strip()
    if not summary:
        raise HTTPException(status_code=502, detail=f"Code Debugging Pass {pass_number} returned no durable handoff summary.")
    return summary


def _debugging_atomic_replace_report(report_path: Path, text: str) -> None:
    """Atomically replace a debugging report without exposing partial durable state."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = report_path.with_name(f"{report_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8", newline="\n") as report_file:
            report_file.write(text)
            report_file.flush()
            os.fsync(report_file.fileno())
        os.replace(temp_path, report_path)
    except Exception:
        with contextlib.suppress(Exception):
            temp_path.unlink()
        raise


def _debugging_commit_pass_summary(run: DebuggingRunState, pass_number: int, stage: Dict[str, Any]) -> str:
    """Atomically commit one completed pass without advancing memory before durability."""
    _debugging_validate_report_through(run, pass_number - 1)
    summary = _debugging_pass_summary_from_result(pass_number, stage)

    candidate_run = replace(
        run,
        summaries={**run.summaries, pass_number: summary},
    )
    candidate_report = _debugging_render_report_through(candidate_run, pass_number)

    _debugging_atomic_replace_report(run.report_path, candidate_report)

    run.summaries[pass_number] = summary
    _debugging_validate_report_through(run, pass_number)
    return summary


def _debugging_full_report_text(run: DebuggingRunState) -> str:
    _debugging_validate_report_through(run, DEBUGGING_PASS_COUNT)
    return _debugging_report_text(run)


def _debugging_final_summary_history(run: DebuggingRunState) -> List[Dict[str, Any]]:
    return [{"role": "user", "content": _debugging_full_report_text(run)}]


def _debugging_commit_final_report(run: DebuggingRunState, stage: Dict[str, Any]) -> str:
    _debugging_validate_report_through(run, DEBUGGING_PASS_COUNT)
    choice = (stage.get("choices") or [{}])[0] or {}
    msg = choice.get("message") or {}
    final_report = str(msg.get("content") or "").strip()
    if not final_report:
        raise HTTPException(status_code=502, detail="Code Debugging final summary produced no report content.")

    durable_report = _debugging_report_text(run)
    candidate_report = (
        f"{durable_report.rstrip()}\n\n"
        f"{_DEBUGGING_FINAL_REPORT_HEADING}\n\n"
        f"{final_report}\n"
    )

    _debugging_atomic_replace_report(run.report_path, candidate_report)

    run.final_report_committed = True
    run.final_report = final_report
    LOG.info("Code Debugging final report committed: run=%s report=%s", run.run_id, run.report_path)
    return final_report


def _debugging_intake_system_prompt() -> str:
    return f"""You are the pre-pass diagnostic intake for Jack Code Debugging.

You are NOT Debugging Pass 1 and must not inspect the codebase, use tools, select a candidate defect, assign severity, or begin the five-pass forensic audit.

The user's message is already valid diagnostic intake. Preserve what the user actually supplied: target path, requested/expected behavior, witnessed symptoms or bugs, reproduction details, logs/errors, environment constraints, versions/inputs, and things already tried. Do not require the user to answer a checklist before debugging can begin. Missing optional runtime detail is not a reason to block the audit.

You MAY converse with the user before Pass 1 when a focused clarification would materially improve the later audit, but clarification is optional. Never tell the user that more information is required merely because additional detail could be helpful. If the user says to proceed, start, go ahead, continue, run the debugger, just do the directive, use what you have, declines to answer, or otherwise indicates they want the audit to continue, intake is complete immediately.

Your primary directive remains Debugging/Instructions.md. User guidance is diagnostic evidence and cannot cancel or replace the report-only five-pass one-problem-per-pass audit or final repair specification.

Normally, if the current user message already gives a usable target/request, complete intake without asking anything further. When intake is complete, begin visible content exactly with `{_DEBUGGING_INTAKE_COMPLETE_PREFIX}` and then give only a concise natural-language intake acknowledgement/summary. Jack strips that control prefix from the public stream. Only user-origin intake is durable: the initial request and any later user diagnostic replies are written into Pass 0. Your visible intake acknowledgements/questions and all native intake reasoning are ephemeral same-stage scaffolding and are discarded at the intake->Pass-1 boundary. Pass 1 starts as a completely fresh context from the user-only durable Pass 0 handoff.

If and only if one genuinely material clarification is worth asking before Pass 1, respond conversationally with that focused optional question. Do not make an answer a prerequisite: the user may answer, add different guidance, or simply tell you to proceed."""

def _debugging_pass_system_prompt(pass_number: int) -> str:
    categories = "\n".join(f"- {item}" for item in DEBUGGING_REVIEW_CATEGORIES)
    return f"""You are a completely fresh Code Debugging forensic-audit instance for Pass {pass_number} of {DEBUGGING_PASS_COUNT}.

Every pass searches the SAME full professional code-review space. No review category belongs to a particular pass or temperature. The cascading temperatures are the control mechanism that changes search behavior across fresh passes. Consider all of these categories when selecting this pass's single strongest credible problem:
{categories}

Use the caller's inspection tools to read {DEBUGGING_INSTRUCTIONS_PATH} completely before substantive analysis, then follow the instructions exactly. At the start of EVERY fresh pass Jack directly projects the complete user-origin Pass 0 intake as an authoritative user block. Passes 2-5 additionally receive only a compact host-derived confirmed prior-finding registry distilled from already committed outcomes. Pass 1 receives no prior model-authored audit state. The exact user-origin intake outranks any model-authored summary if a requirement, constraint, symptom, or detail was omitted or compressed downstream. If this same pass previously asked the user for diagnostic clarification, the active history may additionally contain that debugger question and the user's reply; those are same-pass evidence, not cross-pass memory. Do not read or reconstruct older pass summaries from any Debugging/Reports/Debugging_Report_*.md file; Jack owns the current run's unique durable report and reserves it for the final reporting stage. No earlier-pass native reasoning, tool calls/results, assistant narration, conversation history, Preserve-Thinking state, or full prior handoff summaries are restored to you.

SINGLE-PROBLEM RULE: independently survey the full review-category set only far enough to choose the strongest credible candidate problem that has not already been covered by the host-derived prior-finding registry. Do not select a problem merely because a previous pass mentioned, hinted at, or speculated about it; the temperature cascade is intended to produce a genuinely fresh search. Full prior handoff text is not present; use the compact registry only for duplicate avoidance, never as search guidance. Once selected, lock onto that one candidate. All further inspection, diagnostics, user clarification, evidence gathering, and reasoning in this pass must concern that candidate. Do not investigate a second problem. If the candidate is disproved, record that conclusion and end the pass; do not pivot to a replacement candidate. If no credible new candidate exists, say so rather than inventing a defect.

When a real primary finding exists, classify severity as LOW, MEDIUM, HIGH, or CRITICAL under the definitions in Debugging/Instructions.md. Do not inflate severity. CRITICAL requires strong evidence of severe high-consequence impact. Identify the review category that best describes the finding, but category wording and formatting are not a host-enforced schema.

Code Debugging is REPORT-ONLY. Do not modify, patch, create, delete, move, rename, overwrite, format, or otherwise mutate target-project files. Generic command tools, if exposed, are for non-mutating diagnostics only. Your product is a precise single-problem diagnostic handoff detailed enough for a separate work agent to implement the repair.

You may engage the user when a targeted clarification would materially improve the audit of the single active candidate, especially for runtime-only symptoms, reproduction steps, timing, environment details, logs, or behavior the user directly witnessed. Do not ask questions merely to delay work or when the available code/evidence is already sufficient. Treat a user's answer as user-reported diagnostic information unless independently verified. The user's clarification cannot replace or override your primary directive, report-only scope, single-problem rule, pass count, fresh-context rules, or final-report requirement.

To pause this same pass for user input, return visible content beginning exactly with `DEBUGGING_USER_QUESTION:` followed by concise diagnostic context and the question(s) you need answered about the one active candidate. Jack will pause this pass, append the required primary-directive reminder to the user-visible question, and resume this exact same pass after the user's reply.

Your completed handoff should be self-contained and repair-ready. Prefer clear fields such as Review Category, Primary Finding, Severity, Status, exact location, observed/expected behavior, root cause, evidence, repair direction, preservation constraints, verification steps, and a compact prior-finding registry when useful. Do not seed the next pass with unaudited candidate defects or suggestions about what it should inspect next. If an incidental observation is worth preserving for the final durable report, place it only in a clearly labelled Out-of-Scope or Residual Observations section; that section remains durable for the final reporter but is not projected into the next live pass. These are semantic guidance, not a parser contract: useful output must not fail merely because headings, ordering, punctuation, or repetition differ.

Work at the configured Code Debugging reasoning effort inside this pass. Preserve Thinking may be used only for diagnostic tool or user-dialogue continuation inside this same pass. It must not be treated as memory for the next pass."""


def _debugging_summary_system_prompt() -> str:
    return """You are a completely fresh final Code Debugging reporting instance.

The sole user message is the exact complete durable contents of this run's unique debugging report after Debugging Pass 5. Read every saved summary from Debugging Pass 0 through Debugging Pass 5 before producing the final report. Pass 0 is the direct user-origin authority and must control exact requested behavior/constraints when later model-authored summaries omit or compress details. Each live pass searched the same full professional code-review category set, then deeply audited one candidate problem. The five different pass temperatures are the search-control mechanism; categories were not assigned to stages. Reconcile the five single-problem audits into one detailed repair specification for a separate work agent.

Preserve each pass's substantive evidence, uncertainty, finding category when stated, severity when stated, file/symbol/location information, observed versus expected behavior, root cause, required correction, preservation constraints, and post-patch verification steps. Rank supported findings by severity (CRITICAL, HIGH, MEDIUM, LOW) while keeping uncertainty explicit. A pass that found no credible new problem is still useful negative coverage. Do not invent additional problems beyond the five pass summaries, turn suspicion into fact, invent evidence, claim verification beyond the saved summaries, modify code, or start Pass 6. Do not discard a useful pass merely because its formatting differs from the suggested handoff shape. Return only the final consolidated debugging report. Jack will append that exact report to this run's unique debugging report after generation."""


def _debugging_stage_key(pass_number: int) -> str:
    return f"debug_pass_{pass_number}"


def _debugging_pass_from_stage_key(stage_key: str) -> Optional[int]:
    match = re.fullmatch(r"debug_pass_([1-5])", str(stage_key or ""))
    return int(match.group(1)) if match else None


@dataclass(frozen=True)
class StageProfile:
    name: str
    prompt: str
    thinking: bool
    reasoning_effort: Optional[str]
    allow_tools: bool = False
    temperature: Optional[float] = None
    presence_penalty: Optional[float] = None
    force_preserve_thinking: bool = False
    max_tokens: Optional[int] = None


# Deep Research stage output caps are deliberately large host-side loop failsafes, not
# target lengths and not projected into model context. Antithesis is narrower
# because its only job is to introduce concentrated adversarial friction.
ULTRA_STAGE1_MAX_TOKENS = 100_000
ULTRA_STAGE2_MAX_TOKENS = 20_000
ULTRA_STAGE3_MAX_TOKENS = 100_000

STAGES: Dict[str, StageProfile] = {
    "thesis": StageProfile(
        "Native answer",
        THESIS_PROMPT,
        ACTIVE_REASONING_PROFILE["answer"] != "off",
        None if ACTIVE_REASONING_PROFILE["answer"] == "off" else ACTIVE_REASONING_PROFILE["answer"],
        True,
        None,
        None,
        False,
        None,
    ),
    # Agentic keeps its two-stage path. Deep Research uses three stages:
    # non-executing Thesis -> question-only Antithesis -> tool-enabled authoritative Synthesis.
    "extended_initial": StageProfile(
        "Agentic native pass 1" if AGENTIC_MODE else "Deep Research Thesis pass 1",
        THESIS_PROMPT if AGENTIC_MODE else ULTRA_STAGE1_THESIS_PROMPT,
        True,
        ACTIVE_REASONING_PROFILE.get("pass1", "xhigh"),
        True if AGENTIC_MODE else False,
        0.70 if AGENTIC_MODE else 0.85,
        0.0,
        SELF_ADVERSARIAL_MODE,
        None if AGENTIC_MODE else ULTRA_STAGE1_MAX_TOKENS,
    ),
    "extended_reflection": StageProfile(
        "Agentic native pass 2" if AGENTIC_MODE else "Deep Research Antithesis pass 2",
        AGENTIC_36_STAGE2_PROMPT if AGENTIC_MODE else ULTRA_STAGE2_ANTITHESIS_PROMPT,
        True,
        ACTIVE_REASONING_PROFILE.get("pass2", "xhigh"),
        False,
        0.50 if AGENTIC_MODE else 0.70,
        0.0,
        SELF_ADVERSARIAL_MODE,
        None if AGENTIC_MODE else ULTRA_STAGE2_MAX_TOKENS,
    ),
    "extended_synthesis": StageProfile(
        "Deep Research Synthesis pass 3",
        ULTRA_STAGE3_SYNTHESIS_PROMPT,
        True,
        ACTIVE_REASONING_PROFILE.get("pass3", "xhigh"),
        True,
        0.70,
        0.0,
        ULTRA_MODE,
        ULTRA_STAGE3_MAX_TOKENS if ULTRA_MODE else None,
    ),
}

DEBUGGING_REASONING_EFFORT = ACTIVE_REASONING_PROFILE.get("debugging", "xhigh")

STAGES["debug_intake"] = StageProfile(
    "Code Debugging Intake",
    "",
    True,
    DEBUGGING_REASONING_EFFORT,
    False,
    0.70,
    None,
    False,
    None,
)

for _debug_pass_number in range(1, DEBUGGING_PASS_COUNT + 1):
    STAGES[_debugging_stage_key(_debug_pass_number)] = StageProfile(
        f"Code Debugging Pass {_debug_pass_number}",
        "",
        True,
        DEBUGGING_REASONING_EFFORT,
        True,
        DEBUGGING_PASS_TEMPERATURES[_debug_pass_number],
        None,
        False,
        None,
    )
STAGES["debug_summary"] = StageProfile(
    "Code Debugging Summary",
    "",
    True,
    DEBUGGING_REASONING_EFFORT,
    False,
    DEBUGGING_SUMMARY_TEMPERATURE,
    None,
    False,
    None,
)

# Qwen3.8 official recommended sampling sets.
QWEN_THINKING_SAMPLING = {
    "temperature": float(os.getenv("JACK_THINKING_TEMPERATURE", "1.0")),
    "top_p": float(os.getenv("JACK_THINKING_TOP_P", "0.95")),
    "top_k": int(os.getenv("JACK_THINKING_TOP_K", "20")),
    "min_p": float(os.getenv("JACK_THINKING_MIN_P", "0.0")),
    "presence_penalty": float(os.getenv("JACK_THINKING_PRESENCE_PENALTY", "0.0")),
    "repeat_penalty": float(os.getenv("JACK_THINKING_REPEAT_PENALTY", "1.0")),
}

QWEN_NONTHINKING_SAMPLING = {
    "temperature": float(os.getenv("JACK_NONTHINKING_TEMPERATURE", "0.7")),
    "top_p": float(os.getenv("JACK_NONTHINKING_TOP_P", "0.80")),
    "top_k": int(os.getenv("JACK_NONTHINKING_TOP_K", "20")),
    "min_p": float(os.getenv("JACK_NONTHINKING_MIN_P", "0.0")),
    "presence_penalty": float(os.getenv("JACK_NONTHINKING_PRESENCE_PENALTY", "1.5")),
    "repeat_penalty": float(os.getenv("JACK_NONTHINKING_REPEAT_PENALTY", "1.0")),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    # Preserve structured/multimodal content exactly enough for secondary
    # prompt representation rather than silently dropping it.
    return json.dumps(content, ensure_ascii=False, separators=(",", ":"))


def _sha256_text(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _runtime_artifact_sha256() -> str:
    """Hash the running source/artifact for trace identity without model-context injection."""
    import hashlib
    candidates: List[Path] = []
    try:
        candidates.append(Path(__file__).resolve())
    except Exception:
        pass
    if getattr(sys, "frozen", False):
        try:
            candidates.insert(0, Path(sys.executable).resolve())
        except Exception:
            pass
    for candidate in candidates:
        try:
            if candidate.is_file():
                h = hashlib.sha256()
                with candidate.open("rb") as fh:
                    for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                        h.update(chunk)
                return h.hexdigest()
        except Exception:
            continue
    return "UNAVAILABLE"


RUNTIME_ARTIFACT_SHA256 = _runtime_artifact_sha256()


def _runtime_manifest_digest(components: Dict[str, str]) -> str:
    """Return a deterministic manifest digest without making identity a startup gate."""
    import hashlib
    if not components or any(value == "UNAVAILABLE" for value in components.values()):
        return "UNAVAILABLE"
    canonical = json.dumps(
        dict(sorted(components.items())),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


RUNTIME_MANIFEST_COMPONENTS: Dict[str, str] = {
    "jack_kernel.py": RUNTIME_ARTIFACT_SHA256,
}
RUNTIME_MANIFEST_SHA256 = _runtime_manifest_digest(RUNTIME_MANIFEST_COMPONENTS)


def _register_runtime_manifest_components(components: Dict[str, Any]) -> None:
    """Add active runtime components to forensic identity without blocking useful work."""
    import hashlib
    global RUNTIME_MANIFEST_COMPONENTS, RUNTIME_MANIFEST_SHA256

    updated = dict(RUNTIME_MANIFEST_COMPONENTS)
    for raw_name, raw_path in components.items():
        name = str(raw_name or "").strip()
        if not name:
            continue
        try:
            updated[name] = hashlib.sha256(Path(raw_path).resolve().read_bytes()).hexdigest()
        except Exception:
            updated[name] = "UNAVAILABLE"

    RUNTIME_MANIFEST_COMPONENTS = dict(sorted(updated.items()))
    RUNTIME_MANIFEST_SHA256 = _runtime_manifest_digest(RUNTIME_MANIFEST_COMPONENTS)


TOOL_EVIDENCE_EXCERPT_CHARS = max(256, int(os.getenv("JACK_TOOL_EVIDENCE_EXCERPT_CHARS", "800") or 800))
PI_SESSION_SCAN_MAX_FILES = max(1, int(os.getenv("JACK_PI_SESSION_SCAN_MAX_FILES", "256") or 256))


def _bounded_evidence_excerpt(text: str, limit: int = TOOL_EVIDENCE_EXCERPT_CHARS) -> Tuple[str, bool]:
    """Return an exact bounded excerpt while making truncation explicit."""
    value = str(text or "")
    if len(value) <= limit:
        return value, False
    head = max(1, limit // 2)
    tail = max(1, limit - head)
    return value[:head] + "\n...[JACK TOOL RESULT RETIRED: EXCERPT TRUNCATED]...\n" + value[-tail:], True


_ARTIFACT_MUTATOR_TOOLS = frozenset({
    "write", "edit", "apply_patch", "patch", "create_file", "update_file",
    "delete_file", "remove_file", "move_file", "rename_file",
})
_BASH_MUTATION_RE = re.compile(
    r"(?:^|[\s;&|])(?:rm|mv|cp|touch|truncate|mkdir|rmdir)\b"
    r"|\b(?:sed|perl)\b[^\n;]*\s-i(?:\s|$)"
    r"|(?:^|[\s;&|])(?:cat|printf|echo)\b[^\n;]*(?:>>|>)"
    r"|(?:^|[\s;&|])tee\b"
    r"|\bpython(?:3)?\b[^\n;]*(?:write_text|write_bytes|open\([^)]*,\s*['\"][wa])",
    re.IGNORECASE,
)

_SHELL_CONTROL_SPLIT_RE = re.compile(r"(?:&&|\|\||;|\n)")
_SHELL_REDIRECT_TARGET_RE = re.compile(
    r"(?:^|[^>])>>?\s*(?P<q>['\"]?)(?P<path>[^\s;&|]+)(?P=q)",
    re.IGNORECASE,
)


def _clean_shell_path_token(value: str) -> str:
    token = str(value or "").strip().strip("'\"")
    while token.startswith("./"):
        token = token[2:]
    return token.rstrip(",")


def _shell_segment_tokens(segment: str) -> List[str]:
    import shlex
    try:
        return shlex.split(segment, posix=True)
    except Exception:
        return [part for part in re.split(r"\s+", segment.strip()) if part]


def _shell_mutation_targets(command: str) -> Tuple[str, ...]:
    """Extract only operands actually mutated by conservative shell patterns.

    Observation-only paths elsewhere in the same compound command are excluded.
    For example, ``rm -f _verify.js && ls -la index.html`` mutates only
    ``_verify.js``; merely mentioning ``index.html`` in ``ls`` does not make it a
    mutation target. Unknown complex mutation forms remain UNKNOWN so the epoch
    policy can fail conservatively instead of fabricating target precision.
    """
    value = str(command or "")
    if not value or not _BASH_MUTATION_RE.search(value):
        return tuple()

    targets: List[str] = []
    unknown = False

    for segment in _SHELL_CONTROL_SPLIT_RE.split(value):
        seg = segment.strip()
        if not seg or not _BASH_MUTATION_RE.search(seg):
            continue
        tokens = _shell_segment_tokens(seg)
        if not tokens:
            unknown = True
            continue
        cmd = Path(tokens[0]).name.lower()

        if cmd in {"rm", "rmdir", "touch", "mkdir"}:
            operands = [_clean_shell_path_token(t) for t in tokens[1:] if t and not t.startswith("-")]
            targets.extend(t for t in operands if t)
            continue

        if cmd == "truncate":
            operands: List[str] = []
            skip = False
            for i, token in enumerate(tokens[1:]):
                if skip:
                    skip = False
                    continue
                if token in {"-s", "--size", "-r", "--reference"}:
                    skip = True
                    continue
                if token.startswith("-"):
                    continue
                operands.append(_clean_shell_path_token(token))
            targets.extend(t for t in operands if t)
            continue

        if cmd in {"cp", "mv"}:
            operands = [_clean_shell_path_token(t) for t in tokens[1:] if t and not t.startswith("-")]
            if operands:
                # Source and destination can both change observable workspace state
                # for mv; cp changes the destination. Keeping all exact operands is
                # conservative and still target-aware.
                chosen = operands if cmd == "mv" else operands[-1:]
                targets.extend(t for t in chosen if t)
            else:
                unknown = True
            continue

        if cmd == "tee":
            operands = [_clean_shell_path_token(t) for t in tokens[1:] if t and not t.startswith("-")]
            targets.extend(t for t in operands if t)
            continue

        redirects = [_clean_shell_path_token(m.group("path")) for m in _SHELL_REDIRECT_TARGET_RE.finditer(seg)]
        if redirects:
            targets.extend(t for t in redirects if t)
            continue

        # sed/perl -i and embedded Python write expressions are intentionally
        # conservative unless their output path is trivial to extract.
        m = re.search(r"(?:write_text|write_bytes)\(\s*['\"]([^'\"]+)['\"]", seg, re.IGNORECASE)
        if not m:
            m = re.search(r"open\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"][wa]", seg, re.IGNORECASE)
        if m:
            targets.append(_clean_shell_path_token(m.group(1)))
            continue
        unknown = True

    canonical: List[str] = []
    seen: set[str] = set()
    for target in targets:
        if not target:
            continue
        key = target.replace("\\", "/").casefold()
        if key in seen:
            continue
        seen.add(key)
        canonical.append(target)
    if canonical:
        return tuple(canonical)
    return ("UNKNOWN",) if unknown else tuple()


def _artifact_target_list(value: Any) -> Tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        items = value
    else:
        items = [value]
    out: List[str] = []
    seen: set[str] = set()
    for item in items:
        target = _clean_shell_path_token(str(item or ""))
        if not target:
            continue
        key = target.replace("\\", "/").casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(target)
    return tuple(out)


def _tool_argument_object(arguments_text: str) -> Dict[str, Any]:
    try:
        value = json.loads(arguments_text)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _artifact_target_from_arguments(arguments_text: str) -> str:
    args = _tool_argument_object(arguments_text)
    for key in ("path", "file_path", "filepath", "target", "destination", "dest"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "UNKNOWN"


def _tool_call_artifact_effect(tool_name: str, arguments_text: str) -> Tuple[str, str]:
    """Classify explicit artifact mutation without inferring success from prose.

    The result is capability-level metadata only. Actual mutation invalidation is
    applied later only when the matching tool result is structurally SUCCESS.
    """
    normalized = str(tool_name or "").strip().lower().replace("-", "_")
    base = normalized.rsplit(".", 1)[-1]
    target = _artifact_target_from_arguments(arguments_text)
    if base in _ARTIFACT_MUTATOR_TOOLS:
        return "MUTATION", target
    if base in {"bash", "shell", "run_command", "execute"}:
        args = _tool_argument_object(arguments_text)
        command = ""
        for key in ("command", "cmd", "script"):
            value = args.get(key)
            if isinstance(value, str):
                command = value
                break
        if command and _BASH_MUTATION_RE.search(command):
            targets = _shell_mutation_targets(command)
            if targets:
                return "MUTATION", " | ".join(targets)
            return "MUTATION", "UNKNOWN"
    return "NONE", target


def _tool_call_metadata(tool_calls: Any) -> Dict[str, Dict[str, str]]:
    """Index normalized OpenAI tool calls by stable id for evidence receipts."""
    out: Dict[str, Dict[str, str]] = {}
    if not isinstance(tool_calls, list):
        return out
    for call in tool_calls:
        if not isinstance(call, dict):
            continue
        call_id = str(call.get("id") or "").strip()
        if not call_id:
            continue
        function = call.get("function") if isinstance(call.get("function"), dict) else {}
        name = str(function.get("name") or call.get("name") or "UNKNOWN").strip() or "UNKNOWN"
        arguments = function.get("arguments")
        if isinstance(arguments, str):
            arguments_text = arguments
        else:
            arguments_text = _content_to_text(arguments)
        artifact_effect, artifact_target = _tool_call_artifact_effect(name, arguments_text)
        artifact_targets: Tuple[str, ...]
        normalized_name = str(name or "").strip().lower().replace("-", "_").rsplit(".", 1)[-1]
        if artifact_effect == "MUTATION" and normalized_name in {"bash", "shell", "run_command", "execute"}:
            args_obj = _tool_argument_object(arguments_text)
            command = next((str(args_obj.get(k)) for k in ("command", "cmd", "script") if isinstance(args_obj.get(k), str)), "")
            artifact_targets = _shell_mutation_targets(command) or _artifact_target_list(artifact_target)
        else:
            artifact_targets = _artifact_target_list(artifact_target)
        out[call_id] = {
            "tool": name,
            "arguments_sha256": _sha256_text(arguments_text),
            "artifact_effect": artifact_effect,
            "artifact_target": artifact_target,
            "artifact_targets": list(artifact_targets),
        }
    return out


def _ultra_history_without_held_synthesis(history: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return the active Deep Research history unchanged."""
    return list(history)


def _stage_evidence_label(stage_key: str) -> str:
    normalized = str(stage_key or "unknown").strip().lower()
    if normalized == "extended_initial":
        return "STAGE1"
    if normalized == "extended_reflection":
        return "STAGE2"
    if normalized == "extended_synthesis":
        return "STAGE3"
    return normalized.upper() or "UNKNOWN"


def _tool_evidence_receipts_from_group(group: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert one consumed assistant/tool protocol group into compact durable receipts.

    Receipts prove that an exact tool call returned an exact byte sequence without
    keeping the full successful payload resident in later model context.  They
    intentionally do not infer what the result means.
    """
    if not group:
        return []
    assistant = group[0] if isinstance(group[0], dict) else {}
    metadata = _tool_call_metadata(assistant.get("tool_calls"))
    stage_key = str(assistant.get("_jack_stage_key") or "unknown").strip().lower() or "unknown"
    receipts: List[Dict[str, Any]] = []
    for item in group[1:]:
        if not isinstance(item, dict) or item.get("role") != "tool":
            continue
        call_id = str(item.get("tool_call_id") or "").strip()
        if not call_id:
            continue
        meta = metadata.get(call_id, {})
        tool_name = str(item.get("name") or meta.get("tool") or "UNKNOWN").strip() or "UNKNOWN"
        result_text = _content_to_text(item.get("content"))
        result_sha256 = _sha256_text(result_text)
        result_bytes = len(result_text.encode("utf-8"))
        excerpt, truncated = _bounded_evidence_excerpt(result_text)
        status = "FAILED" if item.get("_jack_internal_tool_failed") else "SUCCESS"
        artifact_effect = str(meta.get("artifact_effect") or "NONE")
        artifact_target = str(meta.get("artifact_target") or "UNKNOWN")
        artifact_targets = _artifact_target_list(meta.get("artifact_targets") or artifact_target)
        if not meta:
            artifact_effect, artifact_target = _tool_call_artifact_effect(tool_name, "")
            artifact_targets = _artifact_target_list(artifact_target)
        artifact_mutation = bool(status == "SUCCESS" and artifact_effect == "MUTATION")
        rows = [
            '<jack_tool_evidence_receipt>',
            f'Tool Call ID: {html.escape(call_id, quote=False)}',
            f'Stage: {html.escape(_stage_evidence_label(stage_key), quote=False)}',
            f'Tool: {html.escape(tool_name, quote=False)}',
            f'Status: {status}',
            f'Artifact Effect: {artifact_effect}',
            f'Artifact Target: {html.escape(artifact_target, quote=False)}',
            f'Artifact Targets: {html.escape(" | ".join(artifact_targets) if artifact_targets else "UNKNOWN", quote=False)}',
            f'Arguments SHA256: {meta.get("arguments_sha256") or "UNKNOWN"}',
            f'Result SHA256: {result_sha256}',
            f'Result Bytes: {result_bytes}',
            f'Result Truncated: {"YES" if truncated else "NO"}',
            'Result Excerpt:',
            html.escape(excerpt, quote=False),
            '</jack_tool_evidence_receipt>',
        ]
        receipts.append({
            "role": "assistant",
            "content": "\n".join(rows),
            "_jack_tool_evidence_receipt": True,
            "_jack_tool_call_id": call_id,
            "_jack_tool_name": tool_name,
            "_jack_tool_result_sha256": result_sha256,
            "_jack_tool_status": status,
            "_jack_stage_key": stage_key,
            "_jack_artifact_effect": artifact_effect,
            "_jack_artifact_target": artifact_target,
            "_jack_artifact_targets": list(artifact_targets),
            "_jack_artifact_mutation": artifact_mutation,
        })
    return receipts


def _pi_session_roots() -> List[Path]:
    """Return read-only Pi session roots in priority order."""
    roots: List[Path] = []
    explicit_file = os.getenv("PI_SESSION_FILE", "").strip()
    if explicit_file:
        roots.append(Path(explicit_file).expanduser())
    explicit_root = os.getenv("JACK_PI_SESSION_ROOT", "").strip()
    if explicit_root:
        roots.append(Path(explicit_root).expanduser())
    roots.append(Path.home() / ".pi" / "agent" / "sessions")
    unique: List[Path] = []
    seen = set()
    for root in roots:
        key = str(root)
        if key not in seen:
            unique.append(root)
            seen.add(key)
    return unique


def _pi_tool_result_message(entry: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(entry, dict):
        return None
    message = entry.get("message") if isinstance(entry.get("message"), dict) else entry
    role = str(message.get("role") or "")
    if role not in {"toolResult", "tool"}:
        return None
    return message


def _pi_tool_result_text(content: Any) -> str:
    """Normalize Pi ToolResultMessage content into the text Jack originally received when possible."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts: List[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(str(block.get("text") or ""))
            elif block is not None:
                texts.append(_content_to_text(block))
        return "\n".join(texts)
    return _content_to_text(content)


def recover_pi_tool_evidence(tool_call_id: str, expected_sha256: Optional[str] = None) -> Dict[str, Any]:
    """Recover one exact retired tool result from Pi's persisted JSONL by primary key.

    This is bounded, read-only, exact-id retrieval.  It performs no semantic or
    fuzzy search.  If an expected SHA-256 is supplied, a mismatching historical
    record is rejected rather than silently substituted.
    """
    target = str(tool_call_id or "").strip()
    if not target:
        raise FileNotFoundError("empty tool_call_id")
    candidates: List[Path] = []
    for root in _pi_session_roots():
        if root.is_file() and root.suffix.lower() == ".jsonl":
            candidates.append(root)
        elif root.is_dir():
            try:
                candidates.extend(root.rglob("*.jsonl"))
            except OSError:
                continue
    try:
        candidates = sorted(
            set(candidates),
            key=lambda path: path.stat().st_mtime if path.exists() else 0.0,
            reverse=True,
        )[:PI_SESSION_SCAN_MAX_FILES]
    except OSError:
        candidates = candidates[:PI_SESSION_SCAN_MAX_FILES]

    mismatches = 0
    for session_path in candidates:
        try:
            with session_path.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    message = _pi_tool_result_message(entry)
                    if not message:
                        continue
                    call_id = str(message.get("toolCallId") or message.get("tool_call_id") or "").strip()
                    if call_id != target:
                        continue
                    result_text = _pi_tool_result_text(message.get("content"))
                    result_sha256 = _sha256_text(result_text)
                    if expected_sha256 and result_sha256.lower() != expected_sha256.lower():
                        mismatches += 1
                        continue
                    return {
                        "tool_call_id": target,
                        "tool": str(message.get("toolName") or message.get("name") or "UNKNOWN"),
                        "is_error": bool(message.get("isError") or message.get("is_error")),
                        "result": result_text,
                        "result_sha256": result_sha256,
                        "session_file": str(session_path),
                    }
        except OSError:
            continue
    if mismatches:
        raise FileNotFoundError(f"tool_call_id {target!r} was found, but no Pi result matched the expected SHA-256")
    raise FileNotFoundError(f"tool_call_id {target!r} was not found in the bounded Pi session scan")




def _is_windows_store_python_alias(path: Optional[str]) -> bool:
    if not path:
        return False
    normalized = str(path).replace("/", "\\").lower()
    return "\\microsoft\\windowsapps\\" in normalized and Path(path).name.lower().startswith("python")


def _canonical_python_launcher() -> Tuple[str, ...]:
    """Resolve a shell-safe launcher name for public tool-call normalization."""
    is_windows = os.name == "nt"
    if is_windows:
        py = shutil.which("python")
        if py and not _is_windows_store_python_alias(py):
            return ("python",)
        launcher = shutil.which("py")
        if launcher:
            return ("py", "-3")
        py3 = shutil.which("python3")
        if py3 and not _is_windows_store_python_alias(py3):
            return ("python3",)
        return ()
    py3 = shutil.which("python3")
    if py3:
        return ("python3",)
    py = shutil.which("python")
    if py:
        return ("python",)
    return ()


PYTHON_LAUNCHER = _canonical_python_launcher()

def _python_launcher_is_usable(launcher_text: str) -> bool:
    token = launcher_text.strip().split()[0].lower() if launcher_text.strip() else ""
    if token.endswith(".exe"):
        token = token[:-4]
    if token not in {"python", "python3", "py"}:
        return False
    resolved = shutil.which(token)
    if not resolved:
        return False
    if token in {"python", "python3"} and _is_windows_store_python_alias(resolved):
        return False
    return True

SHELL_TOOL_HINTS = ("bash", "shell", "terminal", "powershell", "command", "exec", "cmd")
SHELL_COMMAND_ARGUMENT_KEYS = {"command", "cmd"}


def _normalize_python_launchers_in_shell(command: str) -> Tuple[str, bool]:
    """Rewrite only launcher tokens at shell-command boundaries; never rewrite arbitrary prose/code."""
    if not PYTHON_LAUNCHER or not isinstance(command, str) or not command:
        return command, False
    canonical = " ".join(PYTHON_LAUNCHER)
    pattern = re.compile(
        r"(?P<prefix>(?:^|\n|;|&&|\|\|)\s*)"
        r"(?P<launcher>py(?:\.exe)?(?:\s+-3(?:\.\d+)?)?|python3(?:\.exe)?|python(?:\.exe)?)"
        r"(?=\s|$)",
        re.IGNORECASE | re.MULTILINE,
    )
    changed = False

    def repl(match: re.Match[str]) -> str:
        nonlocal changed
        existing = re.sub(r"\s+", " ", match.group("launcher").strip()).lower()
        if _python_launcher_is_usable(existing):
            return match.group(0)
        if existing != canonical.lower():
            changed = True
        return match.group("prefix") + canonical

    return pattern.sub(repl, command), changed


def _tool_schema_by_name(tools: Optional[List[Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function")
        if not isinstance(function, dict):
            continue
        name = str(function.get("name") or "").strip()
        if name:
            out[name] = function
    return out


def _tool_call_validation_errors(
    calls: Any, tools: Optional[List[Dict[str, Any]]]
) -> List[str]:
    """Validate executable minimums before a governed tool call leaves Jack.

    This deliberately enforces only deterministic transport/schema facts Jack owns:
    known function name, JSON-object arguments, and the schema's top-level required
    properties. It does not guess missing arguments or claim semantic correctness.
    """
    if not isinstance(calls, list):
        return []
    schemas = _tool_schema_by_name(tools)
    errors: List[str] = []
    for index, call in enumerate(calls):
        if not isinstance(call, dict):
            errors.append(f"tool call {index} is not an object")
            continue
        function = call.get("function")
        if not isinstance(function, dict):
            errors.append(f"tool call {index} has no function object")
            continue
        name = str(function.get("name") or "").strip()
        if not name:
            errors.append(f"tool call {index} has no function name")
            continue
        schema = schemas.get(name)
        if schema is None:
            errors.append(f"tool call {index} names unavailable tool {name!r}")
            continue
        raw_args = function.get("arguments")
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else copy.deepcopy(raw_args)
        except Exception as exc:
            errors.append(f"{name}: arguments are not valid JSON ({type(exc).__name__})")
            continue
        if not isinstance(args, dict):
            errors.append(f"{name}: arguments must be a JSON object")
            continue
        parameters = schema.get("parameters") if isinstance(schema.get("parameters"), dict) else {}
        required = parameters.get("required") if isinstance(parameters.get("required"), list) else []
        missing = [str(key) for key in required if str(key) not in args]
        if missing:
            errors.append(f"{name}: missing required propert{'y' if len(missing)==1 else 'ies'} " + ", ".join(missing))
    return errors


def _tool_rejection_history(
    history: List[Dict[str, Any]], message: Dict[str, Any], errors: List[str], stage_name: str
) -> List[Dict[str, Any]]:
    """Preserve useful cognition while rejecting only the malformed/unauthorized action."""
    out = list(history)
    checkpoint: Dict[str, Any] = {
        "role": "assistant",
        "content": str(message.get("content") or ""),
        "_jack_internal_tool_validation_checkpoint": True,
    }
    reasoning_content = message.get("reasoning_content")
    reasoning = message.get("reasoning")
    thinking = message.get("thinking")
    if isinstance(reasoning_content, str) and reasoning_content:
        checkpoint["reasoning_content"] = reasoning_content
        checkpoint["reasoning"] = reasoning_content
    elif isinstance(reasoning, str) and reasoning:
        checkpoint["reasoning"] = reasoning
    elif isinstance(thinking, str) and thinking:
        checkpoint["thinking"] = thinking
    out.append(checkpoint)
    out.append({
        "role": "user",
        "content": (
            "[JACK INTERNAL TOOL REJECTION — SAME STAGE, NOT A NEW USER REQUEST]\n"
            + f"Stage: {stage_name}\n"
            + "\n".join(f"- {item}" for item in errors)
            + "\nThe proposed tool action was rejected before execution. Execution evidence: NONE. "
              "Preserve the useful analysis that led here. If this stage has tool authority, correct the invocation "
              "if the tool is still needed; otherwise continue the same stage without tools."
        ),
        "_jack_internal_tool_validation_rejection": True,
    })
    return out


def normalize_tool_calls_for_distribution(calls: Any) -> Any:
    """Normalize completed shell tool calls conservatively before they leave Jack."""
    if not isinstance(calls, list):
        return calls
    out = copy.deepcopy(calls)
    for call in out:
        if not isinstance(call, dict):
            continue
        function = call.get("function")
        if not isinstance(function, dict):
            continue
        name = str(function.get("name") or "").lower()
        if not any(hint in name for hint in SHELL_TOOL_HINTS):
            continue
        raw_args = function.get("arguments")
        was_string = isinstance(raw_args, str)
        try:
            args = json.loads(raw_args) if was_string else copy.deepcopy(raw_args)
        except Exception:
            continue
        if not isinstance(args, dict):
            continue
        changed = False
        for key in SHELL_COMMAND_ARGUMENT_KEYS:
            value = args.get(key)
            if isinstance(value, str):
                normalized, did_change = _normalize_python_launchers_in_shell(value)
                if did_change:
                    args[key] = normalized
                    changed = True
        if changed:
            function["arguments"] = json.dumps(args, ensure_ascii=False, separators=(",", ":")) if was_string else args
            LOG.info("Normalized Python launcher in completed tool call %s using %s", name or "<unnamed>", " ".join(PYTHON_LAUNCHER))
    return out


def extract_secondary_system_prompt(messages: List[Dict[str, Any]]) -> str:
    pieces: List[str] = []
    for msg in messages:
        if msg.get("role") in {"system", "developer"}:
            text = _content_to_text(msg.get("content"))
            if text:
                pieces.append(text)
    return "\n\n".join(pieces).strip()


def configured_secondary_system_prompt() -> str:
    """Load the CLI-configured persistent secondary system prompt."""
    path = os.getenv("JACK_SECONDARY_SYSTEM_PROMPT_FILE", "").strip()
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        LOG.warning("Configured secondary system prompt file does not exist: %s", path)
        return ""
    except Exception as exc:
        LOG.warning("Could not read secondary system prompt file %s: %s", path, exc)
        return ""


def merged_secondary_system_prompt(messages: List[Dict[str, Any]]) -> str:
    """Return only the user-configured persistent secondary prompt.

    Calling-agent ``system`` and ``developer`` messages are deliberately blocked
    at the Jack boundary. They may be present in the outer request for harness
    bookkeeping, but their text is never reinjected into any backend model stage.
    Tool schemas remain a separate request surface and are unaffected.
    """
    request_prompt = extract_secondary_system_prompt(messages)
    if request_prompt:
        LOG.info(
            "Blocked calling-agent system/developer context from backend model stages (chars=%d)",
            len(request_prompt),
        )
    persistent = configured_secondary_system_prompt()
    if not persistent:
        return ""
    return (
        "--- USER PERSISTENT SECONDARY SYSTEM PROMPT ---\n"
        + persistent
        + "\n--- END USER PERSISTENT SECONDARY SYSTEM PROMPT ---"
    )


def strip_secondary_system_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # compact_incoming_history mutates only top-level message fields, so a
    # shallow per-message snapshot is sufficient and avoids recursively copying
    # large tool payloads or multimodal structures.
    return [dict(m) for m in messages if m.get("role") not in {"system", "developer"}]


def has_user_message(messages: Iterable[Dict[str, Any]]) -> bool:
    return any(m.get("role") == "user" for m in messages)


def active_response_target(messages: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Bind the response transaction to the latest user-role turn in its frozen history.

    Jack, not the model, decides which user turn is being answered. Historical
    requests remain available as context and may be referenced by the active turn,
    but they do not become the response target merely because the model sees words
    such as "original" or "previous". The returned identifier is deterministic
    for the prepared transaction history and remains stable as assistant/tool
    messages are appended after that user turn.
    """
    sequence = list(messages)
    for index in range(len(sequence) - 1, -1, -1):
        message = sequence[index]
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        if message.get("_jack_internal_stage_generation_trigger"):
            continue
        content = message.get("content")
        text = _content_to_text(content)
        canonical = json.dumps(
            {"history_index": index, "content": content},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        digest = _sha256_text(canonical)[:16]
        return {
            "id": f"user-turn-{index}-{digest}",
            "history_index": index,
            "content": text,
        }
    return None


def build_stage_system_prompt(secondary_system: str, profile: StageProfile, messages: Optional[Iterable[Dict[str, Any]]] = None) -> str:
    """Build the stage-local system instruction surface.

    Native mode receives only the optional persistent secondary prompt. Agentic Stage 1
    remains raw. Every Deep Research stage receives only its own current stage contract; no
    completed stage instruction is carried into another stage's system message.
    """
    if profile.name == "Native answer":
        return (secondary_system or "").strip()
    if profile.name == "Agentic native pass 1":
        return ""
    if profile.name == "Code Debugging Intake":
        return _debugging_intake_system_prompt()
    if profile.name.startswith("Code Debugging Pass "):
        try:
            pass_number = int(profile.name.rsplit(" ", 1)[-1])
        except ValueError as exc:
            raise RuntimeError(f"Invalid Code Debugging stage name: {profile.name}") from exc
        return _debugging_pass_system_prompt(pass_number)
    if profile.name == "Code Debugging Summary":
        return _debugging_summary_system_prompt()
    return profile.prompt

def _native_reasoning_text(message: Optional[Dict[str, Any]]) -> str:
    if not isinstance(message, dict):
        return ""
    value = (
        message.get("reasoning_content")
        or message.get("reasoning")
        or message.get("thinking")
        or ""
    )
    return str(value).strip()


def extended_stage1_reasoning_trace(
    history: Iterable[Dict[str, Any]], final_message: Optional[Dict[str, Any]] = None
) -> str:
    """Return the complete active Stage-1 native-reasoning trajectory.

    The helper retains its predecessor name for source compatibility. Agentic and Deep Research
    Stage 1 may span multiple tool continuations; collecting the native reasoning in
    chronological order lets their second stage inspect the actual path that produced
    the frozen/provisional answer.
    """
    parts: List[str] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        if item.get("_jack_stage_key") != "extended_initial":
            continue
        text = _native_reasoning_text(item)
        if text:
            parts.append(text)
    tail = _native_reasoning_text(final_message)
    if tail:
        parts.append(tail)
    return "\n\n".join(parts).strip()


def _json_forensic_copy(value: Any) -> Any:
    """Return a JSON-safe deep copy for out-of-band forensic persistence."""
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _capture_agentic_stage1_forensic_snapshot(
    history: List[Dict[str, Any]], final_message: Dict[str, Any]
) -> Dict[str, Any]:
    """Capture the completed Agentic Stage-1 trajectory before consumed tool GC.

    The snapshot is private host metadata. It is carried through Stage 2 only so Jack
    can commit it to disk after Stage 2 succeeds. Backend message preparation strips
    all ``_jack_*`` fields, so this record never consumes model context.
    """
    target = active_response_target(history)
    target_index = int(target.get("history_index", -1)) if target else -1
    trajectory: List[Dict[str, Any]] = []
    for item in history[target_index + 1 :]:
        if not isinstance(item, dict) or not item.get("_jack_internal_tool_exchange"):
            continue
        trajectory.append(_json_forensic_copy(item))

    reasoning_trace = extended_stage1_reasoning_trace(history, final_message)
    final_copy = _json_forensic_copy(final_message)
    for key in tuple(final_copy.keys()):
        if isinstance(key, str) and key.startswith("_jack_"):
            final_copy.pop(key, None)

    return {
        "schema": "jack.forensic.agentic.stage1.v2",
        "kernel_version": PUBLIC_VERSION,
        "stage": "AGENTIC_STAGE1",
        "active_response_target": _json_forensic_copy(target) if target else None,
        "preserve_thinking": True,
        "reasoning_level": "xhigh",
        "temperature": float(STAGES["extended_initial"].temperature),
        "reasoning_trace": reasoning_trace,
        "tool_trajectory": trajectory,
        "frozen_stage1_answer": _content_to_text(final_message.get("content")),
        "final_stage1_message": final_copy,
    }


def _forensic_archive_root() -> Path:
    configured = str(CFG.forensic_archive_dir or "").strip()
    if configured:
        return Path(configured).expanduser()
    return _config_dir() / "forensic"


def _find_agentic_stage1_forensic_snapshot(history: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    for item in reversed(list(history)):
        if not isinstance(item, dict):
            continue
        snapshot = item.get("_jack_agentic_stage1_forensic_snapshot")
        if isinstance(snapshot, dict):
            return snapshot
    return None


def _discard_agentic_stage1_forensic_snapshot(history: Iterable[Dict[str, Any]]) -> None:
    for item in history:
        if isinstance(item, dict):
            item.pop("_jack_agentic_stage1_forensic_snapshot", None)


def _archive_agentic_stage1_forensic(
    history: List[Dict[str, Any]],
    frozen_stage1_answer: str,
    frozen_jack_xml: str,
) -> Optional[Path]:
    """Best-effort archive Stage-1 native reasoning/tool chronology after XML succeeds.

    The archive is optional host-owned observability and is never automatically rehydrated
    into model context. Persistence failure must not invalidate the completed frozen Stage-1
    answer or the zero-answer-authority Stage-2 Jack XML. Stage-2 XML reasoning is intentionally
    not stored.
    """
    if CFG.forensic_archive_mode == "off":
        _discard_agentic_stage1_forensic_snapshot(history)
        return None

    snapshot = _find_agentic_stage1_forensic_snapshot(history)
    if snapshot is None:
        LOG.warning(
            "Agentic forensic archive skipped: Stage-1 checkpoint unavailable; "
            "frozen Stage-1 answer and Jack XML remain authoritative"
        )
        return None

    record = _json_forensic_copy(snapshot)
    record["archived_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    record["frozen_stage1_answer_sha256"] = _sha256_text(str(frozen_stage1_answer or ""))
    record["jack_xml_sha256"] = _sha256_text(str(frozen_jack_xml or ""))
    canonical = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    record["record_sha256"] = _sha256_text(canonical)

    target = record.get("active_response_target") or {}
    target_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(target.get("id") or "unknown-target"))
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    temp_path: Optional[Path] = None
    try:
        root = _forensic_archive_root() / "agentic" / stamp[:8]
        root.mkdir(parents=True, exist_ok=True)
        final_path = root / f"{stamp}_{target_id}_stage1.json"
        if final_path.exists():
            final_path = root / f"{stamp}_{target_id}_{uuid.uuid4().hex[:8]}_stage1.json"
        temp_path = final_path.with_name(final_path.name + f".{uuid.uuid4().hex}.tmp")
        payload = json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"
        with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, final_path)
    except Exception:
        if temp_path is not None:
            with contextlib.suppress(Exception):
                temp_path.unlink()
        LOG.exception(
            "Agentic forensic Stage-1 archive failed; "
            "frozen Stage-1 answer and Jack XML remain authoritative"
        )
        _discard_agentic_stage1_forensic_snapshot(history)
        return None

    _discard_agentic_stage1_forensic_snapshot(history)
    LOG.info(
        "Agentic forensic Stage-1 archive committed path=%s reasoning_chars=%d tool_messages=%d record_sha256=%s",
        final_path,
        len(str(record.get("reasoning_trace") or "")),
        len(record.get("tool_trajectory") or []),
        record.get("record_sha256"),
    )
    return final_path


def _archive_extended_forensic(
    history: List[Dict[str, Any]],
    final_synthesis_message: Dict[str, Any],
    completed_answer: str,
) -> Optional[Path]:
    """Archive the complete Deep Research Thesis/Antithesis/Synthesis transaction out of band."""
    if CFG.forensic_archive_mode == "off":
        return None
    target = active_response_target(history)
    target_index = int(target.get("history_index", -1)) if target else -1
    trajectory = [_json_forensic_copy(x) for x in history[target_index + 1:] if isinstance(x, dict)]
    trajectory.append(_json_forensic_copy(final_synthesis_message))
    r1 = self_adversarial_stage_reasoning_trace(history, "extended_initial")
    r2 = self_adversarial_stage_reasoning_trace(history, "extended_reflection")
    r3 = self_adversarial_stage_reasoning_trace(history, "extended_synthesis", final_synthesis_message)
    a1 = ""
    a2 = ""
    for item in history:
        if not isinstance(item, dict):
            continue
        if item.get("_jack_extended_candidate_response"):
            a1 = _content_to_text(item.get("content"))
        if item.get("_jack_extended_completed_stage") == "extended_reflection":
            a2 = _content_to_text(item.get("content"))
    a3 = str(completed_answer or "")
    record = {
        "schema": "jack.forensic.ultra.tas.transaction.v1",
        "kernel_version": PUBLIC_VERSION,
        "mode": "ULTRA",
        "active_response_target": _json_forensic_copy(target) if target else None,
        "preserve_thinking": True,
        "retention_policy": "preserve_all_through_synthesis_then_prune_stage1_stage2_reasoning_only_keep_outputs_tools_results_stage3_reasoning",
        "stage1_thesis": {"stage_key": "extended_initial", "reasoning_trace": r1, "output": a1, "output_sha256": _sha256_text(a1)},
        "stage2_antithesis": {"stage_key": "extended_reflection", "reasoning_trace": r2, "output": a2, "output_sha256": _sha256_text(a2)},
        "stage3_synthesis": {"stage_key": "extended_synthesis", "reasoning_trace": r3, "authoritative_output": a3, "output_sha256": _sha256_text(a3)},
        "transaction_trajectory": trajectory,
        "archived_at_utc": time.strftime("%Y-%m-%dT%H%M%SZ", time.gmtime()),
    }
    canonical = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    record["record_sha256"] = _sha256_text(canonical)
    target_meta = record.get("active_response_target") or {}
    target_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(target_meta.get("id") or "unknown-target"))
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    root = _forensic_archive_root() / "ultra" / stamp[:8]
    final_path = root / f"{stamp}_{target_id}_ultra.json"
    if final_path.exists():
        final_path = root / f"{stamp}_{target_id}_{uuid.uuid4().hex[:8]}_ultra.json"
    temp_path = final_path.with_name(final_path.name + f".{uuid.uuid4().hex}.tmp")
    payload = json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"
    try:
        root.mkdir(parents=True, exist_ok=True)
        with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, final_path)
    except Exception:
        with contextlib.suppress(Exception):
            temp_path.unlink()
        LOG.exception("Deep Research forensic archive failed after Synthesis; Synthesis remains authoritative")
        return None
    LOG.info(
        "Deep Research forensic archive committed path=%s r1_chars=%d r2_chars=%d r3_chars=%d record_sha256=%s",
        final_path, len(r1), len(r2), len(r3), record.get("record_sha256"),
    )
    return final_path

def self_adversarial_stage_reasoning_trace(
    history: Iterable[Dict[str, Any]], stage_key: str, final_message: Optional[Dict[str, Any]] = None
) -> str:
    """Return the complete active same-stage native-reasoning trajectory."""
    parts: List[str] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        if (
            item.get("_jack_stage_key") != stage_key
            and item.get("_jack_extended_completed_stage") != stage_key
        ):
            continue
        text = _native_reasoning_text(item)
        if text:
            parts.append(text)
    tail = _native_reasoning_text(final_message)
    if tail:
        parts.append(tail)
    return "\n\n".join(parts).strip()


def append_extended_candidate_response(
    history: List[Dict[str, Any]], message: Dict[str, Any]
) -> str:
    """Append a provisional Stage-1 completion for the active two-stage turn.

    Agentic freezes A1 for XML review. Deep Research freezes A1 only as the Stage-2 evaluation target.
    Raw Stage-1 reasoning/tool/result chronology remains in history through Stage 2.
    """
    candidate = str(message.get("content") or "")
    if not candidate.strip():
        raise HTTPException(
            status_code=502,
            detail="Stage 1 completed without a proposed response to continue from.",
        )

    forensic_snapshot = message.pop("_jack_agentic_stage1_forensic_snapshot", None)
    message.pop("_jack_extended_stage1_reasoning_trace", None)
    entry: Dict[str, Any] = {
        "role": "assistant",
        "content": candidate,
        "_jack_extended_candidate_response": True,
        "_jack_extended_bridge_mode": "native_preserve_intra_turn",
        "_jack_stage_key": "extended_initial",
    }
    if isinstance(forensic_snapshot, dict):
        entry["_jack_agentic_stage1_forensic_snapshot"] = forensic_snapshot

    reasoning_content = message.get("reasoning_content")
    reasoning = message.get("reasoning")
    thinking = message.get("thinking")
    if isinstance(reasoning_content, str) and reasoning_content:
        entry["reasoning_content"] = reasoning_content
        entry["reasoning"] = reasoning_content
    elif isinstance(reasoning, str) and reasoning:
        entry["reasoning"] = reasoning
    elif isinstance(thinking, str) and thinking:
        entry["thinking"] = thinking

    history.append(entry)
    return candidate


def append_ultra_intermediate_response(
    history: List[Dict[str, Any]], stage_key: str, message: Dict[str, Any]
) -> str:
    """Append one completed Deep Research intermediate stage without pruning any cognition."""
    content = _content_to_text(message.get("content"))
    if not content.strip():
        raise HTTPException(status_code=502, detail=f"{STAGES[stage_key].name} completed without visible stage output.")
    entry: Dict[str, Any] = {
        "role": "assistant",
        "content": content,
        "_jack_stage_key": stage_key,
        "_jack_extended_completed_stage": stage_key,
        "_jack_extended_raw_output": content,
        "_jack_ultra_intermediate_response": True,
    }
    for key in ("reasoning_content", "reasoning", "thinking"):
        value = message.get(key)
        if isinstance(value, str) and value:
            entry[key] = value
    if isinstance(entry.get("reasoning_content"), str) and entry.get("reasoning_content") and not entry.get("reasoning"):
        entry["reasoning"] = entry["reasoning_content"]
    history.append(entry)
    return content


def append_stage_result(
    history: List[Dict[str, Any]], stage_key: str, message: Dict[str, Any]
) -> None:
    """Append one compact stage artifact for later stages.

    Native reasoning is carried forward only when Preserve Thinking is ON *and*
    the stage was intentionally configured with native thinking enabled. This
    prevents an OpenAI-compatible backend that ignores thinking-off controls from
    polluting later context with unintended reasoning.
    """
    msg: Dict[str, Any] = {"role": "assistant"}
    content = message.get("content") or ""
    msg["content"] = f"<jack_{stage_key}>\n{content}\n</jack_{stage_key}>"

    profile = STAGES.get(stage_key)
    preserve_reasoning = bool(CFG.preserve_thinking and profile and profile.thinking)
    if preserve_reasoning:
        reasoning_content = message.get("reasoning_content")
        reasoning = message.get("reasoning")
        if reasoning_content is not None:
            msg["reasoning_content"] = reasoning_content
        if reasoning is not None:
            msg["reasoning"] = reasoning
        elif reasoning_content is not None:
            msg["reasoning"] = reasoning_content

    history.append(msg)


def aggregate_usage(total: Dict[str, int], usage: Optional[Dict[str, Any]]) -> None:
    if not usage:
        return
    total["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
    total["completion_tokens"] += int(usage.get("completion_tokens") or 0)
    total["total_tokens"] += int(usage.get("total_tokens") or 0)


def normalize_usage(total: Dict[str, int]) -> Dict[str, int]:
    if not total["total_tokens"]:
        total["total_tokens"] = total["prompt_tokens"] + total["completion_tokens"]
    return total


def usage_delta(current: Dict[str, int], baseline: Optional[Dict[str, int]] = None) -> Dict[str, int]:
    """Return response-local usage from a cumulative Jack transaction counter."""
    baseline = baseline or {}
    prompt = max(0, int(current.get("prompt_tokens") or 0) - int(baseline.get("prompt_tokens") or 0))
    completion = max(0, int(current.get("completion_tokens") or 0) - int(baseline.get("completion_tokens") or 0))
    total = max(0, int(current.get("total_tokens") or 0) - int(baseline.get("total_tokens") or 0))
    if not total:
        total = prompt + completion
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }


def freeze_xml_stage_output(text: Any) -> str:
    """Freeze Jack XML stage content without schema parsing or structural repair.

    Jack XML is a semantic attention-anchor artifact, not an authority-selection
    gate. The model-written content is therefore preserved as produced (apart
    from surrounding whitespace) even when tags are missing, misordered, or
    imperfectly nested. Frozen-answer authority and deterministic tool receipts
    remain runtime-owned and do not depend on XML syntax.
    """
    return _content_to_text(text).strip()


def strip_final_answer_heading(text: str) -> str:
    value = (text or "").strip()
    upper = value.upper()
    if upper.startswith("FINAL ANSWER:"):
        return value[len("FINAL ANSWER:") :].lstrip()
    return value


FROZEN_XML_MARKER = "===== FROZEN JACK XML ====="
FINAL_ANSWER_MARKER = "FINAL ANSWER:"


def _split_prior_jack_output(content: Any) -> tuple[Optional[str], Optional[str]]:
    """Recover the committed Jack XML + frozen Stage-1 answer boundary.

    Current Agentic output is emitted as an exact <Jack XML>...</Jack XML> block followed
    directly by the frozen Stage-1 answer. Legacy FINAL ANSWER/FROZEN XML markers remain
    readable for predecessor conversations.
    """
    if not isinstance(content, str) or not content:
        return None, None
    text = content.strip()

    jack_start = text.find("<Jack XML>")
    jack_end = text.find("</Jack XML>", jack_start + 10) if jack_start >= 0 else -1
    if jack_start >= 0 and jack_end >= 0:
        jack_end += len("</Jack XML>")
        xml = freeze_xml_stage_output(text[jack_start:jack_end])
        answer = text[jack_end:].lstrip()
        if answer.upper().startswith(FINAL_ANSWER_MARKER):
            answer = strip_final_answer_heading(answer)
        return xml or None, answer

    marker_pos = text.find(FROZEN_XML_MARKER)
    if marker_pos >= 0:
        tail = text[marker_pos + len(FROZEN_XML_MARKER) :].lstrip()
        answer_pos = tail.find(FINAL_ANSWER_MARKER)
        xml_region = tail if answer_pos < 0 else tail[:answer_pos]
        xml = freeze_xml_stage_output(xml_region)
        answer = None
        if answer_pos >= 0:
            answer = strip_final_answer_heading(tail[answer_pos:])
        if xml:
            return xml, answer

    answer_pos = text.find(FINAL_ANSWER_MARKER)
    if answer_pos >= 0:
        xml_region = text[:answer_pos]
        xml = freeze_xml_stage_output(xml_region)
        jack_markers = (
            "<grounding",
            "<verification",
            "<challenge",
            # Agentic/TAS XML markers remain readable for retained conversation compatibility.
            "<workspace_state",
            "<grounded_source",
            "<anchor_fact",
            "<deterministic_check",
            "<pitfall_check",
        )
        if xml and any(marker in xml for marker in jack_markers):
            return xml, strip_final_answer_heading(text[answer_pos:])
    return None, None


def _stage2_reasoning_trace(reasoning: Optional[str]) -> Optional[str]:
    """Format final substantive-stage reasoning for response observability."""
    text = str(reasoning or "").strip()
    if not text:
        return None
    label = "AGENTIC NATIVE PASS 2" if AGENTIC_MODE else "DEEP RESEARCH RE-EVALUATION PASS 2"
    return f"===== JACK {label} =====\n[NATIVE REASONING]\n" + text

def _compact_agentic_completed_capsules(
    messages: List[Dict[str, Any]],
) -> Optional[List[Dict[str, Any]]]:
    """Retain every completed visible turn capsule while pruning native cognition.

    A durable Agentic turn is represented in ordinary conversation order as:
        exact host-captured user message
        + committed assistant artifact (Jack XML + exact frozen Stage-1 answer).

    Historical native reasoning, consumed tool-call/result protocol, Jack runtime prompts,
    and other transient stage machinery are removed. The newest user turn remains active
    and is not duplicated into the completed history. This keeps user authority byte-faithful
    while letting each Jack XML checkpoint remain turn-local rather than acting as a lossy
    rewrite of the entire conversation. User requests survive directly in user-role messages,
    not through a model-authored User Request field in Jack XML.
    """
    compact = strip_secondary_system_messages(messages)
    latest_user_index: Optional[int] = None
    for index in range(len(compact) - 1, -1, -1):
        if isinstance(compact[index], dict) and compact[index].get("role") == "user":
            latest_user_index = index
            break
    if latest_user_index is None:
        return None

    retained: List[Dict[str, Any]] = []
    retained_user_turns = 0
    retained_agentic_commits = 0
    pruned_tool_messages = 0
    pruned_reasoning_chars = 0

    # Completed history: preserve exact user-role messages and visible assistant commits.
    # Tool protocol and hidden reasoning are execution/cognition state, not durable authority.
    for raw in compact[:latest_user_index]:
        if not isinstance(raw, dict):
            continue
        role = raw.get("role")
        if role == "user":
            item = dict(raw)
            for key in tuple(item.keys()):
                if isinstance(key, str) and key.startswith("_jack_"):
                    item.pop(key, None)
            retained.append(item)
            retained_user_turns += 1
            continue
        if role == "tool" or raw.get("tool_calls"):
            pruned_tool_messages += 1
            continue
        if role != "assistant":
            continue
        text = _content_to_text(raw.get("content")).strip()
        if not text:
            continue
        item = dict(raw)
        for key in ("reasoning_content", "reasoning", "thinking", "_jack_prior_stage2_reasoning"):
            value = item.pop(key, None)
            if isinstance(value, str):
                pruned_reasoning_chars += len(value)
        for key in tuple(item.keys()):
            if isinstance(key, str) and key.startswith("_jack_"):
                item.pop(key, None)
        item.pop("tool_calls", None)
        item["content"] = text
        retained.append(item)
        frozen_xml, frozen_answer = _split_prior_jack_output(text)
        if frozen_xml and frozen_answer is not None:
            retained_agentic_commits += 1

    # Active tail: preserve the exact current user message and any caller-provided tail.
    # In normal first-entry execution this is only the new user turn.
    tail: List[Dict[str, Any]] = []
    for raw in compact[latest_user_index:]:
        item = dict(raw) if isinstance(raw, dict) else raw
        if isinstance(item, dict):
            for key in tuple(item.keys()):
                if isinstance(key, str) and key.startswith("_jack_"):
                    item.pop(key, None)
            if item.get("role") == "assistant":
                for key in ("reasoning_content", "reasoning", "thinking", "_jack_prior_stage2_reasoning"):
                    value = item.pop(key, None)
                    if isinstance(value, str):
                        pruned_reasoning_chars += len(value)
        tail.append(item)

    if not retained:
        return None

    active_target = active_response_target(tail)
    active_hash = "NONE"
    if active_target is not None:
        active_hash = _sha256_text(active_target["content"])

    LOG.info(
        "Agentic completed-turn GC: retained user_turns=%d agentic_commits=%d active_user_sha256=%s; pruned tool_messages=%d native_reasoning_chars=%d",
        retained_user_turns,
        retained_agentic_commits,
        active_hash,
        pruned_tool_messages,
        pruned_reasoning_chars,
    )
    return retained + tail


_ULTRA_STAGE1_REASONING_MARKER = "===== JACK DEEP RESEARCH STAGE 1 — THESIS ====="
_ULTRA_STAGE2_REASONING_MARKER = "===== JACK DEEP RESEARCH STAGE 2 — ANTITHESIS ====="
_ULTRA_STAGE3_REASONING_MARKER = "===== JACK DEEP RESEARCH STAGE 3 — SYNTHESIS ====="
_ULTRA_RETAINED_STAGE1_OUTPUT_MARKER = "===== JACK DEEP RESEARCH RETAINED STAGE 1 — THESIS OUTPUT ====="
_ULTRA_RETAINED_STAGE2_OUTPUT_MARKER = "===== JACK DEEP RESEARCH RETAINED STAGE 2 — CRITIQUE OUTPUT ====="


def _split_completed_ultra_reasoning(text: str) -> Optional[Tuple[str, str, str, str, str, str]]:
    """Split a completed Deep Research reasoning surface into preamble/R1/A1/R2/A2/R3.

    Both non-stream and streamed Jack reasoning surfaces are recognized. A completed
    Synthesis boundary is required, so partial active transactions are never compacted.
    """
    raw = str(text or "")

    # Non-stream committed surface produced by _build_ultra_committed_result().
    # Ultra markers remain readable so an in-progress or retained session
    # created before the public rename can continue without losing post-final GC.
    nonstream_marker_sets = (
        (_ULTRA_STAGE1_REASONING_MARKER, _ULTRA_STAGE2_REASONING_MARKER, _ULTRA_STAGE3_REASONING_MARKER),
        (
            "===== JACK ULTRA STAGE 1 — THESIS =====",
            "===== JACK ULTRA STAGE 2 — ANTITHESIS =====",
            "===== JACK ULTRA STAGE 3 — SYNTHESIS =====",
        ),
    )
    for stage1_marker, stage2_marker, stage3_marker in nonstream_marker_sets:
        i1 = raw.find(stage1_marker)
        i2 = raw.find(stage2_marker)
        i3 = raw.find(stage3_marker)
        if 0 <= i1 < i2 < i3:
            stage1 = raw[i1 + len(stage1_marker):i2]
            stage2 = raw[i2 + len(stage2_marker):i3]
            stage3 = raw[i3 + len(stage3_marker):]
            r1_part, sep1, a1 = stage1.partition("\n[THESIS]\n")
            r2_part, sep2, a2 = stage2.partition("\n[ANTITHESIS]\n")
            if sep1 and sep2:
                r1 = r1_part.replace("\n[NATIVE REASONING]\n", "", 1).strip()
                r2 = r2_part.replace("\n[NATIVE REASONING]\n", "", 1).strip()
                r3 = stage3.replace("\n[NATIVE REASONING]\n", "", 1).strip()
                return raw[:i1].strip(), r1, a1.strip(), r2, a2.strip(), r3

    # Streaming surface assembled by OpenAI-compatible clients such as Pi.
    streaming_marker_sets = (
        (
            "[DEEP RESEARCH STAGE 1 — THESIS]",
            "[END DEEP RESEARCH STAGE 1 — THESIS COMPLETE]",
            "===== JACK DEEP RESEARCH ANTITHESIS PASS 2 =====",
            "[END DEEP RESEARCH STAGE 2 — ANTITHESIS COMPLETE]",
            "===== JACK DEEP RESEARCH SYNTHESIS PASS 3 =====",
            "[END DEEP RESEARCH STAGE 3 — SYNTHESIS COMPLETE]",
        ),
        (
            "[ULTRA STAGE 1 — THESIS]",
            "[END ULTRA STAGE 1 — THESIS COMPLETE]",
            "===== JACK ULTRA ANTITHESIS PASS 2 =====",
            "[END ULTRA STAGE 2 — ANTITHESIS COMPLETE]",
            "===== JACK ULTRA SYNTHESIS PASS 3 =====",
            "[END ULTRA STAGE 3 — SYNTHESIS COMPLETE]",
        ),
    )
    s1_output = "[THESIS OUTPUT]"
    s2_output = "[ANTITHESIS OUTPUT]"
    for s1_marker, s1_end, s2_marker, s2_end, s3_marker, s3_end in streaming_marker_sets:
        j1 = raw.find(s1_marker)
        j1o = raw.find(s1_output, j1 + len(s1_marker)) if j1 >= 0 else -1
        j1e = raw.find(s1_end, j1o + len(s1_output)) if j1o >= 0 else -1
        j2 = raw.find(s2_marker, j1e + len(s1_end)) if j1e >= 0 else -1
        j2o = raw.find(s2_output, j2 + len(s2_marker)) if j2 >= 0 else -1
        j2e = raw.find(s2_end, j2o + len(s2_output)) if j2o >= 0 else -1
        j3 = raw.find(s3_marker, j2e + len(s2_end)) if j2e >= 0 else -1
        j3e = raw.find(s3_end, j3 + len(s3_marker)) if j3 >= 0 else -1
        if 0 <= j1 < j1o < j1e < j2 < j2o < j2e < j3 < j3e:
            r1 = raw[j1 + len(s1_marker):j1o].strip()
            a1 = raw[j1o + len(s1_output):j1e].strip()
            r2 = raw[j2 + len(s2_marker):j2o].replace("[NATIVE REASONING]\n", "", 1).strip()
            a2 = raw[j2o + len(s2_output):j2e].strip()
            r3 = raw[j3 + len(s3_marker):j3e].replace("[NATIVE REASONING]\n", "", 1).strip()
            return raw[:j1].strip(), r1, a1, r2, a2, r3

    return None


def _compact_completed_ultra_reasoning(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Prune only completed Stage-1/Stage-2 reasoning after Synthesis has finished.

    The current three-stage transaction remains lossless through Synthesis. On the next
    request, the completed final response proves the final-output boundary was crossed.
    Jack then removes R1/R2 while retaining A1/A2, tool chronology/results, R3, and the
    authoritative Synthesis answer. This function is idempotent.
    """
    compact = [dict(m) if isinstance(m, dict) else m for m in messages]
    completed_index: Optional[int] = None
    completed_parts: Optional[Tuple[str, str, str, str, str, str]] = None
    for index in range(len(compact) - 1, -1, -1):
        message = compact[index]
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        reasoning_text = _native_reasoning_text(message)
        if _ULTRA_RETAINED_STAGE1_OUTPUT_MARKER in reasoning_text and _ULTRA_STAGE3_REASONING_MARKER in reasoning_text:
            # Already compacted on an earlier request.
            return compact
        parts = _split_completed_ultra_reasoning(reasoning_text)
        if parts is not None:
            completed_index = index
            completed_parts = parts
            break
    if completed_index is None or completed_parts is None:
        return compact

    preamble, r1, a1, r2, a2, r3 = completed_parts

    # Remove any separately echoed Stage-1/Stage-2 reasoning fragments when they can be
    # deterministically matched to the completed R1/R2 transcript. Tool calls/results and
    # visible stage outputs are left untouched. If a fragment also appears in R3, preserve it.
    for index, message in enumerate(compact):
        if index == completed_index or not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        for key in ("reasoning_content", "reasoning", "thinking"):
            value = message.get(key)
            if not isinstance(value, str) or not value.strip():
                continue
            fragment = value.strip()
            belongs_to_pruned_stage = bool((r1 and fragment in r1) or (r2 and fragment in r2))
            also_belongs_to_stage3 = bool(r3 and fragment in r3)
            if belongs_to_pruned_stage and not also_belongs_to_stage3:
                message.pop(key, None)

    retained_parts: List[str] = []
    if preamble:
        retained_parts.append(preamble)
    if a1:
        retained_parts.append(_ULTRA_RETAINED_STAGE1_OUTPUT_MARKER + "\n" + a1)
    if a2:
        retained_parts.append(_ULTRA_RETAINED_STAGE2_OUTPUT_MARKER + "\n" + a2)
    if r3:
        retained_parts.append(
            _ULTRA_STAGE3_REASONING_MARKER + "\n[NATIVE REASONING]\n" + r3
        )
    retained_reasoning = "\n\n".join(retained_parts).strip()
    final_message = compact[completed_index]
    for key in ("reasoning_content", "reasoning", "thinking"):
        if key in final_message:
            if retained_reasoning:
                final_message[key] = retained_reasoning
            else:
                final_message.pop(key, None)

    LOG.info(
        "Deep Research post-final reasoning GC: pruned Stage-1 chars=%d Stage-2 chars=%d; retained Thesis/Antithesis outputs, Stage-3 reasoning, tools/results, and final answer",
        len(r1), len(r2),
    )
    return compact


def compact_incoming_history(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Apply the selected mode's completed-turn retention policy.

    Deep Research preserves everything through the active Thesis -> Antithesis -> Synthesis transaction.
    Only after a completed Synthesis is present on the next request does Jack remove Stage-1
    and Stage-2 native-reasoning blocks. Their visible outputs, all tool calls/results,
    Stage-3 reasoning, and the authoritative final answer remain. Temporary TAS stage-control
    instructions are also absent after Synthesis. Agentic keeps its existing compaction policy.
    """
    if ULTRA_MODE:
        return _compact_completed_ultra_reasoning(strip_secondary_system_messages(messages))

    if AGENTIC_MODE:
        agentic_capsules = _compact_agentic_completed_capsules(messages)
        if agentic_capsules is not None:
            return agentic_capsules

    compact = strip_secondary_system_messages(messages)
    latest_xml: Optional[str] = None
    latest_xml_index: Optional[int] = None
    removed_reasoning_chars = 0
    removed_xml_snapshots = 0

    for index, message in enumerate(compact):
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue

        message.pop("_jack_prior_stage2_reasoning", None)
        for key in ("reasoning_content", "reasoning", "thinking"):
            value = message.pop(key, None)
            if isinstance(value, str):
                removed_reasoning_chars += len(value)

        if message.get("tool_calls"):
            continue

        if SELF_ADVERSARIAL_MODE:
            xml, final_answer = _split_prior_jack_output(message.get("content"))
            if xml:
                removed_xml_snapshots += 1
                latest_xml = xml
                latest_xml_index = index
                message["content"] = final_answer or ""

    if SELF_ADVERSARIAL_MODE and latest_xml is not None and latest_xml_index is not None:
        # Keep exactly one newest Jack XML snapshot in ordinary assistant content.
        # All older snapshots are reduced to their visible answer surface.
        for index, message in enumerate(compact):
            if not isinstance(message, dict) or message.get("role") != "assistant" or message.get("tool_calls"):
                continue
            xml, final_answer = _split_prior_jack_output(message.get("content"))
            if xml and index != latest_xml_index:
                message["content"] = final_answer or ""
        target = compact[latest_xml_index]
        answer = _content_to_text(target.get("content")).strip()
        committed = (
            latest_xml
            if str(latest_xml).lstrip().startswith("<Jack XML>")
            else f"<Jack XML>\n{latest_xml}\n</Jack XML>"
        )
        target["content"] = f"{committed}\n\nFINAL ANSWER:\n\n{answer}" if answer else committed

    if removed_reasoning_chars or removed_xml_snapshots > 1:
        LOG.info(
            "Context GC: removed %d historical native-reasoning chars; compacted %d Jack XML snapshots to %d; no native thinking survives between turns",
            removed_reasoning_chars,
            removed_xml_snapshots,
            1 if (SELF_ADVERSARIAL_MODE and latest_xml is not None) else 0,
        )
    return compact



AGENT_REQUEST_ALLOWLIST = frozenset({"messages", "tools", "tool_choice", "stream"})
AGENT_COGNITION_CONTROL_FIELDS = frozenset({
    "reasoning_effort",
    "reasoning",
    "thinking",
    "thinking_level",
    "enable_thinking",
    "preserve_thinking",
    "temperature",
    "top_p",
    "top_k",
    "min_p",
    "presence_penalty",
    "frequency_penalty",
    "repeat_penalty",
    "max_tokens",
    "max_completion_tokens",
    "stop",
    "seed",
    "logit_bias",
    "n",
    "parallel_tool_calls",
    "response_format",
})


def _normalize_agent_tool_choice(
    value: Any, tools: Optional[List[Dict[str, Any]]]
) -> Any:
    """Preserve valid outer-agent tool authority without silently weakening it."""
    if value is None:
        return None
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"auto", "none"}:
            return lowered
        if lowered == "required":
            if not tools:
                raise HTTPException(
                    status_code=400,
                    detail="tool_choice='required' requires at least one available tool.",
                )
            return lowered
        LOG.info("Ignoring unsupported calling-agent tool_choice=%r", value)
        return None
    if isinstance(value, dict):
        if value.get("type") != "function":
            LOG.info("Ignoring unsupported calling-agent tool_choice object")
            return None
        function = value.get("function")
        name = function.get("name") if isinstance(function, dict) else None
        if not isinstance(name, str) or not name.strip():
            LOG.info("Ignoring malformed calling-agent function tool_choice")
            return None
        available = {
            str((tool.get("function") or {}).get("name"))
            for tool in (tools or [])
            if isinstance(tool, dict) and isinstance(tool.get("function"), dict)
        }
        if name not in available:
            raise HTTPException(
                status_code=400,
                detail=f"tool_choice function {name!r} is not available in the supplied tool surface.",
            )
        return {"type": "function", "function": {"name": name}}
    LOG.info("Ignoring unsupported calling-agent tool_choice type %s", type(value).__name__)
    return None


def sanitize_agent_request(request_body: Dict[str, Any]) -> Dict[str, Any]:
    """Rebuild an agent request from Jack's explicit authority allowlist.

    The calling agent owns ordinary conversation content, tool definitions, bounded
    tool choice, multimodal user/assistant/tool message content, and the decision
    to request SSE streaming. Incoming calling-agent system/developer messages are
    blocked at the Jack boundary and are never forwarded to backend model stages.
    Jack owns reasoning profiles, native
    thinking, sampling, completion limits, backend/model selection, stage
    topology, preserve_thinking, and Jack XML behavior.
    """
    if not isinstance(request_body, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")

    messages = request_body.get("messages")
    tools = request_body.get("tools") if isinstance(request_body.get("tools"), list) else None
    sanitized: Dict[str, Any] = {
        # Request payloads are treated as immutable after validation. Downstream
        # code creates a top-level/history snapshot only where mutation is
        # actually required, avoiding a redundant full recursive copy here.
        "messages": messages,
        "stream": bool(request_body.get("stream", False)),
    }
    normalized_choice = _normalize_agent_tool_choice(request_body.get("tool_choice"), tools)
    if tools is not None:
        sanitized["tools"] = tools
        if normalized_choice is not None:
            sanitized["tool_choice"] = normalized_choice

    ignored = sorted(k for k in request_body if k not in AGENT_REQUEST_ALLOWLIST)
    cognition = [k for k in ignored if k in AGENT_COGNITION_CONTROL_FIELDS]
    if cognition:
        LOG.info("Ignored calling-agent cognition controls: %s", ", ".join(cognition))
    if "model" in request_body:
        LOG.debug("Calling-agent model is virtual-only; backend model selection remains Kernel-owned")
    other = [
        k for k in ignored
        if k not in AGENT_COGNITION_CONTROL_FIELDS and k != "model"
    ]
    if other:
        LOG.debug("Ignored unsupported calling-agent request fields: %s", ", ".join(other))
    return sanitized



# ---------------------------------------------------------------------------
# OpenAI-compatible backend
# ---------------------------------------------------------------------------


def _compose_backend_headers(
    *,
    auth_mode: str,
    api_key: str = "",
    header_name: str = "",
    header_value: str = "",
    username: str = "",
    password: str = "",
    authorization_value: str = "",
    extra_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Build request headers without assuming any particular serving platform."""
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    mode = (auth_mode or "none").strip().lower()
    if mode == "bearer" and api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    elif mode == "header" and header_name and header_value:
        headers[header_name] = header_value
    elif mode == "basic" and (username or password):
        raw = f"{username}:{password}".encode("utf-8")
        headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")
    elif mode == "authorization" and authorization_value:
        headers["Authorization"] = authorization_value

    for key, value in (extra_headers or {}).items():
        key = str(key).strip()
        if key:
            headers[key] = str(value)
    return headers



def _openai_base_to_server_root(base_url: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    return base[:-3] if base.endswith("/v1") else base


def _parse_lmstudio_v1_loaded_llms(payload: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(payload, dict):
        return out
    models = payload.get("models") or []
    if not isinstance(models, list):
        return out
    for model in models:
        if not isinstance(model, dict) or str(model.get("type") or "").lower() != "llm":
            continue
        key = str(model.get("key") or "").strip()
        display_name = str(model.get("display_name") or key).strip()
        max_ctx = model.get("max_context_length")
        instances = model.get("loaded_instances") or []
        if not isinstance(instances, list):
            continue
        for instance in instances:
            if not isinstance(instance, dict):
                continue
            instance_id = str(instance.get("id") or key).strip()
            if not instance_id:
                continue
            config = instance.get("config") if isinstance(instance.get("config"), dict) else {}
            ctx = config.get("context_length") or max_ctx or 0
            try:
                ctx = int(ctx)
            except Exception:
                ctx = 0
            out.append({
                "model_key": key,
                "instance_id": instance_id,
                "display_name": display_name,
                "context_length": ctx,
            })
    return out


def _parse_lmstudio_v0_loaded_llms(payload: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(payload, dict):
        return out
    data = payload.get("data") or []
    if not isinstance(data, list):
        return out
    for model in data:
        if not isinstance(model, dict):
            continue
        if str(model.get("state") or "").lower() != "loaded":
            continue
        model_type = str(model.get("type") or "").lower()
        if model_type not in {"llm", "vlm"}:
            continue
        model_id = str(model.get("id") or "").strip()
        if not model_id:
            continue
        try:
            ctx = int(model.get("loaded_context_length") or model.get("context_length") or model.get("max_context_length") or 0)
        except Exception:
            ctx = 0
        out.append({
            "model_key": model_id,
            "instance_id": model_id,
            "display_name": model_id,
            "context_length": ctx,
        })
    return out


def _match_loaded_lmstudio_model(candidates: List[Dict[str, Any]], configured: str) -> List[Dict[str, Any]]:
    wanted = str(configured or "").strip()
    if not wanted:
        return []
    return [
        item for item in candidates
        if wanted in {str(item.get("instance_id") or ""), str(item.get("model_key") or "")}
    ]


class OpenAICompatibleBackend:
    def __init__(self, cfg: KernelConfig):
        self.cfg = cfg
        self._configured_model: Optional[str] = str(cfg.backend_model or "").strip() or None
        # Never treat a configured/stored ID as already resolved. It must be
        # verified against the active backend before inference begins.
        self._resolved_model: Optional[str] = None
        self._detected_context_length: int = 0
        self._model_metadata_checked: bool = False
        self._client = httpx.AsyncClient(timeout=cfg.backend_timeout_seconds)
        self._model_lock = asyncio.Lock()

    @property
    def context_length(self) -> int:
        # LM Studio exposes the context length of the *currently loaded instance*.
        # That value is authoritative for what the backend can actually accept and
        # must win over a stale/manual Jack setting. Other OpenAI-compatible
        # backends may not expose a loaded-instance context, so an explicit Jack
        # configuration remains their preferred fallback/override.
        if self.cfg.backend_profile == "lmstudio" and self._detected_context_length > 0:
            return int(self._detected_context_length)
        return int(self.cfg.backend_context_length or self._detected_context_length or 0)

    @property
    def context_length_source(self) -> str:
        if self.cfg.backend_profile == "lmstudio" and self._detected_context_length > 0:
            return "lmstudio_loaded_instance"
        if self.cfg.backend_context_length > 0:
            return "configured"
        if self._detected_context_length > 0:
            return "backend_model_metadata"
        return "unknown"

    @staticmethod
    def _extract_context_length(model_item: Any) -> int:
        if not isinstance(model_item, dict):
            return 0
        preferred = (
            "loaded_context_length", "context_length", "max_context_length",
            "max_model_len", "n_ctx", "max_position_embeddings",
        )
        for key in preferred:
            value = model_item.get(key)
            try:
                parsed = int(value)
            except Exception:
                parsed = 0
            if parsed > 0:
                return parsed
        for value in model_item.values():
            if isinstance(value, dict):
                found = OpenAICompatibleBackend._extract_context_length(value)
                if found > 0:
                    return found
        return 0

    async def close(self) -> None:
        await self._client.aclose()

    def _headers(self) -> Dict[str, str]:
        return _compose_backend_headers(
            auth_mode=self.cfg.backend_auth_mode,
            api_key=self.cfg.backend_api_key,
            header_name=self.cfg.backend_header_name,
            header_value=self.cfg.backend_header_value,
            username=self.cfg.backend_username,
            password=self.cfg.backend_password,
            authorization_value=self.cfg.backend_authorization_value,
            extra_headers=self.cfg.backend_extra_headers,
        )

    async def _lmstudio_loaded_models(self) -> Tuple[List[Dict[str, Any]], str]:
        root = _openai_base_to_server_root(self.cfg.backend_base_url)
        attempts = [
            (f"{root}/api/v1/models", _parse_lmstudio_v1_loaded_llms),
            (f"{root}/api/v0/models", _parse_lmstudio_v0_loaded_llms),
        ]
        last_error: Optional[Exception] = None
        for url, parser in attempts:
            try:
                r = await self._client.get(url, headers=self._headers())
                if r.status_code == 404:
                    continue
                r.raise_for_status()
                return parser(r.json()), url
            except Exception as exc:
                last_error = exc
                continue
        raise HTTPException(
            status_code=502,
            detail=(
                "Cannot determine which LM Studio model is currently loaded. "
                f"Tried {attempts[0][0]} and {attempts[1][0]}: {last_error}"
            ),
        )

    async def _resolve_lmstudio_model(self) -> str:
        candidates, source_url = await self._lmstudio_loaded_models()
        configured = self._configured_model

        if configured:
            matches = _match_loaded_lmstudio_model(candidates, configured)
            if len(matches) != 1:
                loaded = ", ".join(str(x.get("instance_id") or x.get("model_key")) for x in candidates) or "none"
                if len(matches) > 1:
                    detail = (
                        f"Configured LM Studio model {configured!r} matches multiple loaded instances. "
                        f"Select an exact loaded instance ID. Loaded instances: {loaded}."
                    )
                else:
                    detail = (
                        f"Configured LM Studio model {configured!r} is not currently loaded. "
                        f"Loaded LLM instances: {loaded}. Jack will not JIT-load a different/downloaded model."
                    )
                raise HTTPException(status_code=409, detail=detail)
            selected = matches[0]
        else:
            if not candidates:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "LM Studio has no loaded LLM instance. Load the model you want in LM Studio first. "
                        "Jack AUTO-DETECT uses loaded_instances and does not choose from downloaded/JIT-visible models."
                    ),
                )
            if len(candidates) > 1:
                loaded = ", ".join(str(x.get("instance_id") or x.get("model_key")) for x in candidates)
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "LM Studio has multiple loaded LLM instances and AUTO-DETECT is ambiguous. "
                        f"Select one explicitly in Model Selection. Loaded instances: {loaded}."
                    ),
                )
            selected = candidates[0]

        resolved = str(selected.get("instance_id") or selected.get("model_key") or "").strip()
        if not resolved:
            raise HTTPException(status_code=502, detail=f"LM Studio loaded-model metadata from {source_url} had no usable model ID")
        self._resolved_model = resolved
        try:
            self._detected_context_length = int(selected.get("context_length") or 0)
        except Exception:
            self._detected_context_length = 0
        self._model_metadata_checked = True
        if self._detected_context_length > 0 and not self.cfg.backend_context_length:
            LOG.info("Detected loaded LM Studio context length: %d", self._detected_context_length)
        LOG.info("Resolved currently loaded LM Studio model: %s", self._resolved_model)
        return self._resolved_model

    async def resolve_model(self) -> str:
        if self._resolved_model and (self.cfg.backend_context_length or self._model_metadata_checked):
            return self._resolved_model
        async with self._model_lock:
            if self._resolved_model and (self.cfg.backend_context_length or self._model_metadata_checked):
                return self._resolved_model

            if self.cfg.backend_profile == "lmstudio":
                return await self._resolve_lmstudio_model()

            url = f"{self.cfg.backend_base_url}/models"
            try:
                r = await self._client.get(url, headers=self._headers())
                r.raise_for_status()
                data = r.json().get("data") or []
            except Exception as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"Cannot query backend models at {url}: {exc}",
                ) from exc
            self._model_metadata_checked = True
            ids = [str(item.get("id", "")) for item in data if isinstance(item, dict) and item.get("id")]
            if self._configured_model:
                if self._configured_model not in ids:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"Configured backend model {self._configured_model!r} is not reported by {url}. "
                            f"Available model IDs: {', '.join(ids) or 'none'}."
                        ),
                    )
                self._resolved_model = self._configured_model
            else:
                if not ids:
                    raise HTTPException(
                        status_code=503,
                        detail="The backend returned no models. Load a model or set JACK_BACKEND_MODEL explicitly.",
                    )
                preferred = [
                    model_id for model_id in ids
                    if "qwen3.8" in model_id.lower() and "27b" in model_id.lower()
                ]
                self._resolved_model = preferred[0] if preferred else ids[0]
                if not preferred:
                    LOG.warning(
                        "No model ID looked like Qwen3.8-27B; using %s. "
                        "The stage reasoning defaults are optimized for Qwen3.8-27B.",
                        self._resolved_model,
                    )

            selected_item = next((item for item in data if str(item.get("id", "")) == self._resolved_model), {})
            self._detected_context_length = self._extract_context_length(selected_item)
            if self._detected_context_length > 0 and not self.cfg.backend_context_length:
                LOG.info("Detected backend context length from model metadata: %d", self._detected_context_length)
            LOG.info("Resolved backend model: %s", self._resolved_model)
            return self._resolved_model

    def _sampling_for_profile(self, profile: StageProfile) -> Dict[str, Any]:
        base = dict(QWEN_THINKING_SAMPLING if profile.thinking else QWEN_NONTHINKING_SAMPLING)
        if profile.temperature is not None:
            base["temperature"] = float(profile.temperature)
        if profile.presence_penalty is not None:
            base["presence_penalty"] = float(profile.presence_penalty)
        # Ollama's OpenAI-compatible endpoint intentionally supports a narrower
        # sampler surface. Do not send llama.cpp-only extensions that it may reject.
        if self.cfg.backend_profile == "ollama":
            allowed = {"temperature", "top_p", "presence_penalty"}
            return {k: v for k, v in base.items() if k in allowed}
        return base


    def _ultra_thesis_history_projection(
        self, messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Project completed history for non-executing Deep Research Thesis.

        Canonical Deep Research retention is unchanged: prior tool calls/results remain in
        conversation history for authoritative Synthesis and forensic continuity.
        Thesis receives a narrower backend view that excludes historical execution
        protocol so prior tool traffic cannot masquerade as current-stage capability.
        """
        projected: List[Dict[str, Any]] = []
        removed_tool_calls = 0
        removed_tool_results = 0
        for message in messages:
            if not isinstance(message, dict):
                projected.append(message)
                continue
            if message.get("role") == "tool":
                removed_tool_results += 1
                continue
            if message.get("role") == "assistant" and message.get("tool_calls"):
                calls = message.get("tool_calls")
                removed_tool_calls += len(calls) if isinstance(calls, list) else 1
                continue
            projected.append(message)
        if removed_tool_calls or removed_tool_results:
            LOG.info(
                "Deep Research Thesis history projection: excluded historical tool_calls=%d tool_results=%d; canonical Deep Research retention unchanged",
                removed_tool_calls,
                removed_tool_results,
            )
        return projected


    def _stage_messages_for_profile(
        self, messages: List[Dict[str, Any]], profile: StageProfile
    ) -> List[Dict[str, Any]]:
        """Prepare a backend-safe request view with copy-on-write semantics.

        Private Jack host metadata is never sent to the model. Thinking-OFF native
        profiles do not receive historical native reasoning. Agentic and Deep Research active
        stages keep their native reasoning because those profiles run thinking-ON with
        Preserve Thinking under their stage contracts.
        """
        strip_reasoning = not profile.thinking
        source_messages = (
            self._ultra_thesis_history_projection(messages)
            if ULTRA_MODE and profile.name == "Deep Research Thesis pass 1"
            else messages
        )
        prepared: List[Dict[str, Any]] = []
        for message in source_messages:
            if not isinstance(message, dict):
                prepared.append(message)
                continue

            has_private = any(
                isinstance(key, str) and key.startswith("_jack_")
                for key in message.keys()
            )
            must_strip_reasoning = bool(
                strip_reasoning
                and message.get("role") == "assistant"
                and any(key in message for key in ("reasoning_content", "reasoning", "thinking"))
            )
            if not has_private and not must_strip_reasoning:
                prepared.append(message)
                continue

            item = dict(message)
            if item.get("_jack_tool_evidence_receipt"):
                evidence_lines = [
                    line
                    for line in _content_to_text(item.get("content")).splitlines()
                    if line.strip().lower() not in {
                        "<jack_tool_evidence_receipt>",
                        "</jack_tool_evidence_receipt>",
                    }
                ]
                item["content"] = (
                    "[TOOL EVIDENCE FACTS]\n"
                    + "\n".join(evidence_lines)
                    + "\n[END TOOL EVIDENCE FACTS]"
                )
            for key in tuple(item.keys()):
                if isinstance(key, str) and key.startswith("_jack_"):
                    item.pop(key, None)
            if must_strip_reasoning:
                item.pop("reasoning_content", None)
                item.pop("reasoning", None)
                item.pop("thinking", None)
            prepared.append(item)
        return prepared

    def _apply_qwen_controls(
        self, payload: Dict[str, Any], profile: StageProfile
    ) -> None:
        # Ollama's OpenAI-compatible API maps reasoning_effort onto its native
        # thinking control. xhigh maps to Ollama's current "max" level.
        if self.cfg.backend_profile == "ollama" or self.cfg.qwen_control_shape == "ollama_openai":
            if not profile.thinking:
                payload["reasoning_effort"] = "none"
            elif profile.reasoning_effort:
                payload["reasoning_effort"] = {
                    "xhigh": "max",
                    "medium": "medium",
                    "low": "low",
                }.get(profile.reasoning_effort, profile.reasoning_effort)
            return

        # Agentic and Deep Research may preserve native thinking across their active
        # stage boundaries. Code Debugging is intentionally different: a new pass must
        # start with Preserve Thinking OFF regardless of the global setting, and Jack
        # enables it only for same-pass tool continuation via force_preserve_thinking.
        debugging_fresh_boundary = profile.name.startswith("Code Debugging Pass ") or profile.name == "Code Debugging Summary"
        effective_preserve = bool(
            profile.thinking
            and (
                profile.force_preserve_thinking
                or (self.cfg.preserve_thinking and not debugging_fresh_boundary)
            )
        )
        kwargs: Dict[str, Any] = {
            "enable_thinking": profile.thinking,
            "preserve_thinking": effective_preserve,
        }
        if profile.force_preserve_thinking:
            LOG.debug(
                "same-stage reasoning preservation forced for %s tool continuation",
                profile.name,
            )
        if profile.thinking and profile.reasoning_effort:
            kwargs["reasoning_effort"] = profile.reasoning_effort

        shape = self.cfg.qwen_control_shape
        if shape in {"template_kwargs", "hybrid"}:
            payload["chat_template_kwargs"] = kwargs
        if shape in {"top_level", "hybrid"}:
            payload["enable_thinking"] = profile.thinking
            payload["preserve_thinking"] = effective_preserve
            if (
                profile.thinking
                and profile.reasoning_effort
                and self.cfg.backend_profile != "lmstudio"
            ):
                payload["reasoning_effort"] = profile.reasoning_effort

        # LM Studio's OpenAI-compatible path needs an explicit top-level
        # reasoning_effort value to override a reasoning model's default. The
        # template booleans alone are not sufficient on every LM Studio build/model
        # combination. For a thinking-OFF stage, send `none` explicitly.
        if self.cfg.backend_profile == "lmstudio":
            if profile.thinking and profile.reasoning_effort:
                effort = profile.reasoning_effort
                if effort not in {"minimal", "low", "medium", "high", "xhigh"}:
                    raise RuntimeError(
                        f"Unsupported LM Studio reasoning effort for stage {profile.name}: {effort}"
                    )
                payload["reasoning_effort"] = effort
            elif not profile.thinking:
                payload["reasoning_effort"] = "none"
            # Do not send a reasoning_effort field: some LM Studio models expose only
            # an on/off thinking switch and reject graded effort values.

    def _apply_tool_policy(
        self, payload: Dict[str, Any], tools: Optional[List[Dict[str, Any]]], tool_choice: Any
    ) -> None:
        if not tools:
            return
        # LM Studio currently accepts string tool_choice values
        # (auto/none/required) but rejects OpenAI named-tool objects. Preserve
        # exact named authority by exposing only the selected tool and requiring
        # a call; this is equivalent to the caller's named selection.
        if self.cfg.backend_profile == "lmstudio" and isinstance(tool_choice, dict):
            fn = tool_choice.get("function") if isinstance(tool_choice.get("function"), dict) else {}
            name = fn.get("name")
            selected_tools = [
                tool for tool in tools
                if isinstance(tool, dict)
                and isinstance(tool.get("function"), dict)
                and tool["function"].get("name") == name
            ]
            if not selected_tools:
                raise HTTPException(
                    status_code=400,
                    detail=f"LM Studio named tool_choice function {name!r} is not available.",
                )
            payload["tools"] = selected_tools
            payload["tool_choice"] = "required"
            return

        # Ollama accepts a tool surface but does not implement OpenAI tool_choice.
        # Auto/none can be represented faithfully. Forced choice cannot: merely
        # exposing one tool does not make the model call it, so reject rather than
        # silently weakening caller authority.
        if self.cfg.backend_profile == "ollama":
            if tool_choice == "none":
                return
            if tool_choice not in (None, "auto"):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "The Ollama backend does not support forced tool_choice. "
                        "Jack Kernel will not weaken 'required' or named-tool authority."
                    ),
                )
            payload["tools"] = tools
            return

        payload["tools"] = tools
        payload["tool_choice"] = tool_choice if tool_choice is not None else "auto"

    async def chat(
        self,
        *,
        messages: List[Dict[str, Any]],
        secondary_system: str,
        profile: StageProfile,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Any = None,
    ) -> Dict[str, Any]:
        model = await self.resolve_model()
        prepared_messages = self._stage_messages_for_profile(messages, profile)
        stage_system = build_stage_system_prompt(secondary_system, profile, prepared_messages)
        stage_messages = (
            [{"role": "system", "content": stage_system}] if stage_system else []
        ) + prepared_messages
        if (
            prepared_messages
            and prepared_messages[-1].get("role") == "assistant"
            and _stage_requires_user_continuation(profile)
        ):
            stage_messages.append(_stage_generation_trigger(profile, messages))

        sampling = self._sampling_for_profile(profile)
        payload: Dict[str, Any] = {
            "model": model,
            "messages": stage_messages,
            "stream": False,
            **sampling,
        }
        self._apply_qwen_controls(payload, profile)
        if profile.max_tokens is not None:
            payload["max_tokens"] = int(profile.max_tokens)

        if self.cfg.seed:
            payload["seed"] = int(self.cfg.seed)

        if profile.allow_tools and tools:
            self._apply_tool_policy(payload, tools, tool_choice)

        url = f"{self.cfg.backend_base_url}/chat/completions"
        current_payload = payload
        try:
            response = await self._client.post(url, headers=self._headers(), json=current_payload)
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Backend request failed during {profile.name}: {exc}",
            ) from exc

        # min_p is a Qwen-recommended no-op at 0.0, but some OpenAI-compatible
        # implementations reject the field. Retry once without only that no-op.
        if response.status_code == 400 and "min_p" in current_payload:
            body_lower = response.text.lower()
            if "min_p" in body_lower or "unknown" in body_lower or "unsupported" in body_lower:
                retry_payload = dict(current_payload)
                retry_payload.pop("min_p", None)
                current_payload = retry_payload
                response = await self._client.post(
                    url, headers=self._headers(), json=current_payload
                )

        if response.status_code >= 500:
            LOG.warning("Backend returned HTTP %d during %s; retrying once", response.status_code, profile.name)
            await asyncio.sleep(0.15)
            response = await self._client.post(url, headers=self._headers(), json=current_payload)

        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Backend rejected stage {profile.name} with HTTP "
                    f"{response.status_code}: {response.text[:4000]}"
                ),
            )

        data = response.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = data.get("usage") or {}

        reasoning = message.get("reasoning_content") or message.get("reasoning") or ""
        if reasoning and not profile.thinking:
            LOG.warning(
                "Backend emitted native reasoning during thinking-OFF stage %s; "
                "Jack will not preserve that reasoning into later stage context.",
                profile.name,
            )
        if reasoning and self.cfg.log_reasoning:
            LOG.debug("%s reasoning:\n%s", profile.name, reasoning)

        return data


    async def chat_stream(
        self,
        *,
        messages: List[Dict[str, Any]],
        secondary_system: str,
        profile: StageProfile,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Any = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream one backend stage as normalized OpenAI-style chunks internally."""
        model = await self.resolve_model()
        prepared_messages = self._stage_messages_for_profile(messages, profile)
        stage_system = build_stage_system_prompt(secondary_system, profile, prepared_messages)
        stage_messages = (
            [{"role": "system", "content": stage_system}] if stage_system else []
        ) + prepared_messages
        if (
            prepared_messages
            and prepared_messages[-1].get("role") == "assistant"
            and _stage_requires_user_continuation(profile)
        ):
            stage_messages.append(_stage_generation_trigger(profile, messages))

        sampling = self._sampling_for_profile(profile)
        payload: Dict[str, Any] = {
            "model": model,
            "messages": stage_messages,
            "stream": True,
            "stream_options": {"include_usage": True},
            **sampling,
        }
        self._apply_qwen_controls(payload, profile)
        if profile.max_tokens is not None:
            payload["max_tokens"] = int(profile.max_tokens)
        if self.cfg.seed:
            payload["seed"] = int(self.cfg.seed)
        if profile.allow_tools and tools:
            self._apply_tool_policy(payload, tools, tool_choice)

        url = f"{self.cfg.backend_base_url}/chat/completions"

        async def send_stream(current_payload: Dict[str, Any]) -> httpx.Response:
            req = self._client.build_request(
                "POST", url, headers=self._headers(), json=current_payload
            )
            return await self._client.send(req, stream=True)

        current_payload = payload
        response = await send_stream(current_payload)

        # Compatibility retry: min_p=0 is a recommended no-op but may be
        # rejected by some OpenAI-compatible builds. Some builds also reject
        # stream_options; usage streaming is optional, live token streaming is not.
        if response.status_code == 400:
            raw = (await response.aread()).decode("utf-8", errors="replace")
            await response.aclose()
            retry_payload = dict(current_payload)
            changed = False
            lower = raw.lower()
            if "min_p" in retry_payload and (
                "min_p" in lower or "unknown" in lower or "unsupported" in lower
            ):
                retry_payload.pop("min_p", None)
                changed = True
            if "stream_options" in retry_payload and (
                "stream_options" in lower or "unknown" in lower or "unsupported" in lower
            ):
                retry_payload.pop("stream_options", None)
                changed = True
            if changed:
                current_payload = retry_payload
                response = await send_stream(current_payload)
            else:
                raise HTTPException(
                    status_code=502,
                    detail=f"Backend rejected streaming stage {profile.name}: {raw[:4000]}",
                )

        if response.status_code >= 500:
            raw = (await response.aread()).decode("utf-8", errors="replace")
            status = response.status_code
            await response.aclose()
            LOG.warning("Backend returned HTTP %d during streaming %s; retrying once", status, profile.name)
            await asyncio.sleep(0.15)
            response = await send_stream(current_payload)

        if response.status_code >= 400:
            raw = (await response.aread()).decode("utf-8", errors="replace")
            await response.aclose()
            raise HTTPException(
                status_code=502,
                detail=(
                    f"Backend rejected streaming stage {profile.name} with HTTP "
                    f"{response.status_code}: {raw[:4000]}"
                ),
            )

        try:
            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data_text = line[5:].strip()
                if not data_text or data_text == "[DONE]":
                    continue
                try:
                    chunk = json.loads(data_text)
                except json.JSONDecodeError:
                    LOG.warning("Ignoring malformed backend SSE chunk: %r", data_text[:500])
                    continue
                yield chunk
        finally:
            await response.aclose()


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass
class KernelResult:
    content: Optional[str]
    tool_calls: Optional[List[Dict[str, Any]]]
    finish_reason: str
    usage: Dict[str, int]
    reasoning_content: Optional[str] = None


@dataclass
class PreparedCommit:
    frozen_xml: str
    frozen_answer: str
    authoritative_source: str
    usage: Dict[str, int]
    stage2_reasoning: Optional[str] = None


@dataclass
class PendingDebuggingIntakeResume:
    resume_id: str
    run_id: str
    history: List[Dict[str, Any]]
    secondary_system: str
    usage: Dict[str, int]
    tools: Optional[List[Dict[str, Any]]]
    tool_choice: Any
    user_visible_response: str
    created_at: float
    in_flight: bool = False


@dataclass
class PendingDebuggingUserResume:
    resume_id: str
    stage_key: str
    history: List[Dict[str, Any]]
    secondary_system: str
    usage: Dict[str, int]
    tools: Optional[List[Dict[str, Any]]]
    tool_choice: Any
    user_visible_question: str
    created_at: float
    debugging_run_id: Optional[str] = None
    in_flight: bool = False


@dataclass
class PendingToolResume:
    resume_id: str
    stage_key: str
    history: List[Dict[str, Any]]
    secondary_system: str
    usage: Dict[str, int]
    tools: Optional[List[Dict[str, Any]]]
    tool_choice: Any
    expected_tool_call_ids: Tuple[str, ...]
    created_at: float
    debugging_run_id: Optional[str] = None
    in_flight: bool = False


class JackQwenKernel:
    def __init__(self, backend: OpenAICompatibleBackend, cfg: KernelConfig):
        self.backend = backend
        self.cfg = cfg
        self._semaphore = asyncio.Semaphore(max(1, cfg.max_concurrent_requests))
        self._pending_tool_resumes: Dict[str, PendingToolResume] = {}
        self._pending_tool_resume_lock = asyncio.Lock()
        self._pending_debugging_intake_resumes: Dict[str, PendingDebuggingIntakeResume] = {}
        self._pending_debugging_intake_resume_lock = asyncio.Lock()
        self._pending_debugging_user_resumes: Dict[str, PendingDebuggingUserResume] = {}
        self._pending_debugging_user_resume_lock = asyncio.Lock()

    async def _run_stage(
        self,
        history: List[Dict[str, Any]],
        secondary_system: str,
        stage_key: str,
        usage: Dict[str, int],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Any = None,
        append: bool = True,
        same_stage_resume: bool = False,
        tool_validation_repair_depth: int = 0,
    ) -> Dict[str, Any]:
        force_native_resume = bool(
            same_stage_resume
            and (stage_key == "thesis" or _debugging_pass_from_stage_key(stage_key) is not None)
            and STAGES[stage_key].thinking
        )
        profile = (
            replace(STAGES[stage_key], force_preserve_thinking=True)
            if force_native_resume
            else STAGES[stage_key]
        )
        effective_tools = tools if profile.allow_tools else None
        effective_tool_choice = tool_choice if profile.allow_tools else None
        data = await self.backend.chat(
            messages=history,
            secondary_system=secondary_system,
            profile=profile,
            tools=effective_tools,
            tool_choice=effective_tool_choice,
        )
        aggregate_usage(usage, data.get("usage"))
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        if isinstance(msg.get("tool_calls"), list):
            msg["tool_calls"] = normalize_tool_calls_for_distribution(msg.get("tool_calls"))
        governed_stage = bool(SELF_ADVERSARIAL_MODE or (CODE_DEBUGGING_MODE and _debugging_pass_from_stage_key(stage_key) is not None))
        if governed_stage and msg.get("tool_calls"):
            if not profile.allow_tools:
                validation_errors = [f"{profile.name}: this stage has no tool authority"]
            else:
                validation_errors = _tool_call_validation_errors(msg.get("tool_calls"), effective_tools)
            if validation_errors:
                if tool_validation_repair_depth >= 2:
                    raise HTTPException(status_code=502, detail=(
                        f"{STAGES[stage_key].name} repeatedly emitted rejected tool actions: " + "; ".join(validation_errors)
                    ))
                LOG.warning("%s rejected tool action before execution: %s", STAGES[stage_key].name, "; ".join(validation_errors))
                repair_history = _tool_rejection_history(history, msg, validation_errors, STAGES[stage_key].name)
                return await self._run_stage(
                    repair_history, secondary_system, stage_key, usage, tools=tools, tool_choice=tool_choice,
                    append=append, same_stage_resume=True, tool_validation_repair_depth=tool_validation_repair_depth + 1,
                )
        if not msg.get("tool_calls"):
            if SELF_ADVERSARIAL_MODE and stage_key == "extended_initial":
                if AGENTIC_MODE and CFG.forensic_archive_mode == "stage":
                    msg["_jack_agentic_stage1_forensic_snapshot"] = _capture_agentic_stage1_forensic_snapshot(
                        history, msg
                    )
                trace = extended_stage1_reasoning_trace(history, msg)
                if trace:
                    msg["_jack_extended_stage1_reasoning_trace"] = trace
            elif SELF_ADVERSARIAL_MODE and stage_key == "extended_reflection":
                trace = self_adversarial_stage_reasoning_trace(history, stage_key, msg)
                if trace:
                    msg["_jack_stage2_reasoning_trace"] = trace
            elif ULTRA_MODE and stage_key == "extended_synthesis":
                trace = self_adversarial_stage_reasoning_trace(history, stage_key, msg)
                if trace:
                    msg["_jack_stage3_reasoning_trace"] = trace
            defer_extended_context = bool(
                (
                    ULTRA_MODE
                    and stage_key in {"extended_initial", "extended_reflection", "extended_synthesis"}
                )
                or (AGENTIC_MODE and stage_key in {"extended_initial", "extended_reflection", "extended_synthesis"})
                or (CODE_DEBUGGING_MODE and _debugging_pass_from_stage_key(stage_key) is not None)
            )
            if not defer_extended_context:
                pruned_messages = self._prune_internal_tool_exchanges(history)
                if pruned_messages:
                    LOG.info(
                        "%s completed; retired %d consumed stage-local tool protocol message(s)",
                        STAGES[stage_key].name,
                        pruned_messages,
                    )
            if append:
                append_stage_result(history, stage_key, msg)
        return data

    @staticmethod
    def _merge_tool_call_delta(
        state: Dict[int, Dict[str, Any]], deltas: Any
    ) -> None:
        """Reconstruct OpenAI streaming tool-call fragments by index."""
        if not isinstance(deltas, list):
            return
        for raw in deltas:
            if not isinstance(raw, dict):
                continue
            try:
                index = int(raw.get("index", 0))
            except Exception:
                index = 0
            call = state.setdefault(
                index,
                {
                    "id": None,
                    "type": "function",
                    "function": {"name": "", "arguments": ""},
                },
            )
            if raw.get("id"):
                call["id"] = raw["id"]
            if raw.get("type"):
                call["type"] = raw["type"]
            function = raw.get("function") or {}
            if isinstance(function, dict):
                if function.get("name"):
                    call["function"]["name"] += str(function["name"])
                if function.get("arguments"):
                    call["function"]["arguments"] += str(function["arguments"])

    async def _run_stage_streamed(
        self,
        history: List[Dict[str, Any]],
        secondary_system: str,
        stage_key: str,
        usage: Dict[str, int],
        *,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Any = None,
        append: bool = True,
        same_stage_resume: bool = False,
        tool_validation_repair_depth: int = 0,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Run one Jack stage with backend streaming and reconstruct its message.

        Packets with kind=reasoning/content/tool_calls are suitable for immediate
        forwarding to an OpenAI streaming client. The final kind=result packet
        contains the reconstructed OpenAI-style stage response used internally.
        """
        force_native_resume = bool(
            same_stage_resume
            and (stage_key == "thesis" or _debugging_pass_from_stage_key(stage_key) is not None)
            and STAGES[stage_key].thinking
        )
        profile = (
            replace(STAGES[stage_key], force_preserve_thinking=True)
            if force_native_resume
            else STAGES[stage_key]
        )
        effective_tools = tools if profile.allow_tools else None
        effective_tool_choice = tool_choice if profile.allow_tools else None
        content_parts: List[str] = []
        reasoning_content_parts: List[str] = []
        reasoning_parts: List[str] = []
        tool_state: Dict[int, Dict[str, Any]] = {}
        tool_call_fragments_streamed = False
        stage_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        finish_reason = "stop"

        backend_stream = self.backend.chat_stream(
            messages=history,
            secondary_system=secondary_system,
            profile=profile,
            tools=effective_tools,
            tool_choice=effective_tool_choice,
        ).__aiter__()
        pending_next: Optional[asyncio.Task] = None
        try:
            while True:
                pending_next = asyncio.create_task(backend_stream.__anext__())
                while True:
                    done, _ = await asyncio.wait({pending_next}, timeout=3.0)
                    if done:
                        break
                    # A comment heartbeat is later written to the public SSE
                    # connection. It does not become model content and does not
                    # alter Jack state, but keeps Pi/proxies alive through long
                    # backend prompt processing or queue waits.
                    yield {"kind": "keepalive", "event": f"{profile.name}.wait"}

                try:
                    chunk = pending_next.result()
                except StopAsyncIteration:
                    pending_next = None
                    break
                pending_next = None

                if chunk.get("_jack_keepalive"):
                    yield {
                        "kind": "keepalive",
                        "event": str(chunk.get("_jack_event") or "backend.activity"),
                    }
                    continue

                chunk_usage = chunk.get("usage")
                if chunk_usage:
                    aggregate_usage(usage, chunk_usage)
                    aggregate_usage(stage_usage, chunk_usage)

                choices = chunk.get("choices") or []
                if not choices:
                    continue
                choice = choices[0] or {}
                delta = choice.get("delta") or {}

                # Qwen/LM Studio may expose native reasoning under either field.
                reasoning_content = delta.get("reasoning_content")
                reasoning = delta.get("reasoning")
                if reasoning_content is not None:
                    text = str(reasoning_content)
                    if text:
                        reasoning_content_parts.append(text)
                        yield {"kind": "reasoning", "text": text}
                elif reasoning is not None:
                    text = str(reasoning)
                    if text:
                        reasoning_parts.append(text)
                        yield {"kind": "reasoning", "text": text}

                content = delta.get("content")
                if content is not None:
                    text = str(content)
                    if text:
                        content_parts.append(text)
                        yield {"kind": "content", "text": text}

                tool_deltas = delta.get("tool_calls")
                if tool_deltas:
                    self._merge_tool_call_delta(tool_state, tool_deltas)
                    # Tool-call arguments are model output too. Large write/edit
                    # calls can contain most of a coding stage's generated tokens,
                    # so buffering them until JSON completion defeats live stage
                    # streaming. Forward each OpenAI delta immediately while the
                    # reconstruction above retains the exact deterministic call.
                    if not (CODE_DEBUGGING_MODE and _debugging_pass_from_stage_key(stage_key) is not None):
                        tool_call_fragments_streamed = True
                        yield {"kind": "tool_calls", "tool_calls": copy.deepcopy(tool_deltas)}

                if choice.get("finish_reason"):
                    finish_reason = str(choice["finish_reason"])
        finally:
            if pending_next is not None and not pending_next.done():
                pending_next.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await pending_next
            aclose = getattr(backend_stream, "aclose", None)
            if aclose is not None:
                with contextlib.suppress(Exception):
                    await aclose()

        message: Dict[str, Any] = {
            "role": "assistant",
            "content": "".join(content_parts),
        }
        if not message["content"] and not reasoning_content_parts and not reasoning_parts and not tool_state:
            LOG.warning(
                "Stage %s completed with an empty streamed backend response; retrying once non-streaming",
                profile.name,
            )
            recovery = await self.backend.chat(
                messages=history,
                secondary_system=secondary_system,
                profile=profile,
                tools=effective_tools,
                tool_choice=effective_tool_choice,
            )
            recovery_usage = recovery.get("usage")
            if recovery_usage:
                aggregate_usage(usage, recovery_usage)
                aggregate_usage(stage_usage, recovery_usage)
            recovery_choice = (recovery.get("choices") or [{}])[0] or {}
            recovered = recovery_choice.get("message") or {}
            recovered_content = str(recovered.get("content") or "")
            recovered_reasoning_content = str(recovered.get("reasoning_content") or "")
            recovered_reasoning = str(recovered.get("reasoning") or "")
            recovered_tool_calls = recovered.get("tool_calls") if isinstance(recovered.get("tool_calls"), list) else []

            if recovered_reasoning_content:
                reasoning_content_parts.append(recovered_reasoning_content)
                yield {"kind": "reasoning", "text": recovered_reasoning_content}
            elif recovered_reasoning:
                reasoning_parts.append(recovered_reasoning)
                yield {"kind": "reasoning", "text": recovered_reasoning}
            if recovered_content:
                content_parts.append(recovered_content)
                yield {"kind": "content", "text": recovered_content}
            if recovered_tool_calls:
                for index, call in enumerate(recovered_tool_calls):
                    if not isinstance(call, dict):
                        continue
                    delta_call = copy.deepcopy(call)
                    delta_call["index"] = index
                    self._merge_tool_call_delta(tool_state, [delta_call])
            if recovery_choice.get("finish_reason"):
                finish_reason = str(recovery_choice["finish_reason"])

            if not content_parts and not reasoning_content_parts and not reasoning_parts and not tool_state:
                raise HTTPException(
                    status_code=502,
                    detail=f"Stage {profile.name} returned an empty response in both streaming and non-streaming modes.",
                )

            message = {
                "role": "assistant",
                "content": "".join(content_parts),
            }
        if reasoning_content_parts:
            joined = "".join(reasoning_content_parts)
            message["reasoning_content"] = joined
            message["reasoning"] = joined
        elif reasoning_parts:
            message["reasoning"] = "".join(reasoning_parts)
        if tool_state:
            message["tool_calls"] = normalize_tool_calls_for_distribution([tool_state[i] for i in sorted(tool_state)])

        governed_stage = bool(SELF_ADVERSARIAL_MODE or (CODE_DEBUGGING_MODE and _debugging_pass_from_stage_key(stage_key) is not None))
        if governed_stage and message.get("tool_calls"):
            if not profile.allow_tools:
                validation_errors = [f"{profile.name}: this stage has no tool authority"]
            else:
                validation_errors = _tool_call_validation_errors(message.get("tool_calls"), effective_tools)
            if validation_errors:
                if tool_validation_repair_depth >= 2:
                    raise HTTPException(status_code=502, detail=(
                        f"{STAGES[stage_key].name} repeatedly emitted rejected tool actions: " + "; ".join(validation_errors)
                    ))
                LOG.warning("%s rejected streamed tool action before execution: %s", STAGES[stage_key].name, "; ".join(validation_errors))
                repair_history = _tool_rejection_history(history, message, validation_errors, STAGES[stage_key].name)
                yield {"kind": "reasoning", "text": "\n[JACK TOOL ACTION REJECTED BEFORE EXECUTION — CORRECTING IN SAME STAGE]\n"}
                async for packet in self._run_stage_streamed(
                    repair_history, secondary_system, stage_key, usage, tools=tools, tool_choice=tool_choice,
                    append=append, same_stage_resume=True, tool_validation_repair_depth=tool_validation_repair_depth + 1,
                ):
                    yield packet
                return

        unexpected_reasoning = message.get("reasoning_content") or message.get("reasoning")
        if unexpected_reasoning and not profile.thinking:
            LOG.warning(
                "Backend emitted native reasoning during thinking-OFF stage %s; "
                "Jack will not preserve that reasoning into later stage context.",
                profile.name,
            )

        if not message.get("tool_calls"):
            if SELF_ADVERSARIAL_MODE and stage_key == "extended_initial":
                if AGENTIC_MODE and CFG.forensic_archive_mode == "stage":
                    message["_jack_agentic_stage1_forensic_snapshot"] = _capture_agentic_stage1_forensic_snapshot(
                        history, message
                    )
                trace = extended_stage1_reasoning_trace(history, message)
                if trace:
                    message["_jack_extended_stage1_reasoning_trace"] = trace
            elif SELF_ADVERSARIAL_MODE and stage_key == "extended_reflection":
                trace = self_adversarial_stage_reasoning_trace(history, stage_key, message)
                if trace:
                    message["_jack_stage2_reasoning_trace"] = trace
            elif ULTRA_MODE and stage_key == "extended_synthesis":
                trace = self_adversarial_stage_reasoning_trace(history, stage_key, message)
                if trace:
                    message["_jack_stage3_reasoning_trace"] = trace
            defer_extended_context = bool(
                (
                    ULTRA_MODE
                    and stage_key in {"extended_initial", "extended_reflection", "extended_synthesis"}
                )
                or (AGENTIC_MODE and stage_key in {"extended_initial", "extended_reflection", "extended_synthesis"})
                or (CODE_DEBUGGING_MODE and _debugging_pass_from_stage_key(stage_key) is not None)
            )
            if not defer_extended_context:
                pruned_messages = self._prune_internal_tool_exchanges(history)
                if pruned_messages:
                    LOG.info(
                        "%s completed; retired %d consumed stage-local tool protocol message(s)",
                        STAGES[stage_key].name,
                        pruned_messages,
                    )
            if append:
                append_stage_result(history, stage_key, message)

        data = {
            "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
            "usage": normalize_usage(stage_usage),
            "_jack_tool_call_fragments_streamed": tool_call_fragments_streamed,
        }
        if self.cfg.log_reasoning:
            reason_text = message.get("reasoning_content") or message.get("reasoning") or ""
            if reason_text:
                LOG.debug("%s reasoning:\n%s", profile.name, reason_text)
        yield {"kind": "result", "data": data}

    @staticmethod
    def _tool_interrupt(data: Dict[str, Any], usage: Dict[str, int]) -> Optional[KernelResult]:
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        calls = msg.get("tool_calls")
        if calls:
            return KernelResult(
                content=msg.get("content"),
                tool_calls=calls,
                finish_reason="tool_calls",
                usage=normalize_usage(usage),
            )
        return None

    @staticmethod
    def _tool_call_ids(data: Dict[str, Any]) -> Tuple[str, ...]:
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        calls = msg.get("tool_calls") if isinstance(msg.get("tool_calls"), list) else []
        ids: List[str] = []
        for call in calls:
            if not isinstance(call, dict):
                continue
            call_id = call.get("id")
            if not isinstance(call_id, str) or not call_id.strip():
                raise HTTPException(
                    status_code=502,
                    detail="A tool-enabled Jack stage emitted a tool call without a stable tool_call id; stage-local resume is impossible.",
                )
            ids.append(call_id.strip())
        if len(ids) != len(set(ids)):
            raise HTTPException(
                status_code=502,
                detail="A tool-enabled Jack stage emitted duplicate tool_call ids; stage-local resume is impossible.",
            )
        return tuple(ids)

    async def _expire_pending_tool_resumes_locked(self, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        cutoff = now - (6 * 60 * 60)
        stale = {
            state.resume_id
            for state in self._pending_tool_resumes.values()
            if state.created_at < cutoff and not state.in_flight
        }
        if not stale:
            return
        for call_id, state in list(self._pending_tool_resumes.items()):
            if state.resume_id in stale:
                self._pending_tool_resumes.pop(call_id, None)
        LOG.info("Expired %d stale Jack tool-resume transaction(s)", len(stale))

    @staticmethod
    def _tool_result_explicitly_failed(message: Dict[str, Any]) -> bool:
        """Recognize only structured caller-provided failure signals.

        Jack deliberately does not infer failure from free-text tool output. A
        caller may explicitly mark a failed tool result with is_error=true,
        success=false, a failure status, or a non-empty error field.
        """
        if not isinstance(message, dict):
            return False
        if message.get("is_error") is True or message.get("success") is False:
            return True
        status = str(message.get("status") or "").strip().lower()
        if status in {"error", "failed", "failure"}:
            return True
        error = message.get("error")
        return error not in (None, False, "", {}, [])

    @staticmethod
    def _prune_internal_tool_exchanges(history: List[Dict[str, Any]]) -> int:
        """Retire consumed tool protocol while preserving compact deterministic receipts."""
        kept: List[Dict[str, Any]] = []
        removed = 0
        index = 0
        size = len(history)
        while index < size:
            message = history[index]
            is_internal = isinstance(message, dict) and message.get("_jack_internal_tool_exchange")
            if not is_internal:
                kept.append(message)
                index += 1
                continue
            if message.get("role") != "assistant" or not message.get("tool_calls"):
                removed += 1
                index += 1
                continue
            group: List[Dict[str, Any]] = [message]
            index += 1
            while index < size:
                candidate = history[index]
                if not (isinstance(candidate, dict) and candidate.get("_jack_internal_tool_exchange")):
                    break
                if candidate.get("role") == "assistant" and candidate.get("tool_calls"):
                    break
                group.append(candidate)
                index += 1
            kept.extend(_tool_evidence_receipts_from_group(group))
            removed += len(group)
        history[:] = kept
        return removed

    @classmethod
    def _roll_tool_frontier(
        cls, history: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], int, int]:
        """Build the next active frontier without deep-copying prior history.

        Internal tool protocol is grouped as one assistant tool-call message plus
        its following tool-result messages. Successful groups retire immediately
        after consumption. If any result carries an explicit structured failure
        signal, that complete protocol group survives exactly one additional
        frontier so the backend still sees a valid assistant/tool sequence while
        evaluating the corrective action.
        """
        kept: List[Dict[str, Any]] = []
        removed = 0
        carried_failures = 0
        index = 0
        size = len(history)
        while index < size:
            message = history[index]
            is_internal = isinstance(message, dict) and message.get("_jack_internal_tool_exchange")
            if not is_internal:
                kept.append(message)
                index += 1
                continue

            # A valid internal transaction starts with the assistant tool call.
            if message.get("role") != "assistant" or not message.get("tool_calls"):
                removed += 1
                index += 1
                continue

            group: List[Dict[str, Any]] = [message]
            index += 1
            while index < size:
                candidate = history[index]
                if not (isinstance(candidate, dict) and candidate.get("_jack_internal_tool_exchange")):
                    break
                if candidate.get("role") == "assistant" and candidate.get("tool_calls"):
                    break
                group.append(candidate)
                index += 1

            failed_results = [
                item
                for item in group
                if item.get("role") == "tool"
                and item.get("_jack_internal_tool_failed")
                and int(item.get("_jack_failure_carry_hops") or 0) > 0
            ]
            if failed_results:
                for item in group:
                    cloned = dict(item)
                    if cloned.get("_jack_internal_tool_failed"):
                        hops = int(cloned.get("_jack_failure_carry_hops") or 0)
                        cloned["_jack_failure_carry_hops"] = max(0, hops - 1)
                    kept.append(cloned)
                carried_failures += len(failed_results)
            else:
                kept.extend(_tool_evidence_receipts_from_group(group))
                removed += len(group)
        return kept, removed, carried_failures

    async def _expire_pending_debugging_intake_resumes_locked(self, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        cutoff = now - (6 * 60 * 60)
        stale = [
            resume_id
            for resume_id, state in self._pending_debugging_intake_resumes.items()
            if state.created_at < cutoff and not state.in_flight
        ]
        for resume_id in stale:
            self._pending_debugging_intake_resumes.pop(resume_id, None)
        if stale:
            LOG.info("Expired %d stale Code Debugging intake transaction(s)", len(stale))

    async def _register_debugging_intake_resume(
        self,
        *,
        run: DebuggingRunState,
        history: List[Dict[str, Any]],
        secondary_system: str,
        usage: Dict[str, int],
        tools: Optional[List[Dict[str, Any]]],
        tool_choice: Any,
        data: Dict[str, Any],
    ) -> KernelResult:
        if not CODE_DEBUGGING_MODE:
            raise HTTPException(status_code=500, detail="Debugging intake is valid only in Code Debugging mode.")
        choice = (data.get("choices") or [{}])[0] or {}
        msg = choice.get("message") or {}
        raw_content = str(msg.get("content") or "").strip()
        if raw_content.startswith(_DEBUGGING_INTAKE_COMPLETE_PREFIX):
            raise HTTPException(status_code=500, detail="Completed debugging intake cannot be checkpointed as pending.")
        if not raw_content:
            raw_content = "Before I begin the five debugging passes, tell me any runtime symptoms, reproduction details, expected behavior, or witnessed bugs that could help guide the audit."
        _debugging_append_intake_turn(run, "assistant", raw_content)
        user_visible_response = f"{raw_content}\n\n{_DEBUGGING_INTAKE_PRIMARY_DIRECTIVE_REMINDER}"
        resume_history = list(history)
        resume_history.append({
            "role": "assistant",
            "content": raw_content,
            "_jack_internal_debugging_intake": True,
        })
        state = PendingDebuggingIntakeResume(
            resume_id=f"jack-debug-intake-{uuid.uuid4().hex}",
            run_id=run.run_id,
            history=resume_history,
            secondary_system=secondary_system,
            usage=dict(usage),
            tools=tools,
            tool_choice=tool_choice,
            user_visible_response=user_visible_response,
            created_at=time.time(),
        )
        async with self._pending_debugging_intake_resume_lock:
            await self._expire_pending_debugging_intake_resumes_locked()
            self._pending_debugging_intake_resumes[state.resume_id] = state
        LOG.info("Code Debugging pre-pass intake paused for user guidance: run=%s resume_id=%s", run.run_id, state.resume_id)
        reasoning = msg.get("reasoning_content") or msg.get("reasoning") or msg.get("thinking")
        return KernelResult(
            content=user_visible_response,
            tool_calls=None,
            finish_reason="stop",
            usage=normalize_usage(dict(usage)),
            reasoning_content=str(reasoning) if reasoning else None,
        )

    async def _consume_pending_debugging_intake_resume(
        self, messages: List[Dict[str, Any]]
    ) -> Optional[Tuple[PendingDebuggingIntakeResume, Dict[str, Any]]]:
        if not CODE_DEBUGGING_MODE or not messages:
            return None
        last_user_index = None
        for index in range(len(messages) - 1, -1, -1):
            raw = messages[index]
            if isinstance(raw, dict) and raw.get("role") == "user":
                last_user_index = index
                break
            if isinstance(raw, dict) and raw.get("role") == "tool":
                return None
        if last_user_index is None:
            return None
        reply_text = _content_to_text(messages[last_user_index].get("content")).strip()
        if not reply_text:
            raise HTTPException(status_code=400, detail="Code Debugging intake reply is empty.")

        async with self._pending_debugging_intake_resume_lock:
            await self._expire_pending_debugging_intake_resumes_locked()
            if not self._pending_debugging_intake_resumes:
                return None
            prior_assistant_contents = {
                _content_to_text(item.get("content")).strip()
                for item in messages[:last_user_index]
                if isinstance(item, dict) and item.get("role") == "assistant"
            }
            matched = [
                state for state in self._pending_debugging_intake_resumes.values()
                if state.user_visible_response in prior_assistant_contents
            ]
            if not matched:
                return None
            if len(matched) != 1:
                raise HTTPException(status_code=409, detail="Code Debugging intake reply could not be matched to exactly one pending intake.")
            state = matched[0]
            if state.in_flight:
                raise HTTPException(status_code=409, detail="Code Debugging intake transaction is already being resumed.")
            state.in_flight = True

        run = _debugging_get_run(state.run_id)
        user_message = {
            "role": "user",
            "content": reply_text,
            "_jack_internal_debugging_intake_reply": True,
            "_jack_debugging_intake_proceed": _debugging_user_requests_intake_close(reply_text),
        }
        LOG.info("Resuming Code Debugging pre-pass intake: run=%s resume_id=%s", run.run_id, state.resume_id)
        return state, user_message

    async def _retire_pending_debugging_intake_resume(self, state: PendingDebuggingIntakeResume) -> None:
        async with self._pending_debugging_intake_resume_lock:
            if self._pending_debugging_intake_resumes.get(state.resume_id) is state:
                self._pending_debugging_intake_resumes.pop(state.resume_id, None)
            state.in_flight = False

    async def _rearm_pending_debugging_intake_resume(self, state: PendingDebuggingIntakeResume) -> None:
        async with self._pending_debugging_intake_resume_lock:
            if self._pending_debugging_intake_resumes.get(state.resume_id) is state:
                state.in_flight = False

    async def _run_debugging_intake_nonstream(
        self,
        *,
        run: DebuggingRunState,
        history: List[Dict[str, Any]],
        secondary_system: str,
        usage: Dict[str, int],
        tools: Optional[List[Dict[str, Any]]],
        tool_choice: Any,
        same_stage_resume: bool = False,
        pending_resume: Optional[PendingDebuggingIntakeResume] = None,
    ) -> KernelResult:
        resumed_user_text = ""
        if same_stage_resume and history and isinstance(history[-1], dict) and history[-1].get("_jack_internal_debugging_intake_reply"):
            resumed_user_text = _content_to_text(history[-1].get("content")).strip()
        if history and isinstance(history[-1], dict) and history[-1].get("_jack_debugging_intake_proceed"):
            if resumed_user_text:
                _debugging_append_intake_turn(run, "user", resumed_user_text)
            _debugging_freeze_intake(run)
            if pending_resume is not None:
                await self._retire_pending_debugging_intake_resume(pending_resume)
            return await self._run_code_debugging_nonstream(
                run=run,
                secondary_system=secondary_system,
                usage=usage,
                tools=tools,
                tool_choice=tool_choice,
                start_pass=1,
            )

        stage = await self._run_stage(
            history,
            secondary_system,
            "debug_intake",
            usage,
            tools=None,
            tool_choice=None,
            append=False,
            same_stage_resume=same_stage_resume,
        )
        if self._tool_interrupt(stage, usage):
            raise HTTPException(status_code=502, detail="Code Debugging pre-pass intake attempted a tool call even though intake tools are disabled.")
        if _debugging_intake_complete_from_result(stage):
            if resumed_user_text:
                _debugging_append_intake_turn(run, "user", resumed_user_text)
            _debugging_freeze_intake(run)
            if pending_resume is not None:
                await self._retire_pending_debugging_intake_resume(pending_resume)
            return await self._run_code_debugging_nonstream(
                run=run,
                secondary_system=secondary_system,
                usage=usage,
                tools=tools,
                tool_choice=tool_choice,
                start_pass=1,
            )
        if resumed_user_text:
            _debugging_append_intake_turn(run, "user", resumed_user_text)
        successor = await self._register_debugging_intake_resume(
            run=run,
            history=history,
            secondary_system=secondary_system,
            usage=usage,
            tools=tools,
            tool_choice=tool_choice,
            data=stage,
        )
        if pending_resume is not None:
            await self._retire_pending_debugging_intake_resume(pending_resume)
        return successor

    async def _expire_pending_debugging_user_resumes_locked(self, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        cutoff = now - (6 * 60 * 60)
        stale = [
            resume_id
            for resume_id, state in self._pending_debugging_user_resumes.items()
            if state.created_at < cutoff and not state.in_flight
        ]
        for resume_id in stale:
            self._pending_debugging_user_resumes.pop(resume_id, None)
        if stale:
            LOG.info("Expired %d stale Code Debugging user-clarification transaction(s)", len(stale))

    async def _register_debugging_user_resume(
        self,
        *,
        stage_key: str,
        history: List[Dict[str, Any]],
        secondary_system: str,
        usage: Dict[str, int],
        tools: Optional[List[Dict[str, Any]]],
        tool_choice: Any,
        data: Dict[str, Any],
        question: str,
        debugging_run_id: Optional[str] = None,
    ) -> KernelResult:
        pass_number = _debugging_pass_from_stage_key(stage_key)
        if not CODE_DEBUGGING_MODE or pass_number is None:
            raise HTTPException(status_code=500, detail="User clarification is valid only inside a live Code Debugging pass.")
        choice = (data.get("choices") or [{}])[0] or {}
        msg = choice.get("message") or {}
        user_visible_question = _debugging_render_user_question(question)
        checkpoint_message: Dict[str, Any] = {
            "role": "assistant",
            "content": user_visible_question,
            "_jack_internal_debugging_user_question": True,
            "_jack_stage_key": stage_key,
        }
        reasoning_content = msg.get("reasoning_content")
        reasoning = msg.get("reasoning")
        thinking = msg.get("thinking")
        if isinstance(reasoning_content, str) and reasoning_content:
            checkpoint_message["reasoning_content"] = reasoning_content
            checkpoint_message["reasoning"] = reasoning_content
        elif isinstance(reasoning, str) and reasoning:
            checkpoint_message["reasoning"] = reasoning
        elif isinstance(thinking, str) and thinking:
            checkpoint_message["thinking"] = thinking
        resume_history = list(history)
        resume_history.append(checkpoint_message)
        state = PendingDebuggingUserResume(
            resume_id=f"jack-debug-user-{uuid.uuid4().hex}",
            stage_key=stage_key,
            history=resume_history,
            secondary_system=secondary_system,
            usage=dict(usage),
            tools=tools,
            tool_choice=tool_choice,
            user_visible_question=user_visible_question,
            created_at=time.time(),
            debugging_run_id=debugging_run_id,
        )
        async with self._pending_debugging_user_resume_lock:
            await self._expire_pending_debugging_user_resumes_locked()
            self._pending_debugging_user_resumes[state.resume_id] = state
        LOG.info("Code Debugging Pass %d paused for user clarification: resume_id=%s", pass_number, state.resume_id)
        reasoning_trace = msg.get("reasoning_content") or msg.get("reasoning") or msg.get("thinking")
        return KernelResult(
            content=user_visible_question,
            tool_calls=None,
            finish_reason="stop",
            usage=normalize_usage(dict(usage)),
            reasoning_content=str(reasoning_trace) if reasoning_trace else None,
        )

    async def _consume_pending_debugging_user_resume(
        self, messages: List[Dict[str, Any]]
    ) -> Optional[Tuple[PendingDebuggingUserResume, Dict[str, Any]]]:
        if not CODE_DEBUGGING_MODE or not messages:
            return None
        last_user_index = None
        for index in range(len(messages) - 1, -1, -1):
            raw = messages[index]
            if isinstance(raw, dict) and raw.get("role") == "user":
                last_user_index = index
                break
            if isinstance(raw, dict) and raw.get("role") == "tool":
                return None
        if last_user_index is None:
            return None
        raw_user = messages[last_user_index]
        reply_text = _content_to_text(raw_user.get("content")).strip()
        if not reply_text:
            raise HTTPException(status_code=400, detail="Code Debugging clarification reply is empty.")

        async with self._pending_debugging_user_resume_lock:
            await self._expire_pending_debugging_user_resumes_locked()
            if not self._pending_debugging_user_resumes:
                return None
            matched: List[PendingDebuggingUserResume] = []
            prior_assistant_contents = {
                _content_to_text(item.get("content")).strip()
                for item in messages[:last_user_index]
                if isinstance(item, dict) and item.get("role") == "assistant"
            }
            for state in self._pending_debugging_user_resumes.values():
                if state.user_visible_question in prior_assistant_contents:
                    matched.append(state)
            if not matched:
                return None
            if len(matched) != 1:
                raise HTTPException(
                    status_code=409,
                    detail="Code Debugging user reply could not be matched to exactly one pending clarification.",
                )
            state = matched[0]
            if state.in_flight:
                raise HTTPException(status_code=409, detail="Code Debugging clarification transaction is already being resumed.")
            state.in_flight = True

        user_message = {
            "role": "user",
            "content": reply_text,
            "_jack_internal_debugging_user_reply": True,
            "_jack_stage_key": state.stage_key,
        }
        LOG.info("Resuming %s after user clarification: resume_id=%s", STAGES[state.stage_key].name, state.resume_id)
        return state, user_message

    async def _retire_pending_debugging_user_resume(self, state: PendingDebuggingUserResume) -> None:
        async with self._pending_debugging_user_resume_lock:
            if self._pending_debugging_user_resumes.get(state.resume_id) is state:
                self._pending_debugging_user_resumes.pop(state.resume_id, None)
            state.in_flight = False

    async def _rearm_pending_debugging_user_resume(self, state: PendingDebuggingUserResume) -> None:
        async with self._pending_debugging_user_resume_lock:
            if self._pending_debugging_user_resumes.get(state.resume_id) is state:
                state.in_flight = False

    async def _rearm_pending_debugging_resumes_for_messages(self, messages: Any) -> None:
        if not CODE_DEBUGGING_MODE or not isinstance(messages, list) or not messages:
            return
        last_user_index = None
        for index in range(len(messages) - 1, -1, -1):
            item = messages[index]
            if isinstance(item, dict) and item.get("role") == "user":
                last_user_index = index
                break
            if isinstance(item, dict) and item.get("role") == "tool":
                return
        if last_user_index is None:
            return
        prior_assistant_contents = {
            _content_to_text(item.get("content")).strip()
            for item in messages[:last_user_index]
            if isinstance(item, dict) and item.get("role") == "assistant"
        }
        async with self._pending_debugging_intake_resume_lock:
            candidates = [
                state for state in self._pending_debugging_intake_resumes.values()
                if state.in_flight and state.user_visible_response in prior_assistant_contents
            ]
            for state in candidates:
                state.in_flight = False
        async with self._pending_debugging_user_resume_lock:
            candidates = [
                state for state in self._pending_debugging_user_resumes.values()
                if state.in_flight and state.user_visible_question in prior_assistant_contents
            ]
            for state in candidates:
                state.in_flight = False

    async def _resume_debugging_user_stage_nonstream(
        self, state: PendingDebuggingUserResume, user_message: Dict[str, Any]
    ) -> KernelResult:
        run = _debugging_get_run(state.debugging_run_id)
        history = list(state.history)
        history.append(user_message)
        usage = dict(state.usage)
        stage = await self._run_stage(
            history,
            state.secondary_system,
            state.stage_key,
            usage,
            tools=state.tools,
            tool_choice=state.tool_choice,
            append=False,
            same_stage_resume=True,
        )
        if self._tool_interrupt(stage, usage):
            successor = await self._register_stage_tool_resume(
                stage_key=state.stage_key,
                history=history,
                secondary_system=state.secondary_system,
                usage=usage,
                tools=state.tools,
                tool_choice=state.tool_choice,
                data=stage,
                debugging_run_id=run.run_id,
            )
            await self._retire_pending_debugging_user_resume(state)
            return successor
        question = _debugging_user_question_from_result(stage)
        if question is not None:
            successor = await self._register_debugging_user_resume(
                stage_key=state.stage_key,
                history=history,
                secondary_system=state.secondary_system,
                usage=usage,
                tools=state.tools,
                tool_choice=state.tool_choice,
                data=stage,
                question=question,
                debugging_run_id=run.run_id,
            )
            await self._retire_pending_debugging_user_resume(state)
            return successor
        pass_number = _debugging_pass_from_stage_key(state.stage_key)
        if pass_number is None:
            raise HTTPException(status_code=500, detail="Invalid Code Debugging user-resume stage")
        _debugging_commit_pass_summary(run, pass_number, stage)
        await self._retire_pending_debugging_user_resume(state)
        return await self._run_code_debugging_nonstream(
            run=run,
            secondary_system=state.secondary_system,
            usage=usage,
            tools=state.tools,
            tool_choice=state.tool_choice,
            start_pass=pass_number + 1,
        )

    async def _register_stage_tool_resume(
        self,
        *,
        stage_key: str,
        history: List[Dict[str, Any]],
        secondary_system: str,
        usage: Dict[str, int],
        tools: Optional[List[Dict[str, Any]]],
        tool_choice: Any,
        data: Dict[str, Any],
        debugging_run_id: Optional[str] = None,
    ) -> KernelResult:
        if ULTRA_MODE:
            allowed_tool_stages = {"extended_synthesis"}
        elif AGENTIC_MODE:
            allowed_tool_stages = {"extended_initial"}
        elif CODE_DEBUGGING_MODE:
            allowed_tool_stages = {_debugging_stage_key(i) for i in range(1, DEBUGGING_PASS_COUNT + 1)}
        else:
            allowed_tool_stages = {"thesis"}
        if stage_key not in allowed_tool_stages:
            raise HTTPException(status_code=500, detail=f"Stage {stage_key} is not tool-enabled")
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        calls = msg.get("tool_calls") if isinstance(msg.get("tool_calls"), list) else []
        call_ids = self._tool_call_ids(data)
        if not calls or not call_ids:
            raise HTTPException(status_code=500, detail=f"Attempted to checkpoint {stage_key} without a tool call")

        # Active Agentic/Deep Research stages are uninterrupted cognitive stages. Code
        # Debugging also preserves complete native reasoning/tool protocol, but only while
        # one pass is active. At pass commit Jack drops that entire context and the next
        # next pass receives exact user-origin Pass 0 plus only the host-derived confirmed prior-finding registry.
        if (
            SELF_ADVERSARIAL_MODE and stage_key in {"extended_initial", "extended_reflection", "extended_synthesis"}
        ) or (CODE_DEBUGGING_MODE and _debugging_pass_from_stage_key(stage_key) is not None):
            resume_history = list(history)
            pruned_messages = 0
            carried_failures = 0
        else:
            resume_history, pruned_messages, carried_failures = self._roll_tool_frontier(history)
            if pruned_messages or carried_failures:
                LOG.info(
                    "%s rolling tool frontier retired=%d carried_failures=%d",
                    STAGES[stage_key].name,
                    pruned_messages,
                    carried_failures,
                )
        # Deep Research Synthesis is initially opened with one Jack-owned transition reminder
        # containing the active user request as quoted context. Persist that same bridge
        # exactly once before the assistant tool call so a tool continuation reconstructs
        # the same Synthesis transaction. Never inject another bridge on tool resume.
        if ULTRA_MODE and stage_key == "extended_synthesis" and not any(
            isinstance(item, dict)
            and item.get("_jack_internal_stage_generation_trigger")
            and item.get("_jack_stage_key") == stage_key
            for item in resume_history
        ):
            _append_ultra_stage_generation_trigger(resume_history, stage_key)

        # Append the current pre-tool frontier. Self-adversarial stages extend the
        # complete active-stage transcript; other stage paths use
        # the bounded rolling-frontier behavior.
        checkpoint_message: Dict[str, Any] = {
            "role": "assistant",
            "content": msg.get("content") or "",
            "tool_calls": calls,
            "_jack_internal_tool_exchange": True,
            "_jack_stage_key": stage_key,
        }
        reasoning_content = msg.get("reasoning_content")
        reasoning = msg.get("reasoning")
        thinking = msg.get("thinking")
        if isinstance(reasoning_content, str) and reasoning_content:
            checkpoint_message["reasoning_content"] = reasoning_content
            # LM Studio/Qwen variants may consume either reasoning field.
            checkpoint_message["reasoning"] = reasoning_content
        elif isinstance(reasoning, str) and reasoning:
            checkpoint_message["reasoning"] = reasoning
        elif isinstance(thinking, str) and thinking:
            checkpoint_message["thinking"] = thinking
        resume_history.append(checkpoint_message)
        state = PendingToolResume(
            resume_id=f"jack-resume-{uuid.uuid4().hex}",
            stage_key=stage_key,
            history=resume_history,
            secondary_system=secondary_system,
            usage=dict(usage),
            tools=tools,
            tool_choice=tool_choice,
            expected_tool_call_ids=call_ids,
            created_at=time.time(),
            debugging_run_id=debugging_run_id,
        )
        async with self._pending_tool_resume_lock:
            await self._expire_pending_tool_resumes_locked()
            collision = [call_id for call_id in call_ids if call_id in self._pending_tool_resumes]
            if collision:
                raise HTTPException(
                    status_code=409,
                    detail=f"{STAGES[stage_key].name} tool_call_id collision with an existing pending transaction: " + ", ".join(collision),
                )
            for call_id in call_ids:
                self._pending_tool_resumes[call_id] = state
        LOG.info(
            "%s checkpointed for stage-local tool resume: resume_id=%s calls=%s",
            STAGES[stage_key].name,
            state.resume_id,
            ",".join(call_ids),
        )
        reasoning = msg.get("reasoning_content") or msg.get("reasoning") or msg.get("thinking")
        return KernelResult(
            # Deep Research never exposes provisional Thesis/Antithesis output as authoritative content
            # at a tool boundary. Only the final completed Synthesis is committed.
            content=None if ULTRA_MODE else msg.get("content"),
            tool_calls=calls,
            finish_reason="tool_calls",
            usage=normalize_usage(dict(usage)),
            reasoning_content=(str(reasoning) if (reasoning and not AGENTIC_MODE) else None),
        )

    async def _consume_pending_tool_resume(
        self, messages: List[Dict[str, Any]]
    ) -> Optional[Tuple[PendingToolResume, List[Dict[str, Any]]]]:
        tool_messages: List[Dict[str, Any]] = []
        ids_in_request: List[str] = []
        for raw in messages:
            if not isinstance(raw, dict) or raw.get("role") != "tool":
                continue
            call_id = raw.get("tool_call_id")
            if not isinstance(call_id, str) or not call_id.strip():
                continue
            ids_in_request.append(call_id.strip())
            item: Dict[str, Any] = {
                "role": "tool",
                "tool_call_id": call_id.strip(),
                "content": raw.get("content"),
                "_jack_internal_tool_exchange": True,
            }
            if raw.get("name") is not None:
                item["name"] = raw.get("name")
            if self._tool_result_explicitly_failed(raw):
                item["_jack_internal_tool_failed"] = True
                item["_jack_failure_carry_hops"] = 1
            tool_messages.append(item)

        if not ids_in_request:
            return None
        if len(ids_in_request) != len(set(ids_in_request)):
            raise HTTPException(
                status_code=409,
                detail="Duplicate tool_call_id values in one Jack tool-result request.",
            )

        async with self._pending_tool_resume_lock:
            await self._expire_pending_tool_resumes_locked()
            matched = [self._pending_tool_resumes[i] for i in ids_in_request if i in self._pending_tool_resumes]
            if not matched:
                return None
            resume_ids = {state.resume_id for state in matched}
            if len(resume_ids) != 1:
                raise HTTPException(
                    status_code=409,
                    detail="Tool-result request matches multiple pending Jack stage transactions.",
                )
            state = matched[0]
            if state.in_flight:
                raise HTTPException(
                    status_code=409,
                    detail=f"{STAGES[state.stage_key].name} tool-result transaction is already being resumed.",
                )
            expected = set(state.expected_tool_call_ids)
            supplied = {i for i in ids_in_request if i in expected}
            missing = expected - supplied
            if missing:
                raise HTTPException(
                    status_code=409,
                    detail=f"Incomplete {STAGES[state.stage_key].name} tool-result set; missing tool_call_id(s): " + ", ".join(sorted(missing)),
                )
            state.in_flight = True

        matched_messages = [m for m in tool_messages if m["tool_call_id"] in expected]
        LOG.info(
            "Resuming %s transaction in place: resume_id=%s tool_results=%d",
            STAGES[state.stage_key].name,
            state.resume_id,
            len(matched_messages),
        )
        return state, matched_messages

    async def _retire_pending_tool_resume(self, state: PendingToolResume) -> None:
        async with self._pending_tool_resume_lock:
            for call_id in state.expected_tool_call_ids:
                if self._pending_tool_resumes.get(call_id) is state:
                    self._pending_tool_resumes.pop(call_id, None)
            state.in_flight = False

    async def _rearm_pending_tool_resume(self, state: PendingToolResume) -> None:
        async with self._pending_tool_resume_lock:
            if any(self._pending_tool_resumes.get(call_id) is state for call_id in state.expected_tool_call_ids):
                state.in_flight = False

    async def _rearm_pending_tool_resume_for_messages(self, messages: Any) -> None:
        if not isinstance(messages, list):
            return
        ids = {
            str(item.get("tool_call_id") or "").strip()
            for item in messages
            if isinstance(item, dict) and item.get("role") == "tool" and str(item.get("tool_call_id") or "").strip()
        }
        if not ids:
            return
        async with self._pending_tool_resume_lock:
            states = {id(self._pending_tool_resumes[call_id]): self._pending_tool_resumes[call_id] for call_id in ids if call_id in self._pending_tool_resumes}
            for state in states.values():
                state.in_flight = False

    @staticmethod
    def _required_completed_answer_from_stage(data: Dict[str, Any], stage_name: str) -> str:
        """Require a nonempty completed answer surface without rewriting it."""
        msg = ((data.get("choices") or [{}])[0].get("message") or {})
        answer = _content_to_text(msg.get("content"))
        if not answer.strip():
            raise HTTPException(status_code=502, detail=f"{stage_name} produced no authoritative answer content.")
        return answer

    @staticmethod
    def _exact_frozen_answer_from_stage(data: Dict[str, Any], stage_name: str) -> str:
        """Freeze the exact completed stage answer bytes without a rewrite/cleanup pass."""
        return JackQwenKernel._required_completed_answer_from_stage(data, stage_name)

    async def _complete_commit(
        self,
        history: List[Dict[str, Any]],
        secondary_system: str,
        usage: Dict[str, int],
        frozen_stage1_answer: str,
        frozen_jack_xml: str,
        stage2_reasoning: Optional[str] = None,
    ) -> PreparedCommit:
        """Commit Stage-2 Jack XML beside the exact frozen Stage-1 answer.

        Stage 1 is the sole answer-generating stage. Stage 2 reviews the complete
        Stage-1 trajectory under Preserve Thinking and emits Jack XML only. After XML
        reaches EOS, Jack archives Stage-1 reasoning when enabled, clears all native
        cognition (including Stage-2 XML reasoning), and retains only the exact user-role message,
        Jack XML, and frozen Stage-1 answer for future turns. Jack XML does not need to
        reproduce the user request because the user-role message itself survives.
        """
        if not AGENTIC_MODE:
            raise HTTPException(status_code=500, detail="Agentic two-stage commit is only valid in Agentic mode")
        xml = freeze_xml_stage_output(frozen_jack_xml)
        if not xml:
            raise HTTPException(status_code=502, detail="Agentic Stage 2 produced no Jack XML content.")
        _archive_agentic_stage1_forensic(history, frozen_stage1_answer, xml)
        history.clear()
        return PreparedCommit(
            frozen_xml=xml,
            frozen_answer=frozen_stage1_answer,
            authoritative_source="STAGE1_FROZEN_PLUS_STAGE2_XML",
            usage=usage,
            stage2_reasoning=str(stage2_reasoning or "").strip() or None,
        )

    def _agentic_degraded_result(
        self, history: List[Dict[str, Any]], usage: Dict[str, int], frozen_stage1_answer: str, reason: str
    ) -> KernelResult:
        """Preserve exact frozen A1 when zero-authority semantic consolidation cannot complete."""
        _discard_agentic_stage1_forensic_snapshot(history)
        history.clear()
        LOG.warning("Agentic degraded commit: exact frozen A1 preserved without Jack XML: %s", reason)
        return KernelResult(
            content=frozen_stage1_answer,
            tool_calls=None,
            finish_reason="stop",
            usage=normalize_usage(dict(usage)),
            reasoning_content=(
                "[JACK AGENTIC DEGRADED COMMIT — A1 PRESERVED; JACK XML NOT PRODUCED]\n"
                + reason[:1200]
            ),
        )

    def _build_ultra_committed_result(
        self,
        *,
        history: List[Dict[str, Any]],
        usage: Dict[str, int],
        completed_answer: str,
        final_message: Dict[str, Any],
        finish_reason: str = "stop",
    ) -> KernelResult:
        """Build authoritative Deep Research Synthesis with the full current-turn cognition surface.

        R1/R2 remain available through final-output completion. They are compacted only when
        a later request re-enters Jack through compact_incoming_history().
        """
        clean_history = _ultra_history_without_held_synthesis(history)
        r1 = self_adversarial_stage_reasoning_trace(clean_history, "extended_initial")
        r2 = self_adversarial_stage_reasoning_trace(clean_history, "extended_reflection")
        r3 = self_adversarial_stage_reasoning_trace(clean_history, "extended_synthesis", final_message)
        a1 = ""
        a2 = ""
        for item in clean_history:
            if not isinstance(item, dict) or item.get("role") != "assistant":
                continue
            if item.get("_jack_extended_candidate_response"):
                a1 = _content_to_text(item.get("content"))
            if item.get("_jack_extended_completed_stage") == "extended_reflection":
                a2 = _content_to_text(item.get("content"))
        reasoning_parts: List[str] = []
        if r1 or a1:
            reasoning_parts.append(
                "===== JACK DEEP RESEARCH STAGE 1 — THESIS =====\n[NATIVE REASONING]\n"
                + (r1 or "")
                + "\n[THESIS]\n"
                + (a1 or "")
            )
        if r2 or a2:
            reasoning_parts.append(
                "===== JACK DEEP RESEARCH STAGE 2 — ANTITHESIS =====\n[NATIVE REASONING]\n"
                + (r2 or "")
                + "\n[ANTITHESIS]\n"
                + (a2 or "")
            )
        if r3:
            reasoning_parts.append(
                "===== JACK DEEP RESEARCH STAGE 3 — SYNTHESIS =====\n[NATIVE REASONING]\n" + r3
            )
        _archive_extended_forensic(clean_history, final_message, completed_answer)
        return KernelResult(
            content=completed_answer,
            tool_calls=None,
            finish_reason=str(finish_reason or "stop"),
            usage=normalize_usage(dict(usage)),
            reasoning_content="\n\n".join(reasoning_parts) or None,
        )

    async def _finalize_ultra_synthesis_nonstream(
        self,
        *,
        history: List[Dict[str, Any]],
        secondary_system: str,
        usage: Dict[str, int],
        tools: Optional[List[Dict[str, Any]]],
        tool_choice: Any,
        stage: Dict[str, Any],
    ) -> KernelResult:
        """Commit the completed Deep Research Synthesis directly.

        Deep Research no longer runs a deterministic post-EOS artifact disposition or
        follow-through gate. Artifact correction belongs to the tool-enabled
        Synthesis stage under its explicit disk-overwrite instruction.
        """
        choice = (stage.get("choices") or [{}])[0] or {}
        msg = choice.get("message") or {}
        completed_answer = self._required_completed_answer_from_stage(
            stage, "Deep Research Synthesis"
        )
        return self._build_ultra_committed_result(
            history=history,
            usage=usage,
            completed_answer=completed_answer,
            final_message=msg,
            finish_reason=str(choice.get("finish_reason") or "stop"),
        )

    async def _run_code_debugging_nonstream(
        self,
        *,
        run: DebuggingRunState,
        secondary_system: str,
        usage: Dict[str, int],
        tools: Optional[List[Dict[str, Any]]],
        tool_choice: Any,
        start_pass: int = 1,
    ) -> KernelResult:
        """Run fresh debugging passes with exact user authority plus host-derived prior-outcome registry state."""
        debug_tools, debug_tool_choice = _debugging_report_only_tool_surface(tools, tool_choice)
        for pass_number in range(start_pass, DEBUGGING_PASS_COUNT + 1):
            stage_key = _debugging_stage_key(pass_number)
            pass_history = _debugging_fresh_pass_history(run, pass_number)
            stage = await self._run_stage(
                pass_history,
                secondary_system,
                stage_key,
                usage,
                tools=debug_tools,
                tool_choice=debug_tool_choice,
                append=False,
            )
            if self._tool_interrupt(stage, usage):
                return await self._register_stage_tool_resume(
                    stage_key=stage_key,
                    history=pass_history,
                    secondary_system=secondary_system,
                    usage=usage,
                    tools=debug_tools,
                    tool_choice=debug_tool_choice,
                    data=stage,
                    debugging_run_id=run.run_id,
                )
            question = _debugging_user_question_from_result(stage)
            if question is not None:
                return await self._register_debugging_user_resume(
                    stage_key=stage_key,
                    history=pass_history,
                    secondary_system=secondary_system,
                    usage=usage,
                    tools=debug_tools,
                    tool_choice=debug_tool_choice,
                    data=stage,
                    question=question,
                    debugging_run_id=run.run_id,
                )
            _debugging_commit_pass_summary(run, pass_number, stage)
            if pass_number < DEBUGGING_PASS_COUNT:
                LOG.info(
                    "Code Debugging Pass %d committed; all native reasoning/tool context is discarded before fresh Pass %d",
                    pass_number,
                    pass_number + 1,
                )
            else:
                LOG.info(
                    "Code Debugging Pass 5 committed; all pass cognition is discarded before the fresh final-report instance"
                )

        summary = await self._run_stage(
            _debugging_final_summary_history(run),
            secondary_system,
            "debug_summary",
            usage,
            tools=None,
            tool_choice=None,
            append=False,
        )
        if self._tool_interrupt(summary, usage):
            raise HTTPException(status_code=502, detail="Code Debugging final report attempted a tool call even though the full report was already supplied by Jack")
        choice = (summary.get("choices") or [{}])[0] or {}
        msg = choice.get("message") or {}
        final_report = _debugging_commit_final_report(run, summary)
        reasoning = msg.get("reasoning_content") or msg.get("reasoning") or msg.get("thinking")
        return KernelResult(
            content=final_report,
            tool_calls=None,
            finish_reason=str(choice.get("finish_reason") or "stop"),
            usage=normalize_usage(dict(usage)),
            reasoning_content=str(reasoning) if reasoning else None,
        )

    async def _resume_tool_stage_nonstream(
        self,
        state: PendingToolResume,
        tool_messages: List[Dict[str, Any]],
    ) -> KernelResult | PreparedCommit:
        if ULTRA_MODE:
            allowed = {"extended_synthesis"}
        elif AGENTIC_MODE:
            allowed = {"extended_initial"}
        elif CODE_DEBUGGING_MODE:
            allowed = {_debugging_stage_key(i) for i in range(1, DEBUGGING_PASS_COUNT + 1)}
        else:
            allowed = {"thesis"}
        if state.stage_key not in allowed:
            raise HTTPException(status_code=500, detail="Unsupported pending Jack stage resume for active reasoning mode")

        history = list(state.history)
        history.extend(tool_messages)
        usage = dict(state.usage)
        stage_key = state.stage_key
        debugging_run = _debugging_get_run(state.debugging_run_id) if CODE_DEBUGGING_MODE else None

        stage = await self._run_stage(
            history,
            state.secondary_system,
            stage_key,
            usage,
            tools=state.tools,
            tool_choice=state.tool_choice,
            append=False,
            same_stage_resume=True,
        )
        if self._tool_interrupt(stage, usage):
            successor = await self._register_stage_tool_resume(
                stage_key=stage_key,
                history=history,
                secondary_system=state.secondary_system,
                usage=usage,
                tools=state.tools,
                tool_choice=state.tool_choice,
                data=stage,
                debugging_run_id=(debugging_run.run_id if debugging_run is not None else None),
            )
            await self._retire_pending_tool_resume(state)
            return successor

        if CODE_DEBUGGING_MODE:
            pass_number = _debugging_pass_from_stage_key(stage_key)
            if pass_number is None:
                raise HTTPException(status_code=500, detail="Invalid Code Debugging tool-resume stage")
            question = _debugging_user_question_from_result(stage)
            if question is not None:
                successor = await self._register_debugging_user_resume(
                    stage_key=stage_key,
                    history=history,
                    secondary_system=state.secondary_system,
                    usage=usage,
                    tools=state.tools,
                    tool_choice=state.tool_choice,
                    data=stage,
                    question=question,
                    debugging_run_id=debugging_run.run_id,
                )
                await self._retire_pending_tool_resume(state)
                return successor
            _debugging_commit_pass_summary(debugging_run, pass_number, stage)
            await self._retire_pending_tool_resume(state)
            LOG.info(
                "Code Debugging Pass %d committed after tool resume; previous pass cognition is not restored to the next pass",
                pass_number,
            )
            return await self._run_code_debugging_nonstream(
                run=debugging_run,
                secondary_system=state.secondary_system,
                usage=usage,
                tools=state.tools,
                tool_choice=state.tool_choice,
                start_pass=pass_number + 1,
            )

        if ULTRA_MODE:
            if stage_key != "extended_synthesis":
                raise HTTPException(status_code=500, detail="Deep Research tool resume is valid only for Synthesis")

            completed = await self._finalize_ultra_synthesis_nonstream(
                history=history,
                secondary_system=state.secondary_system,
                usage=usage,
                tools=state.tools,
                tool_choice=state.tool_choice,
                stage=stage,
            )
            await self._retire_pending_tool_resume(state)
            return completed

        if AGENTIC_MODE:
            if stage_key != "extended_initial":
                raise HTTPException(status_code=500, detail="Agentic Stage 2 cannot resume tools because XML-stage tools are disabled")

            first_msg = ((stage.get("choices") or [{}])[0].get("message") or {})
            frozen_stage1_answer = append_extended_candidate_response(history, first_msg)
            try:
                xml_stage = await self._run_stage(
                    history,
                    state.secondary_system,
                    "extended_reflection",
                    usage,
                    tools=None,
                    tool_choice=None,
                    append=False,
                )
                if self._tool_interrupt(xml_stage, usage):
                    raise HTTPException(status_code=502, detail="Agentic Stage 2 attempted a tool call even though XML-stage tools are disabled")
                choice = (xml_stage.get("choices") or [{}])[0] or {}
                msg = choice.get("message") or {}
                reasoning = msg.get("_jack_stage2_reasoning_trace") or msg.get("reasoning_content") or msg.get("reasoning") or msg.get("thinking")
                frozen_jack_xml = self._exact_frozen_answer_from_stage(xml_stage, "Agentic Stage 2 Jack XML")
                completed = await self._complete_commit(
                    history,
                    state.secondary_system,
                    usage,
                    frozen_stage1_answer,
                    frozen_jack_xml,
                    stage2_reasoning=str(reasoning or "").strip() or None,
                )
            except Exception as exc:
                detail = str(exc.detail) if isinstance(exc, HTTPException) else f"{type(exc).__name__}: {exc}"
                completed = self._agentic_degraded_result(history, usage, frozen_stage1_answer, detail)
            await self._retire_pending_tool_resume(state)
            return completed

        await self._retire_pending_tool_resume(state)
        choice = (stage.get("choices") or [{}])[0] or {}
        msg = choice.get("message") or {}
        reasoning = msg.get("reasoning_content") or msg.get("reasoning") or msg.get("thinking")
        return KernelResult(
            content=msg.get("content"),
            tool_calls=None,
            finish_reason=str(choice.get("finish_reason") or "stop"),
            usage=normalize_usage(dict(usage)),
            reasoning_content=str(reasoning) if reasoning else None,
        )

    async def _prepare_commit(
        self, request_body: Dict[str, Any]
    ) -> KernelResult | PreparedCommit:
        messages = request_body.get("messages")
        if not isinstance(messages, list) or not messages:
            raise HTTPException(status_code=400, detail="messages must be a non-empty list")
        if not has_user_message(messages):
            raise HTTPException(status_code=400, detail="At least one user message is required")

        secondary_system = merged_secondary_system_prompt(messages)
        history = (
            compact_incoming_history(messages)
            if SELF_ADVERSARIAL_MODE
            else strip_secondary_system_messages(messages)
        )
        tools = request_body.get("tools") if isinstance(request_body.get("tools"), list) else None
        tool_choice = request_body.get("tool_choice")
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        if ULTRA_MODE:
            thesis = await self._run_stage(
                history, secondary_system, "extended_initial", usage,
                tools=tools, tool_choice=tool_choice, append=False,
            )
            if self._tool_interrupt(thesis, usage):
                raise HTTPException(status_code=502, detail="Deep Research Thesis attempted a tool call even though the non-executing Thesis stage has tools disabled")
            thesis_msg = ((thesis.get("choices") or [{}])[0].get("message") or {})
            append_extended_candidate_response(history, thesis_msg)
            _append_ultra_stage_generation_trigger(history, "extended_reflection")

            antithesis = await self._run_stage(
                history, secondary_system, "extended_reflection", usage,
                tools=None, tool_choice=None, append=False,
            )
            if self._tool_interrupt(antithesis, usage):
                raise HTTPException(status_code=502, detail="Deep Research Antithesis attempted a tool call even though tools are disabled")
            anti_msg = ((antithesis.get("choices") or [{}])[0].get("message") or {})
            append_ultra_intermediate_response(history, "extended_reflection", anti_msg)
            _append_ultra_stage_generation_trigger(history, "extended_synthesis")

            synthesis = await self._run_stage(
                history, secondary_system, "extended_synthesis", usage,
                tools=tools, tool_choice=tool_choice, append=False,
            )
            if self._tool_interrupt(synthesis, usage):
                return await self._register_stage_tool_resume(
                    stage_key="extended_synthesis", history=history,
                    secondary_system=secondary_system, usage=usage,
                    tools=tools, tool_choice=tool_choice, data=synthesis,
                )
            return await self._finalize_ultra_synthesis_nonstream(
                history=history,
                secondary_system=secondary_system,
                usage=usage,
                tools=tools,
                tool_choice=tool_choice,
                stage=synthesis,
            )

        if AGENTIC_MODE:
            first = await self._run_stage(
                history,
                secondary_system,
                "extended_initial",
                usage,
                tools=tools,
                tool_choice=tool_choice,
                append=False,
            )
            if self._tool_interrupt(first, usage):
                return await self._register_stage_tool_resume(
                    stage_key="extended_initial",
                    history=history,
                    secondary_system=secondary_system,
                    usage=usage,
                    tools=tools,
                    tool_choice=tool_choice,
                    data=first,
                )

            first_msg = ((first.get("choices") or [{}])[0].get("message") or {})
            frozen_stage1_answer = append_extended_candidate_response(history, first_msg)
            try:
                second = await self._run_stage(
                    history,
                    secondary_system,
                    "extended_reflection",
                    usage,
                    tools=None,
                    tool_choice=None,
                    append=False,
                )
                if self._tool_interrupt(second, usage):
                    raise HTTPException(status_code=502, detail="Agentic Stage 2 attempted a tool call even though XML-stage tools are disabled")
                choice = (second.get("choices") or [{}])[0] or {}
                msg = choice.get("message") or {}
                reasoning = msg.get("_jack_stage2_reasoning_trace") or msg.get("reasoning_content") or msg.get("reasoning") or msg.get("thinking")
                frozen_jack_xml = self._exact_frozen_answer_from_stage(second, "Agentic Stage 2 Jack XML")
                return await self._complete_commit(
                    history,
                    secondary_system,
                    usage,
                    frozen_stage1_answer,
                    frozen_jack_xml,
                    stage2_reasoning=str(reasoning or "").strip() or None,
                )
            except Exception as exc:
                detail = str(exc.detail) if isinstance(exc, HTTPException) else f"{type(exc).__name__}: {exc}"
                return self._agentic_degraded_result(history, usage, frozen_stage1_answer, detail)

        if CODE_DEBUGGING_MODE:
            completed_run = _debugging_completed_run_for_history(history)
            if completed_run is not None:
                followup_history = _debugging_followup_history(completed_run, history)
                followup = await self._run_stage(
                    followup_history,
                    secondary_system,
                    "thesis",
                    usage,
                    tools=None,
                    tool_choice=None,
                    append=False,
                )
                if self._tool_interrupt(followup, usage):
                    raise HTTPException(
                        status_code=502,
                        detail="Completed Code Debugging follow-up attempted a tool call even though follow-up chat is tools-off.",
                    )
                choice = (followup.get("choices") or [{}])[0] or {}
                msg = choice.get("message") or {}
                reasoning = msg.get("reasoning_content") or msg.get("reasoning") or msg.get("thinking")
                return KernelResult(
                    content=msg.get("content"),
                    tool_calls=None,
                    finish_reason=str(choice.get("finish_reason") or "stop"),
                    usage=normalize_usage(dict(usage)),
                    reasoning_content=str(reasoning) if reasoning else None,
                )

            initial_request = _debugging_initial_request(history)
            run = _debugging_create_run(initial_request)
            intake_history = [{"role": "user", "content": initial_request}]
            return await self._run_debugging_intake_nonstream(
                run=run,
                history=intake_history,
                secondary_system=secondary_system,
                usage=usage,
                tools=tools,
                tool_choice=tool_choice,
                same_stage_resume=False,
            )

        native = await self._run_stage(
            history,
            secondary_system,
            "thesis",
            usage,
            tools=tools,
            tool_choice=tool_choice,
            append=False,
        )
        if self._tool_interrupt(native, usage):
            return await self._register_stage_tool_resume(
                stage_key="thesis",
                history=history,
                secondary_system=secondary_system,
                usage=usage,
                tools=tools,
                tool_choice=tool_choice,
                data=native,
            )
        choice = (native.get("choices") or [{}])[0] or {}
        msg = choice.get("message") or {}
        reasoning = msg.get("reasoning_content") or msg.get("reasoning") or msg.get("thinking")
        return KernelResult(
            content=msg.get("content"),
            tool_calls=None,
            finish_reason=str(choice.get("finish_reason") or "stop"),
            usage=normalize_usage(dict(usage)),
            reasoning_content=str(reasoning) if reasoning else None,
        )

    async def run(self, request_body: Dict[str, Any]) -> KernelResult:
        request_body = sanitize_agent_request(request_body)
        async with self._semaphore:
            messages = request_body.get("messages")
            pending = None
            debugging_intake_pending = None
            debugging_user_pending = None
            response_usage_baseline = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            if isinstance(messages, list):
                debugging_intake_pending = await self._consume_pending_debugging_intake_resume(messages)
                if debugging_intake_pending is None:
                    debugging_user_pending = await self._consume_pending_debugging_user_resume(messages)
                if debugging_intake_pending is None and debugging_user_pending is None:
                    pending = await self._consume_pending_tool_resume(messages)
            if debugging_intake_pending is not None:
                state, user_message = debugging_intake_pending
                response_usage_baseline = normalize_usage(dict(state.usage))
                run = _debugging_get_run(state.run_id)
                history = list(state.history)
                history.append(user_message)
                try:
                    prepared = await self._run_debugging_intake_nonstream(
                        run=run,
                        history=history,
                        secondary_system=state.secondary_system,
                        usage=dict(state.usage),
                        tools=state.tools,
                        tool_choice=state.tool_choice,
                        same_stage_resume=True,
                        pending_resume=state,
                    )
                except Exception:
                    await self._rearm_pending_debugging_intake_resume(state)
                    raise
            elif debugging_user_pending is not None:
                state, user_message = debugging_user_pending
                response_usage_baseline = normalize_usage(dict(state.usage))
                try:
                    prepared = await self._resume_debugging_user_stage_nonstream(state, user_message)
                except Exception:
                    await self._rearm_pending_debugging_user_resume(state)
                    raise
            elif pending is not None:
                state, tool_messages = pending
                response_usage_baseline = normalize_usage(dict(state.usage))
                try:
                    prepared = await self._resume_tool_stage_nonstream(state, tool_messages)
                except Exception:
                    await self._rearm_pending_tool_resume(state)
                    raise
            else:
                if isinstance(messages, list) and messages and isinstance(messages[-1], dict) and messages[-1].get("role") == "tool":
                    raise HTTPException(
                        status_code=409,
                        detail="Tool result arrived without a matching Jack stage checkpoint; Jack will not restart the pipeline from a tool-result turn.",
                    )
                prepared = await self._prepare_commit(request_body)
            if isinstance(prepared, KernelResult):
                prepared.usage = usage_delta(prepared.usage, response_usage_baseline)
                return prepared

            complete = f"{prepared.frozen_xml}\n\n{prepared.frozen_answer}"
            return KernelResult(
                content=complete,
                tool_calls=None,
                finish_reason="stop",
                usage=usage_delta(prepared.usage, response_usage_baseline),
                # Current-turn observability may expose Stage-2 thinking, but Jack
                # never restores it on the next user turn.
                reasoning_content=_stage2_reasoning_trace(prepared.stage2_reasoning),
            )

    async def stream(self, request_body: Dict[str, Any]) -> AsyncIterator[bytes]:
        """Stream the active Jack reasoning program.

        Agentic keeps its two-stage frozen-A1/XML behavior. Deep Research runs a full-retention
        Thesis -> Antithesis -> Synthesis transaction. Code Debugging runs five fresh
        report-only inspection passes with report-backed rehydration and exposes only the final report.
        """
        request_body = sanitize_agent_request(request_body)
        response_id = f"chatcmpl-jack-{uuid.uuid4().hex}"
        created = int(time.time())

        def event(delta: Dict[str, Any], finish_reason: Optional[str] = None) -> bytes:
            obj = {
                "id": response_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": self.cfg.virtual_model,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
            }
            return ("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode("utf-8")

        def usage_event(usage: Dict[str, int]) -> bytes:
            obj = {
                "id": response_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": self.cfg.virtual_model,
                "choices": [],
                "usage": normalize_usage(usage),
            }
            return ("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode("utf-8")

        messages = request_body.get("messages")
        if not isinstance(messages, list) or not messages:
            raise HTTPException(status_code=400, detail="messages must be a non-empty list")
        if not has_user_message(messages):
            raise HTTPException(status_code=400, detail="At least one user message is required")

        async with self._semaphore:
            debugging_intake_pending = await self._consume_pending_debugging_intake_resume(messages)
            debugging_user_pending = None if debugging_intake_pending is not None else await self._consume_pending_debugging_user_resume(messages)
            pending = None if (debugging_intake_pending is not None or debugging_user_pending is not None) else await self._consume_pending_tool_resume(messages)
            pending_state: Optional[PendingToolResume] = None
            pending_debugging_intake_state: Optional[PendingDebuggingIntakeResume] = None
            pending_debugging_user_state: Optional[PendingDebuggingUserResume] = None
            debugging_run: Optional[DebuggingRunState] = None
            debugging_followup_run: Optional[DebuggingRunState] = None
            pending_tool_messages: List[Dict[str, Any]] = []
            resume_stage_key: Optional[str] = None
            response_usage_baseline = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            if debugging_intake_pending is not None:
                state, user_message = debugging_intake_pending
                pending_debugging_intake_state = state
                debugging_run = _debugging_get_run(state.run_id)
                response_usage_baseline = normalize_usage(dict(state.usage))
                secondary_system = state.secondary_system
                history = list(state.history)
                history.append(user_message)
                tools = state.tools
                tool_choice = state.tool_choice
                usage = dict(state.usage)
            elif debugging_user_pending is not None:
                state, user_message = debugging_user_pending
                pending_debugging_user_state = state
                debugging_run = _debugging_get_run(state.debugging_run_id)
                response_usage_baseline = normalize_usage(dict(state.usage))
                resume_stage_key = state.stage_key
                secondary_system = state.secondary_system
                history = list(state.history)
                history.append(user_message)
                tools = state.tools
                tool_choice = state.tool_choice
                usage = dict(state.usage)
            elif pending is not None:
                state, tool_messages = pending
                pending_state = state
                pending_tool_messages = tool_messages
                response_usage_baseline = normalize_usage(dict(state.usage))
                if ULTRA_MODE:
                    allowed = {"extended_synthesis"}
                elif AGENTIC_MODE:
                    allowed = {"extended_initial"}
                elif CODE_DEBUGGING_MODE:
                    allowed = {_debugging_stage_key(i) for i in range(1, DEBUGGING_PASS_COUNT + 1)}
                else:
                    allowed = {"thesis"}
                if state.stage_key not in allowed:
                    raise HTTPException(status_code=500, detail="Unsupported pending Jack stage resume for active reasoning mode")
                resume_stage_key = state.stage_key
                secondary_system = state.secondary_system
                history = list(state.history)
                history.extend(tool_messages)
                tools = state.tools
                tool_choice = state.tool_choice
                usage = dict(state.usage)
                if CODE_DEBUGGING_MODE:
                    debugging_run = _debugging_get_run(state.debugging_run_id)
            else:
                if messages and isinstance(messages[-1], dict) and messages[-1].get("role") == "tool":
                    raise HTTPException(
                        status_code=409,
                        detail="Tool result arrived without a matching Jack stage checkpoint; Jack will not restart the pipeline from a tool-result turn.",
                    )
                secondary_system = merged_secondary_system_prompt(messages)
                history = (
                    compact_incoming_history(messages)
                    if SELF_ADVERSARIAL_MODE
                    else strip_secondary_system_messages(messages)
                )
                tools = request_body.get("tools") if isinstance(request_body.get("tools"), list) else None
                tool_choice = request_body.get("tool_choice")
                usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                if CODE_DEBUGGING_MODE:
                    debugging_followup_run = _debugging_completed_run_for_history(history)
                    if debugging_followup_run is not None:
                        history = _debugging_followup_history(debugging_followup_run, history)
                    else:
                        initial_request = _debugging_initial_request(history)
                        debugging_run = _debugging_create_run(initial_request)
                        history = [{"role": "user", "content": initial_request}]

            if CODE_DEBUGGING_MODE and debugging_followup_run is not None:
                yield event({"role": "assistant"})
                followup_result: Optional[Dict[str, Any]] = None
                async for packet in self._run_stage_streamed(
                    history,
                    secondary_system,
                    "thesis",
                    usage,
                    tools=None,
                    tool_choice=None,
                    append=False,
                ):
                    kind = packet.get("kind")
                    if kind == "reasoning":
                        yield event({"reasoning_content": packet["text"]})
                    elif kind == "content":
                        yield event({"content": packet["text"]})
                    elif kind == "keepalive":
                        label = str(packet.get("event") or "backend.activity")
                        yield f": jack-keepalive {label}\n\n".encode("utf-8")
                    elif kind == "tool_calls":
                        raise HTTPException(
                            status_code=502,
                            detail="Completed Code Debugging follow-up attempted a tool call even though follow-up chat is tools-off.",
                        )
                    elif kind == "result":
                        followup_result = packet["data"]
                if followup_result is None:
                    raise HTTPException(status_code=502, detail="Completed Code Debugging follow-up produced no result")
                choice = (followup_result.get("choices") or [{}])[0] or {}
                yield event({}, str(choice.get("finish_reason") or "stop"))
                yield usage_event(usage_delta(usage, response_usage_baseline))
                yield b"data: [DONE]\n\n"
                return

            if SELF_ADVERSARIAL_MODE:
                yield event({"role": "assistant"})

                async def run_self_adversarial_stage(
                    stage_key: str, *, emit_content: bool, same_stage_resume: bool = False,
                ):
                    result: Optional[Dict[str, Any]] = None
                    mirrored_tool_indexes: set[int] = set()
                    stage_reasoning_started = False
                    stage_content_started = False

                    if stage_key == "extended_initial" and not same_stage_resume:
                        label = "DEEP RESEARCH STAGE 1 — THESIS" if ULTRA_MODE else "STAGE 1 PROPOSED RESPONSE"
                        yield event({"reasoning_content": f"\n[{label}]\n"})
                    elif stage_key in {"extended_reflection", "extended_synthesis"}:
                        yield event({"reasoning_content": f"\n===== JACK {STAGES[stage_key].name.upper()} =====\n"})

                    async for packet in self._run_stage_streamed(
                        history,
                        secondary_system,
                        stage_key,
                        usage,
                        tools=tools,
                        tool_choice=tool_choice,
                        append=False,
                        same_stage_resume=same_stage_resume,
                    ):
                        kind = packet.get("kind")
                        if kind == "reasoning":
                            if stage_key in {"extended_reflection", "extended_synthesis"} and not stage_reasoning_started:
                                stage_reasoning_started = True
                                yield event({"reasoning_content": "[NATIVE REASONING]\n"})
                            yield event({"reasoning_content": packet["text"]})
                        elif kind == "content":
                            if stage_key == "extended_initial":
                                if AGENTIC_MODE:
                                    # Agentic exposes the provisional answer on reasoning while
                                    # withholding authoritative content until XML commit.
                                    yield event({"reasoning_content": packet["text"]})
                                else:
                                    # Deep Research Thesis has zero answer authority, but its generated
                                    # plan is part of the live cognitive transaction. Stream it immediately
                                    # on reasoning_content rather than buffering it until EOS.
                                    if not stage_content_started:
                                        stage_content_started = True
                                        yield event({"reasoning_content": "\n[THESIS OUTPUT]\n"})
                                    yield event({"reasoning_content": packet["text"]})
                            elif AGENTIC_MODE:
                                if not stage_content_started:
                                    stage_content_started = True
                                    yield event({"reasoning_content": "\n[STAGE 2 JACK XML GENERATION]\n"})
                                yield event({"reasoning_content": packet["text"]})
                            elif ULTRA_MODE and stage_key == "extended_reflection":
                                # Antithesis is advisory and non-authoritative, but it should still be
                                # observable token-by-token while it is being generated.
                                if not stage_content_started:
                                    stage_content_started = True
                                    yield event({"reasoning_content": "\n[ANTITHESIS OUTPUT]\n"})
                                yield event({"reasoning_content": packet["text"]})
                            elif ULTRA_MODE and stage_key == "extended_synthesis":
                                # Synthesis is Deep Research's sole authoritative response stage.
                                # Forward its answer deltas immediately as normal content so a client
                                # actually sees the response being generated instead of receiving one
                                # buffered block after EOS.
                                yield event({"content": packet["text"]})
                        elif kind == "tool_calls":
                            if ULTRA_MODE and stage_key in {"extended_initial", "extended_reflection"}:
                                # No tool authority: retain only for deterministic in-stage rejection.
                                pass
                            elif stage_key == "extended_initial" or (ULTRA_MODE and stage_key == "extended_synthesis"):
                                # Governed tool-enabled stages buffer executable calls until the full call
                                # is reconstructed and schema-validated. Tool-generation text remains observable.
                                calls = packet.get("tool_calls") or []
                                for call in calls:
                                    if not isinstance(call, dict):
                                        continue
                                    raw_index = call.get("index", 0)
                                    try:
                                        index = int(raw_index)
                                    except (TypeError, ValueError):
                                        index = 0
                                    if index not in mirrored_tool_indexes:
                                        mirrored_tool_indexes.add(index)
                                        function = call.get("function") if isinstance(call.get("function"), dict) else {}
                                        name = str(function.get("name") or "tool")
                                        label = "STAGE 1" if stage_key == "extended_initial" else "SYNTHESIS"
                                        yield event({"reasoning_content": f"\n[{label} TOOL GENERATION: {name}]\n"})
                                    function = call.get("function") if isinstance(call.get("function"), dict) else {}
                                    arguments = function.get("arguments")
                                    if arguments is not None:
                                        text = str(arguments)
                                        if text:
                                            yield event({"reasoning_content": text})
                            else:
                                yield event({"tool_calls": packet["tool_calls"]})
                        elif kind == "keepalive":
                            label = str(packet.get("event") or "backend.activity")
                            yield f": jack-keepalive {label}\n\n".encode("utf-8")
                        elif kind == "result":
                            result = packet["data"]
                    if result is None:
                        raise HTTPException(status_code=502, detail=f"Self-adversarial stage {stage_key} produced no result")
                    self_adversarial_results[stage_key] = result

                self_adversarial_results: Dict[str, Dict[str, Any]] = {}
                if AGENTIC_MODE:
                    sequence = [("extended_initial", False), ("extended_reflection", False)]
                else:
                    if resume_stage_key == "extended_synthesis":
                        sequence = [("extended_synthesis", False)]
                    else:
                        sequence = [("extended_initial", False), ("extended_reflection", False), ("extended_synthesis", False)]

                agentic_frozen_stage1_answer: Optional[str] = None

                for stage_key, emit_content in sequence:
                    if (
                        ULTRA_MODE
                        and stage_key in {"extended_reflection", "extended_synthesis"}
                        and resume_stage_key != stage_key
                    ):
                        _append_ultra_stage_generation_trigger(history, stage_key)
                    try:
                        async for wire in run_self_adversarial_stage(
                            stage_key,
                            emit_content=emit_content,
                            same_stage_resume=(resume_stage_key == stage_key),
                        ):
                            yield wire
                    except Exception as exc:
                        if AGENTIC_MODE and stage_key == "extended_reflection" and agentic_frozen_stage1_answer is not None:
                            detail = str(exc.detail) if isinstance(exc, HTTPException) else f"{type(exc).__name__}: {exc}"
                            degraded = self._agentic_degraded_result(history, usage, agentic_frozen_stage1_answer, detail)
                            if pending_state is not None:
                                await self._retire_pending_tool_resume(pending_state)
                            yield event({"reasoning_content": "\n" + (degraded.reasoning_content or "") + "\n"})
                            yield event({"content": degraded.content or ""})
                            yield event({}, "stop")
                            yield usage_event(usage_delta(usage, response_usage_baseline))
                            yield b"data: [DONE]\n\n"
                            return
                        raise
                    stage_result = self_adversarial_results[stage_key]
                    if self._tool_interrupt(stage_result, usage):
                        if AGENTIC_MODE and stage_key == "extended_reflection":
                            raise HTTPException(status_code=502, detail="Agentic Stage 2 attempted a tool call even though XML-stage tools are disabled")
                        if ULTRA_MODE and stage_key == "extended_initial":
                            raise HTTPException(status_code=502, detail="Deep Research Thesis attempted a tool call even though the non-executing Thesis stage has tools disabled")
                        if ULTRA_MODE and stage_key == "extended_reflection":
                            raise HTTPException(status_code=502, detail="Deep Research Antithesis attempted a tool call even though tools are disabled")
                        await self._register_stage_tool_resume(
                            stage_key=stage_key,
                            history=history,
                            secondary_system=secondary_system,
                            usage=usage,
                            tools=tools,
                            tool_choice=tool_choice,
                            data=stage_result,
                        )
                        if pending_state is not None and resume_stage_key == stage_key:
                            await self._retire_pending_tool_resume(pending_state)
                        calls = (((stage_result.get("choices") or [{}])[0].get("message") or {}).get("tool_calls") or [])
                        if calls and (
                            stage_key in {"extended_initial", "extended_synthesis"}
                            or not stage_result.get("_jack_tool_call_fragments_streamed")
                        ):
                            wire_calls = []
                            for index, call in enumerate(calls):
                                item = copy.deepcopy(call)
                                if isinstance(item, dict):
                                    item["index"] = index
                                wire_calls.append(item)
                            yield event({"tool_calls": wire_calls})
                        yield event({}, "tool_calls")
                        yield usage_event(usage_delta(usage, response_usage_baseline))
                        yield b"data: [DONE]\n\n"
                        return

                    if stage_key == "extended_initial":
                        first_msg = ((stage_result.get("choices") or [{}])[0].get("message") or {})
                        if ULTRA_MODE:
                            append_extended_candidate_response(history, first_msg)
                            yield event({"reasoning_content": "\n[END DEEP RESEARCH STAGE 1 — THESIS COMPLETE]\n"})
                        else:
                            agentic_frozen_stage1_answer = append_extended_candidate_response(history, first_msg)
                            yield event({"reasoning_content": "\n[END STAGE 1 — A1 FROZEN]\n"})
                    elif ULTRA_MODE and stage_key == "extended_reflection":
                        anti_msg = ((stage_result.get("choices") or [{}])[0].get("message") or {})
                        append_ultra_intermediate_response(history, "extended_reflection", anti_msg)
                        yield event({"reasoning_content": "\n[END DEEP RESEARCH STAGE 2 — ANTITHESIS COMPLETE]\n"})

                final_result = self_adversarial_results["extended_synthesis"] if ULTRA_MODE else self_adversarial_results["extended_reflection"]
                choice = (final_result.get("choices") or [{}])[0] or {}
                if ULTRA_MODE:
                    held_result = final_result
                    held_choice = choice
                    held_answer = self._required_completed_answer_from_stage(
                        held_result, "Deep Research Synthesis"
                    )
                    held_msg = (
                        (held_result.get("choices") or [{}])[0].get("message") or {}
                    )

                    clean_history = _ultra_history_without_held_synthesis(history)
                    _archive_extended_forensic(clean_history, held_msg, held_answer)
                    if pending_state is not None and resume_stage_key == "extended_synthesis":
                        await self._retire_pending_tool_resume(pending_state)
                    yield event({"reasoning_content": "\n[END DEEP RESEARCH STAGE 3 — SYNTHESIS COMPLETE]\n"})
                    # Synthesis content was already forwarded token-by-token by the streaming
                    # stage runner. Do not emit the reconstructed answer again at EOS.
                    yield event({}, str(held_choice.get("finish_reason") or "stop"))
                    yield usage_event(usage_delta(usage, response_usage_baseline))
                    yield b"data: [DONE]\n\n"
                    return

                # AGENTIC (3.6+ REQUIRED) COMMIT BOUNDARY: A1 was frozen at Stage 1.
                # Stage 2 has now reviewed the complete Stage-1 trajectory under
                # Preserve Thinking and emitted Jack XML only. No answer rewrite exists.
                try:
                    final_msg = ((final_result.get("choices") or [{}])[0].get("message") or {})
                    stage2_reasoning = (
                        final_msg.get("_jack_stage2_reasoning_trace")
                        or final_msg.get("reasoning_content")
                        or final_msg.get("reasoning")
                        or final_msg.get("thinking")
                        or ""
                    )
                    frozen_jack_xml = self._exact_frozen_answer_from_stage(final_result, "Agentic Stage 2 Jack XML")
                    if agentic_frozen_stage1_answer is None:
                        raise HTTPException(status_code=500, detail="Agentic Stage-1 frozen answer was unavailable at commit")
                    committed_output = f"{freeze_xml_stage_output(frozen_jack_xml)}\n\n{agentic_frozen_stage1_answer}"
                    _archive_agentic_stage1_forensic(
                        history, agentic_frozen_stage1_answer, freeze_xml_stage_output(frozen_jack_xml)
                    )
                    history.clear()
                except Exception as exc:
                    if agentic_frozen_stage1_answer is None:
                        raise
                    detail = str(exc.detail) if isinstance(exc, HTTPException) else f"{type(exc).__name__}: {exc}"
                    degraded = self._agentic_degraded_result(history, usage, agentic_frozen_stage1_answer, detail)
                    if pending_state is not None:
                        await self._retire_pending_tool_resume(pending_state)
                    yield event({"reasoning_content": "\n" + (degraded.reasoning_content or "") + "\n"})
                    yield event({"content": degraded.content or ""})
                    yield event({}, "stop")
                    yield usage_event(usage_delta(usage, response_usage_baseline))
                    yield b"data: [DONE]\n\n"
                    return
                if pending_state is not None:
                    await self._retire_pending_tool_resume(pending_state)
                yield event({"reasoning_content": "\n[END AGENTIC STAGE 2 — JACK XML COMPLETE; A1 COMMIT]\n"})
                yield event({"content": committed_output})
                yield event({}, "stop")
                yield usage_event(usage_delta(usage, response_usage_baseline))
                yield b"data: [DONE]\n\n"
                return

            if CODE_DEBUGGING_MODE:
                if debugging_run is None:
                    raise HTTPException(status_code=500, detail="Code Debugging run state was not initialized.")

                # Pre-pass diagnostic intake is intentionally outside Pass 1..5.
                # The user's supplied message is already sufficient intake. Optional
                # conversation may add diagnostic context, but it must never become a
                # prerequisite for starting the forensic passes.
                if not debugging_run.intake_frozen:
                    intake_proceed = bool(
                        pending_debugging_intake_state is not None
                        and history
                        and isinstance(history[-1], dict)
                        and history[-1].get("_jack_debugging_intake_proceed")
                    )
                    if intake_proceed:
                        resumed_user_text = _content_to_text(history[-1].get("content")).strip()
                        if resumed_user_text:
                            _debugging_append_intake_turn(debugging_run, "user", resumed_user_text)
                        _debugging_freeze_intake(debugging_run)
                        await self._retire_pending_debugging_intake_resume(pending_debugging_intake_state)
                        pending_debugging_intake_state = None
                        yield event({"role": "assistant"})
                        yield event({"reasoning_content": "\n[DEBUGGING DIAGNOSTIC INTAKE FROZEN — STARTING FRESH PASS 1]\n"})
                    else:
                        intake_result: Optional[Dict[str, Any]] = None
                        intake_prefix = _DEBUGGING_INTAKE_COMPLETE_PREFIX
                        intake_probe = ""
                        intake_content_classified: Optional[bool] = None
                        yield event({"role": "assistant"})
                        async for packet in self._run_stage_streamed(
                            history,
                            secondary_system,
                            "debug_intake",
                            usage,
                            tools=None,
                            tool_choice=None,
                            append=False,
                            same_stage_resume=(pending_debugging_intake_state is not None),
                        ):
                            kind = packet.get("kind")
                            if kind == "reasoning":
                                # Intake is a normal thinking stage. Native reasoning is
                                # observable token-by-token just like the other Jack stages.
                                yield event({"reasoning_content": packet["text"]})
                            elif kind == "content":
                                # Hold only enough leading content to hide Jack's internal
                                # completion prefix. Once classified, public intake output
                                # is forwarded token-by-token without EOS buffering.
                                text = str(packet.get("text") or "")
                                if intake_content_classified is None:
                                    intake_probe += text
                                    stripped = intake_probe.lstrip()
                                    if intake_prefix.startswith(stripped) and len(stripped) < len(intake_prefix):
                                        continue
                                    if stripped.startswith(intake_prefix):
                                        intake_content_classified = True
                                        remainder = stripped[len(intake_prefix):].lstrip()
                                        intake_probe = ""
                                        if remainder:
                                            yield event({"content": remainder})
                                    else:
                                        intake_content_classified = False
                                        if intake_probe:
                                            yield event({"content": intake_probe})
                                        intake_probe = ""
                                elif text:
                                    yield event({"content": text})
                            elif kind == "keepalive":
                                label = str(packet.get("event") or "backend.activity")
                                yield f": qwen-keepalive {label}\n\n".encode("utf-8")
                            elif kind == "tool_calls":
                                raise HTTPException(status_code=502, detail="Code Debugging pre-pass intake attempted a tool call even though intake tools are disabled.")
                            elif kind == "result":
                                intake_result = packet["data"]
                        if intake_probe:
                            yield event({"content": intake_probe})
                        if intake_result is None:
                            raise HTTPException(status_code=502, detail="Code Debugging pre-pass intake produced no result")

                        if not _debugging_intake_complete_from_result(intake_result):
                            if pending_debugging_intake_state is not None and history and isinstance(history[-1], dict):
                                resumed_user_text = _content_to_text(history[-1].get("content")).strip()
                                if resumed_user_text:
                                    _debugging_append_intake_turn(debugging_run, "user", resumed_user_text)
                            await self._register_debugging_intake_resume(
                                run=debugging_run,
                                history=history,
                                secondary_system=secondary_system,
                                usage=usage,
                                tools=tools,
                                tool_choice=tool_choice,
                                data=intake_result,
                            )
                            if pending_debugging_intake_state is not None:
                                await self._retire_pending_debugging_intake_resume(pending_debugging_intake_state)
                                pending_debugging_intake_state = None
                            # Model content and reasoning were already streamed live. Add
                            # only the host-owned primary-directive reminder at EOS.
                            yield event({"content": f"\n\n{_DEBUGGING_INTAKE_PRIMARY_DIRECTIVE_REMINDER}"})
                            yield event({}, "stop")
                            yield usage_event(usage_delta(usage, response_usage_baseline))
                            yield b"data: [DONE]\n\n"
                            return

                        if pending_debugging_intake_state is not None and history and isinstance(history[-1], dict):
                            resumed_user_text = _content_to_text(history[-1].get("content")).strip()
                            if resumed_user_text:
                                _debugging_append_intake_turn(debugging_run, "user", resumed_user_text)
                        _debugging_freeze_intake(debugging_run)
                        if pending_debugging_intake_state is not None:
                            await self._retire_pending_debugging_intake_resume(pending_debugging_intake_state)
                            pending_debugging_intake_state = None
                        yield event({"reasoning_content": "\n[DEBUGGING DIAGNOSTIC INTAKE FROZEN — STARTING FRESH PASS 1]\n"})

                    history = []
                    resume_stage_key = None
                    pending_state = None
                    pending_debugging_user_state = None

                debug_tools, debug_tool_choice = _debugging_report_only_tool_surface(tools, tool_choice)
                if pending_state is None and pending_debugging_user_state is None:
                    start_pass = 1
                else:
                    resumed_pass = _debugging_pass_from_stage_key(resume_stage_key or "")
                    if resumed_pass is None:
                        raise HTTPException(status_code=500, detail="Invalid Code Debugging pending stage")
                    start_pass = resumed_pass

                yield event({"role": "assistant"})
                for pass_number in range(start_pass, DEBUGGING_PASS_COUNT + 1):
                    stage_key = _debugging_stage_key(pass_number)
                    same_stage_resume = bool(resume_stage_key == stage_key)
                    pass_history = history if same_stage_resume else _debugging_fresh_pass_history(debugging_run, pass_number)
                    yield event({"reasoning_content": f"\n===== JACK CODE DEBUGGING PASS {pass_number} =====\n"})
                    stage_result: Optional[Dict[str, Any]] = None
                    async for packet in self._run_stage_streamed(
                        pass_history,
                        secondary_system,
                        stage_key,
                        usage,
                        tools=debug_tools,
                        tool_choice=debug_tool_choice,
                        append=False,
                        same_stage_resume=same_stage_resume,
                    ):
                        kind = packet.get("kind")
                        if kind == "reasoning":
                            yield event({"reasoning_content": packet["text"]})
                        elif kind == "content":
                            yield event({"reasoning_content": packet["text"]})
                        elif kind == "tool_calls":
                            yield event({"tool_calls": packet["tool_calls"]})
                        elif kind == "keepalive":
                            label = str(packet.get("event") or "backend.activity")
                            yield f": qwen-keepalive {label}\n\n".encode("utf-8")
                        elif kind == "result":
                            stage_result = packet["data"]

                    if stage_result is None:
                        raise HTTPException(status_code=502, detail=f"Code Debugging Pass {pass_number} produced no result")
                    if self._tool_interrupt(stage_result, usage):
                        await self._register_stage_tool_resume(
                            stage_key=stage_key,
                            history=pass_history,
                            secondary_system=secondary_system,
                            usage=usage,
                            tools=debug_tools,
                            tool_choice=debug_tool_choice,
                            data=stage_result,
                            debugging_run_id=debugging_run.run_id,
                        )
                        if same_stage_resume and pending_state is not None:
                            await self._retire_pending_tool_resume(pending_state)
                        if same_stage_resume and pending_debugging_user_state is not None:
                            await self._retire_pending_debugging_user_resume(pending_debugging_user_state)
                            pending_debugging_user_state = None
                        calls = (((stage_result.get("choices") or [{}])[0].get("message") or {}).get("tool_calls") or [])
                        if calls and not stage_result.get("_jack_tool_call_fragments_streamed"):
                            wire_calls = []
                            for index, call in enumerate(calls):
                                item = copy.deepcopy(call)
                                if isinstance(item, dict):
                                    item["index"] = index
                                wire_calls.append(item)
                            yield event({"tool_calls": wire_calls})
                        yield event({}, "tool_calls")
                        yield usage_event(usage_delta(usage, response_usage_baseline))
                        yield b"data: [DONE]\n\n"
                        return

                    question = _debugging_user_question_from_result(stage_result)
                    if question is not None:
                        paused = await self._register_debugging_user_resume(
                            stage_key=stage_key,
                            history=pass_history,
                            secondary_system=secondary_system,
                            usage=usage,
                            tools=debug_tools,
                            tool_choice=debug_tool_choice,
                            data=stage_result,
                            question=question,
                            debugging_run_id=debugging_run.run_id,
                        )
                        if same_stage_resume and pending_state is not None:
                            await self._retire_pending_tool_resume(pending_state)
                        if same_stage_resume and pending_debugging_user_state is not None:
                            await self._retire_pending_debugging_user_resume(pending_debugging_user_state)
                            pending_debugging_user_state = None
                        yield event({"content": paused.content or ""})
                        yield event({}, "stop")
                        yield usage_event(usage_delta(usage, response_usage_baseline))
                        yield b"data: [DONE]\n\n"
                        return

                    _debugging_commit_pass_summary(debugging_run, pass_number, stage_result)
                    if same_stage_resume and pending_state is not None:
                        await self._retire_pending_tool_resume(pending_state)
                    if same_stage_resume and pending_debugging_user_state is not None:
                        await self._retire_pending_debugging_user_resume(pending_debugging_user_state)
                        pending_debugging_user_state = None
                    yield event({"reasoning_content": f"\n[DEBUGGING PASS {pass_number} SUMMARY COMMITTED — FRESH CONTEXT NEXT PASS]\n"})
                    history = []
                    resume_stage_key = None

                yield event({"reasoning_content": "\n===== JACK CODE DEBUGGING FINAL REPORT =====\n"})
                summary_result: Optional[Dict[str, Any]] = None
                async for packet in self._run_stage_streamed(
                    _debugging_final_summary_history(debugging_run),
                    secondary_system,
                    "debug_summary",
                    usage,
                    tools=None,
                    tool_choice=None,
                    append=False,
                ):
                    kind = packet.get("kind")
                    if kind == "reasoning":
                        yield event({"reasoning_content": packet["text"]})
                    elif kind == "content":
                        yield event({"content": packet["text"]})
                    elif kind == "keepalive":
                        label = str(packet.get("event") or "backend.activity")
                        yield f": qwen-keepalive {label}\n\n".encode("utf-8")
                    elif kind == "tool_calls":
                        raise HTTPException(status_code=502, detail="Code Debugging final report attempted a tool call")
                    elif kind == "result":
                        summary_result = packet["data"]
                if summary_result is None:
                    raise HTTPException(status_code=502, detail="Code Debugging final report produced no result")
                _debugging_commit_final_report(debugging_run, summary_result)
                choice = (summary_result.get("choices") or [{}])[0] or {}
                yield event({}, str(choice.get("finish_reason") or "stop"))
                yield usage_event(usage_delta(usage, response_usage_baseline))
                yield b"data: [DONE]\n\n"
                return

            # Native control modes bypass Jack's staged cognition.
            # trace, deterministic commit wrapper, and Jack XML generation.
            if not AGENTIC_MODE:
                yield event({"role": "assistant"})
                native_result: Optional[Dict[str, Any]] = None
                async for packet in self._run_stage_streamed(
                    history,
                    secondary_system,
                    "thesis",
                    usage,
                    tools=tools,
                    tool_choice=tool_choice,
                    append=False,
                    same_stage_resume=(resume_stage_key == "thesis"),
                ):
                    kind = packet.get("kind")
                    if kind == "reasoning":
                        yield event({"reasoning_content": packet["text"]})
                    elif kind == "content":
                        yield event({"content": packet["text"]})
                    elif kind == "tool_calls":
                        yield event({"tool_calls": packet["tool_calls"]})
                    elif kind == "keepalive":
                        label = str(packet.get("event") or "backend.activity")
                        yield f": qwen-keepalive {label}\n\n".encode("utf-8")
                    elif kind == "result":
                        native_result = packet["data"]

                if native_result is None:
                    raise HTTPException(status_code=502, detail="Native Qwen completion produced no result")

                interrupted = self._tool_interrupt(native_result, usage)
                if interrupted:
                    await self._register_stage_tool_resume(
                        stage_key="thesis",
                        history=history,
                        secondary_system=secondary_system,
                        usage=usage,
                        tools=tools,
                        tool_choice=tool_choice,
                        data=native_result,
                    )
                    if pending_state is not None and resume_stage_key == "thesis":
                        await self._retire_pending_tool_resume(pending_state)
                    calls = (((native_result.get("choices") or [{}])[0].get("message") or {}).get("tool_calls") or [])
                    if calls and not native_result.get("_jack_tool_call_fragments_streamed"):
                        wire_calls = []
                        for index, call in enumerate(calls):
                            item = copy.deepcopy(call)
                            if isinstance(item, dict):
                                item["index"] = index
                            wire_calls.append(item)
                        yield event({"tool_calls": wire_calls})
                    yield event({}, "tool_calls")
                    yield usage_event(usage_delta(usage, response_usage_baseline))
                    yield b"data: [DONE]\n\n"
                    return

                if pending_state is not None and resume_stage_key == "thesis":
                    await self._retire_pending_tool_resume(pending_state)
                choice = (native_result.get("choices") or [{}])[0] or {}
                yield event({}, str(choice.get("finish_reason") or "stop"))
                yield usage_event(usage_delta(usage, response_usage_baseline))
                yield b"data: [DONE]\n\n"
                return



# ---------------------------------------------------------------------------
# OpenAI-compatible server surface
# ---------------------------------------------------------------------------


BACKEND = OpenAICompatibleBackend(CFG)
KERNEL = JackQwenKernel(BACKEND, CFG)


# ---------------------------------------------------------------------------
# Pi build-agent orchestration gateway
# ---------------------------------------------------------------------------

ORCHESTRATION_BASE_PATH = "/jack/orchestration"
_PI_CONTROL_CONFIG_ENV = "JACK_PI_CONTROL_CONFIG"
_PI_CONTROL_URL_ENV = "JACK_PI_CONTROL_URL"
_PI_CONTROL_TOKEN_ENV = "JACK_PI_CONTROL_TOKEN"
_ORCHESTRATION_REPLAY_ENV = "JACK_ORCHESTRATION_REPLAY_EVENTS"
_ORCHESTRATION_REPLAY_DEFAULT = 512


def _pi_control_config_path() -> Path:
    override = os.getenv(_PI_CONTROL_CONFIG_ENV, "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".pi" / "agent" / "jack-kernel.json"


def _load_pi_control_bridge() -> Dict[str, Any]:
    """Resolve Pi's existing local control bridge without exposing its token.

    Environment variables can override the local Pi configuration for testing.
    Otherwise Jack reads the same ``jack-kernel.json`` already used by the Pi
    control extension. Only ``controlPort`` and ``controlToken`` are consumed.
    """
    persisted: Dict[str, Any] = {}
    config_path = _pi_control_config_path()
    try:
        parsed = json.loads(config_path.read_text(encoding="utf-8-sig"))
        if isinstance(parsed, dict):
            persisted = parsed
    except (FileNotFoundError, OSError, ValueError):
        persisted = {}

    url = os.getenv(_PI_CONTROL_URL_ENV, "").strip().rstrip("/")
    if not url:
        raw_port = persisted.get("controlPort")
        try:
            control_port = int(raw_port)
        except (TypeError, ValueError):
            control_port = 0
        if 0 < control_port <= 65535:
            url = f"http://127.0.0.1:{control_port}"

    token = os.getenv(_PI_CONTROL_TOKEN_ENV, "") or str(persisted.get("controlToken") or "")
    return {
        "url": url,
        "token": token,
        "configured": bool(url and token),
        "config_path": str(config_path),
    }


def _require_pi_control_bridge() -> Tuple[str, str]:
    bridge = _load_pi_control_bridge()
    url = str(bridge.get("url") or "").rstrip("/")
    token = str(bridge.get("token") or "")
    if not url:
        raise HTTPException(status_code=503, detail="Pi control bridge URL is not configured")
    if not token:
        raise HTTPException(status_code=503, detail="Pi control bridge token is not configured")
    return url, token


def _pi_control_headers(
    token: str, *, content_type: Optional[str] = None, accept: Optional[str] = None
) -> Dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if content_type:
        headers["Content-Type"] = content_type
    if accept:
        headers["Accept"] = accept
    return headers


def _orchestration_public_base_from_agent_url(agent_base_url: str) -> str:
    root = str(agent_base_url or "").strip().rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3]
    return root.rstrip("/") + ORCHESTRATION_BASE_PATH


def _orchestration_url_from_cli_config(cfg: Dict[str, Any]) -> str:
    return _orchestration_public_base_from_agent_url(_effective_agent_base_url(cfg))


def _build_agent_bridge_display() -> str:
    bridge = _load_pi_control_bridge()
    url = str(bridge.get("url") or "")
    if not url:
        return "NOT CONFIGURED"
    return f"{url} [{'CONFIGURED' if bridge.get('configured') else 'TOKEN MISSING'}]"


def _downstream_pi_response(response: httpx.Response) -> Response:
    headers: Dict[str, str] = {}
    content_type = response.headers.get("content-type")
    if content_type:
        headers["content-type"] = content_type
    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=headers,
    )


async def _proxy_pi_control_request(
    request: Request,
    method: str,
    downstream_path: str,
    *,
    forward_body: bool = False,
) -> Response:
    """Proxy one orchestration control request to Pi outside inference concurrency.

    These requests intentionally do not enter Jack's model-inference semaphore.
    Pi may call Jack's normal /v1/chat/completions endpoint while the control
    request or SSE monitor remains active.
    """
    await enforce_kernel_auth(request)
    base_url, token = _require_pi_control_bridge()
    body = await request.body() if forward_body else b""
    content_type = (
        request.headers.get("content-type", "application/json")
        if forward_body
        else None
    )
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method,
                f"{base_url}{downstream_path}",
                content=body if forward_body else None,
                headers=_pi_control_headers(
                    token,
                    content_type=content_type,
                    accept="application/json",
                ),
            )
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
        raise HTTPException(status_code=502, detail="Pi control bridge is unavailable") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="Pi control bridge request failed") from exc
    return _downstream_pi_response(response)


def _utc_iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _orchestration_replay_limit() -> int:
    raw = os.getenv(_ORCHESTRATION_REPLAY_ENV, "").strip()
    try:
        value = int(raw) if raw else _ORCHESTRATION_REPLAY_DEFAULT
    except ValueError:
        value = _ORCHESTRATION_REPLAY_DEFAULT
    return max(32, min(value, 10000))


class OrchestrationEventHub:
    """Single Pi SSE ingestion path with run-bound Jack envelopes and replay.

    Pi's control bridge remains the authority for task/run attribution. Jack does
    not infer ownership from timing or from whichever task happens to be current.
    Untagged source events remain untagged except for Pi task/status snapshots whose
    own task ``id`` is authoritative.
    """

    def __init__(self, replay_limit: Optional[int] = None) -> None:
        from collections import deque
        self.replay_limit = int(replay_limit or _orchestration_replay_limit())
        self._buffer = deque(maxlen=self.replay_limit)
        self._seq = 0
        self._subscribers: set = set()
        self._lock = asyncio.Lock()
        self._runner: Optional[asyncio.Task] = None
        self._stopping = False
        self._last_error: Optional[str] = None

    async def close(self) -> None:
        self._stopping = True
        runner = self._runner
        if runner and not runner.done():
            runner.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await runner
        async with self._lock:
            subscribers = list(self._subscribers)
            self._subscribers.clear()
        for queue in subscribers:
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(None)

    async def probe(self) -> None:
        """Preserve v1 failure semantics before an SSE client is accepted."""
        base_url, token = _require_pi_control_bridge()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{base_url}/v1/status",
                    headers=_pi_control_headers(token, accept="application/json"),
                )
            if response.status_code >= 500:
                raise HTTPException(status_code=502, detail="Pi control bridge is unavailable")
            if response.status_code >= 400:
                raise HTTPException(status_code=response.status_code, detail=response.text)
        except HTTPException:
            raise
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
            raise HTTPException(status_code=502, detail="Pi control bridge is unavailable") from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Pi control bridge request failed") from exc

    async def ensure_running(self) -> None:
        if self._runner is None or self._runner.done():
            self._stopping = False
            self._runner = asyncio.create_task(self._run(), name="jack-orchestration-sse")

    async def subscribe(self, after_seq: Optional[int]) -> Tuple[asyncio.Queue, List[bytes]]:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1024)
        async with self._lock:
            replay: List[bytes] = []
            if after_seq is not None:
                oldest = self._buffer[0]["seq"] if self._buffer else self._seq + 1
                latest = self._buffer[-1]["seq"] if self._buffer else self._seq
                if after_seq < oldest - 1:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "error": "orchestration_replay_gap",
                            "requested_after": after_seq,
                            "oldest_available_seq": oldest,
                            "latest_seq": latest,
                        },
                    )
                replay = [self._encode_sse(event) for event in self._buffer if event["seq"] > after_seq]
            self._subscribers.add(queue)
        return queue, replay

    async def unsubscribe(self, queue: asyncio.Queue) -> None:
        async with self._lock:
            self._subscribers.discard(queue)

    @staticmethod
    def _encode_sse(event: Dict[str, Any]) -> bytes:
        encoded = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        return (
            f"id: {event['seq']}\n"
            f"event: {event['type']}\n"
            f"data: {encoded}\n\n"
        ).encode("utf-8")

    @staticmethod
    def _source_task_id(event_type: str, source_event: Any) -> Optional[str]:
        if isinstance(source_event, dict):
            task_id = source_event.get("task_id")
            if task_id:
                return str(task_id)
            if event_type == "task":
                data = source_event.get("data")
                if isinstance(data, dict) and data.get("id"):
                    return str(data["id"])
                if source_event.get("id"):
                    return str(source_event["id"])
            if event_type == "status" and source_event.get("id"):
                return str(source_event["id"])
        return None

    @staticmethod
    def _source_run_id(source_event: Any) -> Optional[str]:
        if not isinstance(source_event, dict):
            return None
        run_id = source_event.get("run_id")
        if run_id:
            return str(run_id)
        data = source_event.get("data")
        if isinstance(data, dict) and data.get("runId"):
            return str(data["runId"])
        if source_event.get("runId"):
            return str(source_event["runId"])
        return None

    @staticmethod
    def _source_run_epoch(source_event: Any) -> Optional[int]:
        if not isinstance(source_event, dict):
            return None
        value = source_event.get("run_epoch")
        if value is None:
            data = source_event.get("data")
            if isinstance(data, dict):
                value = data.get("runEpoch")
        if value is None:
            value = source_event.get("runEpoch")
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _source_attribution(source_event: Any) -> Optional[str]:
        if isinstance(source_event, dict) and source_event.get("attribution"):
            return str(source_event["attribution"])
        return None

    async def _publish(self, event_type: str, source_event: Any) -> None:
        if isinstance(source_event, dict) and "data" in source_event and "type" in source_event:
            payload = source_event.get("data")
            source_at = source_event.get("at")
            source_type = str(source_event.get("type") or event_type or "message")
        else:
            payload = source_event
            source_at = source_event.get("at") if isinstance(source_event, dict) else None
            source_type = str(event_type or "message")

        async with self._lock:
            self._seq += 1
            envelope: Dict[str, Any] = {
                "seq": self._seq,
                "task_id": self._source_task_id(source_type, source_event),
                "run_id": self._source_run_id(source_event),
                "run_epoch": self._source_run_epoch(source_event),
                "attribution": self._source_attribution(source_event),
                "type": source_type,
                "source": "pi",
                "source_at": source_at,
                "jack_received_at": _utc_iso_now(),
                "data": payload,
                "source_event": source_event,
            }
            self._buffer.append(envelope)
            encoded = self._encode_sse(envelope)
            subscribers = list(self._subscribers)

        for queue in subscribers:
            try:
                queue.put_nowait(encoded)
            except asyncio.QueueFull:
                # A lagging observer has lost continuity. End that stream so the
                # client must reconnect and recover by sequence number.
                await self.unsubscribe(queue)
                while not queue.empty():
                    with contextlib.suppress(asyncio.QueueEmpty):
                        queue.get_nowait()
                queue.put_nowait(None)

    async def _consume_stream(self, upstream: httpx.Response) -> None:
        event_name = "message"
        data_lines: List[str] = []
        async for line in upstream.aiter_lines():
            if self._stopping:
                return
            if line == "":
                if data_lines:
                    raw = "\n".join(data_lines)
                    try:
                        source_event: Any = json.loads(raw)
                    except ValueError:
                        source_event = {"raw": raw}
                    await self._publish(event_name, source_event)
                event_name = "message"
                data_lines = []
                continue
            if line.startswith(":"):
                continue
            if line.startswith("event:"):
                event_name = line[6:].strip() or "message"
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if data_lines:
            raw = "\n".join(data_lines)
            try:
                source_event = json.loads(raw)
            except ValueError:
                source_event = {"raw": raw}
            await self._publish(event_name, source_event)

    async def _run(self) -> None:
        while not self._stopping:
            try:
                base_url, token = _require_pi_control_bridge()
                async with httpx.AsyncClient(timeout=None) as client:
                    async with client.stream(
                        "GET",
                        f"{base_url}/v1/events",
                        headers=_pi_control_headers(token, accept="text/event-stream"),
                    ) as upstream:
                        if upstream.status_code != 200:
                            body = await upstream.aread()
                            self._last_error = f"Pi SSE status {upstream.status_code}: {body[:200]!r}"
                            await asyncio.sleep(1.0)
                            continue
                        self._last_error = None
                        await self._consume_stream(upstream)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._last_error = str(exc)
                if self._stopping:
                    return
                await asyncio.sleep(1.0)


ORCHESTRATION_EVENTS = OrchestrationEventHub()

@asynccontextmanager
async def app_lifespan(_: FastAPI):
    try:
        yield
    finally:
        await ORCHESTRATION_EVENTS.close()
        await BACKEND.close()


APP = FastAPI(title="Jack Kernel", version=PUBLIC_VERSION, lifespan=app_lifespan)


async def enforce_kernel_auth(request: Request) -> None:
    if not CFG.api_key:
        return
    auth = request.headers.get("authorization", "")
    if auth != f"Bearer {CFG.api_key}":
        raise HTTPException(status_code=401, detail="Invalid Jack Kernel API key")


def completion_envelope(result: KernelResult) -> Dict[str, Any]:
    now = int(time.time())
    response_id = f"chatcmpl-jack-{uuid.uuid4().hex}"
    message: Dict[str, Any] = {"role": "assistant", "content": result.content}
    if result.reasoning_content:
        message["reasoning_content"] = result.reasoning_content
    if result.tool_calls:
        message["tool_calls"] = result.tool_calls
    return {
        "id": response_id,
        "object": "chat.completion",
        "created": now,
        "model": CFG.virtual_model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": result.finish_reason,
            }
        ],
        "usage": result.usage,
    }


def _runtime_identity_details() -> Dict[str, Any]:
    if ULTRA_MODE:
        mode = "deep-research"
        flow = ["extended_initial", "extended_reflection", "extended_synthesis"]
        authoritative_stage = "extended_synthesis"
        retention_policy = (
            "preserve_all_through_synthesis_then_prune_stage1_stage2_reasoning_only_"
            "keep_outputs_tools_results_stage3_reasoning"
        )
    elif AGENTIC_MODE:
        mode = "agentic"
        flow = ["extended_initial", "extended_reflection"]
        authoritative_stage = "extended_initial"
        retention_policy = (
            "retain_completed_user_xml_frozen_a1_prune_historical_native_reasoning_"
            "and_consumed_tool_protocol"
        )
    elif CODE_DEBUGGING_MODE:
        mode = "code-debugging"
        flow = (
            ["debug_intake"]
            + [_debugging_stage_key(i) for i in range(1, DEBUGGING_PASS_COUNT + 1)]
            + ["debug_summary"]
        )
        authoritative_stage = "debug_summary"
        retention_policy = (
            "retain_user_pass0_and_committed_pass_summaries_fresh_context_per_pass"
        )
    else:
        mode = "native"
        flow = ["thesis"]
        authoritative_stage = "thesis"
        retention_policy = "caller_history_with_internal_tool_exchange_pruning"

    stage_controls: Dict[str, Dict[str, Any]] = {}
    for stage_key in flow:
        profile = STAGES[stage_key]
        stage_controls[stage_key] = {
            "name": profile.name,
            "thinking": bool(profile.thinking),
            "reasoning_effort": profile.reasoning_effort,
            "allow_tools": bool(profile.allow_tools),
            "temperature": profile.temperature,
            "force_preserve_thinking": bool(profile.force_preserve_thinking),
            "max_tokens": profile.max_tokens,
        }

    return {
        "reasoning_profile": "deep-research" if _reasoning_level == "ultra" else _reasoning_level,
        "mode": mode,
        "flow": flow,
        "authoritative_stage": authoritative_stage,
        "preserve_thinking": bool(CFG.preserve_thinking),
        "stage_controls": stage_controls,
        "context_policy": {
            "context_length": BACKEND.context_length,
            "context_length_source": BACKEND.context_length_source,
        },
        "retention_policy": retention_policy,
    }


@APP.get("/")
async def root() -> Dict[str, Any]:
    preset = BACKEND_PRESETS.get(CFG.backend_profile, BACKEND_PRESETS["custom"])
    return {
        "name": "Jack Kernel",
        "version": PUBLIC_VERSION,
        "runtime_artifact_sha256": RUNTIME_ARTIFACT_SHA256,
        "runtime_manifest_sha256": RUNTIME_MANIFEST_SHA256,
        "runtime_manifest_components": dict(RUNTIME_MANIFEST_COMPONENTS),
        "forensic_archive_mode": CFG.forensic_archive_mode,
        "runtime_identity": _runtime_identity_details(),
        "reasoning_level": ACTIVE_REASONING_PROFILE["label"],
        "backend_profile": CFG.backend_profile,
        "backend_name": preset["short_label"],
        "virtual_model": CFG.virtual_model,
        "agent_base_url": CFG.agent_base_url,
        "orchestration_base_url": _orchestration_public_base_from_agent_url(CFG.agent_base_url),
        "orchestration_protocol_version": 2,
        "orchestration_replay_events": ORCHESTRATION_EVENTS.replay_limit,
    }


@APP.get("/health")
async def health(request: Request) -> Dict[str, Any]:
    await enforce_kernel_auth(request)
    model = await BACKEND.resolve_model()
    preset = BACKEND_PRESETS.get(CFG.backend_profile, BACKEND_PRESETS["custom"])
    return {
        "status": "ok",
        "name": "Jack Kernel",
        "version": PUBLIC_VERSION,
        "runtime_artifact_sha256": RUNTIME_ARTIFACT_SHA256,
        "runtime_manifest_sha256": RUNTIME_MANIFEST_SHA256,
        "runtime_manifest_components": dict(RUNTIME_MANIFEST_COMPONENTS),
        "forensic_archive_mode": CFG.forensic_archive_mode,
        "runtime_identity": _runtime_identity_details(),
        "reasoning_level": ACTIVE_REASONING_PROFILE["label"],
        "backend_profile": CFG.backend_profile,
        "backend_name": preset["short_label"],
        "backend": CFG.backend_base_url,
        "backend_model": model,
        "virtual_model": CFG.virtual_model,
        "context_length": BACKEND.context_length,
        "context_length_source": BACKEND.context_length_source,
        "agent_base_url": CFG.agent_base_url,
        "orchestration_base_url": _orchestration_public_base_from_agent_url(CFG.agent_base_url),
        "orchestration_protocol_version": 2,
        "orchestration_replay_events": ORCHESTRATION_EVENTS.replay_limit,
        "build_agent_bridge_configured": bool(_load_pi_control_bridge().get("configured")),
        "listen_address": f"{CFG.host}:{CFG.port}",
    }


@APP.get(f"{ORCHESTRATION_BASE_PATH}/status")
async def orchestration_status(request: Request) -> Response:
    return await _proxy_pi_control_request(request, "GET", "/v1/status")


@APP.post(f"{ORCHESTRATION_BASE_PATH}/tasks")
async def orchestration_tasks(request: Request) -> Response:
    return await _proxy_pi_control_request(
        request, "POST", "/v1/tasks", forward_body=True
    )


@APP.post(f"{ORCHESTRATION_BASE_PATH}/tasks/cancel")
async def orchestration_cancel(request: Request) -> Response:
    return await _proxy_pi_control_request(request, "POST", "/v1/tasks/cancel")


@APP.post(f"{ORCHESTRATION_BASE_PATH}/session/new")
async def orchestration_new_session(request: Request) -> Response:
    return await _proxy_pi_control_request(request, "POST", "/v1/session/new")


@APP.get(f"{ORCHESTRATION_BASE_PATH}/events")
async def orchestration_events(request: Request):
    """Task-attributed, sequenced Pi SSE transport with bounded replay."""
    await enforce_kernel_auth(request)
    await ORCHESTRATION_EVENTS.probe()
    await ORCHESTRATION_EVENTS.ensure_running()

    after_raw = str(request.query_params.get("after") or "").strip()
    if not after_raw:
        after_raw = str(request.headers.get("last-event-id") or "").strip()
    after_seq: Optional[int] = None
    if after_raw:
        try:
            after_seq = int(after_raw)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="after/Last-Event-ID must be an integer") from exc
        if after_seq < 0:
            raise HTTPException(status_code=400, detail="after/Last-Event-ID must be non-negative")

    queue, replay = await ORCHESTRATION_EVENTS.subscribe(after_seq)

    async def relay() -> AsyncIterator[bytes]:
        try:
            for item in replay:
                yield item
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield b": keepalive\n\n"
                    continue
                if item is None:
                    return
                yield item
        finally:
            await ORCHESTRATION_EVENTS.unsubscribe(queue)

    return StreamingResponse(
        relay(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@APP.get("/jack/tool-evidence/{tool_call_id}")
async def jack_tool_evidence(tool_call_id: str, request: Request) -> Dict[str, Any]:
    """Read-only exact-key recovery of a retired Pi tool result.

    This endpoint is intentionally outside the model's ordinary tool surface.
    It performs no fuzzy/semantic search and is protected by Jack's API auth.
    """
    await enforce_kernel_auth(request)
    expected_sha256 = str(request.query_params.get("sha256") or "").strip() or None
    try:
        loop = asyncio.get_running_loop()
        evidence = await loop.run_in_executor(None, recover_pi_tool_evidence, tool_call_id, expected_sha256)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "status": "ok",
        "recovery_mode": "exact_tool_call_id",
        **evidence,
    }


@APP.get("/v1/models")
async def list_models(request: Request) -> Dict[str, Any]:
    await enforce_kernel_auth(request)
    # Resolve now so configuration errors are surfaced before the first chat and
    # so the loaded backend instance's context metadata is available to clients.
    backend_model = await BACKEND.resolve_model()
    context_length = int(BACKEND.context_length or 0)
    item: Dict[str, Any] = {
        "id": CFG.virtual_model,
        "object": "model",
        "created": int(time.time()),
        "owned_by": "jack-kernel",
        "backend_model": backend_model,
        "context_length_source": BACKEND.context_length_source,
    }
    if context_length > 0:
        # Different OpenAI-compatible clients use different metadata spellings.
        # Expose the same authoritative loaded-context value under the common
        # aliases without changing the caller-facing virtual model identity.
        item.update({
            "context_length": context_length,
            "context_window": context_length,
            "contextWindow": context_length,
            "max_context_length": context_length,
            "max_model_len": context_length,
        })
    return {"object": "list", "data": [item]}


@APP.get("/api/v1/models")
async def lmstudio_compatible_models(request: Request) -> Dict[str, Any]:
    """Expose Jack's virtual model using LM Studio's loaded-model metadata shape.

    Pi's pi-lmstudio extension discovers contextWindow from
    loaded_instances[0].config.context_length. Jack therefore projects the
    context length of the backend instance it actually resolved, rather than a
    guessed/static Pi-side value.
    """
    await enforce_kernel_auth(request)
    backend_model = await BACKEND.resolve_model()
    context_length = int(BACKEND.context_length or 0)
    if context_length <= 0:
        raise HTTPException(
            status_code=503,
            detail=(
                "Jack could not determine the backend context length. "
                "For LM Studio, ensure a single LLM is loaded so Jack can read "
                "loaded_instances[].config.context_length. For another backend, "
                "configure Backend context length explicitly."
            ),
        )

    return {
        "models": [
            {
                "type": "llm",
                "publisher": "jack-kernel",
                "key": CFG.virtual_model,
                "display_name": "Jack Kernel",
                "architecture": "jack-kernel-proxy",
                "size_bytes": 0,
                "params_string": None,
                "loaded_instances": [
                    {
                        "id": CFG.virtual_model,
                        "config": {
                            "context_length": context_length,
                            "eval_batch_size": 0,
                            "flash_attention": False,
                            "num_experts": 0,
                            "offload_kv_cache_to_gpu": False,
                        },
                    }
                ],
                # Pi's pi-lmstudio extension uses the loaded-instance context for
                # contextWindow and this field for its model maxTokens metadata.
                # Matching them mirrors LM Studio's own discovery contract.
                "max_context_length": context_length,
                "format": "jack-kernel",
                "capabilities": {
                    "trained_for_tool_use": True,
                },
                "description": f"Jack Kernel virtual model routed to {backend_model}",
                "variants": [],
                "selected_variant": "",
                "context_length_source": BACKEND.context_length_source,
            }
        ]
    }


async def _safe_public_stream(body: Dict[str, Any]) -> AsyncIterator[bytes]:
    """Convert internal stage failures into a clean OpenAI SSE termination."""
    try:
        async for chunk in KERNEL.stream(body):
            yield chunk
    except Exception as exc:
        LOG.exception("Jack streamed request failed; closing SSE cleanly")
        await KERNEL._rearm_pending_tool_resume_for_messages(body.get("messages"))
        await KERNEL._rearm_pending_debugging_resumes_for_messages(body.get("messages"))
        detail = str(exc.detail) if isinstance(exc, HTTPException) else f"{type(exc).__name__}: {exc}"
        response_id = f"chatcmpl-jack-error-{uuid.uuid4().hex}"
        created = int(time.time())

        def event(delta: Dict[str, Any], finish_reason: Optional[str] = None) -> bytes:
            obj = {
                "id": response_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": CFG.virtual_model,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
            }
            return ("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode("utf-8")

        if ULTRA_MODE:
            failure_text = (
                "\n\n[Jack Kernel Deep Research interrupted before authoritative Synthesis commit. "
                "Any preceding streamed Synthesis text is partial/uncommitted. Failure: " + detail[:1800] + "]"
            )
        else:
            failure_text = "\n\n[Jack Kernel internal stage failure: " + detail[:2000] + "]"
        yield event({"content": failure_text})
        yield event({}, "stop")
        yield b"data: [DONE]\n\n"
    finally:
        await KERNEL._rearm_pending_tool_resume_for_messages(body.get("messages"))
        await KERNEL._rearm_pending_debugging_resumes_for_messages(body.get("messages"))


@APP.post("/v1/chat/completions")
async def chat_completions(request: Request):
    await enforce_kernel_auth(request)
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON body: {exc}") from exc

    # Agent Authority Boundary. Reconstruct from the allowlist before deciding
    # transport behavior; cognition-control fields are ignored, never forwarded.
    body = sanitize_agent_request(body)

    if body.get("stream"):
        return StreamingResponse(
            _safe_public_stream(body),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    result = await KERNEL.run(body)
    return JSONResponse(completion_envelope(result))



# ---------------------------------------------------------------------------
# Interactive executable CLI
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Jack CLI branding
# ---------------------------------------------------------------------------

# Palette sampled from the supplied Jack logo: near-white chrome, ice blue,
# steel blue, and deep blue on black. ANSI color is best-effort; the CLI falls
# back cleanly to plain text when the host does not support VT sequences.
_JACK_ICE = (235, 246, 255)
_JACK_CHROME = (211, 229, 247)
_JACK_STEEL = (154, 190, 225)
_JACK_BLUE = (92, 137, 185)

DONATION_MESSAGE = (
    "Donations for Project Jack. (I need a DGX Spark :-)\n"
    "Bitcoin BTC: 3P94MYYpfMXKHa5pbkDUhVHtiFo79bvUg4\n"
    "Bittensor Tao: 5HL76hWWJP14Fi5JQo5yC8KT5NHzyJoZwhJDgcc6KQSPN2yQ"
)
CONTACT_MESSAGE = "Contact Me Mlangford75@protonmail.com"
_JACK_MUTED = (126, 151, 177)
_JACK_WHITE = (250, 253, 255)
_CLI_ANSI = False

# Terminal-native stepped rendering of the Jack "J" mark. The geometry follows
# the supplied pixel/block reference and uses only solid block cells so it stays
# stable across Windows Console, Windows Terminal, PowerShell, and PyInstaller.
_JACK_LOGO_LINES: List[Tuple[str, Tuple[int, int, int]]] = [
    (r"    ███████████████████████████████████", _JACK_CHROME),
    (r"    ███████████████████████████████████", _JACK_ICE),
    (r"                              ██████████", _JACK_STEEL),
    (r"                              ██████████", _JACK_CHROME),
    (r"                             ██████████", _JACK_STEEL),
    (r"                             ██████████", _JACK_BLUE),
    (r"                            ██████████", _JACK_STEEL),
    (r"                           ██████████", _JACK_CHROME),
    (r"        ██                ██████████", _JACK_ICE),
    (r"       ███               ██████████", _JACK_CHROME),
    (r"     █████              ██████████", _JACK_STEEL),
    (r"    ███████            ██████████", _JACK_BLUE),
    (r"    ███████          ███████████", _JACK_STEEL),
    (r"     ███████      █████████████", _JACK_CHROME),
    (r"      ████████████████████████", _JACK_ICE),
    (r"        ████████████████████", _JACK_STEEL),
    (r"           ███████████████", _JACK_BLUE),
]


def _enable_cli_branding() -> None:
    """Enable UTF-8/ANSI where possible and set the console title/background."""
    global _CLI_ANSI

    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ansi_requested = sys.stdout.isatty() and not os.getenv("NO_COLOR")

    if os.name == "nt":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleOutputCP(65001)
            kernel32.SetConsoleCP(65001)
            STD_OUTPUT_HANDLE = -11
            ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(
                    handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING
                )
                _CLI_ANSI = bool(ansi_requested)
            else:
                _CLI_ANSI = False
            kernel32.SetConsoleTitleW("Jack Kernel")
        except Exception:
            _CLI_ANSI = False
        # The supplied logo is silver/ice-blue on black. Setting a black console
        # background gives the closest stock-console presentation even when ANSI
        # truecolor is unavailable.
        try:
            os.system("color 0F >nul 2>&1")
        except Exception:
            pass
    else:
        _CLI_ANSI = bool(ansi_requested)


def _ansi_rgb(text: str, rgb: Tuple[int, int, int], *, bold: bool = False) -> str:
    if not _CLI_ANSI:
        return text
    r, g, b = rgb
    weight = "1;" if bold else ""
    return f"\x1b[{weight}38;2;{r};{g};{b}m{text}\x1b[0m"


def _clear_cli() -> None:
    if not sys.stdout.isatty():
        return
    if _CLI_ANSI:
        # Force the branded black field, then clear and home.
        print("\x1b[40m\x1b[2J\x1b[H", end="", flush=True)
    else:
        os.system("cls" if os.name == "nt" else "clear")


def _terminal_width(default: int = 88) -> int:
    try:
        return max(60, shutil.get_terminal_size((default, 24)).columns)
    except Exception:
        return default


def _center_plain(text: str, width: Optional[int] = None) -> str:
    width = width or _terminal_width()
    return text.center(width)


def _print_colored_logo(lines: List[Tuple[str, Tuple[int, int, int]]], *, center: bool) -> None:
    width = _terminal_width()
    rendered_lines = [(line.rstrip(), color) for line, color in lines]
    logo_width = max((len(line) for line, _ in rendered_lines), default=0)
    left_pad = max(0, (width - logo_width) // 2) if center else 0
    prefix = " " * left_pad
    for line, color in rendered_lines:
        # Center the logo canvas once, not each row independently. This keeps
        # stepped geometry aligned even when individual rows have different widths.
        print(_ansi_rgb(prefix + line, color, bold=True))


def _print_brand_block() -> None:
    """Render the single canonical Jack Kernel logo and identity block."""
    terminal_width = _terminal_width()
    print()
    _print_colored_logo(_JACK_LOGO_LINES, center=True)
    print()
    print(_ansi_rgb(_center_plain("J A C K   K E R N E L", terminal_width), _JACK_WHITE, bold=True))
    print(_ansi_rgb(_center_plain(PUBLIC_VERSION, terminal_width), _JACK_ICE, bold=True))
    print(_ansi_rgb(_center_plain("Jack Long-Horizon Cognition", terminal_width), _JACK_STEEL, bold=True))
    print(_ansi_rgb(_center_plain("Local Inference Runtime", terminal_width), _JACK_MUTED))
    print(_ansi_rgb(_center_plain(CONTACT_MESSAGE, terminal_width), _JACK_MUTED))
    print(_ansi_rgb(_center_plain("Qwen edition", terminal_width), _JACK_BLUE))


def _show_brand_intro() -> bool:
    """Show the complete Jack identity block for three seconds.

    The first main-screen render then appends status/menu content underneath this
    existing block without clearing or drawing the logo a second time.
    """
    if not sys.stdout.isatty() or os.getenv("JACK_NO_SPLASH", "0") == "1":
        return False
    _clear_cli()
    _print_brand_block()
    sys.stdout.flush()
    time.sleep(3.0)
    return True


def _status_value(label: str, value: str, *, width: int = 21) -> str:
    plain_label = f"{label:<{width}}"
    return f"{_ansi_rgb(plain_label, _JACK_MUTED)}{_ansi_rgb(value, _JACK_CHROME, bold=True)}"

CLI_DEFAULTS: Dict[str, Any] = {
    "config_schema_version": CONFIG_SCHEMA_VERSION,
    "backend_profile": "lmstudio",
    "backend_base_url": "http://127.0.0.1:1234/v1",
    "backend_model": "",
    "backend_auth_mode": "none",
    "backend_api_key": "",
    "backend_header_name": "",
    "backend_header_value": "",
    "backend_username": "",
    "backend_password": "",
    "backend_authorization_value": "",
    "backend_extra_headers": {},
    "host": "127.0.0.1",
    "port": 8001,
    "agent_base_url": "",
    "api_key": "",
    "virtual_model": "jack-kernel",
    "reasoning_level": "x-high",
    "preserve_thinking": True,
    "backend_timeout_seconds": 1800.0,
    "backend_context_length": 0,
    "max_concurrent_requests": 1,
    "seed": "",
    "qwen_control_shape": "template_kwargs",
    "log_level": "INFO",
    "log_reasoning": False,
    "forensic_archive_mode": "stage",
    "forensic_archive_dir": "",
    "thinking_temperature": 1.0,
    "thinking_top_p": 0.95,
    "thinking_top_k": 20,
    "thinking_min_p": 0.0,
    "thinking_presence_penalty": 0.0,
    "thinking_repeat_penalty": 1.0,
    "nonthinking_temperature": 0.7,
    "nonthinking_top_p": 0.80,
    "nonthinking_top_k": 20,
    "nonthinking_min_p": 0.0,
    "nonthinking_presence_penalty": 1.5,
    "nonthinking_repeat_penalty": 1.0,
}


def _config_dir() -> Path:
    if os.name == "nt":
        base = os.getenv("APPDATA")
        if base:
            return Path(base) / "JackKernel"
    return Path.home() / ".jack-kernel"

def _legacy_config_dir() -> Path:
    if os.name == "nt":
        base = os.getenv("APPDATA")
        if base:
            return Path(base) / "JackKernelLMStudio"
    return Path.home() / ".jack-kernel-lm-studio"

def _config_paths() -> Tuple[Path, Path]:
    root = _config_dir()
    return root / "config.json", root / "secondary_system_prompt.txt"


def _load_cli_config() -> Dict[str, Any]:
    config_path, _ = _config_paths()
    cfg = copy.deepcopy(CLI_DEFAULTS)
    source_path = config_path
    if not source_path.exists():
        legacy = _legacy_config_dir() / "config.json"
        if legacy.exists():
            source_path = legacy
    try:
        loaded = json.loads(source_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            prior_schema = str(loaded.get("config_schema_version") or "")
            if prior_schema != str(CONFIG_SCHEMA_VERSION):
                # Normalize an unpinned generated listener default to Jack's
                # :8001 frontend so a local vLLM backend may use :8000.
                if (
                    int(loaded.get("port", 8000) or 8000) == 8000
                    and not str(loaded.get("agent_base_url") or "").strip()
                ):
                    loaded["port"] = 8001
                loaded["config_schema_version"] = CONFIG_SCHEMA_VERSION
            # Normalize compatible saved configuration into the active backend schema.
            loaded.setdefault("backend_profile", "lmstudio")
            if "backend_base_url" not in loaded and loaded.get("lmstudio_base_url"):
                loaded["backend_base_url"] = loaded.get("lmstudio_base_url")
            if "backend_api_key" not in loaded and loaded.get("lmstudio_api_key"):
                loaded["backend_api_key"] = loaded.get("lmstudio_api_key")
                loaded.setdefault("backend_auth_mode", "bearer")
            for key in cfg:
                if key in loaded:
                    cfg[key] = loaded[key]
            cfg["backend_profile"] = _normalize_backend_profile(str(cfg.get("backend_profile", "lmstudio")))
            legacy_reasoning = str(cfg.get("reasoning_level", "x-high")).strip().lower()
            migrated_reasoning = _REASONING_LEVEL_ALIASES.get(legacy_reasoning, legacy_reasoning)
            if migrated_reasoning == "low":
                # Low is disabled; map it to Medium when loading saved configuration.
                migrated_reasoning = "medium"
            if migrated_reasoning in REASONING_PROFILES and not REASONING_PROFILES[migrated_reasoning].get("disabled"):
                cfg["reasoning_level"] = migrated_reasoning
            # Jack stages require assistant-role history, so LM Studio uses the
            # OpenAI-compatible chat-completions transport with template kwargs.
            if cfg["backend_profile"] == "lmstudio" and cfg.get("qwen_control_shape") in {
                "native_off", "template_kwargs", "hybrid", "top_level"
            }:
                cfg["qwen_control_shape"] = "template_kwargs"
    except FileNotFoundError:
        pass
    except Exception as exc:
        print(f"Warning: could not read {source_path}: {exc}")

    # Startup invariant: every new launcher session begins on X-High.
    # A user may select Deep Research, Agentic, or either Code Debugging profile for the current session before starting
    # the server, but a prior saved reasoning selection never changes startup.
    cfg["reasoning_level"] = "x-high"

    # LM Studio model identity is runtime state, not durable launcher state. A
    # model saved in yesterday's config must never be presented or reused as if
    # it were the model currently loaded in memory. Each fresh LM Studio launcher
    # session returns to loaded-model AUTO-DETECT; an explicit selection may still
    # be made for the current session and is verified before inference.
    if _normalize_backend_profile(str(cfg.get("backend_profile") or "lmstudio")) == "lmstudio":
        cfg["backend_model"] = ""
    return cfg


def _save_cli_config(cfg: Dict[str, Any]) -> None:
    config_path, prompt_path = _config_paths()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    safe = {k: cfg[k] for k in CLI_DEFAULTS if k in cfg}
    config_path.write_text(
        json.dumps(safe, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if not prompt_path.exists():
        prompt_path.write_text("", encoding="utf-8")


def _load_cli_secondary_prompt() -> str:
    _, prompt_path = _config_paths()
    source = prompt_path
    if not source.exists():
        legacy = _legacy_config_dir() / "secondary_system_prompt.txt"
        if legacy.exists():
            source = legacy
    try:
        return source.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except Exception as exc:
        print(f"Warning: could not read {source}: {exc}")
        return ""


def _save_cli_secondary_prompt(text: str) -> None:
    _, prompt_path = _config_paths()
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(text.rstrip() + ("\n" if text.strip() else ""), encoding="utf-8")


class _ReturnToMainMenu(Exception):
    """Internal CLI control flow raised when the user presses Esc."""


_CLI_BACK_COMMANDS = {":back", ":esc"}


def _cli_input(prompt: str = "", *, secret: bool = False) -> str:
    """Read one CLI line and allow immediate Esc-to-main-menu on Windows.

    On non-Windows terminals the typed commands ``:back`` and ``:esc`` provide
    the same escape path.  Secret entry is not echoed.
    """
    if os.name == "nt" and sys.stdin.isatty() and sys.stdout.isatty():
        import msvcrt

        if prompt:
            sys.stdout.write(prompt)
            sys.stdout.flush()
        chars: List[str] = []
        while True:
            ch = msvcrt.getwch()
            if ch == "\x1b":  # Escape
                sys.stdout.write("\n")
                sys.stdout.flush()
                raise _ReturnToMainMenu()
            if ch == "\x03":  # Ctrl+C
                raise KeyboardInterrupt
            if ch in {"\r", "\n"}:
                sys.stdout.write("\n")
                sys.stdout.flush()
                raw = "".join(chars)
                if raw.strip().lower() in _CLI_BACK_COMMANDS:
                    raise _ReturnToMainMenu()
                return raw
            if ch in {"\x00", "\xe0"}:  # Function/arrow key prefix.
                msvcrt.getwch()
                continue
            if ch in {"\x08", "\x7f"}:  # Backspace.
                if chars:
                    chars.pop()
                    if not secret:
                        sys.stdout.write("\b \b")
                        sys.stdout.flush()
                continue
            if ch.isprintable():
                chars.append(ch)
                if not secret:
                    sys.stdout.write(ch)
                    sys.stdout.flush()
    else:
        raw = getpass.getpass(prompt) if secret else input(prompt)
        if raw.strip().lower() in _CLI_BACK_COMMANDS:
            raise _ReturnToMainMenu()
        return raw


def _print_back_hint() -> None:
    print(_ansi_rgb("Esc", _JACK_ICE, bold=True) + "  Return to main menu" + _ansi_rgb("   (:back also works)", _JACK_MUTED))
    print()


def _run_transactional_editor(editor: Any, cfg: Dict[str, Any]) -> None:
    """Commit submenu edits only if the user completes the submenu."""
    candidate = copy.deepcopy(cfg)
    editor(candidate)
    cfg.clear()
    cfg.update(candidate)


def _prompt_value(label: str, current: Any, cast=str, *, allow_empty: bool = False) -> Any:
    raw = _cli_input(f"{label} [{current}]: ").strip()
    if not raw:
        return current
    if allow_empty and raw.lower() in {"none", "clear", "-"}:
        return ""
    try:
        return cast(raw)
    except Exception:
        print("Invalid value; keeping current setting.")
        return current


def _prompt_secret(label: str, current: str = "", *, allow_empty: bool = True) -> str:
    state = "SET" if current else "NOT SET"
    raw = _cli_input(f"{label} [{state}] (Enter keeps current; type clear to erase): ", secret=True).strip()
    if not raw:
        return current
    if allow_empty and raw.lower() in {"none", "clear", "-"}:
        return ""
    return raw


def _prompt_with_description(description: str, label: str, current: Any, cast=str, *, allow_empty: bool = False) -> Any:
    print()
    print(description)
    return _prompt_value(label, current, cast, allow_empty=allow_empty)


def _backend_auth_label(cfg: Dict[str, Any]) -> str:
    labels = {
        "none": "None",
        "bearer": "Bearer token / API key",
        "header": "Named API-key header",
        "basic": "HTTP Basic",
        "authorization": "Custom Authorization",
    }
    return labels.get(str(cfg.get("backend_auth_mode", "none")).lower(), "Custom")


def _backend_profile_key(cfg: Dict[str, Any]) -> str:
    return _normalize_backend_profile(str(cfg.get("backend_profile", "lmstudio")))

def _backend_preset(cfg: Dict[str, Any]) -> Dict[str, str]:
    return BACKEND_PRESETS[_backend_profile_key(cfg)]

def _backend_name(cfg: Dict[str, Any]) -> str:
    return _backend_preset(cfg)["short_label"]

def _clear_backend_credentials(cfg: Dict[str, Any]) -> None:
    cfg["backend_auth_mode"] = "none"
    cfg["backend_api_key"] = ""
    cfg["backend_header_name"] = ""
    cfg["backend_header_value"] = ""
    cfg["backend_username"] = ""
    cfg["backend_password"] = ""
    cfg["backend_authorization_value"] = ""
    cfg["backend_extra_headers"] = {}

def _apply_backend_preset(cfg: Dict[str, Any], profile: str) -> None:
    key = _normalize_backend_profile(profile)
    preset = BACKEND_PRESETS[key]
    cfg["backend_profile"] = key
    cfg["backend_base_url"] = preset["base_url"]
    cfg["backend_model"] = ""
    cfg["qwen_control_shape"] = preset["control_shape"]
    _clear_backend_credentials(cfg)

def _edit_generic_auth(cfg: Dict[str, Any]) -> None:
    print()
    print("Authentication type")
    print("  1) None")
    print("  2) Bearer token / API key")
    print("  3) Named API-key header")
    print("  4) HTTP Basic username/password")
    print("  5) Custom Authorization header value")
    current = str(cfg.get("backend_auth_mode", "none")).lower()
    reverse = {"none":"1", "bearer":"2", "header":"3", "basic":"4", "authorization":"5"}
    choice = _cli_input(f"Select authentication [1-5] [{reverse.get(current, '1')}]: ").strip()
    modes = {"1":"none", "2":"bearer", "3":"header", "4":"basic", "5":"authorization"}
    mode = modes.get(choice, current if not choice else "")
    if not mode:
        print("Invalid authentication selection; keeping current setting.")
        return
    _clear_backend_credentials(cfg)
    cfg["backend_auth_mode"] = mode
    if mode == "bearer":
        print("Bearer token/API key: sent as Authorization: Bearer <secret>.")
        cfg["backend_api_key"] = _prompt_secret("Backend API key")
    elif mode == "header":
        print("Named API-key header: some gateways use api-key or x-api-key instead of Bearer auth.")
        cfg["backend_header_name"] = _prompt_value("Header name", "x-api-key", str)
        cfg["backend_header_value"] = _prompt_secret("Header secret")
    elif mode == "basic":
        print("HTTP Basic: username and password are combined into the Authorization header.")
        cfg["backend_username"] = _prompt_value("Username", "", str, allow_empty=True)
        cfg["backend_password"] = _prompt_secret("Password")
    elif mode == "authorization":
        print("Custom Authorization: enter the complete value, such as Token abc123.")
        cfg["backend_authorization_value"] = _prompt_secret("Authorization value")

    extra: Dict[str, str] = {}
    raw = _cli_input("Add an additional provider/gateway header? [y/N]: ").strip().lower()
    while raw in {"y", "yes"}:
        name = _cli_input("Header name: ").strip()
        if not name:
            break
        print("Header value may contain a tenant ID, project ID, organization ID, or another gateway credential.")
        value = _prompt_secret(f"Value for {name}")
        if value:
            extra[name] = value
        raw = _cli_input("Add another header? [y/N]: ").strip().lower()
    cfg["backend_extra_headers"] = extra


def _backend_headers_from_cli(cfg: Dict[str, Any]) -> Dict[str, str]:
    extra = cfg.get("backend_extra_headers")
    if not isinstance(extra, dict):
        extra = {}
    return _compose_backend_headers(
        auth_mode=str(cfg.get("backend_auth_mode", "none")),
        api_key=str(cfg.get("backend_api_key", "")),
        header_name=str(cfg.get("backend_header_name", "")),
        header_value=str(cfg.get("backend_header_value", "")),
        username=str(cfg.get("backend_username", "")),
        password=str(cfg.get("backend_password", "")),
        authorization_value=str(cfg.get("backend_authorization_value", "")),
        extra_headers={str(k): str(v) for k, v in extra.items()},
    )


def _query_lmstudio_loaded_models_cli(cfg: Dict[str, Any], timeout: float = 1.5) -> List[Dict[str, Any]]:
    root = _openai_base_to_server_root(str(cfg.get("backend_base_url") or BACKEND_PRESETS["lmstudio"]["base_url"]))
    attempts = [
        (f"{root}/api/v1/models", _parse_lmstudio_v1_loaded_llms),
        (f"{root}/api/v0/models", _parse_lmstudio_v0_loaded_llms),
    ]
    last_error: Optional[Exception] = None
    with httpx.Client(timeout=timeout) as client:
        for url, parser in attempts:
            try:
                r = client.get(url, headers=_backend_headers_from_cli(cfg))
                if r.status_code == 404:
                    continue
                r.raise_for_status()
                return parser(r.json())
            except Exception as exc:
                last_error = exc
                continue
    if last_error is not None:
        raise last_error
    return []


def _backend_model_status(cfg: Dict[str, Any]) -> str:
    configured = str(cfg.get("backend_model") or "").strip()
    if _backend_profile_key(cfg) != "lmstudio":
        return configured or "AUTO-DETECT"
    try:
        loaded = _query_lmstudio_loaded_models_cli(cfg)
    except Exception:
        return f"{configured} [UNVERIFIED]" if configured else "AUTO-DETECT [LM STUDIO OFFLINE]"
    if configured:
        matches = _match_loaded_lmstudio_model(loaded, configured)
        if len(matches) == 1:
            return str(matches[0].get("instance_id") or configured)
        if len(matches) > 1:
            return f"{configured} [AMBIGUOUS]"
        return f"{configured} [NOT LOADED]"
    if not loaded:
        return "AUTO-DETECT [NO LOADED LLM]"
    if len(loaded) == 1:
        return f"AUTO: {loaded[0].get('instance_id') or loaded[0].get('model_key')}"
    return f"AUTO-DETECT [{len(loaded)} LOADED LLMs]"


def _effective_agent_base_url(cfg: Dict[str, Any]) -> str:
    override = str(cfg.get("agent_base_url") or "").strip().rstrip("/")
    if override:
        return override if override.endswith("/v1") else override + "/v1"
    host = str(cfg.get("host") or "127.0.0.1").strip()
    if host in {"0.0.0.0", "::", "[::]"}:
        host = "127.0.0.1"
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"http://{host}:{int(cfg.get('port', 8001))}/v1"


def _print_header(
    cfg: Dict[str, Any], *, clear_screen: bool = True, include_brand: bool = True
) -> None:
    prompt = _load_cli_secondary_prompt()
    model = _backend_model_status(cfg)
    if clear_screen:
        _clear_cli()
    terminal_width = _terminal_width()
    width = min(terminal_width, 96)

    if include_brand:
        _print_brand_block()
    print()
    print(_ansi_rgb("━" * width, _JACK_BLUE))
    print(_status_value("Backend profile", _backend_name(cfg)))
    print(_status_value("Backend endpoint", cfg.get('backend_base_url') or 'NOT CONFIGURED'))
    print(_status_value("Backend model", model))
    print(_status_value("Backend auth", _backend_auth_label(cfg)))
    ctx = int(cfg.get("backend_context_length", 0) or 0)
    print(_status_value("Context length", ctx if ctx > 0 else "UNKNOWN"))
    print(_status_value("Agent base URL", _effective_agent_base_url(cfg)))
    print(_status_value("Orchestration API", _orchestration_url_from_cli_config(cfg)))
    print(_status_value("Orchestration protocol", "v2  [run-bound IDs + sequence + replay]"))
    print(_status_value("Event replay buffer", f"{ORCHESTRATION_EVENTS.replay_limit} events"))
    print(_status_value("Build agent bridge", _build_agent_bridge_display()))
    print(_status_value("Listen address", f"{cfg['host']}:{cfg['port']}"))
    print(_status_value("Virtual model", cfg['virtual_model']))
    print(_status_value("Preserve thinking", "ON" if cfg.get("preserve_thinking", True) else "OFF"))
    print(_status_value("Forensic archive", str(cfg.get("forensic_archive_mode", "stage")).upper()))
    print(_status_value("Live stage streaming", "ON  [stream=true]"))
    print(_status_value("Kernel max-token cap", "NONE"))
    level_key = _REASONING_LEVEL_ALIASES.get(str(cfg.get("reasoning_level", "x-high")).lower(), str(cfg.get("reasoning_level", "x-high")).lower())
    level_profile = REASONING_PROFILES.get(level_key, REASONING_PROFILES["x-high"])
    print(_status_value("Reasoning level", level_profile["label"]))
    prompt_state = f"SET  [{len(prompt)} chars]" if prompt.strip() else "NOT SET"
    print(_status_value("Secondary prompt", prompt_state))
    print(_ansi_rgb("━" * width, _JACK_BLUE))
    print(_ansi_rgb(DONATION_MESSAGE, _JACK_MUTED))
    print(_ansi_rgb("━" * width, _JACK_BLUE))


def _edit_secondary_prompt() -> None:
    _print_back_hint()
    existing = _load_cli_secondary_prompt()
    print()
    if existing.strip():
        print(f"A persistent secondary system prompt is currently set ({len(existing)} chars).")
    else:
        print("No persistent secondary system prompt is currently set.")
    print("Paste the complete prompt below.")
    print("Enter a line containing only .end to save.")
    print("Enter a line containing only .clear to erase the prompt.")
    print("Press Esc at any time to cancel and return to the main menu.")
    lines: List[str] = []
    while True:
        try:
            line = _cli_input()
        except EOFError:
            break
        if line == ".end":
            break
        if line == ".clear":
            _save_cli_secondary_prompt("")
            print("Secondary system prompt cleared.")
            return
        lines.append(line)
    text = "\n".join(lines)
    if text.strip():
        _save_cli_secondary_prompt(text)
        print(f"Saved secondary system prompt ({len(text)} chars).")
    else:
        print("No text entered; existing prompt was left unchanged.")


def _edit_reasoning(cfg: Dict[str, Any]) -> None:
    _print_back_hint()
    print()
    print("Jack Kernel reasoning level")
    print()
    print("  1) Off")
    print(_ansi_rgb("  2) Low (Disabled)", _JACK_MUTED))
    print("  3) Medium")
    print("  4) X-High (Default)")
    print("  5) Deep Research")
    print("  6) Agentic")
    print("  7) Code Debugging")
    print("  8) Code Debugging (Deep)")
    print()
    current = str(cfg.get("reasoning_level", "x-high")).lower()
    current = _REASONING_LEVEL_ALIASES.get(current, current)
    if current == "low" or current not in REASONING_PROFILES or REASONING_PROFILES[current].get("disabled"):
        current = "x-high"
    choice = _cli_input(
        f"Select level [1-8] [{REASONING_PROFILES[current]['label']}]: "
    ).strip().lower()
    if not choice:
        return
    if choice in {"2", "low"}:
        print(_ansi_rgb("Low is disabled in Jack Kernel v0.1.1 and cannot be selected.", _JACK_MUTED))
        return
    mapping = {
        "1": "off", "off": "off", "flash": "off",
        "3": "medium", "medium": "medium", "standard": "medium",
        "4": "x-high", "x-high": "x-high", "xhigh": "x-high", "high": "x-high", "default": "x-high", "recommended": "x-high",
        "5": "ultra", "deep-research": "ultra", "deep_research": "ultra", "deep research": "ultra", "deepresearch": "ultra", "ultra": "ultra", "extreme": "ultra", "max": "ultra",
        "6": "agentic", "agentic": "agentic",
        "7": "code-debugging", "code-debugging": "code-debugging", "debug": "code-debugging", "debugging": "code-debugging",
        "8": "code-debugging-deep", "code-debugging-deep": "code-debugging-deep", "code debugging deep": "code-debugging-deep", "debugging deep": "code-debugging-deep", "deep debugging": "code-debugging-deep",
    }
    selected = mapping.get(choice)
    if selected is None:
        print("Invalid selection; keeping current reasoning level.")
        return
    cfg["reasoning_level"] = selected
    print(f"Reasoning level set to {REASONING_PROFILES[selected]['label']}.")


def _edit_preserve_thinking(cfg: Dict[str, Any]) -> None:
    _print_back_hint()
    print("Preserve thinking")
    print()
    print("Agentic forces Preserve Thinking ON for the full current generative turn and prunes all native thinking before the next user turn.")
    print("This general toggle remains available for other compatible reasoning paths.")
    print()
    print("1) On")
    print("2) Off")
    print()
    current = "1" if cfg.get("preserve_thinking", True) else "2"
    selected = _cli_input(f"Select [1-2] [{current}]: ").strip() or current
    if selected == "1":
        cfg["preserve_thinking"] = True
    elif selected == "2":
        cfg["preserve_thinking"] = False
    else:
        print("Invalid selection; keeping current value.")


def _edit_forensic_archive(cfg: Dict[str, Any]) -> None:
    _print_back_hint()
    print("Forensic archive")
    print()
    print("1) Stage  - Agentic: archive retired Stage-1 R1/tools; Deep Research: archive full Thesis/Antithesis/Synthesis trajectory out of band")
    print("2) Off    - do not persist transient reasoning trajectories")
    print()
    current_mode = str(cfg.get("forensic_archive_mode", "stage")).strip().lower()
    current = "1" if current_mode == "stage" else "2"
    selected = _cli_input(f"Select [1-2] [{current}]: ").strip() or current
    if selected == "1":
        cfg["forensic_archive_mode"] = "stage"
    elif selected == "2":
        cfg["forensic_archive_mode"] = "off"
    else:
        print("Invalid selection; keeping current value.")
        return
    root = str(cfg.get("forensic_archive_dir") or "").strip()
    if cfg["forensic_archive_mode"] == "stage":
        print("Archive location: " + (root if root else "Jack config directory / forensic"))


def _edit_sampling(cfg: Dict[str, Any]) -> None:
    _print_back_hint()
    print()
    print("Stage temperatures")
    print("Deep Research: Stage 1 = 0.85; Stage 2 = 0.70; Stage 3 = 0.70 (fixed).")
    print("Agentic: Stage 1 = 0.70; Stage 2 Jack XML = 0.50 (fixed).")
    print("Code Debugging: Passes 1-5 = 1.00 / 0.80 / 0.70 / 0.60 / 0.50; final report = 1.00 (fixed).")

    print()
    print("Thinking-stage sampler shape (temperature overridden per stage)")
    cfg["thinking_top_p"] = _prompt_value("top_p", cfg["thinking_top_p"], float)
    cfg["thinking_top_k"] = _prompt_value("top_k", cfg["thinking_top_k"], int)
    cfg["thinking_min_p"] = _prompt_value("min_p", cfg["thinking_min_p"], float)
    cfg["thinking_repeat_penalty"] = _prompt_value(
        "repeat_penalty", cfg["thinking_repeat_penalty"], float
    )

    print()
    print("Thinking-OFF sampler shape (temperature overridden per stage)")
    cfg["nonthinking_top_p"] = _prompt_value(
        "top_p", cfg["nonthinking_top_p"], float
    )
    cfg["nonthinking_top_k"] = _prompt_value(
        "top_k", cfg["nonthinking_top_k"], int
    )
    cfg["nonthinking_min_p"] = _prompt_value(
        "min_p", cfg["nonthinking_min_p"], float
    )
    cfg["nonthinking_repeat_penalty"] = _prompt_value(
        "repeat_penalty", cfg["nonthinking_repeat_penalty"], float
    )
    print()
    print("Presence penalty is fixed at 0.0 for every Jack stage.")


def _edit_model_selection(cfg: Dict[str, Any]) -> None:
    _print_back_hint()
    print()
    print("Model Selection")
    print()
    print("Inference backend")
    print()
    print("  1) LM Studio (Default)")
    print("  2) Ollama")
    print("  3) Jan.ai")
    print("  4) llama.cpp (raw llama-server)")
    print("  5) Custom OpenAI-compatible")
    print()
    current_key = _backend_profile_key(cfg)
    current_label = BACKEND_PRESETS[current_key]["label"]
    choice = _cli_input(f"Select backend [1-5] [{current_label}]: ").strip().lower()
    mapping = {
        "1":"lmstudio", "lmstudio":"lmstudio", "lm studio":"lmstudio",
        "2":"ollama", "ollama":"ollama",
        "3":"jan", "jan":"jan", "jan.ai":"jan",
        "4":"llamacpp", "llamacpp":"llamacpp", "llama.cpp":"llamacpp", "llama cpp":"llamacpp",
        "5":"custom", "custom":"custom", "vllm":"custom",
    }
    if choice:
        selected = mapping.get(choice)
        if selected is None:
            print("Invalid backend selection; keeping current backend.")
        else:
            _apply_backend_preset(cfg, selected)
            print(f"Applied {BACKEND_PRESETS[selected]['label']} defaults.")

    key = _backend_profile_key(cfg)
    preset = BACKEND_PRESETS[key]
    descriptions = {
        "lmstudio": "LM Studio OpenAI-compatible base URL. Default: http://127.0.0.1:1234/v1.",
        "ollama": "Ollama OpenAI-compatible base URL. Local default: http://127.0.0.1:11434/v1.",
        "jan": "Jan.ai Desktop Local API base URL. Desktop default: http://127.0.0.1:1337/v1. If you use `jan serve`, its CLI default is http://127.0.0.1:6767/v1.",
        "llamacpp": "Raw llama.cpp llama-server OpenAI-compatible base URL. Default: http://127.0.0.1:8080/v1.",
        "custom": "OpenAI-compatible base URL for vLLM, a gateway, or another compatible server. Include /v1 when the server expects it.",
    }
    cfg["backend_base_url"] = _prompt_with_description(
        descriptions[key],
        f"{preset['short_label']} base URL",
        cfg.get("backend_base_url") or preset["base_url"],
        str,
        allow_empty=False,
    ).rstrip("/")

    model_help = (
        "Model ID: leave AUTO-DETECT to use the currently loaded LM Studio LLM only. "
        "Jack reads LM Studio loaded_instances and will not select a downloaded/JIT-visible model."
        if key == "lmstudio"
        else "Model ID: leave AUTO-DETECT to query the backend model list and let Jack select a model."
    )
    cfg["backend_model"] = _prompt_with_description(
        model_help,
        "Backend model ID",
        cfg.get("backend_model") or "AUTO-DETECT",
        str,
        allow_empty=True,
    )
    if not str(cfg["backend_model"]).strip() or str(cfg["backend_model"]).upper() == "AUTO-DETECT":
        cfg["backend_model"] = ""

    if key == "lmstudio":
        print()
        print("LM Studio authentication")
        print("LM Studio local servers do not require authentication by default.")
        print("If Require Authentication is enabled, Jack needs the LM Studio API token.")
        enabled = _cli_input("Is Require Authentication enabled? [y/N]: ").strip().lower() in {"y", "yes"}
        _clear_backend_credentials(cfg)
        if enabled:
            cfg["backend_auth_mode"] = "bearer"
            print("LM Studio API token: copied from Developer > Server Settings > Manage Tokens.")
            cfg["backend_api_key"] = _prompt_secret("LM Studio API token")
    elif key == "ollama":
        print()
        print("Ollama authentication")
        print("Local Ollama does not require authentication. A remote/reverse-proxied endpoint may require a Bearer token.")
        enabled = _cli_input("Does this Ollama endpoint require a Bearer/API token? [y/N]: ").strip().lower() in {"y", "yes"}
        _clear_backend_credentials(cfg)
        if enabled:
            cfg["backend_auth_mode"] = "bearer"
            cfg["backend_api_key"] = _prompt_secret("Ollama/API gateway token")
    elif key == "jan":
        print()
        print("Jan.ai authentication")
        print("Jan's Local API can be configured with an API key. If set, it is sent as a Bearer token.")
        enabled = _cli_input("Is a Jan API key configured? [y/N]: ").strip().lower() in {"y", "yes"}
        _clear_backend_credentials(cfg)
        if enabled:
            cfg["backend_auth_mode"] = "bearer"
            cfg["backend_api_key"] = _prompt_secret("Jan API key")
    elif key == "llamacpp":
        print()
        print("llama.cpp authentication")
        print("Raw llama-server has no API key by default. If started with --api-key, Jack must send that key as Bearer authentication.")
        enabled = _cli_input("Was llama-server started with --api-key? [y/N]: ").strip().lower() in {"y", "yes"}
        _clear_backend_credentials(cfg)
        if enabled:
            cfg["backend_auth_mode"] = "bearer"
            cfg["backend_api_key"] = _prompt_secret("llama-server API key")
    else:
        _edit_generic_auth(cfg)


def _edit_network(cfg: Dict[str, Any]) -> None:
    _print_back_hint()
    print()
    cfg["host"] = _prompt_value("Listen host / bind interface", cfg["host"], str)
    cfg["port"] = _prompt_value("Listen port", cfg["port"], int)
    current_agent = cfg.get("agent_base_url") or "AUTO"
    cfg["agent_base_url"] = _prompt_value(
        "Agent OpenAI base URL (type clear for automatic)",
        current_agent,
        str,
        allow_empty=True,
    )
    if cfg["agent_base_url"].upper() == "AUTO":
        cfg["agent_base_url"] = ""
    cfg["virtual_model"] = _prompt_value(
        "Virtual OpenAI model ID", cfg["virtual_model"], str
    )
    print()
    print("Kernel access key: optional secret for agents connecting TO Jack. "
          "This is separate from the credential Jack uses to connect to the model backend.")
    cfg["api_key"] = _prompt_secret("Kernel access key", str(cfg.get("api_key", "")))


def _edit_advanced(cfg: Dict[str, Any]) -> None:
    _print_back_hint()
    print()
    print("Advanced Qwen / backend runtime settings")
    shape = _cli_input(
        "Qwen control shape [template_kwargs/top_level/hybrid/ollama_openai] "
        f"[{cfg['qwen_control_shape']}]: "
    ).strip().lower()
    if shape:
        if shape in {"template_kwargs", "top_level", "hybrid", "ollama_openai"}:
            cfg["qwen_control_shape"] = shape
        else:
            print("Invalid control shape; keeping current value.")
    cfg["backend_timeout_seconds"] = _prompt_value(
        "Backend transport timeout seconds",
        cfg["backend_timeout_seconds"],
        float,
    )
    cfg["backend_context_length"] = max(0, _prompt_value(
        "Backend context length tokens (0 = unknown)",
        int(cfg.get("backend_context_length", 0) or 0),
        int,
    ))
    cfg["max_concurrent_requests"] = _prompt_value(
        "Maximum concurrent Kernel requests",
        cfg["max_concurrent_requests"],
        int,
    )
    cfg["seed"] = _prompt_value(
        "Seed (type clear for backend default)",
        cfg["seed"] or "BACKEND DEFAULT",
        str,
        allow_empty=True,
    )
    if cfg["seed"] == "BACKEND DEFAULT":
        cfg["seed"] = ""
    level = _cli_input(f"Log level [{cfg['log_level']}]: ").strip().upper()
    if level:
        if level in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            cfg["log_level"] = level
        else:
            print("Invalid log level; keeping current value.")
    raw = _cli_input(
        f"Log native reasoning? [y/N] [{'Y' if cfg['log_reasoning'] else 'N'}]: "
    ).strip().lower()
    if raw in {"y", "yes"}:
        cfg["log_reasoning"] = True
    elif raw in {"n", "no"}:
        cfg["log_reasoning"] = False


def _test_backend(cfg: Dict[str, Any]) -> None:
    preset = _backend_preset(cfg)
    name = preset["short_label"]
    base = str(cfg.get("backend_base_url") or preset["base_url"]).strip().rstrip("/")
    url = base + "/models"
    print(f"Testing {name} at {url} ...")
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(url, headers=_backend_headers_from_cli(cfg))
            if r.status_code in {401, 403}:
                print(f"FAILED: {name} rejected the configured credential.")
                print("Open option 3 and verify the backend authentication setting and secret.")
                return
            r.raise_for_status()
            payload = r.json()
            data = payload.get("data") if isinstance(payload, dict) else None
            data = data or []
    except httpx.ConnectError as exc:
        print(f"FAILED: cannot reach {name} ({exc}).")
        hints = {
            "lmstudio": "Start LM Studio's Developer server (or `lms server start`).",
            "ollama": "Start Ollama and confirm it is listening on port 11434.",
            "jan": "Start Jan Desktop > Settings > Local API Server. If using `jan serve`, its default port is 6767 instead of 1337.",
            "llamacpp": "Start llama-server, normally with `llama-server -m <model.gguf> --port 8080`.",
            "custom": "Start the configured OpenAI-compatible server and verify its host, port, and /v1 prefix.",
        }
        print(hints[_backend_profile_key(cfg)])
        print(f"Configured OpenAI-compatible base URL: {base}")
        return
    except Exception as exc:
        print(f"FAILED: {exc}")
        return

    if not data:
        print(f"{name} is reachable, but /v1/models returned no model IDs.")
        print("Load/pull/serve a model, or enter the exact model ID manually in option 3.")
        return

    ids = [str(item.get("id", "")) for item in data if isinstance(item, dict) and item.get("id")]
    print(f"{name} is reachable. Models reported by /v1/models:")
    for i, model_id in enumerate(ids, 1):
        print(f"  {i}. {model_id}")
    if not cfg.get("backend_model") and ids:
        preferred = [m for m in ids if "qwen3.8" in m.lower() and "27b" in m.lower()]
        selected = preferred[0] if preferred else ids[0]
        print(f"AUTO-DETECT would select: {selected}")

def _config_to_env(cfg: Dict[str, Any]) -> Dict[str, str]:
    _, prompt_path = _config_paths()
    env = os.environ.copy()
    values = {
        "JACK_HOST": cfg["host"],
        "JACK_PORT": cfg["port"],
        "JACK_AGENT_BASE_URL": cfg.get("agent_base_url", ""),
        "JACK_API_KEY": cfg["api_key"],
        "JACK_BACKEND_PROFILE": _backend_profile_key(cfg),
        "JACK_BACKEND_BASE_URL": cfg.get("backend_base_url", ""),
        "JACK_BACKEND_MODEL": cfg["backend_model"],
        "JACK_BACKEND_AUTH_MODE": cfg.get("backend_auth_mode", "none"),
        "JACK_BACKEND_API_KEY": cfg.get("backend_api_key", ""),
        "JACK_BACKEND_HEADER_NAME": cfg.get("backend_header_name", ""),
        "JACK_BACKEND_HEADER_VALUE": cfg.get("backend_header_value", ""),
        "JACK_BACKEND_USERNAME": cfg.get("backend_username", ""),
        "JACK_BACKEND_PASSWORD": cfg.get("backend_password", ""),
        "JACK_BACKEND_AUTHORIZATION_VALUE": cfg.get("backend_authorization_value", ""),
        "JACK_BACKEND_EXTRA_HEADERS": json.dumps(cfg.get("backend_extra_headers") or {}, ensure_ascii=False),
        "JACK_VIRTUAL_MODEL": cfg["virtual_model"],
        "JACK_REASONING_LEVEL": cfg["reasoning_level"],
        "JACK_PRESERVE_THINKING": "1" if cfg.get("preserve_thinking", True) else "0",
        "JACK_BACKEND_TIMEOUT_SECONDS": cfg["backend_timeout_seconds"],
        "JACK_BACKEND_CONTEXT_LENGTH": cfg.get("backend_context_length", 0),
        "JACK_MAX_CONCURRENT": cfg["max_concurrent_requests"],
        "JACK_SEED": cfg["seed"],
        "JACK_QWEN_CONTROL_SHAPE": cfg["qwen_control_shape"],
        "JACK_LOG_LEVEL": cfg["log_level"],
        "JACK_LOG_REASONING": "1" if cfg["log_reasoning"] else "0",
        "JACK_FORENSIC_ARCHIVE_MODE": cfg.get("forensic_archive_mode", "stage"),
        "JACK_FORENSIC_ARCHIVE_DIR": cfg.get("forensic_archive_dir", ""),
        "JACK_SECONDARY_SYSTEM_PROMPT_FILE": str(prompt_path),
        "JACK_THINKING_TEMPERATURE": cfg["thinking_temperature"],
        "JACK_THINKING_TOP_P": cfg["thinking_top_p"],
        "JACK_THINKING_TOP_K": cfg["thinking_top_k"],
        "JACK_THINKING_MIN_P": cfg["thinking_min_p"],
        "JACK_THINKING_PRESENCE_PENALTY": cfg["thinking_presence_penalty"],
        "JACK_THINKING_REPEAT_PENALTY": cfg["thinking_repeat_penalty"],
        "JACK_NONTHINKING_TEMPERATURE": cfg["nonthinking_temperature"],
        "JACK_NONTHINKING_TOP_P": cfg["nonthinking_top_p"],
        "JACK_NONTHINKING_TOP_K": cfg["nonthinking_top_k"],
        "JACK_NONTHINKING_MIN_P": cfg["nonthinking_min_p"],
        "JACK_NONTHINKING_PRESENCE_PENALTY": cfg["nonthinking_presence_penalty"],
        "JACK_NONTHINKING_REPEAT_PENALTY": cfg["nonthinking_repeat_penalty"],
    }
    for key, value in values.items():
        env[key] = str(value)
    return env


def _server_command() -> List[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--serve"]
    return [sys.executable, str(Path(__file__).resolve()), "--serve"]


def _start_server_from_cli(cfg: Dict[str, Any]) -> None:
    if not str(cfg.get("backend_base_url") or "").strip():
        print()
        print("Backend endpoint is not configured. Use option 3 first.")
        return
    _save_cli_config(cfg)
    env = _config_to_env(cfg)
    print()
    print("Starting Jack Kernel...")
    print(f"Backend        : {_backend_name(cfg)}")
    print(f"Backend URL    : {cfg.get('backend_base_url')}")
    print(f"Backend model  : {_backend_model_status(cfg)}")
    print(f"Agent base URL     : {_effective_agent_base_url(cfg)}")
    print(f"Orchestration API  : {_orchestration_url_from_cli_config(cfg)}")
    print("Orchestration proto: v2 [run-bound IDs + sequence + replay]")
    print(f"Event replay buffer: {ORCHESTRATION_EVENTS.replay_limit} events")
    print(f"Build agent bridge : {_build_agent_bridge_display()}")
    print(f"Listen address     : {cfg['host']}:{cfg['port']}")
    print(f"Virtual model  : {cfg['virtual_model']}")
    level_key = _REASONING_LEVEL_ALIASES.get(str(cfg.get("reasoning_level", "x-high")).lower(), str(cfg.get("reasoning_level", "x-high")).lower())
    print(f"Reasoning level  : {REASONING_PROFILES.get(level_key, REASONING_PROFILES['x-high'])['label']}")
    print(f"Preserve thinking: {'ON' if cfg.get('preserve_thinking', True) else 'OFF'}")
    print(f"Forensic archive : {str(cfg.get('forensic_archive_mode', 'stage')).upper()}")
    print("Deep Research max_tokens failsafes: Thesis 100000 / Antithesis 20000 / Synthesis 100000" if level_key == "ultra" else "Kernel-side max_tokens limits: NONE")
    print("Press Ctrl+C to stop the server and return to the launcher.")
    print()
    try:
        subprocess.run(_server_command(), env=env, check=False)
    except KeyboardInterrupt:
        pass


def _print_main_menu_options() -> None:
    print(_ansi_rgb("  1", _JACK_ICE, bold=True) + "  Start Kernel")
    print(_ansi_rgb("  2", _JACK_STEEL, bold=True) + "  Persistent secondary system prompt")
    print(_ansi_rgb("  3", _JACK_STEEL, bold=True) + "  Model Selection")
    print(_ansi_rgb("  4", _JACK_STEEL, bold=True) + "  Reasoning level")
    print(_ansi_rgb("  5", _JACK_STEEL, bold=True) + "  Sampling settings")
    print(_ansi_rgb("  6", _JACK_STEEL, bold=True) + "  Server / agent endpoint")
    print(_ansi_rgb("  7", _JACK_STEEL, bold=True) + "  Advanced settings")
    print(_ansi_rgb("  8", _JACK_STEEL, bold=True) + "  Test backend connection")
    print(_ansi_rgb("  9", _JACK_STEEL, bold=True) + "  Reset Jack defaults")
    print(_ansi_rgb("  P", _JACK_STEEL, bold=True) + "  Preserve thinking")
    print(_ansi_rgb("  F", _JACK_STEEL, bold=True) + "  Forensic archive")
    print(_ansi_rgb("  S", _JACK_STEEL, bold=True) + "  Save settings")
    print(_ansi_rgb("  M", _JACK_STEEL, bold=True) + "  Main screen / refresh")
    print(_ansi_rgb("  Q", _JACK_STEEL, bold=True) + "  Quit")
    print()


def _print_compact_main_commands() -> None:
    """Return control without repainting the branded screen."""
    print()
    print(_ansi_rgb("Main:", _JACK_MUTED) +
          " 1 Start  2 Prompt  3 Models  4 Reasoning  5 Sampling  6 Endpoint")
    print("      7 Advanced  8 Test  9 Reset  P Thinking  F Forensic  S Save  M Main screen  Q Quit")
    print(_ansi_rgb("Use M only when you want the full status screen redrawn.", _JACK_MUTED))
    print()


def _render_full_main_screen(cfg: Dict[str, Any], *, preserve_intro: bool = False) -> None:
    if preserve_intro:
        _print_header(cfg, clear_screen=False, include_brand=False)
    else:
        _print_header(cfg, clear_screen=True, include_brand=True)
    _print_main_menu_options()


def run_cli() -> None:
    _enable_cli_branding()
    intro_shown = _show_brand_intro()
    cfg = _load_cli_config()
    _save_cli_config(cfg)

    # Render the complete branded main screen once.  Normal actions deliberately
    # do not repaint it; their results remain visible and control returns to the
    # compact JACK prompt.  Esc/back or M explicitly requests a full redraw.
    _render_full_main_screen(cfg, preserve_intro=intro_shown)

    while True:
        try:
            choice = _cli_input(
                _ansi_rgb("JACK", _JACK_ICE, bold=True) + _ansi_rgb("  ›  ", _JACK_BLUE)
            ).strip().lower()

            if choice == "1":
                _start_server_from_cli(cfg)
            elif choice == "2":
                _edit_secondary_prompt()
            elif choice == "3":
                _run_transactional_editor(_edit_model_selection, cfg)
            elif choice == "4":
                _run_transactional_editor(_edit_reasoning, cfg)
            elif choice == "5":
                _run_transactional_editor(_edit_sampling, cfg)
            elif choice == "6":
                _run_transactional_editor(_edit_network, cfg)
            elif choice == "7":
                _run_transactional_editor(_edit_advanced, cfg)
            elif choice == "8":
                _test_backend(cfg)
            elif choice == "9":
                confirm = _cli_input("Reset all settings to Jack defaults? [y/N]: ").strip().lower()
                if confirm in {"y", "yes"}:
                    cfg = copy.deepcopy(CLI_DEFAULTS)
                    print("Defaults restored. Secondary system prompt was preserved.")
            elif choice == "p":
                _run_transactional_editor(_edit_preserve_thinking, cfg)
            elif choice == "f":
                _run_transactional_editor(_edit_forensic_archive, cfg)
            elif choice == "s":
                _save_cli_config(cfg)
                print("Settings saved.")
            elif choice == "m":
                _render_full_main_screen(cfg)
                continue
            elif choice == "q":
                _save_cli_config(cfg)
                return
            else:
                print("Unknown selection.")
                continue

            _print_compact_main_commands()

        except _ReturnToMainMenu:
            # Esc/:back is an explicit request to return to the full main screen.
            _render_full_main_screen(cfg)


def run_server() -> None:
    import uvicorn

    if not CFG.backend_base_url:
        raise RuntimeError(
            "No backend endpoint is configured. Set JACK_BACKEND_BASE_URL or configure it in the Jack launcher."
        )
    preset = BACKEND_PRESETS.get(CFG.backend_profile, BACKEND_PRESETS["custom"])
    LOG.info("Starting Jack Kernel on %s:%s", CFG.host, CFG.port)
    LOG.info("Agent OpenAI base URL: %s", CFG.agent_base_url)
    LOG.info("Orchestration API: %s", _orchestration_public_base_from_agent_url(CFG.agent_base_url))
    LOG.info("Orchestration protocol: v2 (run-bound IDs + sequence + replay; %s events)", ORCHESTRATION_EVENTS.replay_limit)
    LOG.info("Build agent bridge: %s", _build_agent_bridge_display())
    LOG.info("Backend profile: %s", preset["short_label"])
    LOG.info("Backend endpoint: %s", CFG.backend_base_url)
    LOG.info("Virtual model: %s", CFG.virtual_model)
    LOG.info("Qwen control shape: %s", CFG.qwen_control_shape)
    LOG.info("Reasoning level: %s", ACTIVE_REASONING_PROFILE["label"])
    LOG.info("Preserve thinking: %s", "ON" if CFG.preserve_thinking else "OFF")
    LOG.info("Forensic archive: %s", CFG.forensic_archive_mode.upper())
    LOG.info("Live stage streaming: ON for OpenAI stream=true requests")
    LOG.info("Deep Research max_tokens failsafes: Thesis 100000 / Antithesis 20000 / Synthesis 100000" if ULTRA_MODE else "Kernel-side max_tokens limits: NONE")
    uvicorn.run(APP, host=CFG.host, port=CFG.port, log_level=CFG.log_level.lower())


def _install_bundled_runtime_extensions() -> None:
    """Install Jack's bundled authority/security extensions for every supported entrypoint."""
    import jack_evidence_guard
    import jack_responses_compat

    jack_evidence_guard.install(sys.modules[__name__])
    jack_responses_compat.register(sys.modules[__name__])
    root = Path(__file__).resolve().parent
    _register_runtime_manifest_components({
        "jack_secure_entrypoint.py": root / "jack_secure_entrypoint.py",
        "jack_evidence_guard.py": Path(jack_evidence_guard.__file__).resolve(),
        "jack_responses_compat.py": Path(jack_responses_compat.__file__).resolve(),
    })


def main() -> None:
    _install_bundled_runtime_extensions()
    if "--serve" in sys.argv:
        run_server()
    else:
        run_cli()


if __name__ == "__main__":
    main()
