"""Experimental Jack Kernel wiring for Deep Reasoning, including Pi live reasoning.

The module is intentionally installed only when JACK_REASONING_LEVEL selects
Deep Reasoning. It delegates generation, schema checks, filesystem guard, tool
release, pending-ID registration and result matching to the existing Jack Kernel.
It NEVER executes tools itself. Process-lifetime pending orchestration is kept
separately from client-provided conversation data. Pi live reasoning and a one-hop R3 bridge are implemented by scoped modules.
"""
from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from jack_deep_reasoning_orchestrator import (
    CompletedAnswer, DeepReasoningOrchestrator, DeepReasoningProtocolError,
    PendingToolRequest, load_exact_v6_prompts,
)


@dataclass
class _Pending:
    orchestrator: DeepReasoningOrchestrator
    proposal: PendingToolRequest
    usage: dict[str, int]
    secondary_system: str
    tools: list[dict[str, Any]]
    abandon: Callable[[], None] | None = None
    owner_key: str | None = None


def install_deep_reasoning(kernel: Any, namespace: Any) -> None:
    """Attach the scoped TAS driver to one initialized Kernel instance.

    Namespace supplies the existing Jack classes/functions. No security wrapper
    or Phase-4 tool admission function is replaced.
    """
    if not namespace.DEEP_REASONING_MODE:
        return
    HTTPException = namespace.HTTPException
    KernelResult = namespace.KernelResult
    original_prepare = kernel._prepare_commit
    original_resume = kernel._resume_tool_stage_nonstream
    pending_by_resume: dict[str, _Pending] = {}
    prompt_path = Path(namespace.__file__).resolve().parent / "tas_v6_prompts.json"
    prompts = load_exact_v6_prompts(prompt_path)
    stage_keys = {
        "thesis": "deep_reasoning_thesis",
        "antithesis": "deep_reasoning_antithesis",
        "synthesis": "deep_reasoning_synthesis",
    }
    # Experimental strict capability binding; no user content authorizes ownership.
    strict_owner = os.environ.get("JACK_TAS_R3_OWNER_ENFORCEMENT", "0") == "1"
    from jack_tas_r3_owner import current_owner as current_tas_owner

    def error(exc: Exception) -> HTTPException:
        return HTTPException(status_code=502, detail=f"Deep Reasoning protocol: {exc}")

    async def _register_pending(
        value: PendingToolRequest,
        orchestrator: DeepReasoningOrchestrator,
        usage: dict[str, int],
        secondary_system: str,
        tools: list[dict[str, Any]],
        abandon: Callable[[], None] | None = None,
    ) -> Any:
        stage_key = stage_keys[value.stage]
        synthetic = {
            "choices": [{
                "message": {"role": "assistant", "content": "", "tool_calls": list(value.calls)},
                "finish_reason": "tool_calls",
            }]
        }
        # The calls were produced by the Kernel's _run_stage, which already ran
        # tool/schema and Phase-4 authorization before the host is asked to execute.
        released = await kernel._register_stage_tool_resume(
            stage_key=stage_key,
            history=[{k:v for k,v in m.items() if k not in {"reasoning_content", "reasoning", "thinking"}}
                     for m in value.session.messages],
            secondary_system=secondary_system,
            usage=usage,
            tools=tools,
            tool_choice="auto",
            data=synthetic,
        )
        call_id = value.calls[0]["id"]
        async with kernel._pending_tool_resume_lock:
            live = kernel._pending_tool_resumes.get(call_id)
            if live is None:
                raise HTTPException(status_code=500, detail="Deep Reasoning pending call missing after registration")
            rid = live.resume_id
        if rid in pending_by_resume:
            raise HTTPException(status_code=409, detail="Deep Reasoning resume ID collision")
        pending_by_resume[rid] = _Pending(orchestrator, value, usage, secondary_system, tools, abandon,
                                          current_tas_owner() if strict_owner else None)
        # Jack's shared stage-resume function predates Deep Reasoning and may
        # attach a provisional stage message to its tool-call response. In TAS,
        # Thesis and Antithesis have zero user-facing answer authority. A tool
        # checkpoint must release *only* host-authorized structured tool calls.
        # Do not expose interim native reasoning on the caller's thinking field.
        if released.finish_reason != "tool_calls" or not released.tool_calls:
            pending_by_resume.pop(rid, None)
            await kernel._retire_pending_tool_resume(live)
            raise HTTPException(status_code=502, detail="Deep Reasoning tool checkpoint returned no releasable calls")
        return KernelResult(
            content=None,
            tool_calls=copy.deepcopy(released.tool_calls),
            finish_reason="tool_calls",
            usage=namespace.normalize_usage(dict(released.usage)),
            reasoning_content=None,
        )

    async def _cleanup_expired_pending() -> None:
        # The Kernel owns expiry; TAS must not retain orphaned active sessions
        # after an expired/consumed host checkpoint is removed.
        async with kernel._pending_tool_resume_lock:
            expire = getattr(kernel, "_expire_pending_tool_resumes_locked", None)
            if expire is not None:
                await expire()
            active = {state.resume_id for state in kernel._pending_tool_resumes.values()}
        for rid in list(pending_by_resume):
            if rid not in active:
                orphan = pending_by_resume.pop(rid, None)
                if orphan is not None and orphan.abandon is not None:
                    # Tool checkpoint expired or was retired by Jack before
                    # the receiving Thesis completed. Its single-hop R3 lease
                    # must be released for a bounded same-turn retry.
                    orphan.abandon()

    def _finish(answer: CompletedAnswer, usage: dict[str, int], *, user_request: str) -> Any:
        # Host-produced Synthesis is the only source of a future R3 frontier.
        # The Pi SSE layer may suppress outward reasoning without losing this
        # process-local, bounded one-hop bridge.
        if preserve_enabled:
            bridge.publish(
                user_request=user_request,
                answer=answer.answer,
                reasoning=answer.synthesis_native_reasoning,
                owner_key=current_tas_owner() if strict_owner else None,
            )
        return KernelResult(
            content=answer.answer,
            tool_calls=None,
            finish_reason="stop",
            usage=namespace.normalize_usage(usage),
            # ONLY Stage-3 native reasoning, not a joined Stage-1/2/3 transcript.
            reasoning_content=answer.synthesis_native_reasoning or None,
        )

    async def _prepare(request_body: dict[str, Any]) -> Any:
        await _cleanup_expired_pending()
        messages = request_body.get("messages")
        if not isinstance(messages, list) or not namespace.has_user_message(messages):
            raise HTTPException(status_code=400, detail="Deep Reasoning requires user messages")
        current = namespace.active_response_target(messages)
        if not current or not str(current.get("content") or "").strip():
            raise HTTPException(status_code=400, detail="Deep Reasoning requires a nonempty text request")
        caller_tools = request_body.get("tools") or []
        if not isinstance(caller_tools, list):
            raise HTTPException(status_code=400, detail="Deep Reasoning tools must be a list")
        tools = copy.deepcopy(caller_tools)
        secondary_system = namespace.merged_secondary_system_prompt(messages)
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        original_request = str(current["content"])

        # Reconstruct visible dialogue only. Never trust caller-supplied
        # reasoning_content / reasoning / thinking from earlier turns.
        history: list[dict[str, str]] = []
        for item in messages[: current["history_index"]]:
            if not isinstance(item, dict) or item.get("role") not in ("user", "assistant"):
                continue
            if item.get("tool_calls") or item.get("_jack_internal_stage_generation_trigger"):
                continue
            content = item.get("content")
            # Pi sends text turns as structured content parts. The active user
            # request is canonically serialized by Jack's _content_to_text;
            # use that SAME representation for historical user turns. Otherwise
            # the host drops the preceding user turn and loses the one-hop R3
            # eligibility pair, as well as ordinary historical user context.
            if item["role"] == "user" and content is not None and not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False, separators=(",", ":"))
            if isinstance(content, str) and content:
                history.append({"role": item["role"], "content": content})

        # ONE-HOP: prior completed Synthesis R3+A3 is eligible only to the
        # next Thesis if a matching host-owned frontier exists. Retain ordinary
        # visible history if the global Preserve Thinking switch is OFF.
        prior_synthesis = None
        reservation_token = None
        if preserve_enabled:
            # Reserve the one-hop R3, but preserve complete committed history for
            # every role; next_thesis_messages attaches R3 to the matching prior
            # assistant without duplicating that user/answer pair.
            _, prior_synthesis, reservation_token = bridge.reserve(
                history, owner_key=current_tas_owner() if strict_owner else None)
            if prior_synthesis is not None:
                namespace.LOG.info(
                    "Deep Reasoning one-hop R3 restored to next Thesis; chars=%d",
                    len(prior_synthesis.reasoning),
                )

        def release_r3_reservation() -> None:
            nonlocal prior_synthesis, reservation_token
            if reservation_token is not None:
                bridge.release(reservation_token)
                reservation_token = None
                prior_synthesis = None

        async def adapter(**params: Any) -> dict[str, Any]:
            nonlocal prior_synthesis, reservation_token
            stage = str(params["stage"])
            offered = params["tools"]
            choice = params["tool_choice"]
            # First Antithesis request prefers the exact Python tool that TAS v6
            # used, when it is among caller-authorized schemas.
            if stage == "antithesis" and choice == "required":
                python = [t for t in offered if isinstance(t, dict)
                          and isinstance(t.get("function"), dict)
                          and t["function"].get("name") == "python_repl"]
                if python:
                    offered = python
            # The incoming message projection, not the preserve flag, enforces
            # TAS independence. Only the completed previous R3 may enter Thesis.
            r3_bridge = bool(
                stage == "thesis"
                and prior_synthesis is not None
                and any(
                    isinstance(m, dict) and m.get("role") == "assistant"
                    and m.get("reasoning_content") == prior_synthesis.reasoning
                    for m in params["messages"]
                )
            )
            # A tool result resumes the SAME role, never a new role. Backend
            # continuation permission is scoped to this active stage only;
            # global Preserve Thinking OFF must not authorize native replay.
            resumed_stage = bool(preserve_enabled and any(
                isinstance(m, dict) and m.get("role") == "tool"
                for m in params["messages"]
            ))
            extra = {"same_stage_resume": True} if (r3_bridge or resumed_stage) else {}
            from deep_reasoning_pi_stream import current_reasoning_sink
            sink = current_reasoning_sink()
            if sink is None:
                # Non-streaming requests retain the original host-authorized path.
                data = await kernel._run_stage(
                    params["messages"], secondary_system, stage_keys[stage], usage,
                    tools=offered, tool_choice=choice, append=False, **extra,
                )
            else:
                # Reuse Jack's existing streaming stage engine, including its
                # tool validation, filesystem policy, and release restrictions.
                # All visible stage drafts stay private; only reasoning tokens
                # enter Pi's observer channel until Synthesis commits.
                sink.offer("reasoning", "\n[" + stage.upper() + "]\n")
                data = None
                async for packet in kernel._run_stage_streamed(
                    params["messages"], secondary_system, stage_keys[stage], usage,
                    tools=offered, tool_choice=choice, append=False, **extra,
                ):
                    if packet.get("kind") == "reasoning":
                        sink.offer("reasoning", str(packet.get("text") or ""))
                    elif packet.get("kind") == "keepalive":
                        sink.offer("keepalive", ":")
                    elif packet.get("kind") == "result":
                        data = packet["data"]
                if data is None:
                    raise DeepReasoningProtocolError("streaming stage produced no authoritative result")
            choice_response = (data.get("choices") or [{}])[0]
            message = dict((choice_response.get("message") or {}))
            # Keep transport diagnostics privately on the adapter response, not
            # in any model-visible message, tool checkpoint, or final answer.
            message["_tas_finish_reason"] = choice_response.get("finish_reason")
            counted = (data.get("usage") or {}).get("completion_tokens")
            message["_tas_completion_tokens"] = counted if isinstance(counted, int) else None
            # Show each completed stage report in Pi's *observation* channel.
            # Use reasoning_content as transport-only display because publishing
            # A1/A2 as normal assistant content would give interim drafts final
            # answer authority in Pi's stored conversation. Never send these
            # diagnostic copies into the following stage's model input; the
            # orchestrator performs its existing explicit A1/A2 projections.
            if sink is not None and stage in ("thesis", "antithesis"):
                stage_output = message.get("content")
                if (isinstance(stage_output, str) and stage_output.strip()
                        and not message.get("tool_calls")
                        and choice_response.get("finish_reason") in (None, "stop")):
                    sink.offer(
                        "reasoning",
                        "\n[" + stage.upper() + " OUTPUT]\n"
                        + stage_output.strip() + "\n",
                    )
            # Retire the old R3 only after a successful, complete next Thesis.
            # Never let the bridge linger in the subsequent evaluator adapter.
            if stage == "thesis" and reservation_token is not None:
                content = message.get("content")
                if (isinstance(content, str) and content.strip()
                        and not message.get("tool_calls")
                        and choice_response.get("finish_reason") in (None, "stop")):
                    if not bridge.retire(reservation_token):
                        raise DeepReasoningProtocolError("R3 reservation expired before Thesis completion")
                    namespace.LOG.info("Deep Reasoning one-hop R3 consumed after successful Thesis")
                    reservation_token = None
                    prior_synthesis = None
            return message

        # One common continuation rule for R1, R2, and R3. Enabled whenever
        # the user's Preserve Thinking setting is ON; TAS-only emergency
        # disable is available without modifying global settings.
        preserve_stage_native = bool(
            preserve_enabled
            and os.environ.get("JACK_TAS_STAGE_NATIVE_TOOL_CONTINUITY", "1") != "0"
        )
        # A universal 20-call ceiling was never tied to task resources. Let
        # the operator explicitly configure a per-stage round cap if needed.
        # Unset/0 means TAS adds no numeric ceiling; Jack's existing tool
        # authorization, validation, and host resource controls still apply.
        rounds_text = os.environ.get("JACK_TAS_MAX_TOOL_ROUNDS", "0")
        try:
            max_rounds = int(rounds_text)
        except (ValueError, TypeError) as exc:
            raise DeepReasoningProtocolError(
                "JACK_TAS_MAX_TOOL_ROUNDS must be an integer >= 0"
            ) from exc
        if max_rounds < 0:
            raise DeepReasoningProtocolError(
                "JACK_TAS_MAX_TOOL_ROUNDS must be an integer >= 0"
            )
        orchestrator = DeepReasoningOrchestrator(
            adapter, prompts=prompts, tools=tools,
            max_tool_rounds=max_rounds or None,
            preserve_stage_tool_reasoning=preserve_stage_native,
        )
        try:
            result = await orchestrator.start(
                request=original_request,
                visible_history=history,
                prior_synthesis=prior_synthesis,
                preserve_thinking=bool(preserve_enabled and prior_synthesis is not None),
                # Authorize meaningful tool tests without forcing a first call simply
                # because the caller supplied a tool surface. A required call
                # on a creative/no-evidence request is not verification.
                require_verification=False,
            )
        except BaseException as exc:
            # Failed or cancelled Thesis may retry its one allowed R3 handoff.
            # After Thesis succeeds the reservation is already retired.
            release_r3_reservation()
            if isinstance(exc, (DeepReasoningProtocolError, ValueError)):
                raise error(exc) from exc
            raise
        if isinstance(result, PendingToolRequest):
            try:
                return await _register_pending(
                    result, orchestrator, usage, secondary_system, tools,
                    abandon=release_r3_reservation,
                )
            except BaseException:
                release_r3_reservation()
                raise
        return _finish(result, usage, user_request=original_request)

    async def _resume(state: Any, tool_messages: list[dict[str, Any]]) -> Any:
        await _cleanup_expired_pending()
        active = pending_by_resume.get(state.resume_id)
        if active is None:
            raise HTTPException(status_code=409, detail="Deep Reasoning active tool session expired or unavailable")
        if strict_owner and (not active.owner_key or active.owner_key != current_tas_owner()):
            raise HTTPException(status_code=409, detail="Deep Reasoning tool checkpoint session owner mismatch")
        ids = [m.get("tool_call_id") for m in tool_messages]
        if len(ids) != len(set(ids)):
            raise HTTPException(status_code=409, detail="Deep Reasoning received repeated tool result IDs")
        try:
            proposal = await active.orchestrator.resume(
                active.proposal,
                results=[{"tool_call_id": str(m["tool_call_id"]), "content": str(m.get("content") or "")}
                         for m in tool_messages],
            )
        except (DeepReasoningProtocolError, ValueError, TypeError) as exc:
            raise error(exc) from exc
        if isinstance(proposal, PendingToolRequest):
            released = await _register_pending(
                proposal, active.orchestrator, active.usage, active.secondary_system,
                active.tools, abandon=active.abandon,
            )
        else:
            released = _finish(proposal, active.usage, user_request=active.proposal.session.request)
        await kernel._retire_pending_tool_resume(state)
        pending_by_resume.pop(state.resume_id, None)
        return released

    async def wrapped_prepare(request_body: dict[str, Any]) -> Any:
        return await _prepare(request_body)

    async def wrapped_resume(state: Any, tool_messages: list[dict[str, Any]]) -> Any:
        if state.stage_key in stage_keys.values():
            return await _resume(state, tool_messages)
        return await original_resume(state, tool_messages)

    # Pi normally replays prior tool calls and results in later user turns.
    # If a failed TAS continuation left its checkpoint live, those historical
    # results must NEVER resurrect an obsolete TAS transaction instead of
    # answering the new user request. Restrict checkpoint matching to the
    # host-selected active user turn. This is TAS-only; all other Jack modes
    # retain the original pending-tool admission path unchanged.
    prior_consume = getattr(kernel, "_consume_pending_tool_resume", None)
    if callable(prior_consume):
        async def tas_current_turn_pending_consume(messages):
            eligible_messages = messages
            if isinstance(messages, list):
                active_target = namespace.active_response_target(messages)
                if isinstance(active_target, dict):
                    start = active_target.get("history_index")
                    if isinstance(start, int) and 0 <= start < len(messages):
                        # Preserve the current user message and subsequent tool
                        # protocol. Only earlier historical results are excluded
                        # from *checkpoint selection*, not from caller history.
                        eligible_messages = messages[start:]
            return await prior_consume(eligible_messages)
        kernel._consume_pending_tool_resume = tas_current_turn_pending_consume

    kernel._prepare_commit = wrapped_prepare
    kernel._resume_tool_stage_nonstream = wrapped_resume

    from deep_reasoning_pi_stream import deep_reasoning_pi_stream
    from jack_deep_reasoning_bridge import OneHopSynthesisBridge
    bridge = OneHopSynthesisBridge(require_owner=strict_owner)
    preserve_enabled = bool(getattr(getattr(namespace, "CFG", None), "preserve_thinking", False))

    # Pi receives native reasoning deltas live. It never receives provisional
    # stage answers, unapproved tool calls, or cross-stage reasoning as input.
    async def pi_stream(request_body: dict[str, Any]):
        async for frame in deep_reasoning_pi_stream(kernel, request_body, namespace):
            yield frame

    kernel._deep_reasoning_pi_stream = pi_stream
    kernel._deep_reasoning_phase3_nonstream_enabled = True
