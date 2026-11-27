"""Regression tests for deterministic native-reasoning cycle detection."""
from jack_loop_detector import (
    DEFAULT_LOOP_THRESHOLD, LOOP_THRESHOLDS, MIN_CYCLE_WORDS,
    ReasoningLoopDetector,
)


def test_public_defaults():
    assert LOOP_THRESHOLDS == (4, 6, 8, 12, 16, 24, 32, 48, 64, 128)
    assert DEFAULT_LOOP_THRESHOLD == 12
    assert MIN_CYCLE_WORDS == 64


def test_no_early_detection_for_23_copies():
    detector = ReasoningLoopDetector(24)
    cycle = [f"step_{i:03d}" for i in range(128)]
    assert detector.feed(" ".join(cycle * 23) + " ") is False
    assert detector.detected_cycle_words is None
    assert detector.feed(" ".join(cycle) + " ") is True
    assert detector.detected_cycle_words == 128


def test_detects_shorter_base_cycle_across_generations():
    cycle = [f"reason_{i:02d}" for i in range(64)]
    detector = ReasoningLoopDetector(4)
    for _ in range(3):
        assert detector.feed(" ".join(cycle)) is False
        detector.generation_boundary()
    assert detector.feed(" ".join(cycle) + " ") is True
    assert detector.detected_cycle_words == 64


def test_chunk_invariance_and_whitespace_normalization():
    cycle = [f"token{i}" for i in range(128)]
    text = "\n \t".join(cycle * 24) + " "
    detector = ReasoningLoopDetector()
    detected = False
    for index in range(0, len(text), 7):
        detected = detector.feed(text[index:index + 7]) or detected
    assert detected
    assert detector.detected_cycle_words == 128


def test_reconsideration_and_similar_prose_not_matched():
    detector = ReasoningLoopDetector()
    prefix = [f"item{i}" for i in range(127)]
    # A unique final word in every long near-repeat invalidates exact
    # sequence equality, even after 64 passes.
    text = " ".join(
        word
        for pass_number in range(64)
        for word in (prefix + [f"uniquely_changed_{pass_number}"])
    ) + " "
    assert detector.feed(text) is False


def test_repeated_short_phrase_is_not_enough():
    detector = ReasoningLoopDetector()
    assert detector.feed("apply the fix " * 24 + " ") is False


def test_threshold_choices():
    cycle = [f"item{i}" for i in range(128)]
    for threshold in LOOP_THRESHOLDS:
        detector = ReasoningLoopDetector(threshold)
        assert not detector.feed(" ".join(cycle * (threshold - 1)) + " ")
        assert detector.feed(" ".join(cycle) + " ")


def test_invalid_threshold_rejected():
    import pytest
    with pytest.raises(ValueError):
        ReasoningLoopDetector(31)


def test_trimmed_exact_detector_keeps_hash_ranges_and_detects_full_width_cycle():
    import pytest
    for repetitions in (4, 12, 128):
        detector = ReasoningLoopDetector(repetitions, max_cycle_words=64)
        limit = detector.max_cycle_words * repetitions + 1024 + 4096
        # Exercise multiple real trim boundaries with unique words, but
        # isolate the retention path from expensive negative suffix scanning.
        for index in range(limit * 2):
            detector._record(f"unique_{index}")
        assert len(detector._words) <= limit
        assert len(detector._prefix) == len(detector._words) + 1
        assert len(detector._words) % 16 == (limit * 2) % 16
        cycle = [f"new_{i}" for i in range(64)]
        assert not detector.feed(" ".join(cycle * (repetitions - 1)) + " ")
        assert detector.feed(" ".join(cycle) + " ")
        assert detector.detected_cycle_words == 64
