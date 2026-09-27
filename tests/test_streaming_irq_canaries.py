from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


MODULE = Path(__file__).resolve().parents[1] / "jack_evidence_guard.py"
spec = importlib.util.spec_from_file_location(
    "jack_streaming_irq_canary_test",
    MODULE,
)
guard = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = guard
spec.loader.exec_module(guard)


def pattern(canary_id, tier, value):
    return guard.CanaryPattern(
        canary_id=canary_id,
        tier=tier,
        value=value,
    )


def test_canary_tiers_are_exact():
    assert tuple(tier.value for tier in guard.CanaryTier) == (
        "A",
        "B",
        "C",
    )


def test_canary_value_is_hidden_from_repr_and_match_metadata():
    secret = "JACK-CANARY-VERY-SECRET-VALUE"

    item = pattern(
        "tier-a-1",
        guard.CanaryTier.A,
        secret,
    )

    canaries = guard.DeterministicCanarySet(
        [item],
        max_window=128,
    )

    match = canaries.find(
        "prefix " + secret + " suffix"
    )

    assert match == guard.CanaryMatch(
        canary_id="tier-a-1",
        tier=guard.CanaryTier.A,
    )

    assert secret not in repr(item)
    assert secret not in repr(match)
    assert not hasattr(match, "value")


def test_matching_is_exact_and_case_sensitive():
    secret = "Exact-Canary-ABC123"

    canaries = guard.DeterministicCanarySet(
        [
            pattern(
                "tier-b-1",
                guard.CanaryTier.B,
                secret,
            )
        ],
        max_window=64,
    )

    assert canaries.find(secret) is not None
    assert canaries.find(secret.lower()) is None
    assert canaries.find("Exact Canary ABC123") is None
    assert canaries.find("Exact-Canary-ABC12") is None


def test_required_window_is_longest_canary_length_minus_one():
    values = (
        "abc",
        "abcdefgh",
        "abcdefghijklmnop",
    )

    canaries = guard.DeterministicCanarySet(
        [
            pattern("a", guard.CanaryTier.A, values[0]),
            pattern("b", guard.CanaryTier.B, values[1]),
            pattern("c", guard.CanaryTier.C, values[2]),
        ],
        max_window=64,
    )

    assert canaries.required_window == len(values[2]) - 1


def test_empty_canary_set_requires_no_quarantine():
    canaries = guard.DeterministicCanarySet(
        [],
        max_window=0,
    )

    assert canaries.count == 0
    assert canaries.required_window == 0
    assert canaries.find("ordinary text") is None


def test_single_character_canary_requires_zero_lookbehind():
    canaries = guard.DeterministicCanarySet(
        [
            pattern(
                "one",
                guard.CanaryTier.C,
                "X",
            )
        ],
        max_window=0,
    )

    assert canaries.required_window == 0
    assert canaries.find("aXb") == guard.CanaryMatch(
        canary_id="one",
        tier=guard.CanaryTier.C,
    )


def test_detector_matches_at_every_two_chunk_boundary():
    secret = "TIER-C-DYNAMIC-CANARY"
    surrounding = "before-" + secret + "-after"

    canaries = guard.DeterministicCanarySet(
        [
            pattern(
                "dynamic-1",
                guard.CanaryTier.C,
                secret,
            )
        ],
        max_window=128,
    )

    for split in range(len(surrounding) + 1):
        detector = guard.StreamingCanaryDetector(
            canaries
        )

        first = detector.feed(
            surrounding[:split]
        )
        second = (
            None
            if first is not None
            else detector.feed(
                surrounding[split:]
            )
        )

        match = first or second

        assert match == guard.CanaryMatch(
            canary_id="dynamic-1",
            tier=guard.CanaryTier.C,
        ), split


def test_detector_matches_from_one_character_chunks():
    secret = "ONE-CHAR-BOUNDARY-CANARY"

    canaries = guard.DeterministicCanarySet(
        [
            pattern(
                "charwise",
                guard.CanaryTier.A,
                secret,
            )
        ],
        max_window=128,
    )

    detector = guard.StreamingCanaryDetector(
        canaries
    )

    match = None

    for char in secret:
        match = detector.feed(char)
        if match is not None:
            break

    assert match == guard.CanaryMatch(
        canary_id="charwise",
        tier=guard.CanaryTier.A,
    )


def test_detector_does_not_fuzzy_match_partial_or_benign_text():
    secret = "JACK-EXACT-CANARY-9012"

    canaries = guard.DeterministicCanarySet(
        [
            pattern(
                "exact-only",
                guard.CanaryTier.B,
                secret,
            )
        ],
        max_window=128,
    )

    detector = guard.StreamingCanaryDetector(
        canaries
    )

    benign = (
        "JACK EXACT CANARY 9012 "
        "jack-exact-canary-9012 "
        "JACK-EXACT-CANARY-901"
    )

    for char in benign:
        assert detector.feed(char) is None


def test_same_start_overlap_chooses_shorter_configured_canary_deterministically():
    canaries = guard.DeterministicCanarySet(
        [
            pattern(
                "long",
                guard.CanaryTier.B,
                "ABCDE",
            ),
            pattern(
                "short",
                guard.CanaryTier.A,
                "ABC",
            ),
        ],
        max_window=16,
    )

    assert canaries.find("ABCDE") == guard.CanaryMatch(
        canary_id="short",
        tier=guard.CanaryTier.A,
    )

    detector = guard.StreamingCanaryDetector(
        canaries
    )

    assert detector.feed("ABC") == guard.CanaryMatch(
        canary_id="short",
        tier=guard.CanaryTier.A,
    )


def test_duplicate_canary_ids_are_rejected_without_value_leakage():
    secret_a = "SECRET-VALUE-A"
    secret_b = "SECRET-VALUE-B"

    with pytest.raises(ValueError) as exc:
        guard.DeterministicCanarySet(
            [
                pattern(
                    "duplicate",
                    guard.CanaryTier.A,
                    secret_a,
                ),
                pattern(
                    "duplicate",
                    guard.CanaryTier.B,
                    secret_b,
                ),
            ],
            max_window=64,
        )

    message = str(exc.value)

    assert secret_a not in message
    assert secret_b not in message


def test_duplicate_canary_values_are_rejected_without_value_leakage():
    secret = "DUPLICATE-SECRET-CANARY"

    with pytest.raises(ValueError) as exc:
        guard.DeterministicCanarySet(
            [
                pattern(
                    "first",
                    guard.CanaryTier.A,
                    secret,
                ),
                pattern(
                    "second",
                    guard.CanaryTier.C,
                    secret,
                ),
            ],
            max_window=64,
        )

    assert secret not in str(exc.value)


def test_canary_exceeding_hard_ceiling_is_rejected_without_value_leakage():
    secret = "X" * 66

    with pytest.raises(ValueError) as exc:
        guard.DeterministicCanarySet(
            [
                pattern(
                    "too-long",
                    guard.CanaryTier.A,
                    secret,
                )
            ],
            max_window=64,
        )

    assert secret not in str(exc.value)


@pytest.mark.parametrize(
    "bad_id",
    (
        "",
        "contains space",
        "contains/slash",
        "contains\nnewline",
        "x" * 129,
    ),
)
def test_canary_id_must_be_safe_opaque_metadata(bad_id):
    with pytest.raises(ValueError):
        pattern(
            bad_id,
            guard.CanaryTier.A,
            "safe-value",
        )


def test_canary_tier_must_be_explicit_enum():
    with pytest.raises(TypeError):
        pattern(
            "tier-test",
            "A",
            "safe-value",
        )


def test_detector_flush_discards_only_detector_lookbehind_state():
    canaries = guard.DeterministicCanarySet(
        [
            pattern(
                "partial",
                guard.CanaryTier.C,
                "ABCDEFGHIJ",
            )
        ],
        max_window=32,
    )

    detector = guard.StreamingCanaryDetector(
        canaries
    )

    assert detector.feed("ABCDE") is None
    assert detector.held_length == 5

    detector.flush()

    assert detector.held_length == 0


def test_detection_reports_safe_prefix_inside_current_delta():
    secret = "CANARY"

    canaries = guard.DeterministicCanarySet(
        [
            pattern(
                "boundary-current",
                guard.CanaryTier.C,
                secret,
            )
        ],
        max_window=64,
    )

    detector = guard.StreamingCanaryDetector(
        canaries
    )

    # Populate prior look-behind with text that is not part of the match.
    assert detector.feed("older") is None

    detection = detector.feed_detection(
        "safe-" + secret
    )

    assert detection == guard.CanaryDetection(
        match=guard.CanaryMatch(
            canary_id="boundary-current",
            tier=guard.CanaryTier.C,
        ),
        buffered_prefix_length=(
            len("older") + len("safe-")
        ),
        current_prefix_length=len("safe-"),
        overlaps_prior_carry=False,
    )


def test_detection_reports_cross_boundary_match_as_overlapping_prior_carry():
    secret = "ABCDEF"

    canaries = guard.DeterministicCanarySet(
        [
            pattern(
                "boundary-cross",
                guard.CanaryTier.A,
                secret,
            )
        ],
        max_window=64,
    )

    detector = guard.StreamingCanaryDetector(
        canaries
    )

    assert detector.feed("xxABC") is None

    detection = detector.feed_detection("DEF")

    assert detection == guard.CanaryDetection(
        match=guard.CanaryMatch(
            canary_id="boundary-cross",
            tier=guard.CanaryTier.A,
        ),
        buffered_prefix_length=len("xx"),
        current_prefix_length=0,
        overlaps_prior_carry=True,
    )


def test_detection_metadata_never_contains_canary_value():
    secret = "PRIVATE-CANARY-VALUE"

    canaries = guard.DeterministicCanarySet(
        [
            pattern(
                "safe-meta",
                guard.CanaryTier.B,
                secret,
            )
        ],
        max_window=64,
    )

    detector = guard.StreamingCanaryDetector(
        canaries
    )

    detection = detector.feed_detection(
        "prefix-" + secret
    )

    assert detection is not None
    assert secret not in repr(detection)
    assert not hasattr(detection, "value")
    assert not hasattr(detection.match, "value")


def test_existing_feed_api_still_returns_only_canary_match():
    secret = "API-COMPAT-CANARY"

    canaries = guard.DeterministicCanarySet(
        [
            pattern(
                "api-compat",
                guard.CanaryTier.C,
                secret,
            )
        ],
        max_window=64,
    )

    detector = guard.StreamingCanaryDetector(
        canaries
    )

    assert detector.feed(secret) == guard.CanaryMatch(
        canary_id="api-compat",
        tier=guard.CanaryTier.C,
    )


def test_feed_guarded_releases_only_text_older_than_required_window():
    canaries = guard.DeterministicCanarySet(
        [
            pattern(
                "gate-window",
                guard.CanaryTier.A,
                "ABCDEF",
            )
        ],
        max_window=32,
    )

    detector = guard.StreamingCanaryDetector(
        canaries
    )

    released, detection = detector.feed_guarded(
        "safe-xxABC"
    )

    assert released == "safe-"
    assert detection is None
    assert detector.held_length == len("xxABC")


def test_feed_guarded_cross_boundary_match_returns_safe_buffered_prefix():
    canaries = guard.DeterministicCanarySet(
        [
            pattern(
                "gate-cross",
                guard.CanaryTier.A,
                "ABCDEF",
            )
        ],
        max_window=32,
    )

    detector = guard.StreamingCanaryDetector(
        canaries
    )

    released, detection = detector.feed_guarded(
        "safe-xxABC"
    )

    assert released == "safe-"
    assert detection is None

    released, detection = detector.feed_guarded(
        "DEF-after"
    )

    assert released == "xx"
    assert detection is not None
    assert detection.buffered_prefix_length == 2
    assert detector.held_length == 0


def test_flush_safe_releases_only_benign_detector_carry():
    canaries = guard.DeterministicCanarySet(
        [
            pattern(
                "gate-flush",
                guard.CanaryTier.C,
                "ABCDEFGHIJ",
            )
        ],
        max_window=32,
    )

    detector = guard.StreamingCanaryDetector(
        canaries
    )

    released, detection = detector.feed_guarded(
        "benign"
    )

    assert released == ""
    assert detection is None

    assert detector.flush_safe() == "benign"
    assert detector.held_length == 0


def test_canary_interrupt_carries_safe_structured_metadata_only():
    secret = "NEVER-IN-EXCEPTION"

    match = guard.CanaryMatch(
        canary_id="opaque-tripwire-17",
        tier=guard.CanaryTier.B,
    )

    exc = guard.StreamingIRQCanaryInterrupt(
        match
    )

    assert isinstance(
        exc,
        guard.StreamingIRQHardInterrupt,
    )

    assert exc.match == match

    assert str(exc) == "StreamingIRQ Canary match"

    rendered = repr(exc)

    assert secret not in rendered
    assert "opaque-tripwire-17" not in str(exc)
    assert "tier=B" not in str(exc)


def test_runtime_canary_policy_binds_resolved_owner_identity():
    canaries = guard.DeterministicCanarySet(
        [
            pattern(
                "owner-test",
                guard.CanaryTier.A,
                "OWNER-CANARY",
            )
        ],
        max_window=64,
    )

    policy = guard.RuntimeCanaryPolicy(
        runtime_id="runtime-alpha",
        lane_id="lane-alpha",
        canaries=canaries,
    )

    assert policy.runtime_id == "runtime-alpha"
    assert policy.lane_id == "lane-alpha"
    assert policy.canaries is canaries


def test_runtime_canary_policy_is_frozen():
    canaries = guard.DeterministicCanarySet(
        (),
        max_window=0,
    )

    policy = guard.RuntimeCanaryPolicy(
        runtime_id="runtime-frozen",
        lane_id="lane-frozen",
        canaries=canaries,
    )

    with pytest.raises(Exception):
        policy.runtime_id = "other-runtime"


@pytest.mark.parametrize(
    "runtime_id,lane_id",
    (
        ("", "lane"),
        ("runtime", ""),
    ),
)
def test_runtime_canary_policy_rejects_empty_owner_identity(
    runtime_id,
    lane_id,
):
    with pytest.raises(ValueError):
        guard.RuntimeCanaryPolicy(
            runtime_id=runtime_id,
            lane_id=lane_id,
            canaries=guard.DeterministicCanarySet(
                (),
                max_window=0,
            ),
        )



def test_deterministic_canary_set_is_structurally_frozen():
    canaries = guard.DeterministicCanarySet(
        [
            pattern(
                "frozen-set",
                guard.CanaryTier.A,
                "FROZEN-CANARY",
            )
        ],
        max_window=64,
    )

    with pytest.raises(AttributeError):
        canaries.required_window = 0

    with pytest.raises(AttributeError):
        canaries.max_window = 999

    with pytest.raises(AttributeError):
        canaries._patterns = ()


def test_install_rejects_runtime_policy_owner_mismatch():
    class FakeJack:
        RUNTIME_ID = "runtime-real"
        LANE_ID = "lane-real"

    policy = guard.RuntimeCanaryPolicy(
        runtime_id="runtime-wrong",
        lane_id="lane-real",
        canaries=guard.DeterministicCanarySet(
            (),
            max_window=0,
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="runtime ownership mismatch",
    ):
        guard.install(
            FakeJack(),
            canary_policy=policy,
        )


def test_install_rejects_lane_policy_owner_mismatch():
    class FakeJack:
        RUNTIME_ID = "runtime-real"
        LANE_ID = "lane-real"

    policy = guard.RuntimeCanaryPolicy(
        runtime_id="runtime-real",
        lane_id="lane-wrong",
        canaries=guard.DeterministicCanarySet(
            (),
            max_window=0,
        ),
    )

    with pytest.raises(
        RuntimeError,
        match="lane ownership mismatch",
    ):
        guard.install(
            FakeJack(),
            canary_policy=policy,
        )


def test_reinstall_remains_exact_once_noop_before_identity_validation():
    class AlreadyInstalled:
        _JACK_EVIDENCE_PROVENANCE_GUARD_INSTALLED = True

    guard.install(AlreadyInstalled())


def test_install_closure_enforces_matching_runtime_policy_snapshot():
    import asyncio
    import json
    from types import SimpleNamespace

    secret = "INSTALL-BOUND-CANARY"

    class Kernel:
        async def run(self, _body):
            return SimpleNamespace(
                content="ok",
                reasoning_content=None,
            )

        async def stream(self, _body):
            payload = {
                "id": "install-policy-test",
                "object": "chat.completion.chunk",
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "content":
                                "safe-prefix-" + secret
                        },
                        "finish_reason": None,
                    }
                ],
            }

            yield (
                "data: "
                + json.dumps(
                    payload,
                    separators=(",", ":"),
                )
                + "\n\n"
            ).encode("utf-8")

    jk = SimpleNamespace(
        RUNTIME_ID="runtime-bound",
        LANE_ID="lane-bound",
        KERNEL=Kernel(),
    )

    canaries = guard.DeterministicCanarySet(
        [
            pattern(
                "install-bound",
                guard.CanaryTier.A,
                secret,
            )
        ],
        max_window=64,
    )

    policy = guard.RuntimeCanaryPolicy(
        runtime_id="runtime-bound",
        lane_id="lane-bound",
        canaries=canaries,
    )

    guard.install(
        jk,
        canary_policy=policy,
    )

    async def consume():
        chunks = []

        try:
            async for chunk in jk.KERNEL.stream({}):
                chunks.append(chunk)
        except guard.StreamingIRQCanaryInterrupt as exc:
            return chunks, exc

        raise AssertionError(
            "Expected installed Canary policy to interrupt"
        )

    chunks, exc = asyncio.run(consume())

    rendered = b"".join(chunks).decode(
        "utf-8",
        "replace",
    )

    assert "safe-prefix-" in rendered
    assert secret not in rendered

    assert exc.match == guard.CanaryMatch(
        canary_id="install-bound",
        tier=guard.CanaryTier.A,
    )

    assert str(exc) == "StreamingIRQ Canary match"
