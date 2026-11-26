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


@pytest.mark.parametrize("use_adaptive", [False, True])
def test_native_reasoning_and_tool_argument_release(use_adaptive):
    value = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    policy = adaptive([pattern(value)]) if use_adaptive else make([pattern(value)], 25)
    width = policy.canaries._patterns[0].match_chars
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

@pytest.mark.parametrize("percent", [1, 5, 9, 10, 25, 50, 99, 100])
def test_partial_match_matches_exhaustive_oracle(percent):
    import random
    rng = random.Random(116)
    for length in (8, 19, 128, 1024):
        value = "".join(rng.choice("ABCD0123456789") for _ in range(length))
        policy = make([pattern(value)], percent)
        width = (length * percent + 99) // 100
        for size in (width - 1, width, width + 1, length * 2):
            text = "".join(rng.choice("ABCD0123456789") for _ in range(size))
            expected = next((i for i in range(len(text) - width + 1)
                             if text[i:i + width] in value), None)
            found = policy.canaries._find_with_position(text)
            assert (found[1] if found else None) == expected


def test_long_mixed_length_canaries_with_partial_matching():
    short = "A" * 128
    long = "".join(chr(0x500 + i) for i in range(1024))
    policy = make([pattern(short, sensitivity_percent=100),
                   {"id": "long", "tier": "B", "value": long, "sensitivity_percent": 9}])
    assert policy.canaries.required_window == 127
    detector = guard.StreamingCanaryDetector(policy.canaries)
    fragment = long[600:693]
    output = ""
    for i, ch in enumerate("safe:" + fragment):
        part, match = detector.feed_guarded(ch)
        output += part
        if i < len("safe:" + fragment) - 1:
            assert match is None
        else:
            assert match.match.canary_id == "long"
    assert output == "safe:"


def adaptive(values, **settings):
    return guard.build_static_runtime_canary_policy(
        runtime_id="r", lane_id="l",
        raw_json=json.dumps({"version": 1, "patterns": values, **settings}),
    )


@pytest.mark.parametrize("length,width", [
    (8, 8), (10, 10), (15, 15), (16, 16), (17, 16), (20, 16),
    (32, 16), (48, 16), (63, 16), (64, 16), (65, 17), (128, 32),
    (256, 64), (512, 128), (1024, 256), (1025, 257),
])
def test_adaptive_threshold_and_chunk_boundary(length, width):
    value = "".join(chr(0x500 + i) for i in range(length))
    policy = adaptive([pattern(value)], max_window=4096)
    assert policy.sensitivity_percent is None
    assert policy.canaries._patterns[0].match_chars == width
    assert policy.canaries.required_window == width - 1
    for offset in {0, (length - width) // 2, length - width}:
        fragment = value[offset:offset + width]
        assert policy.canaries.find(fragment[:-1]) is None
        assert policy.canaries.find(fragment).canary_id == "test"
        for split in {0, 1, width // 2, width - 1}:
            detector = guard.StreamingCanaryDetector(policy.canaries)
            first, matched = detector.feed_guarded("safe:" + fragment[:split])
            assert matched is None
            second, matched = detector.feed_guarded(fragment[split:] + "tail")
            assert matched is not None
            assert first + second == "safe:"


def test_adaptive_inheritance_and_explicit_percentages():
    # The explicit 25% choice is not the same policy as Adaptive.
    value = "ABCDEFGHIJKLMNOP"
    default = adaptive([pattern(value)])
    explicit = adaptive([pattern(value)], sensitivity_percent=25)
    override = adaptive([pattern(value, sensitivity_percent=25)])
    assert default.canaries.required_window == 15
    assert default.canaries.find(value[:4]) is None
    for policy in (explicit, override):
        assert policy.canaries.required_window == 3
        assert policy.canaries.find(value[:4]) is not None
    assert adaptive([pattern(value)], sensitivity_percent=100).canaries.find(value[:-1]) is None
    assert guard.build_static_runtime_canary_policy(runtime_id="r", lane_id="l", raw_json="").sensitivity_percent is None


@pytest.mark.parametrize("invalid", [None, True, 0, 101, 2.5, "adaptive", "25"])
def test_adaptive_does_not_accept_malformed_explicit_overrides(invalid):
    with pytest.raises(RuntimeError):
        adaptive([pattern("ABCDEFGHIJKLMNOP")], sensitivity_percent=invalid)
    with pytest.raises(RuntimeError):
        adaptive([pattern("ABCDEFGHIJKLMNOP", sensitivity_percent=invalid)])


def test_adaptive_quarantine_ceiling_is_enforced():
    value = "A" * 1024
    assert adaptive([pattern(value)], max_window=255).canaries.required_window == 255
    with pytest.raises(RuntimeError, match="over-window"):
        adaptive([pattern(value)], max_window=254)
    # Legacy JSON's 256-character ceiling is still a ceiling, not a fixed buffer.
    assert adaptive([pattern(value)]).canaries.required_window == 255
    with pytest.raises(RuntimeError, match="over-window"):
        adaptive([pattern("A" * 1029)])


@pytest.mark.parametrize("target", ["global", "pattern"])
def test_adaptive_mode_is_bound_even_when_effective_width_is_identical(target):
    policy = adaptive([pattern("A" * 64)])
    authority = RuntimePolicyAuthority()
    def owner():
        return policy
    authority.register_cell(label="test", kind="canary", cell=owner.__closure__[0])
    authority.seal()
    authority.verify_for("test")
    obj = policy if target == "global" else policy.canaries._patterns[0]
    object.__setattr__(obj, "sensitivity_percent", 25)
    assert policy.canaries._patterns[0].match_chars == 16
    with pytest.raises(PolicyIntegrityUnavailable):
        authority.verify_for("test")
