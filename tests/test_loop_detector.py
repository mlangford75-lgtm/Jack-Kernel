"""Regression tests for deterministic native-reasoning cycle detection."""
from jack_loop_detector import (
    DEFAULT_LOOP_THRESHOLD, LOOP_THRESHOLDS, MIN_CYCLE_WORDS,
    ReasoningLoopDetector,
)


def test_public_defaults():
    assert LOOP_THRESHOLDS == (16, 32, 48, 64, 128)
    assert DEFAULT_LOOP_THRESHOLD == 32
    assert MIN_CYCLE_WORDS == 128


def test_no_early_detection_for_31_copies():
    detector = ReasoningLoopDetector()
    cycle = [f"step_{i:03d}" for i in range(128)]
    assert detector.feed(" ".join(cycle * 31) + " ") is False
    assert detector.detected_cycle_words is None
    assert detector.feed(" ".join(cycle) + " ") is True
    assert detector.detected_cycle_words == 128


def test_detects_shorter_base_cycle_via_128_word_supercycle():
    # Gemma-style 66-word base cycles can be detected as a 132-word
    # exact repeated cycle without relaxing the 128-word minimum.
    cycle = [f"reason_{i:02d}" for i in range(66)]
    detector = ReasoningLoopDetector()
    assert detector.feed(" ".join(cycle * 63) + " ") is False
    assert detector.feed(" ".join(cycle) + " ") is True
    assert detector.detected_cycle_words == 132


def test_chunk_invariance_and_whitespace_normalization():
    cycle = [f"token{i}" for i in range(128)]
    text = "\n \t".join(cycle * 32) + " "
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
    assert detector.feed("apply the fix " * 32 + " ") is False


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
