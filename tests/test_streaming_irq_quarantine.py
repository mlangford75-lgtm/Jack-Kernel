from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


MODULE = Path(__file__).resolve().parents[1] / "jack_evidence_guard.py"
spec = importlib.util.spec_from_file_location("jack_streaming_irq_test", MODULE)
guard = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(guard)


def render(chunks, *, window_size, max_window):
    quarantine = guard.StreamingIRQTextQuarantine(
        window_size=window_size,
        max_window=max_window,
    )
    released = [quarantine.feed(chunk) for chunk in chunks]
    released.append(quarantine.flush())
    return "".join(released)


def test_quarantine_reconstructs_exact_text_across_every_two_chunk_boundary():
    text = "NORMAL_OUTPUT_THROUGH_JACK_OK"

    for split in range(len(text) + 1):
        rendered = render(
            [text[:split], text[split:]],
            window_size=8,
            max_window=64,
        )
        assert rendered == text, (split, rendered)


def test_quarantine_reconstructs_exact_text_from_one_character_chunks():
    text = "one-character-stream-boundary-test"

    rendered = render(
        list(text),
        window_size=7,
        max_window=64,
    )

    assert rendered == text


def test_quarantine_releases_only_prefix_beyond_window():
    quarantine = guard.StreamingIRQTextQuarantine(
        window_size=5,
        max_window=32,
    )

    assert quarantine.feed("abcdefgh") == "abc"
    assert quarantine.held_length == 5
    assert quarantine.flush() == "defgh"
    assert quarantine.held_length == 0


def test_zero_window_is_transparent_passthrough():
    quarantine = guard.StreamingIRQTextQuarantine(
        window_size=0,
        max_window=0,
    )

    assert quarantine.feed("abc") == "abc"
    assert quarantine.feed("def") == "def"
    assert quarantine.flush() == ""


def test_flush_is_idempotently_empty_after_release():
    quarantine = guard.StreamingIRQTextQuarantine(
        window_size=4,
        max_window=16,
    )

    assert quarantine.feed("abcdef") == "ab"
    assert quarantine.flush() == "cdef"
    assert quarantine.flush() == ""


def test_none_input_does_not_destroy_held_text():
    quarantine = guard.StreamingIRQTextQuarantine(
        window_size=4,
        max_window=16,
    )

    assert quarantine.feed("abcd") == ""
    assert quarantine.feed(None) == ""
    assert quarantine.flush() == "abcd"


@pytest.mark.parametrize(
    ("window_size", "max_window", "error_type"),
    (
        (-1, 16, ValueError),
        (17, 16, ValueError),
        (1, -1, ValueError),
        (True, 16, TypeError),
        (1, False, TypeError),
        ("4", 16, TypeError),
        (4, "16", TypeError),
    ),
)
def test_quarantine_rejects_invalid_bounds(
    window_size,
    max_window,
    error_type,
):
    with pytest.raises(error_type):
        guard.StreamingIRQTextQuarantine(
            window_size=window_size,
            max_window=max_window,
        )


def test_quarantine_object_has_no_enforcement_side_effect_api():
    quarantine = guard.StreamingIRQTextQuarantine(
        window_size=4,
        max_window=16,
    )

    assert not hasattr(quarantine, "cancel")
    assert not hasattr(quarantine, "interrupt")
    assert not hasattr(quarantine, "terminate")
    assert not hasattr(quarantine, "discard")
