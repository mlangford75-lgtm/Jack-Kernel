"""Flash single-stage commit and durable trailing Work-ID regression tests."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def kernel(tmp_path, monkeypatch):
    monkeypatch.setenv("JACK_REASONING_LEVEL", "agentic")
    monkeypatch.setenv("JACK_AGENTIC_PROFILE", "flash")
    monkeypatch.setenv("JACK_BACKEND_PROFILE", "lmstudio")
    monkeypatch.setenv("JACK_BACKEND_MODEL", "test-model")
    monkeypatch.setenv("JACK_FORENSIC_ARCHIVE_MODE", "off")
    monkeypatch.setenv("JACK_AGENTIC_FORENSIC_DB", str(tmp_path / "flash.sqlite3"))
    monkeypatch.setenv("JACK_AGENTIC_TASK_ANCHOR", "1")
    name = "jack_flash_direct_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, ROOT / "jack_kernel.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    assert module.AGENTIC_FLASH_MODE
    assert not module.STAGES["extended_initial"].thinking
    return module


def commit(kernel, question="Original request", answer="Exact answer\n"):
    history = [{"role": "user", "content": question}]
    original_question = history[0]["content"]
    work_id = kernel._agentic_begin_turn(history, fresh=True)
    assert work_id.startswith("jack-turn-")
    model_view = kernel.BACKEND._stage_messages_for_profile(
        history, kernel.STAGES["extended_initial"]
    )
    # Flash must not insert a random Work ID before historical context
    # or into the current request; even optional task anchors remain host-only.
    assert not any(work_id in json.dumps(item) for item in model_view)
    assert history[0]["content"] == original_question
    frozen = kernel.append_extended_candidate_response(
        history, {"role": "assistant", "content": answer}
    )
    assert frozen == answer
    result = kernel.KERNEL._complete_flash_stage1(
        history, {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
        frozen,
    )
    return work_id, result


def test_flash_commits_from_stage1_without_stage2(kernel):
    work_id, result = commit(kernel)
    label = kernel._agentic_visible_turn_label(work_id)
    assert result.content == "Exact answer\n" + "\n\n[Agentic Turn ID: " + label + "]""
    recovered, frozen = kernel._agentic_unwrap_flash_trailing_id(result.content)
    assert recovered == work_id and frozen == "Exact answer\n"
    row = kernel._agentic_forensic_journal().get(work_id)
    assert row["status"] == "complete"
    assert row["stage2_attempt"] is None
    assert row["memory_chars"] == 0
    assert row["receipt_chars"] == 0
    assert row["a1_sha256"] == kernel._sha256_text(frozen)
    assert row["wire_sha256"] == kernel._sha256_text(result.content)


def test_flash_history_reconstructs_after_journal_restart(kernel):
    work_id, result = commit(kernel)
    kernel._AGENTIC_TURN_LIFECYCLES.clear()
    kernel._AGENTIC_FORENSIC_JOURNAL = None
    inputs = [
        {"role": "user", "content": "Original request"},
        {"role": "assistant", "content": result.content},
        {"role": "user", "content": "Second request"},
    ]
    original = json.dumps(inputs, sort_keys=True)
    projected = kernel.compact_incoming_history(inputs)
    assert json.dumps(inputs, sort_keys=True) == original
    assert projected[1]["role"] == "assistant"
    assert projected[1]["content"] == "Exact answer\n"
    assert "[Agentic Turn ID:" not in json.dumps(projected)
    assert projected[1]["_jack_forensic_turn_id"] == work_id
    assert projected[-1]["content"] == "Second request"
    successor = kernel._agentic_begin_turn(projected, fresh=True)
    assert successor != work_id
    assert kernel._agentic_forensic_journal().ledger(successor)["scope_origin"] == "verified_predecessor"
    model_view = kernel.BACKEND._stage_messages_for_profile(
        projected, kernel.STAGES["extended_initial"]
    )
    assert not any("Work ID" in json.dumps(item) for item in model_view)
    assert not any(successor in json.dumps(item) for item in model_view)


def test_flash_tampered_trailer_cannot_claim_prior_turn(kernel):
    work_id, result = commit(kernel)
    label = kernel._agentic_visible_turn_label(work_id)
    tampered = result.content.replace(label, ("A" if label[0] != "A" else "B") + label[1:])
    messages = [
        {"role": "user", "content": "Original request"},
        {"role": "assistant", "content": tampered},
        {"role": "user", "content": "Second request"},
    ]
    projected = kernel.compact_incoming_history(messages)
    assert projected[1]["content"] == tampered
    assert "_jack_forensic_turn_id" not in projected[1]
    assert kernel._agentic_forensic_journal().get(work_id)["status"] == "complete"


def test_flash_distinct_turns_do_not_change_leading_prompt(kernel):
    first_id, first = commit(kernel, "A", "First")
    model_view = kernel.BACKEND._stage_messages_for_profile(
        [{"role": "user", "content": "B"}], kernel.STAGES["extended_initial"]
    )
    assert not any("Authenticated current work ID:" in json.dumps(m) for m in model_view)
    assert kernel._agentic_unwrap_flash_trailing_id(first.content)[0] == first_id


def test_flash_stream_calls_backend_once_and_has_no_stage2(kernel):
    import asyncio
    import httpx

    calls = []

    def responder(request):
        calls.append(json.loads(request.content))
        chunks = [
            {"choices": [{"index": 0, "delta": {"content": "Flash response"}, "finish_reason": None}]},
            {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
             "usage": {"prompt_tokens": 45, "completion_tokens": 3, "total_tokens": 48}},
        ]
        return httpx.Response(
            200,
            text="".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks)
                 + "data: [DONE]\n\n",
            headers={"content-type": "text/event-stream"},
        )

    async def run():
        backend = kernel.BACKEND
        await backend._client.aclose()
        backend._client = httpx.AsyncClient(transport=httpx.MockTransport(responder))

        async def resolve():
            return "test-model"

        backend.resolve_model = resolve
        chunks = []
        try:
            async for chunk in kernel.KERNEL.stream({
                "model": "jack-kernel",
                "stream": True,
                "messages": [{"role": "user", "content": "Say hello"}],
            }):
                chunks.append(chunk)
        finally:
            await backend._client.aclose()
        return chunks

    wire = b"".join(asyncio.run(run())).decode("utf-8")
    assert len(calls) == 1, "Flash must make exactly one backend request"
    assert "data: [DONE]\n\n" in wire
    assert "Flash response" in wire
    assert "Agentic Turn ID:" in wire
    assert "STAGE 2 REASONING DISTILLATION" not in wire
    assert calls[0]["messages"][0]["role"] == "system"
    assert "Authenticated current work ID:" not in calls[0]["messages"][0]["content"]
    assert "reasoning_effort" in calls[0]
    assert calls[0]["reasoning_effort"] == "none"


def test_previous_flash_trailer_remains_recoverable(kernel):
    work_id, response = commit(kernel, "Legacy request", "Legacy answer")
    shortened = response.content
    assert shortened.endswith("]")
    old_label = shortened.replace("[Agentic Turn ID:", "[Jack Work ID:")
    journal = kernel._agentic_forensic_journal()
    # Old completed artifacts had a different byte-exact wire fingerprint.
    # Simulate an original legacy commit without changing the model answer.
    with journal._write() as db:
        db.execute(
            "UPDATE turns SET wire_sha256=? WHERE turn_id=?",
            (kernel._sha256_text(old_label), work_id),
        )
    projected = kernel.compact_incoming_history([
        {"role": "user", "content": "Legacy request"},
        {"role": "assistant", "content": old_label},
        {"role": "user", "content": "Next request"},
    ])
    assert projected[1]["content"] == "Legacy answer"
    assert projected[1]["_jack_forensic_turn_id"] == work_id
    successor = kernel._agentic_begin_turn(projected, fresh=True)
    assert journal.ledger(successor)["scope_origin"] == "verified_predecessor"
