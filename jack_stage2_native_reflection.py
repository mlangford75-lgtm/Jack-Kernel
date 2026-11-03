"""Opt-in Stage-2 native-reasoning extension transport contract.

This module does NOT claim that OpenAI-compatible SSE can alter token sampling.
A real adapter must suppress the first reasoning-to-final boundary BEFORE it is
committed, inject the provided text into the active decoder/KV state, and then
resume the same streamed inference. The existing OpenAICompatibleBackend does
not advertise this capability and takes the byte-identical normal path.

No model-name guessing, no second inference, no historical/prompt changes.
"""
from __future__ import annotations

from typing import Any, AsyncIterator, Dict, Tuple

PROTOCOL = "jack.stage2.native-reflection.precommit.v1"
INSTRUCTION = (
    "Hold on, I need to ensure I've included everything that helps "
    "later turns recall this work."
)


class NativeReflectionContractError(RuntimeError):
    """A claimed pre-commit extension violated the stream contract."""


def select_stream(
    backend: Any,
    *,
    enabled: bool,
    stage_key: str,
    agentic_mode: bool,
    stream_kwargs: Dict[str, Any],
) -> Tuple[AsyncIterator[Dict[str, Any]], bool]:
    """Return (stream, native_extension_selected).

    Only an explicitly capable backend with a pre-commit adapter gets the
    extension. Missing capability always uses the ORIGINAL streaming call.
    Capability checks are local and require no extra backend request.
    """
    if enabled and agentic_mode and stage_key == "extended_reflection":
        probe = getattr(backend, "native_reflection_capability", None)
        native_stream = getattr(backend, "chat_stream_with_native_reflection", None)
        if callable(probe) and callable(native_stream) and probe() == PROTOCOL:
            return (
                verify_native_reflection_stream(
                    native_stream(
                        **stream_kwargs,
                        reflection_instruction=INSTRUCTION,
                        max_reflections=1,
                    )
                ),
                True,
            )
    return backend.chat_stream(**stream_kwargs), False


async def verify_native_reflection_stream(
    stream: AsyncIterator[Dict[str, Any]],
) -> AsyncIterator[Dict[str, Any]]:
    """Validate the adapter's host-origin injection receipt in-band.

    The adapter MUST send exactly one private receipt between model-native
    reasoning and resumed native reasoning, before visible memory begins:
      {"_jack_native_reflection_receipt": {
          "protocol": PROTOCOL, "event": "injected", "text": INSTRUCTION
      }}
    It then streams the continued native reasoning and memory normally.
    The receipt is never forwarded as model content or tool output. This
    checks transport correctness, not cognitive benefit or backend honesty.
    A model with no reasoning may finish unmodified with zero receipts.

    Once an adapter stream begins, an invalid/missing receipt is a hard
    contract error, NOT an automatic retry that might duplicate output.
    """
    receipts = 0
    saw_reasoning = False
    saw_resumed_reasoning = False
    saw_content = False
    expected = {"protocol": PROTOCOL, "event": "injected", "text": INSTRUCTION}
    async for chunk in stream:
        receipt = chunk.get("_jack_native_reflection_receipt")
        if receipt is not None:
            if receipt != expected or receipts or not saw_reasoning or saw_content:
                raise NativeReflectionContractError(
                    "Invalid, duplicate, or late Stage-2 native reflection receipt"
                )
            receipts = 1
            continue
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
            if reasoning:
                saw_reasoning = True
                if receipts:
                    saw_resumed_reasoning = True
            if delta.get("content"):
                saw_content = True
                if saw_reasoning and (receipts != 1 or not saw_resumed_reasoning):
                    raise NativeReflectionContractError(
                        "Stage-2 memory started without verified native reflection"
                    )
        yield chunk
    if receipts and not saw_resumed_reasoning:
        raise NativeReflectionContractError(
            "Native reflection receipt was not followed by continued reasoning"
        )
    if saw_reasoning and saw_content and receipts != 1:
        raise NativeReflectionContractError(
            "Native reasoning transitioned to memory without reflection receipt"
        )
