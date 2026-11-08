"""Observation-only long native-reasoning cycle monitor.

Long-cycle observation is separate from narrowly gated interruption authority.
Only current backend native-reasoning deltas are loop evidence. User and tool
text supplied at generation start may suppress a source-derived match.
Jack controls whether to interrupt; the monitor itself never aborts streams.

Near-identity is measured with stdlib difflib.SequenceMatcher over word IDs.
Thresholds are experimental; a report is *not* proof of a model failure.
"""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
from typing import Iterable, Optional

from jack_loop_detector import RepeatedReasoningLoop


class LongCycleRepeatedReasoningLoop(RepeatedReasoningLoop):
    """Qualified long near-duplicate self-replanning, caught by existing recovery."""

    def __init__(self, cycle_words: int, repetitions: int):
        super().__init__(cycle_words, repetitions)
        self.args = (
            f"near-identical long native reasoning self-replanning cycle: "
            f"{cycle_words} words x {repetitions} consecutive copies",
        )


MIN_LONG_CYCLE_WORDS = 2049
MAX_LONG_CYCLE_WORDS = 8192
LONG_CYCLE_REPETITIONS = 4
LONG_CYCLE_SIMILARITY = 0.99
SOURCE_SHINGLE_WORDS = 8
SOURCE_OVERLAP_SUPPRESS = 0.75
_SCAN_WORDS = 128
_WIDTH_STEP = 16
_ANCHOR_WORDS = 8
_ANCHOR_JITTER = 48
_MIN_ANCHOR_HITS = 5
# Memory bounds apply per single backend generation attempt.
_MAX_GENERATED_WORDS = LONG_CYCLE_REPETITIONS * MAX_LONG_CYCLE_WORDS + _SCAN_WORDS
_MAX_SOURCE_CHARS = 2_000_000
_COMPLETED_WORD = re.compile(r"\S+\s+")
_WORD = re.compile(r"\S+")


@dataclass(frozen=True)
class LongCycleObservation:
    word_index: int
    cycle_words: int
    repetitions: int
    similarities: tuple[float, ...]
    source_overlap: float
    suppressed_as_source: bool
    source_truncated: bool


def source_texts_from_history(history: Iterable[dict]) -> tuple[str, ...]:
    """Only already-supplied user and tool text; no assistant/reasoning/args.

    Content blocks are treated as text only when explicitly marked text.
    Truncation is reported by the detector rather than hiding the coverage gap.
    """
    texts: list[str] = []
    for item in history:
        if not isinstance(item, dict) or item.get("role") not in {"user", "tool"}:
            continue
        content = item.get("content")
        if isinstance(content, str) and content:
            texts.append(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    value = part.get("text")
                    if isinstance(value, str) and value:
                        texts.append(value)
    return tuple(texts)


class LongCycleShadowDetector:
    """Stream-adaptive, bounded, observation-only long-cycle candidate search.

    A candidate requires four consecutive, >=99% similar 2,049–8,192-word
    blocks. Cheap 8-word anchors reject unrelated periods before running
    similarity checks. Every comparison uses the *same* word tokenization;
    input chunk boundaries cannot introduce words. No interrupt is possible.
    """

    def __init__(self, source_texts: Iterable[str] = ()) -> None:
        self._words: list[int] = []
        self._symbols: dict[str, int] = {}
        self._tail = ""
        self._word_count = 0
        self._sources = tuple(text for text in source_texts if isinstance(text, str) and text)
        self._source_shingles: Optional[set[tuple[str, ...]]] = None
        self._source_truncated = False
        self.observation: Optional[LongCycleObservation] = None

    @staticmethod
    def _anchor_match(a: list[int], b: list[int]) -> bool:
        width = len(a)
        matched = 0
        for numerator in range(1, 7):
            offset = width * numerator // 7
            snippet = b[offset:offset + _ANCHOR_WORDS]
            lower = max(0, offset - _ANCHOR_JITTER)
            upper = min(width - _ANCHOR_WORDS, offset + _ANCHOR_JITTER)
            if any(snippet == a[i:i + _ANCHOR_WORDS] for i in range(lower, upper + 1)):
                matched += 1
                if matched == _MIN_ANCHOR_HITS:
                    return True
        return False

    @staticmethod
    def _similarity(a: list[int], b: list[int]) -> float:
        # autojunk saves substantial CPU on repetitive natural language.
        # It can suppress candidates (false negatives), not authorize action.
        return SequenceMatcher(None, a, b, autojunk=True).ratio()

    @staticmethod
    def _short_internal_period(words: list[int]) -> bool:
        """Ignore long supercycles made entirely from a much shorter exact motif.

        A 500-word passage repeated 20 times must not masquerade as a new
        2,500-word long-cycle signal. This check only rejects candidates.
        """
        pi = [0] * len(words)
        for i in range(1, len(words)):
            j = pi[i - 1]
            while j and words[i] != words[j]:
                j = pi[j - 1]
            if words[i] == words[j]:
                j += 1
            pi[i] = j
        primitive = len(words) - pi[-1]
        return primitive <= 2048 and len(words) >= 3 * primitive

    def _source_index(self) -> set[tuple[str, ...]]:
        if self._source_shingles is None:
            remaining = _MAX_SOURCE_CHARS
            shingles: set[tuple[str, ...]] = set()
            for source in self._sources:
                if remaining <= 0:
                    self._source_truncated = True
                    break
                part = source[:remaining]
                if len(part) < len(source):
                    self._source_truncated = True
                remaining -= len(part)
                # Index each supplied source separately: no artificial 8-grams
                # across independent tool/user message boundaries.
                words = _WORD.findall(part)
                for i in range(len(words) - SOURCE_SHINGLE_WORDS + 1):
                    shingles.add(tuple(words[i:i + SOURCE_SHINGLE_WORDS]))
            self._source_shingles = shingles
            self._sources = ()
        return self._source_shingles

    def _source_overlap(self, cycle: list[int]) -> float:
        # Convert IDs back to their exact token spellings only for a candidate.
        vocabulary = {symbol: word for word, symbol in self._symbols.items()}
        words = [vocabulary[identifier] for identifier in cycle]
        shingles = {
            tuple(words[i:i + SOURCE_SHINGLE_WORDS])
            for i in range(len(words) - SOURCE_SHINGLE_WORDS + 1)
        }
        return len(shingles & self._source_index()) / max(1, len(shingles))

    def _scan(self) -> Optional[LongCycleObservation]:
        n = len(self._words)
        if n < LONG_CYCLE_REPETITIONS * MIN_LONG_CYCLE_WORDS:
            return None
        maximum = min(MAX_LONG_CYCLE_WORDS, n // LONG_CYCLE_REPETITIONS)
        first_width = ((MIN_LONG_CYCLE_WORDS + _WIDTH_STEP - 1) // _WIDTH_STEP) * _WIDTH_STEP
        for width in range(first_width, maximum + 1, _WIDTH_STEP):
            current = self._words[n - width:n]
            previous = self._words[n - 2 * width:n - width]
            if not self._anchor_match(previous, current):
                continue
            score = self._similarity(previous, current)
            if score < LONG_CYCLE_SIMILARITY:
                continue
            similarities = [score]
            for index in range(2, LONG_CYCLE_REPETITIONS):
                older = self._words[n - (index + 1) * width:n - index * width]
                newer = self._words[n - index * width:n - (index - 1) * width]
                if not self._anchor_match(older, newer):
                    break
                score = self._similarity(older, newer)
                if score < LONG_CYCLE_SIMILARITY:
                    break
                similarities.append(score)
            if len(similarities) == LONG_CYCLE_REPETITIONS - 1:
                if self._short_internal_period(current):
                    continue
                overlap = self._source_overlap(current)
                return LongCycleObservation(
                    word_index=self._word_count,
                    cycle_words=width,
                    repetitions=LONG_CYCLE_REPETITIONS,
                    similarities=tuple(similarities),
                    source_overlap=overlap,
                    suppressed_as_source=overlap >= SOURCE_OVERLAP_SUPPRESS,
                    source_truncated=self._source_truncated,
                )
        return None

    def interrupt_eligible(self, observation: LongCycleObservation) -> bool:
        """Conservative authority gate, separate from diagnostic observation.

        Near-exact long repetition alone is not enough to abort a model: it may
        be quoting a document. Require source independence AND repeatedly
        abandoned self-instructions. The caller must additionally require
        Agentic Stage 1, no streamed output/tools, and an enabled loop detector.
        """
        if (
            self.observation is not observation
            or observation.repetitions != LONG_CYCLE_REPETITIONS
            or min(observation.similarities) < LONG_CYCLE_SIMILARITY
            or observation.source_truncated
            or observation.source_overlap > 0.15
            or observation.suppressed_as_source
        ):
            return False
        ids = self._words[-observation.cycle_words:]
        if len(ids) != observation.cycle_words:
            return False
        inverse = {value: key for key, value in self._symbols.items()}
        cycle = " ".join(inverse.get(word, "") for word in ids)
        # Four drafts of the same document could be legitimate quotations.
        # Require a repeatedly restarted model plan, not just repetitive prose.
        promised_work = re.findall(
            r"\blet\s+me\s+(?:write|draft|save|read|verify|check)\b",
            cycle, flags=re.IGNORECASE,
        )
        restarted = re.search(
            r"\b(?:actually[,;:]?\s+let\s+me|wait[,;:]?\s+let\s+me|"
            r"let\s+me\s+(?:reconsider|rewrite|restart|start\s+over|redraft))\b",
            cycle, flags=re.IGNORECASE,
        )
        return len(promised_work) >= 2 and restarted is not None

    def feed(self, text: str) -> Optional[LongCycleObservation]:
        """Observe native reasoning; never raise a loop/retry/interrupt exception."""
        if not text or self.observation is not None:
            return None
        combined = self._tail + str(text)
        last = 0
        for match in _COMPLETED_WORD.finditer(combined):
            word = match.group().strip()
            if word not in self._symbols:
                self._symbols[word] = len(self._symbols) + 1
            self._words.append(self._symbols[word])
            self._word_count += 1
            last = match.end()
            if self._word_count % _SCAN_WORDS == 0:
                observation = self._scan()
                if observation is not None:
                    self.observation = observation
                    self._tail = combined[last:]
                    return observation
            if len(self._words) > _MAX_GENERATED_WORDS + _SCAN_WORDS:
                self._words = self._words[-_MAX_GENERATED_WORDS:]
        self._tail = combined[last:]
        if len(self._tail) > 131072:
            self._tail = ""  # Avoid unbounded unbroken bytes; conservative miss.
        return None
