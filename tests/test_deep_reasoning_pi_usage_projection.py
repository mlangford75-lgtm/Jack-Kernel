"""Deep Reasoning Pi context: preserve aggregate compute, project per-response peak."""
import asyncio
from types import SimpleNamespace
import pytest

from jack_deep_reasoning_usage import ResponseUsage, install_deep_reasoning_usage

A = {"prompt_tokens": 26000, "completion_tokens": 2000, "total_tokens": 28000}
B = {"prompt_tokens": 27500, "completion_tokens": 2500, "total_tokens": 30000}
C = {"prompt_tokens": 31700, "completion_tokens": 3300, "total_tokens": 35000}
D = {"prompt_tokens": 29000, "completion_tokens": 3000, "total_tokens": 32000}


def plus(*records):
    return {key: sum(r.get(key, 0) for r in records)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")}


class Backend:
    async def chat(self, *, record, **kwargs):
        return {"usage": dict(record)}

    async def chat_stream(self, *, records, **kwargs):
        for record in records:
            yield {"usage": dict(record), "choices": []}


class Kernel:
    def __init__(self):
        self.backend = Backend()
        self.payloads = []

    async def _run_impl(self, body):
        baseline = body.get("baseline", plus())
        aggregate = dict(baseline)
        for kind, records in body["requests"]:
            self.payloads.append((kind, records))
            if kind == "stream":
                async for chunk in self.backend.chat_stream(records=records, messages=[{"role": "user", "content": "unchanged"}]):
                    aggregate = plus(aggregate, chunk["usage"])
            else:
                result = await self.backend.chat(record=records, messages=[{"role": "user", "content": "unchanged"}])
                aggregate = plus(aggregate, result["usage"])
        return SimpleNamespace(usage={k: aggregate[k] - baseline[k] for k in aggregate},
                               content="A3", tool_calls=None, finish_reason="stop", reasoning_content="R3")


def configured(adapter="pi"):
    kernel = Kernel()
    ns = SimpleNamespace(_phase4_current_executor_context=lambda: SimpleNamespace(adapter=adapter) if adapter else None)
    install_deep_reasoning_usage(kernel, ns)
    return kernel


def run(kernel, *requests, baseline=None):
    return asyncio.run(kernel._run_impl({"requests": list(requests), "baseline": baseline or plus()}))


def test_three_stage_peak_after_response_delta():
    assert run(configured(), ("nonstream", A), ("nonstream", B), ("nonstream", C)).usage == C


@pytest.mark.parametrize("adapter", ["other", None, "pi_fake"])
def test_non_pi_reports_aggregate(adapter):
    assert run(configured(adapter), ("nonstream", A), ("nonstream", B), ("nonstream", C)).usage == plus(A, B, C)


def test_checkpoint_response_and_resumed_response_are_separate():
    kernel = configured()
    first = run(kernel, ("nonstream", A), ("nonstream", B))
    second = run(kernel, ("nonstream", C), ("nonstream", D), baseline=plus(A, B))
    assert first.usage == B
    assert second.usage == C
    assert plus(A, B, C, D)["total_tokens"] == 125000


def test_stream_and_recovery_request_are_observed_separately():
    assert run(configured(), ("stream", [A]), ("nonstream", B), ("stream", [C])).usage == C


def test_ambiguous_stream_usage_conservatively_falls_back():
    assert run(configured(), ("stream", [A, B]), ("nonstream", C)).usage == plus(A, B, C)


@pytest.mark.parametrize("bad", [
    {}, {"prompt_tokens": "bad", "completion_tokens": 1, "total_tokens": 1},
    {"prompt_tokens": -1, "completion_tokens": 1, "total_tokens": 1},
    {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 22},
    {"prompt_tokens": 1, "completion_tokens": 2},
])
def test_invalid_or_missing_telemetry_never_projects_downward(bad):
    scope = ResponseUsage()
    scope.observe(A)
    scope.observe(bad)
    scope.observe(C)
    fallback = plus(A, C)
    assert scope.projection(fallback) == fallback


def test_mismatched_reports_do_not_lower_aggregate():
    scope = ResponseUsage()
    scope.observe(A)
    scope.observe(B)
    assert scope.projection(plus(A, B, C)) == plus(A, B, C)


def test_simultaneous_calls_do_not_share_scope():
    kernel = configured()
    async def both():
        return await asyncio.gather(
            kernel._run_impl({"requests": [("nonstream", A), ("nonstream", C)]}),
            kernel._run_impl({"requests": [("nonstream", B), ("nonstream", D)]}),
        )
    one, two = asyncio.run(both())
    assert one.usage == C and two.usage == D
