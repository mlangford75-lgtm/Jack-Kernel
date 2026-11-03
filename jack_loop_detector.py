"""Deterministic, conservative native-reasoning repetition monitor.

A detection proves only that the *generated text* contains an exact recurring
word cycle; it never claims that cognition is intrinsically stuck. This module
does not inspect prompts, historical context, visible output, or tool data.
"""
from __future__ import annotations

import hashlib
import re

LOOP_THRESHOLDS = (16, 32, 48, 64, 128)
DEFAULT_LOOP_THRESHOLD = 32
MIN_CYCLE_WORDS = 128
MAX_CYCLE_WORDS = 2048
_MASK = (1 << 64) - 1
_BASE = 0x100000001B3
_COMPLETE_WORD = re.compile(r"\S+\s+")


class RepeatedReasoningLoop(RuntimeError):
    """Backend inference stopped after an exact recurring native-reasoning cycle."""

    def __init__(self, cycle_words: int, repetitions: int):
        self.cycle_words = cycle_words
        self.repetitions = repetitions
        super().__init__(
            f"exact native reasoning cycle: {cycle_words} words x "
            f"{repetitions} consecutive copies"
        )


class RepeatedLoopInterrupt(RuntimeError):
    """The retry also repeated; do not start a third inference."""

    def __init__(self) -> None:
        super().__init__("Jack Kernel interrupt - Repeated Loop Failure")


class PartialOutputLoopInterrupt(RuntimeError):
    """A model-facing retry cannot retract content already released to an agent."""

    def __init__(self) -> None:
        super().__init__("Jack Kernel interrupt - Loop Detected After Partial Output")


class ReasoningLoopDetector:
    """Incremental exact-suffix detector, independent of transport chunk sizes.

    Only completed whitespace-delimited words count. A single contiguous
    repeating cycle must be >= 128 words and recur the selected number of
    times. Rolling fingerprints cheaply identify candidate periods; *every*
    candidate is independently checked by exact word comparison before an
    interrupt is authorized. No semantic similarity or hash-only decisions.

    Retains only enough recent words for 128 copies of the largest supported
    cycle. Detector state is scoped to a single backend generation attempt.
    """

    def __init__(
        self,
        repetitions: int = DEFAULT_LOOP_THRESHOLD,
        *,
        min_cycle_words: int = MIN_CYCLE_WORDS,
        max_cycle_words: int = MAX_CYCLE_WORDS,
    ) -> None:
        if repetitions not in LOOP_THRESHOLDS:
            raise ValueError("loop repetitions must be one of 16, 32, 48, 64, 128")
        if min_cycle_words < MIN_CYCLE_WORDS:
            raise ValueError("minimum cycle must be at least 128 words")
        if max_cycle_words < min_cycle_words:
            raise ValueError("maximum cycle shorter than minimum")
        self.repetitions = repetitions
        self.min_cycle_words = min_cycle_words
        self.max_cycle_words = max_cycle_words
        self._words: list[str] = []
        self._prefix: list[int] = [0]
        self._powers: list[int] = [1]
        for _ in range(max_cycle_words):
            self._powers.append((self._powers[-1] * _BASE) & _MASK)
        self._tail = ""
        self.detected_cycle_words: int | None = None

    def _range_hash(self, first: int, last: int) -> int:
        return (
            self._prefix[last]
            - self._prefix[first] * self._powers[last - first]
        ) & _MASK

    def _record(self, word: str) -> None:
        self._words.append(word)
        value = int.from_bytes(
            hashlib.blake2b(word.encode("utf-8"), digest_size=8).digest(), "big"
        )
        self._prefix.append((self._prefix[-1] * _BASE + value + 1) & _MASK)
        keep = self.max_cycle_words * max(LOOP_THRESHOLDS) + 1024
        if len(self._words) > keep + 4096:
            self._words = self._words[-keep:]
            self._prefix = [0]
            for value_word in self._words:
                h = int.from_bytes(
                    hashlib.blake2b(value_word.encode("utf-8"), digest_size=8).digest(), "big"
                )
                self._prefix.append((self._prefix[-1] * _BASE + h + 1) & _MASK)

    def _check_suffix(self) -> bool:
        count = len(self._words)
        upper = min(self.max_cycle_words, count // self.repetitions)
        if upper < self.min_cycle_words:
            return False
        # Inspect a completed batch rather than every individual word; at
        # most 15 additional words of detection latency. This keeps the monitor
        # inexpensive even with a 128-copy threshold.
        if count % 16:
            return False
        for width in range(self.min_cycle_words, upper + 1):
            # A period is only a candidate if its last two blocks hash alike.
            if self._range_hash(count - width, count) != self._range_hash(
                count - 2 * width, count - width
            ):
                continue
            tail = self._words[count - width:count]
            # Full word-by-word equality is mandatory; hash collisions cannot
            # cause a false-positive classification.
            if all(
                self._words[count - repeat * width:count - (repeat - 1) * width] == tail
                for repeat in range(2, self.repetitions + 1)
            ):
                self.detected_cycle_words = width
                return True
        return False

    def feed(self, text: str) -> bool:
        """Return true exactly once a qualifying repeated suffix is observed."""
        if self.detected_cycle_words is not None:
            return True
        if not text:
            return False
        combined = self._tail + str(text)
        last = 0
        for match in _COMPLETE_WORD.finditer(combined):
            word = match.group().strip()
            self._record(word)
            last = match.end()
            if self._check_suffix():
                self._tail = combined[last:]
                return True
        self._tail = combined[last:]
        # Unbroken text is not a stream of words; cap memory and conservatively
        # forgo detection rather than invent token boundaries.
        if len(self._tail) > 131072:
            self._tail = ""
        return False
