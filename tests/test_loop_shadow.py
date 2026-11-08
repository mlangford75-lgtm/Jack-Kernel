"""Shadow detector contracts: never interrupts, respects sources, streams invariant."""
from jack_loop_shadow import (
    LongCycleShadowDetector,
    SOURCE_OVERLAP_SUPPRESS,
    source_texts_from_history,
)


def as_text(words):
    return " ".join(words) + " "


def test_source_scope_does_not_consume_assistant_or_tool_args():
    history = [
        {"role": "system", "content": "system secret"},
        {"role": "user", "content": [{"type": "text", "text": "document excerpt"}, {"type": "image_url", "text": "never image"}]},
        {"role": "assistant", "content": "assistant reasoning not source", "tool_calls": [{"function": {"arguments": "should not index"}}]},
        {"role": "tool", "content": "tool returned text"},
        {"role": "tool", "content": [{"type": "text", "text": "other tool text"}]},
    ]
    assert source_texts_from_history(history) == (
        "document excerpt", "tool returned text", "other tool text"
    )


def test_near_repeat_shadow_observes_not_interrupts():
    chapter = [f"word-{i:04d}" for i in range(2300)]
    copies = []
    for pass_i in range(4):
        candidate = chapter.copy()
        candidate[800] = f"unique_{pass_i}"
        candidate[1700] = f"revision_{pass_i}"
        copies.extend(candidate)
    detector = LongCycleShadowDetector()
    result = detector.feed(as_text(copies + ["continuation"] * 256))
    assert result is not None
    assert 2049 <= result.cycle_words <= 8192
    assert result.repetitions == 4
    assert result.word_index <= len(copies) + 128
    assert min(result.similarities) >= 0.99
    assert result.suppressed_as_source is False
    assert detector.observation == result
    assert detector.feed("further reasoning ") is None


def test_source_copied_long_document_suppressed():
    chapter = [f"source-{i:04d}" for i in range(2300)]
    detector = LongCycleShadowDetector(source_texts=[as_text(chapter)])
    result = detector.feed(as_text(chapter * 4 + ["continuation"] * 256))
    assert result is not None
    assert result.source_overlap >= SOURCE_OVERLAP_SUPPRESS
    assert result.suppressed_as_source is True


def test_unsourced_deliberate_repetition_reported_but_no_interrupt():
    chapter = [f"unseen-{i:04d}" for i in range(2300)]
    detector = LongCycleShadowDetector()
    result = detector.feed(as_text(chapter * 4 + ["continuation"] * 256))
    assert result is not None
    assert not result.suppressed_as_source
    # Such a passage could still be legitimate. Observation only is essential.


def test_three_long_copies_are_not_enough():
    chapter = [f"repeat-{i:04d}" for i in range(2300)]
    assert LongCycleShadowDetector().feed(as_text(chapter * 3)) is None


def test_repeated_short_document_not_reported_as_long_cycle():
    chapter = [f"line-{i:04d}" for i in range(500)]
    assert LongCycleShadowDetector().feed(as_text(chapter * 20)) is None


def test_stream_chunk_invariance():
    chapter = [f"reprise-{i:04d}" for i in range(2300)]
    full = as_text(chapter * 4 + ["continuation"] * 256)
    expected = LongCycleShadowDetector().feed(full)
    assert expected
    detector = LongCycleShadowDetector()
    result = None
    for start in range(0, len(full), 27):
        observation = detector.feed(full[start:start + 27])
        if observation is not None:
            result = observation
    assert result == expected


def test_distinct_long_passages_do_not_trip():
    chapters = [[f"chapter-{j}-token-{i:04d}" for i in range(2350)] for j in range(5)]
    detector = LongCycleShadowDetector()
    assert detector.feed(as_text([word for block in chapters for word in block])) is None


def test_active_gate_conservatively_rejects_unsourced_document_repetition():
    """An unrecorded repeated quotation is never sufficient to interrupt."""
    chapter = [f"article-{i:04d}" for i in range(2300)]
    monitor = LongCycleShadowDetector()
    observation = monitor.feed(as_text(chapter * 4 + ["end"] * 256))
    assert observation is not None
    assert not observation.suppressed_as_source
    assert not monitor.interrupt_eligible(observation)


def test_active_gate_detects_restarted_unfinished_plan():
    chapter = [f"draft-{i:04d}" for i in range(2300)]
    chapter[50:65] = (
        "Let me write the file now. Let me draft it. "
        "Actually, let me reconsider the structure."
    ).split()
    monitor = LongCycleShadowDetector()
    observation = monitor.feed(as_text(chapter * 4 + ["end"] * 256))
    assert observation is not None
    assert monitor.interrupt_eligible(observation)


def test_active_gate_protects_known_source_with_self_replanning_language():
    chapter = [f"draft-{i:04d}" for i in range(2300)]
    chapter[50:65] = (
        "Let me write the file now. Let me draft it. "
        "Actually, let me reconsider the structure."
    ).split()
    monitor = LongCycleShadowDetector(source_texts=[as_text(chapter)])
    observation = monitor.feed(as_text(chapter * 4 + ["end"] * 256))
    assert observation is not None
    assert observation.suppressed_as_source
    assert not monitor.interrupt_eligible(observation)


def test_active_gate_requires_reconsideration_not_just_repeated_work_words():
    chapter = [f"draft-{i:04d}" for i in range(2300)]
    chapter[40:48] = "Let me write and let me draft".split()
    monitor = LongCycleShadowDetector()
    observation = monitor.feed(as_text(chapter * 4 + ["end"] * 256))
    assert observation is not None
    assert not monitor.interrupt_eligible(observation)
