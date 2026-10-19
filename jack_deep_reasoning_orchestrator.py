"""TAS v6 Deep Reasoning NON-PRODUCTION stage orchestrator (phase-2 prototype).

Does not execute, authorize, or validate tools. A trusted host must execute every
returned tool call using Jack Kernel's existing policy engine; tool outputs
arriving at resume() are not independently authenticated by this module.

This module never modifies other Jack modes, the Kernel process, or its routes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import copy
import hashlib
import logging
import json
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Sequence

from jack_deep_reasoning_context import (
    CompletedSynthesis,
    _safe_visible_history,
    antithesis_messages,
    append_stage_local_tool_results,
    next_thesis_messages,
    synthesis_messages,
)


LOG = logging.getLogger("jack-kernel.deep-reasoning")

MAX_TAS_EVIDENCE_CHARS = 131072  # total raw Synthesis receipt text cap; full hashes preserved
MAX_TAS_ARTIFACT_TARGET_CHARS = 16384  # bounded locator projection, not a tool-execution ceiling

# Deliberately no interpretation of shell commands, tool text or model prose as
# successful file edits. Only explicit structured file-tool arguments qualify as
# unverified target locators. This grants no new file/tool authority.
_FILE_TOOL_NAMES = frozenset({"read", "edit", "write", "read_file", "write_file", "apply_patch", "patch"})
_FILE_PATH_KEYS = ("path", "file_path", "filename", "target_file", "relative_path", "file")


def _tool_target_locator(stage: str, call: Mapping[str, Any]) -> dict[str, Any] | None:
    function = call.get("function")
    if not isinstance(function, Mapping):
        return None
    name = function.get("name")
    if name not in _FILE_TOOL_NAMES:
        return None
    raw = function.get("arguments")
    if isinstance(raw, str):
        try:
            args = json.loads(raw)
        except (ValueError, TypeError):
            return None
    elif isinstance(raw, Mapping):
        args = raw
    else:
        return None
    if not isinstance(args, Mapping):
        return None
    for key in _FILE_PATH_KEYS:
        candidate = args.get(key)
        if (isinstance(candidate, str) and 0 < len(candidate) <= 512
                and candidate.strip() and not any(c in candidate for c in "\r\n\x00")):
            return {"stage": stage, "tool_name": name, "path": candidate,
                    "tool_result_received": True}
    return None

TAS_V6_PROMPT_HASHES = {
    "ULTRA_STAGE1_THESIS_PROMPT": "b1552c9fa6398ed0b8c45e5e1119a0e10bf198e8d621c8f8e7beb0813400cae4",
    "ULTRA_STAGE2_ANTITHESIS_PROMPT": "54c470e77f0c67dce134b00e2b9117bbd7d58dfd39fcdd8e960cf281eda59c21",
    "ULTRA_STAGE3_SYNTHESIS_PROMPT": "0472fa5a78863bf7f9e6c1e1cc14fbe3f070923b7666157b1f624a7aed4c04b1",
}


def load_exact_v6_prompts(path: str | Path) -> dict[str, str]:
    """Load verbatim tested v6 prompts; fail if any byte identity changed."""
    import json
    prompts = json.loads(Path(path).read_text(encoding="utf-8"))
    for name, expected in TAS_V6_PROMPT_HASHES.items():
        val = prompts.get(name)
        if not isinstance(val, str) or hashlib.sha256(val.encode("utf-8")).hexdigest() != expected:
            raise ValueError(f"TAS v6 prompt missing or changed: {name}")
    return {name: prompts[name] for name in TAS_V6_PROMPT_HASHES}


class DeepReasoningProtocolError(RuntimeError):
    """Fail-closed violation of the experimental stage contract."""


@dataclass(frozen=True)
class PendingToolRequest:
    stage: str
    calls: tuple[dict[str, Any], ...]
    # Session is opaque host-owned state; do not serialize into the model prompt.
    session: "DeepReasoningSession"
    generation: int
    # Only the originating stage may use this; never forward to the next role.
    native_tool_reasoning: str = ""


@dataclass(frozen=True)
class CompletedAnswer:
    answer: str
    synthesis_native_reasoning: str
    thesis_answer: str
    antithesis_findings: str
    evidence: tuple[dict[str, Any], ...]
    # Upstream request/output are not proof of correctness.


@dataclass
class DeepReasoningSession:
    request: str
    stage: str
    messages: list[dict[str, Any]]
    thesis_answer: str
    # Immutable sequence of sanitized committed visible turns; not R1/R2/R3.
    conversation_history: tuple[dict[str, str], ...] = ()
    antithesis_findings: str = ""
    evidence: list[dict[str, Any]] = field(default_factory=list)
    artifact_references: list[dict[str, Any]] = field(default_factory=list)
    outstanding: tuple[dict[str, Any], ...] = ()
    tool_rounds: int = 0
    generation: int = 0
    first_verification_completed: bool = False
    verification_required: bool = True
    closed: bool = False


Backend = Callable[..., Awaitable[Mapping[str, Any]]]


class DeepReasoningOrchestrator:
    """Runs model stages; yields tool proposals to a separately authorized host.

    A generator/backend adapter must have an async `__call__` accepting
    stage, system_prompt, messages, temperature, reasoning_effort, tools,
    tool_choice and returning a dictionary with `content`, optional
    `reasoning_content`, and optional structured `tool_calls`.
    """

    def __init__(
        self,
        backend: Backend,
        *,
        prompts: Mapping[str, str],
        tools: Sequence[Mapping[str, Any]],
        max_tool_rounds: int | None = None,
        preserve_stage_tool_reasoning: bool = False,
    ) -> None:
        if (max_tool_rounds is not None and
                (isinstance(max_tool_rounds, bool) or not isinstance(max_tool_rounds, int)
                 or max_tool_rounds < 1)):
            raise ValueError("max_tool_rounds must be a positive integer or None")
        names = ("ULTRA_STAGE1_THESIS_PROMPT", "ULTRA_STAGE2_ANTITHESIS_PROMPT", "ULTRA_STAGE3_SYNTHESIS_PROMPT")
        if any(not isinstance(prompts.get(k), str) or not prompts[k].strip() for k in names):
            raise ValueError("three nonempty TAS v6 prompts required")
        self.prompts = dict(prompts)
        self.tools = copy.deepcopy(list(tools))
        self.backend = backend
        self.max_tool_rounds = max_tool_rounds
        # Stage-local lease only. The driver authorizes this using user Preserve Thinking.
        # The previous-turn R3 lease is independently enforced by the bridge.
        self.preserve_stage_tool_reasoning = bool(preserve_stage_tool_reasoning)

    @staticmethod
    def _reasoning(answer: Mapping[str, Any]) -> str:
        for key in ("reasoning_content", "reasoning", "thinking"):
            v = answer.get(key)
            if isinstance(v, str) and v:
                return v
        return ""

    @staticmethod
    def _content(answer: Mapping[str, Any], stage: str) -> str:
        content = answer.get("content")
        if not isinstance(content, str) or not content.strip():
            reason = str(answer.get("_tas_finish_reason") or "unknown")
            native = DeepReasoningOrchestrator._reasoning(answer)
            completion = answer.get("_tas_completion_tokens")
            raise DeepReasoningProtocolError(
                f"{stage} stopped without a visible answer "
                f"(backend_finish_reason={reason}, native_reasoning_chars={len(native)}, "
                f"completion_tokens={completion if isinstance(completion, int) else 'unknown'})"
            )
        return content

    @staticmethod
    def _calls(answer: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
        calls = answer.get("tool_calls") or []
        if not isinstance(calls, list):
            raise DeepReasoningProtocolError("tool_calls must be a structured list")
        if calls:
            ids = [c.get("id") for c in calls if isinstance(c, Mapping)]
            if len(ids) != len(calls) or any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
                raise DeepReasoningProtocolError("tool calls require unique, nonempty IDs")
            for c in calls:
                if not isinstance(c.get("function"), Mapping) or not isinstance(c["function"].get("name"), str):
                    raise DeepReasoningProtocolError("malformed function tool call")
        return tuple(copy.deepcopy(c) for c in calls)

    async def _generate(self, stage: str, messages: list[dict[str, Any]], tool_choice: str) -> Mapping[str, Any]:
        prompt_name = {
            "thesis": "ULTRA_STAGE1_THESIS_PROMPT",
            "antithesis": "ULTRA_STAGE2_ANTITHESIS_PROMPT",
            "synthesis": "ULTRA_STAGE3_SYNTHESIS_PROMPT",
        }[stage]
        response = await self.backend(
            stage=stage,
            system_prompt=self.prompts[prompt_name],
            messages=copy.deepcopy(messages),
            temperature=1.0 if stage == "thesis" else 0.5,
            reasoning_effort="medium" if stage == "antithesis" else "xhigh",
            tools=copy.deepcopy(self.tools),
            tool_choice=tool_choice,
        )
        if not isinstance(response, Mapping):
            raise DeepReasoningProtocolError("backend returned no structured response")
        return response

    async def start(
        self,
        *,
        request: str,
        visible_history: Sequence[Mapping[str, Any]] = (),
        prior_synthesis: CompletedSynthesis | None = None,
        preserve_thinking: bool = False,
        require_verification: bool = True,
    ) -> PendingToolRequest | CompletedAnswer:
        if require_verification and not self.tools:
            raise DeepReasoningProtocolError("Tool-first verification requires authorized tools; no tools supplied")
        thesis_history = next_thesis_messages(
            request=request, visible_history=visible_history,
            prior_synthesis=prior_synthesis, preserve_thinking=preserve_thinking,
        )
        # Thesis is a real tool-enabled cognition stage, not merely a one-shot
        # prelude. Hold its own stage-local context until its answer is complete.
        # Never allow its native reasoning to cross the Antithesis boundary.
        # Snapshot the precise previous visible conversation given to Thesis.
        # It may include a reconstructed immediately prior A3 (without its R3).
        # This survives Thesis's private-context destruction and is projected
        # into Antithesis/Synthesis without leaking any native reasoning.
        conversation_history = tuple(_safe_visible_history(thesis_history[:-1]))
        session = DeepReasoningSession(
            request=request, stage="thesis", messages=thesis_history, thesis_answer="",
            conversation_history=conversation_history,
            verification_required=require_verification,
        )
        try:
            return await self._advance(session, "auto")
        except BaseException:
            thesis_history.clear()
            raise

    async def _advance(
        self, session: DeepReasoningSession, tool_choice: str, verification_required: bool = False
    ) -> PendingToolRequest | CompletedAnswer:
        if session.closed:
            raise DeepReasoningProtocolError("closed session cannot advance")
        if session.stage not in {"thesis", "antithesis", "synthesis"}:
            raise DeepReasoningProtocolError("invalid active stage")
        result = await self._generate(session.stage, session.messages, tool_choice)
        calls = self._calls(result)
        finish = result.get("_tas_finish_reason")
        if finish == "length":
            raise DeepReasoningProtocolError(
                f"{session.stage} backend generation truncated at token limit; "
                "refusing to accept an incomplete stage or tool proposal"
            )
        # Some thinking backends terminate with native reasoning but no visible
        # answer after a tool result. Retry the *same* stage once, with the exact
        # same prompt, sampling, tools and projected message history; do not
        # publish the incomplete draft or introduce any new instruction.
        if not calls and (not isinstance(result.get("content"), str) or not result["content"].strip()):
            LOG.warning(
                "Deep Reasoning %s returned no visible output (finish_reason=%s, "
                "reasoning_chars=%d, completion_tokens=%s); retrying exact same stage once",
                session.stage, finish or "unknown", len(self._reasoning(result)),
                result.get("_tas_completion_tokens"),
            )
            result = await self._generate(session.stage, session.messages, tool_choice)
            calls = self._calls(result)
            if result.get("_tas_finish_reason") == "length":
                raise DeepReasoningProtocolError(
                    f"{session.stage} backend generation truncated at token limit on retry; "
                    "refusing incomplete stage output"
                )
        if calls:
            if self.max_tool_rounds is not None and session.tool_rounds >= self.max_tool_rounds:
                raise DeepReasoningProtocolError(
                    f"configured {session.stage} tool round budget exceeded "
                    f"({self.max_tool_rounds} rounds)"
                )
            session.outstanding = calls
            session.generation += 1
            return PendingToolRequest(
                session.stage, calls, session, session.generation,
                self._reasoning(result) if self.preserve_stage_tool_reasoning else "",
            )
        if session.stage == "thesis":
            thesis = self._content(result, "thesis")
            del result  # R1 is never made available to Antithesis.
            # The previous Synthesis R3 and Thesis-local tool exchanges have
            # served the receiving Thesis; drop all references at this boundary.
            session.messages.clear()
            session.thesis_answer = thesis
            session.stage = "antithesis"
            session.tool_rounds = 0  # independent per-role tool budget
            session.messages = antithesis_messages(
                request=session.request, thesis_answer=thesis,
                visible_history=session.conversation_history,
                host_artifact_references=session.artifact_references,
            )
            return await self._advance(
                session,
                "required" if session.verification_required else "auto",
                session.verification_required,
            )
        if session.stage == "antithesis":
            if verification_required:
                raise DeepReasoningProtocolError("first Antithesis response did not contain a required structured tool call")
            anti = self._content(result, "antithesis")
            del result  # R2 must not linger while Synthesis is generating.
            session.antithesis_findings = anti
            session.stage = "synthesis"
            session.tool_rounds = 0  # independent per-role tool budget
            session.messages = synthesis_messages(
                request=session.request,
                thesis_answer=session.thesis_answer,
                antithesis_findings=anti,
                visible_history=session.conversation_history,
                host_evidence_receipts=session.evidence,
                host_artifact_references=session.artifact_references,
            )
            return await self._advance(session, "auto")
        answer = self._content(result, "synthesis")
        session.closed = True
        return CompletedAnswer(
            answer=answer,
            synthesis_native_reasoning=self._reasoning(result),
            thesis_answer=session.thesis_answer,
            antithesis_findings=session.antithesis_findings,
            evidence=tuple(copy.deepcopy(session.evidence)),
        )

    async def resume(
        self,
        pending: PendingToolRequest,
        *,
        results: Sequence[Mapping[str, Any]],
    ) -> PendingToolRequest | CompletedAnswer:
        # **Only** the Kernel's validated executor/caller should supply these.
        # A tool result is not authorized/verified merely by reaching this API.
        session = pending.session
        if (session.closed or session.stage != pending.stage
                or session.outstanding != pending.calls or session.generation != pending.generation):
            raise DeepReasoningProtocolError("stale, mutated, or mismatched tool continuation")
        if self.max_tool_rounds is not None and session.tool_rounds >= self.max_tool_rounds:
            raise DeepReasoningProtocolError(
                f"configured {session.stage} tool round budget exceeded "
                f"({self.max_tool_rounds} rounds)"
            )
        # A pending checkpoint is not consumed until the following model call
        # successfully returns a valid successor or completed Synthesis. Otherwise
        # Jack may rearm the same tool result but TAS would reject its generation.
        # Keep the *same session object* so host-owned checkpoint identity holds.
        checkpoint = copy.deepcopy(session.__dict__)
        try:
            try:
                session.messages = append_stage_local_tool_results(
                    session.messages, tool_calls=pending.calls, results=results,
                    native_reasoning=pending.native_tool_reasoning,
                    preserve_same_stage_native=self.preserve_stage_tool_reasoning,
                )
            except (ValueError, TypeError) as exc:
                raise DeepReasoningProtocolError(f"invalid tool result linkage: {exc}") from exc
            by_id = {r["tool_call_id"]: r for r in results}
            for c in pending.calls:
                output = by_id[c["id"]]
                content = output["content"]
                used = sum(len(e["raw_result"]) for e in session.evidence)
                remaining = max(0, MAX_TAS_EVIDENCE_CHARS - used)
                visible_result = content[:remaining]
                raw_args = c["function"].get("arguments")
                # Preserve enough method context for final evaluation while
                # bounding potentially enormous model-supplied script arguments.
                serialized_args = (raw_args if isinstance(raw_args, str)
                                   else json.dumps(raw_args, ensure_ascii=False, default=str))
                visible_args = serialized_args[:4096]
                session.evidence.append({
                    "stage": session.stage,
                    "tool_call_id": c["id"],
                    "tool_name": c["function"]["name"],
                    "arguments": visible_args,
                    "arguments_total_chars": len(serialized_args),
                    "arguments_truncated": len(serialized_args) > len(visible_args),
                    "raw_result": visible_result,
                    "raw_result_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                    "raw_result_total_chars": len(content),
                    "raw_result_truncated": len(content) > len(visible_result),
                    "origin": "external_tool_result_not_authenticated_by_phase2",
                    "methodology_verified": False,
                })
            for call in pending.calls:
                locator = _tool_target_locator(session.stage, call)
                if locator is not None:
                    # Use one current record per (stage, path); stable order
                    # prevents duplicate observations from flooding context.
                    session.artifact_references = [
                        ref for ref in session.artifact_references
                        if (ref["stage"], ref["path"]) != (locator["stage"], locator["path"])
                    ]
                    session.artifact_references.append(locator)
            # Locator projection has a character limit independent of the number
            # of authorized tool rounds; drop oldest locators first. This does
            # not limit tool execution or discard the stage's local tool history.
            while (session.artifact_references and sum(
                len(ref["path"]) + 96 for ref in session.artifact_references
            ) > MAX_TAS_ARTIFACT_TARGET_CHARS):
                session.artifact_references.pop(0)
            session.tool_rounds += 1
            session.outstanding = ()
            session.generation += 1
            session.first_verification_completed |= session.stage == "antithesis"
            return await self._advance(session, "auto")
        except BaseException:
            # Roll back protocol state on backend errors, cancellation and failed
            # successor generation. The Kernel may retry the original tool result.
            session.__dict__.clear()
            session.__dict__.update(checkpoint)
            raise
