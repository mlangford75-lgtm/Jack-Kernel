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
