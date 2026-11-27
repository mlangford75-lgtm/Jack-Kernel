from __future__ import annotations

import ast
import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
GUARD_PATH = ROOT / "jack_evidence_guard.py"
KERNEL_PATH = ROOT / "jack_kernel.py"
RESPONSES_PATH = ROOT / "jack_responses_compat.py"


SPEC = importlib.util.spec_from_file_location(
    "jack_retro_phase0_2_guard",
    GUARD_PATH,
)

guard = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = guard
assert SPEC.loader is not None
SPEC.loader.exec_module(guard)

import jack_kernel as kernel


DONE = b"data: [DONE]\n\n"


def function_source(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    matches = [
        node
        for node in ast.walk(tree)
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        )
        and node.name == name
    ]

    assert len(matches) == 1, (
        f"Expected exactly one function {name!r} in {path.name}, "
        f"found {len(matches)}"
    )

    rendered = ast.get_source_segment(
        source,
        matches[0],
    )

    assert rendered is not None
    return rendered


def choice(
    index,
    delta,
    *,
    finish_reason=None,
):
    return {
        "index": index,
        "delta": delta,
        "finish_reason": finish_reason,
    }


def event(choices):
    obj = {
        "id": "chatcmpl-retro",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": "jack-kernel",
        "choices": choices,
    }

    return (
        "data: "
        + json.dumps(
            obj,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n\n"
    ).encode("utf-8")


def single_event(
    delta,
    *,
    index=0,
    finish_reason=None,
):
    return event(
        [
            choice(
                index,
                delta,
                finish_reason=finish_reason,
            )
        ]
    )


def data_obj(chunk):
    text = (
        chunk.decode("utf-8", "replace")
        if isinstance(chunk, (bytes, bytearray))
        else str(chunk)
    )

    if text.strip() == "data: [DONE]":
        return None

    if not text.lstrip().startswith("data:"):
        return None

    raw = text.strip()[5:].strip()

    try:
        parsed = json.loads(raw)
    except Exception:
        return None

    return parsed if isinstance(parsed, dict) else None


def rendered_field(
    chunks,
    *,
    choice_index,
    field,
):
    rendered = ""

    for chunk in chunks:
        obj = data_obj(chunk)

        if obj is None:
            continue

        for ordinal, item in enumerate(
            obj.get("choices") or []
        ):
            if not isinstance(item, dict):
                continue

            raw_index = item.get(
                "index",
                ordinal,
            )

            try:
                index = int(raw_index)
            except (TypeError, ValueError):
                index = ordinal

            if index != choice_index:
                continue

            delta = item.get("delta")

            if not isinstance(delta, dict):
                continue

            value = delta.get(field)

            if isinstance(value, str):
                rendered += value

    return rendered


def collect(
    source,
    *,
    window,
    maximum,
):
    async def run():
        chunks = []

        async for chunk in guard._guarded_stream(
            source,
            {},
            quarantine_window=window,
            quarantine_max_window=maximum,
        ):
            chunks.append(chunk)

        return chunks

    return asyncio.run(run())


# ============================================================
# PHASE 0
# Topology must continue to route every public cognition
# release through the guarded KERNEL.run / KERNEL.stream seam.
# ============================================================


def test_phase0_chat_completion_release_topology_is_still_guardable():
    route = function_source(
        KERNEL_PATH,
        "chat_completions",
    )

    public_stream = function_source(
        KERNEL_PATH,
        "_safe_public_stream",
    )

    assert "_safe_public_stream(body)" in route
    assert "await KERNEL.run(body)" in route
    assert "KERNEL.stream(body)" in public_stream


def test_phase0_responses_release_topology_is_still_guardable():
    route = function_source(
        RESPONSES_PATH,
        "responses",
    )

    stream = function_source(
        RESPONSES_PATH,
        "_stream",
    )

    assert "jk.KERNEL.run(chat)" in route
    assert "_stream(" in route
    assert "jk.KERNEL.stream(chat)" in stream


def test_phase0_guard_wraps_kernel_before_responses_registration():
    install_source = function_source(
        KERNEL_PATH,
        "_install_bundled_runtime_extensions",
    )

    guard_install_source = function_source(
        GUARD_PATH,
        "install",
    )

    assert (
        install_source.index(
            "jack_evidence_guard.install"
        )
        <
        install_source.index(
            "jack_responses_compat.register"
        )
    )

    assert "kernel.run = guarded_run" in guard_install_source
    assert "kernel.stream = guarded_stream" in guard_install_source


# ============================================================
# PHASE 1
# Exhaustive authority semantics.
# ============================================================


def test_phase1_nonhard_set_is_exact_complement_of_hard():
    all_outcomes = set(kernel.SecurityOutcome)

    assert all_outcomes == {
        kernel.SecurityOutcome.ALLOW,
        kernel.SecurityOutcome.DENY_AND_CONTINUE,
        kernel.SecurityOutcome.REQUIRE_USER_DECISION,
        kernel.SecurityOutcome.HARD_INTERRUPT,
    }

    assert isinstance(
        kernel.NON_HARD_SECURITY_OUTCOMES,
        frozenset,
    )

    assert kernel.NON_HARD_SECURITY_OUTCOMES == (
        all_outcomes
        - {kernel.SecurityOutcome.HARD_INTERRUPT}
    )

    for outcome in all_outcomes:
        assert kernel.is_hard_security_outcome(
            outcome
        ) is (
            outcome
            is kernel.SecurityOutcome.HARD_INTERRUPT
        )


def test_phase1_plain_string_cannot_forge_hard_authority():
    assert not kernel.is_hard_security_outcome(
        "HARD_INTERRUPT"
    )

    with pytest.raises(ValueError):
        kernel.SecurityOutcome(
            "NOT_A_SECURITY_OUTCOME"
        )


# ============================================================
# PHASE 2 PRIMITIVE
# Boundedness and chunk-boundary invariance.
# ============================================================


def test_phase2_quarantine_remains_bounded_over_large_stream():
    window = 17

    quarantine = guard.StreamingIRQTextQuarantine(
        window_size=window,
        max_window=64,
    )

    text = (
        "0123456789abcdef🙂"
        * 12000
    )

    released = []

    for start in range(0, len(text), 31):
        released.append(
            quarantine.feed(
                text[start:start + 31]
            )
        )

        assert quarantine.held_length <= window

    released.append(quarantine.flush())

    assert "".join(released) == text
    assert quarantine.held_length == 0


def test_phase2_quarantine_split_invariance_across_window_matrix():
    text = "α🙂β-漢字-ABCDEFGHIJKLMN"

    for window in (0, 1, 2, 7, 16, 64):
        for split in range(len(text) + 1):
            quarantine = (
                guard.StreamingIRQTextQuarantine(
                    window_size=window,
                    max_window=64,
                )
            )

            released = (
                quarantine.feed(text[:split])
                + quarantine.feed(text[split:])
                + quarantine.flush()
            )

            assert released == text
            assert quarantine.held_length == 0


def test_phase2_independent_quarantines_cannot_cross_contaminate():
    first = guard.StreamingIRQTextQuarantine(
        window_size=3,
        max_window=64,
    )

    second = guard.StreamingIRQTextQuarantine(
        window_size=5,
        max_window=64,
    )

    first_out = ""
    second_out = ""

    first_out += first.feed("alpha-")
    second_out += second.feed("BRAVO-")
    first_out += first.feed("one")
    second_out += second.feed("TWO")
    first_out += first.flush()
    second_out += second.flush()

    assert first_out == "alpha-one"
    assert second_out == "BRAVO-TWO"


# ============================================================
# PHASE 2 STREAM BOUNDARY
# Choice, field, failure, and concurrency isolation.
# ============================================================


def test_phase2_multiple_choices_have_independent_quarantine_state():
    async def source(_body):
        yield event(
            [
                choice(
                    0,
                    {"content": "alpha-"},
                ),
                choice(
                    1,
                    {"content": "BRAVO-"},
                ),
            ]
        )

        yield event(
            [
                choice(
                    0,
                    {"content": "one"},
                ),
                choice(
                    1,
                    {"content": "TWO"},
                ),
            ]
        )

        yield event(
            [
                choice(
                    0,
                    {},
                    finish_reason="stop",
                ),
                choice(
                    1,
                    {},
                    finish_reason="stop",
                ),
            ]
        )

        yield DONE

    chunks = collect(
        source,
        window=4,
        maximum=64,
    )

    assert rendered_field(
        chunks,
        choice_index=0,
        field="content",
    ) == "alpha-one"

    assert rendered_field(
        chunks,
        choice_index=1,
        field="content",
    ) == "BRAVO-TWO"


def test_phase2_content_and_reasoning_have_independent_state():
    async def source(_body):
        yield single_event(
            {
                "content": "visible-",
                "reasoning_content": "reason-",
            }
        )

        yield single_event(
            {
                "content": "🙂tail",
                "reasoning_content": "漢字tail",
            }
        )

        yield single_event(
            {},
            finish_reason="stop",
        )

        yield DONE

    chunks = collect(
        source,
        window=5,
        maximum=64,
    )

    assert rendered_field(
        chunks,
        choice_index=0,
        field="content",
    ) == "visible-🙂tail"

    assert rendered_field(
        chunks,
        choice_index=0,
        field="reasoning_content",
    ) == "reason-漢字tail"


def test_phase2_concurrent_streams_do_not_share_quarantine_state():
    async def run_one(prefix):
        async def source(_body):
            for part in (
                prefix + "-",
                "middle-",
                "tail",
            ):
                yield single_event(
                    {"content": part}
                )
                await asyncio.sleep(0)

            yield single_event(
                {},
                finish_reason="stop",
            )
            yield DONE

        chunks = []

        async for chunk in guard._guarded_stream(
            source,
            {},
            quarantine_window=6,
            quarantine_max_window=64,
        ):
            chunks.append(chunk)

        return rendered_field(
            chunks,
            choice_index=0,
            field="content",
        )

    async def main():
        return await asyncio.gather(
            run_one("FIRST"),
            run_one("SECOND"),
            run_one("THIRD"),
        )

    results = asyncio.run(main())

    assert results == [
        "FIRST-middle-tail",
        "SECOND-middle-tail",
        "THIRD-middle-tail",
    ]


def test_phase2_ordinary_failure_flushes_all_safe_choice_tails():
    class ExpectedFailure(RuntimeError):
        pass

    async def source(_body):
        yield event(
            [
                choice(
                    0,
                    {"content": "abcdefgh"},
                ),
                choice(
                    1,
                    {"content": "ABCDEFGH"},
                ),
            ]
        )

        raise ExpectedFailure(
            "ordinary backend failure"
        )

    async def run():
        chunks = []

        try:
            async for chunk in guard._guarded_stream(
                source,
                {},
                quarantine_window=5,
                quarantine_max_window=64,
            ):
                chunks.append(chunk)

        except ExpectedFailure as exc:
            return chunks, exc

        raise AssertionError(
            "ExpectedFailure was not reraised"
        )

    chunks, exc = asyncio.run(run())

    assert str(exc) == "ordinary backend failure"

    assert rendered_field(
        chunks,
        choice_index=0,
        field="content",
    ) == "abcdefgh"

    assert rendered_field(
        chunks,
        choice_index=1,
        field="content",
    ) == "ABCDEFGH"


def test_phase2_hard_interrupt_withholds_every_unreleased_choice_tail():
    async def source(_body):
        yield event(
            [
                choice(
                    0,
                    {"content": "abcdefgh"},
                ),
                choice(
                    1,
                    {"content": "ABCDEFGH"},
                ),
            ]
        )

        raise guard.StreamingIRQHardInterrupt(
            "hard stop"
        )

    async def run():
        chunks = []

        try:
            async for chunk in guard._guarded_stream(
                source,
                {},
                quarantine_window=5,
                quarantine_max_window=64,
            ):
                chunks.append(chunk)

        except guard.StreamingIRQHardInterrupt as exc:
            return chunks, exc

        raise AssertionError(
            "StreamingIRQHardInterrupt was not reraised"
        )

    chunks, exc = asyncio.run(run())

    assert str(exc) == "hard stop"

    # Eight characters with a five-character hold:
    # only the proven-safe first three may have crossed.
    assert rendered_field(
        chunks,
        choice_index=0,
        field="content",
    ) == "abc"

    assert rendered_field(
        chunks,
        choice_index=1,
        field="content",
    ) == "ABC"

    wire = b"".join(chunks)

    assert b"defgh" not in wire
    assert b"DEFGH" not in wire


# ============================================================
# PROTOCOL ANOMALY TEST
#
# A complete malformed `data:` frame must not bypass an active
# quarantine merely because its JSON cannot be parsed.
#
# This is deliberately expected to challenge the current source.
# ============================================================


def test_phase2_malformed_data_frame_cannot_bypass_active_quarantine():
    marker = b"MODEL-ORIGINATED-UNPARSED-MATERIAL"

    malformed = (
        b'data: {"id":"retro","choices":['
        b'{"index":0,"delta":{"content":"'
        + marker
        + b'"}}]\n\n'
    )

    async def source(_body):
        yield malformed
        yield DONE

    async def run():
        chunks = []

        try:
            async for chunk in guard._guarded_stream(
                source,
                {},
                quarantine_window=8,
                quarantine_max_window=64,
            ):
                chunks.append(chunk)

        except guard.StreamingIRQProtocolError as exc:
            return chunks, exc

        raise AssertionError(
            "Malformed SSE data frame was not rejected"
        )

    chunks, exc = asyncio.run(run())
    wire = b"".join(chunks)

    assert marker not in wire
    assert str(exc) == "Malformed model stream SSE data frame"
    assert marker.decode() not in str(exc)


def test_phase2_protocol_error_is_not_hard_security_authority():
    assert issubclass(
        guard.StreamingIRQProtocolError,
        RuntimeError,
    )

    assert not issubclass(
        guard.StreamingIRQProtocolError,
        guard.StreamingIRQHardInterrupt,
    )


def test_phase2_malformed_frame_preserves_prior_safe_quarantine_tail():
    marker = b"UNPARSED-SECRET-MATERIAL"

    malformed = (
        b'data: {"choices":[{"delta":{"content":"'
        + marker
        + b'"}}]\n\n'
    )

    async def source(_body):
        yield single_event(
            {"content": "abcdefgh"}
        )

        yield malformed

    async def run():
        chunks = []

        try:
            async for chunk in guard._guarded_stream(
                source,
                {},
                quarantine_window=5,
                quarantine_max_window=64,
            ):
                chunks.append(chunk)

        except guard.StreamingIRQProtocolError as exc:
            return chunks, exc

        raise AssertionError(
            "Malformed SSE data frame was not rejected"
        )

    chunks, exc = asyncio.run(run())

    # Ordinary protocol failure is fail-soft for previously safe
    # cognition. The five held characters must be flushed.
    assert rendered_field(
        chunks,
        choice_index=0,
        field="content",
    ) == "abcdefgh"

    wire = b"".join(chunks)

    assert marker not in wire
    assert marker.decode() not in str(exc)


def test_phase2_nondata_sse_control_frame_remains_passthrough():
    heartbeat = b": keep-alive\n\n"

    async def source(_body):
        yield heartbeat
        yield DONE

    chunks = collect(
        source,
        window=8,
        maximum=64,
    )

    assert chunks[0] == heartbeat
    assert chunks[-1] == DONE
