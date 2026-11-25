"""Percentage-based deterministic Canary release controls."""
import asyncio
import json
import pytest
import jack_evidence_guard as guard
from jack_policy_integrity import RuntimePolicyAuthority, PolicyIntegrityUnavailable


def make(values, percent=100, ceiling=4096):
    return guard.build_static_runtime_canary_policy(
        runtime_id="r", lane_id="l",
        raw_json=json.dumps({"version": 1, "patterns": values,
                             "sensitivity_percent": percent, "max_window": ceiling}),
    )


def pattern(value, **kwargs):
    return {"id": "test", "tier": "B", "value": value, **kwargs}


@pytest.mark.parametrize("length", [128, 256, 512, 1024])
@pytest.mark.parametrize("percent", [5, 10, 25, 50, 100, 9])
def test_scaled_threshold_and_all_positions(length, percent):
    value = "".join(chr(0x400 + i) for i in range(length))
    policy = make([pattern(value)], percent)
    width = (length * percent + 99) // 100
    assert policy.canaries.required_window == width - 1
    assert policy.canaries.find(value[:width - 1]) is None
    for offset in (0, (length - width) // 2, length - width):
        fragment = value[offset:offset + width]
        assert policy.canaries.find(fragment).canary_id == "test"
        for split in {0, 1, width // 2, width - 1}:
            detector = guard.StreamingCanaryDetector(policy.canaries)
            first, matched = detector.feed_guarded("safe:" + fragment[:split])
            assert matched is None
            second, matched = detector.feed_guarded(fragment[split:] + "tail")
            assert matched is not None
            assert first + second == "safe:"


def test_override_and_legacy_defaults():
    policy = make([pattern("ABCDEFGHIJKLMNOP", sensitivity_percent=100),
                   {"id": "second", "tier": "B", "value": "0123456789abcdef"}], 25)
    assert policy.canaries.required_window == 15
    assert policy.canaries.find("ABCD") is None
    assert policy.canaries.find("4567").canary_id == "second"
    assert policy.canaries.find("ABCDEFGHIJKLMNOP").canary_id == "test"
    assert make([pattern("ABCDEFGHIJKLMNOP")]).canaries.find("ABCDEFGH") is None


@pytest.mark.parametrize("percent", [0, 101, True, 2.5, "10"])
def test_invalid_percent(percent):
    with pytest.raises(RuntimeError):
        make([pattern("ABCDEFGHIJKLMNOP")], percent)


def test_reject_insufficient_window():
    with pytest.raises(RuntimeError, match="over-window"):
        make([pattern("A" * 1024)], 50, 20)


def test_native_reasoning_and_tool_argument_release():
    value = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    policy = make([pattern(value)], 25)
    width = (len(value) * 25 + 99) // 100
    fragment = value[12:12 + width]

    async def run(field):
        async def source(_):
            for piece in ("safe:", fragment[:3], fragment[3:]):
                delta = ({field: piece} if field != "tool_calls" else
                         {"tool_calls": [{"index": 0, "function": {"arguments": piece}}]})
                yield ("data: " + json.dumps({"choices": [{"index": 0, "delta": delta,
                       "finish_reason": None}]}) + "\n\n").encode()
        released = []
        with pytest.raises(guard.StreamingIRQCanaryInterrupt):
            async for packet in guard._guarded_stream(source, {}, canaries=policy.canaries):
                released.append(packet)
        assert fragment not in b"".join(released).decode()
    for field in ("content", "reasoning_content", "reasoning", "thinking", "tool_calls"):
        asyncio.run(run(field))


def test_sensitivity_integrity():
    policy = make([pattern("ABCDEFGHIJKLMNOP")], 25)
    authority = RuntimePolicyAuthority()
    def owner():
        return policy
    authority.register_cell(label="test", kind="canary", cell=owner.__closure__[0])
    authority.seal()
    authority.verify_for("test")
    object.__setattr__(policy.canaries._patterns[0], "sensitivity_percent", 100)
    with pytest.raises(PolicyIntegrityUnavailable):
        authority.verify_for("test")
