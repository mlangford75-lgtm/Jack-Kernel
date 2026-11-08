#!/usr/bin/env python3
"""Deterministic offline replay for Jack's exact detector and shadow observer.

No LLM, network, server, or random input required.
From repository root:
    python scripts/run_loop_shadow_replay.py
    python scripts/run_loop_shadow_replay.py --pi-session "C:\path\to\pi-session.html"
    python scripts/run_loop_shadow_replay.py --pi-session "C:\path\to\pi-session.html" --expect-chapter4
    python scripts/run_loop_shadow_replay.py --pi-session "C:\path\to\normal-session.html" --expect-no-shadow

Only native Stage 1 reasoning is replayed; users' documents and tool outputs
are used as source-overlap references, NEVER as generated reasoning.
"""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from jack_loop_detector import ReasoningLoopDetector  # noqa: E402
from jack_loop_shadow import LongCycleShadowDetector  # noqa: E402

SESSION_DATA = re.compile(r'<script id="session-data" type="application/json">(.*?)</script>', re.S)
RETRY_MARKER = "[Failure - Loop Detected - Reasoning; retrying once]"


def generate_synthetic_cases():
    """Returns (name, reasoning, source_texts, expect_shadow, expect_suppressed)."""
    paragraph = [f"historical-fact-{i:04d}" for i in range(2300)]
    near = []
    for copy in range(4):
        words = paragraph.copy()
        words[800] = f"revised-fact-{copy}"
        words[1700] = f"updated-reference-{copy}"
        near.extend(words)
    long_quote = " ".join(paragraph) + " "
    return [
        ("runaway_near_repeat", " ".join(near + ["tail"] * 256) + " ", (), True, False),
        ("three_copies_insufficient", " ".join(paragraph * 3) + " ", (), False, None),
        ("known_document_quoted_four_times", long_quote * 4 + "tail " * 256, (long_quote,), True, True),
        ("unrecorded_quote_false_positive_control", long_quote * 4 + "tail " * 256, (), True, False),
        ("legitimate_distinct_chapters", " ".join(
            f"chapter-{c}-fact-{i}" for c in range(5) for i in range(2350)
        ) + " ", (), False, None),
        ("short_phrase_not_long_loop", " ".join(f"phrase-{i}" for i in range(500)) * 20 + " ", (), False, None),
    ]


def replay_native_text(reasoning: str, source_texts=(), *, chunk_chars=113):
    """Run both detectors on the same reasoning-only stream in transport-sized chunks."""
    exact = ReasoningLoopDetector()
    shadow = LongCycleShadowDetector(source_texts)
    exact_hit = None
    shadow_hit = None
    beginning = time.perf_counter()
    for cursor in range(0, len(reasoning), chunk_chars):
        chunk = reasoning[cursor:cursor + chunk_chars]
        if exact_hit is None and exact.feed(chunk):
            exact_hit = {"cycle_words": exact.detected_cycle_words, "repetitions": exact.repetitions}
        if shadow_hit is None:
            candidate = shadow.feed(chunk)
            if candidate is not None:
                shadow_hit = candidate
    return exact_hit, shadow_hit, time.perf_counter() - beginning


def check_synthetic():
    failed = 0
    print("SYNTHETIC REGRESSION (no LLM required)", flush=True)
    for name, reasoning, sources, expect_hit, expect_suppressed in generate_synthetic_cases():
        _, event, seconds = replay_native_text(reasoning, sources)
        ok = (event is not None) == expect_hit
        if event is not None and expect_suppressed is not None:
            ok = ok and event.suppressed_as_source == expect_suppressed
        if not ok:
            failed += 1
        state = ("SOURCE SUPPRESSED" if event and event.suppressed_as_source
                 else "OBSERVED" if event else "NO OBSERVATION")
        print(f"  {'PASS' if ok else 'FAIL'} {name:43} {state:18} "
              f"word={event.word_index if event else '-':>6} seconds={seconds:.3f}", flush=True)
    return failed


def extract_pi_reasoning(session_path: Path):
    """Recover one model generation attempt per segment from a Pi HTML export."""
    html = session_path.read_text(encoding="utf-8")
    match = SESSION_DATA.search(html)
    if match is None:
        raise ValueError(f"No Pi session-data payload in {session_path}")
    document = json.loads(base64.b64decode(match.group(1)))
    turn = 0
    sources: list[str] = []
    for entry in document.get("entries", []):
        message = entry.get("message") or {}
        role = message.get("role")
        content = message.get("content") or []
        if role in {"user", "tool"}:
            if role == "user":
                turn += 1
            if isinstance(content, str):
                sources.append(content)
            elif isinstance(content, list):
                sources.extend(part.get("text") for part in content
                               if isinstance(part, dict)
                               and part.get("type") == "text"
                               and isinstance(part.get("text"), str))
            continue
        if role != "assistant" or not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "thinking":
                continue
            text = part.get("thinking") or ""
            if not isinstance(text, str):
                continue
            # Exclude Jack's human-readable Stage 2 and result framing.
            text = text.split("===== JACK AGENTIC NATIVE PASS 2")[0]
            text = text.split("[STAGE 2 REASONING DISTILLATION]")[0]
            text = text.split("[END STAGE 1")[0]
            text = text.split("[STAGE 1 PROPOSED RESPONSE]")[-1]
            for retry_index, attempt in enumerate(text.split(RETRY_MARKER)):
                if attempt.strip():
                    yield {"turn": turn, "retry": retry_index, "reasoning": attempt,
                           "sources": tuple(sources), "words": len(attempt.split())}


def check_pi(session_path: Path, expect_chapter4: bool, expect_no_shadow: bool):
    print(f"\nPI REPLAY: {session_path.name}", flush=True)
    failures = 0
    chapter4_found = False
    chapter4_hit = False
    chapter3_exact = False
    unexpected_shadows = 0
    segments = 0
    for attempt in extract_pi_reasoning(session_path):
        segments += 1
        words = attempt["words"]
        if words < 128:
            continue
        exact, shadow, seconds = replay_native_text(attempt["reasoning"], attempt["sources"])
        if exact and 7000 <= words <= 9000:
            chapter3_exact = True
        if shadow is not None and not shadow.suppressed_as_source:
            unexpected_shadows += 1
        if words > 14000:
            chapter4_found = True
            chapter4_hit = shadow is not None and not shadow.suppressed_as_source
        if exact or shadow or words >= 5000:
            kind = ("SOURCE-SUPPRESSED" if shadow and shadow.suppressed_as_source
                    else "SHADOW-OBSERVED" if shadow else "NO SHADOW EVENT")
            print(f"  turn={attempt['turn']:2} retry={attempt['retry']} words={words:6} "
                  f"exact={bool(exact)} shadow={kind:18} "
                  f"at={shadow.word_index if shadow else '-'} "
                  f"time={seconds:.3f}s", flush=True)
    print(f"  Parsed {segments} native-reasoning segment(s).", flush=True)
    if expect_chapter4:
        if not chapter4_found or not chapter4_hit or not chapter3_exact:
            print("  FAIL: Expected Chapter 3 exact interrupt and Chapter 4 shadow observation.", flush=True)
            failures += 1
        else:
            print("  PASS: Recorded Chapter 3 exact interrupt and Chapter 4 shadow observation reproduced.", flush=True)
    if expect_no_shadow:
        if unexpected_shadows:
            print(f"  FAIL: {unexpected_shadows} unsuppressed long-cycle observation(s) in negative control.", flush=True)
            failures += 1
        else:
            print("  PASS: No long-cycle observations in negative control.", flush=True)
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pi-session", type=Path, help="Previously exported Pi session HTML (optional)")
    parser.add_argument("--expect-chapter4", action="store_true", help="Fail unless the recorded Chapter 3 and Chapter 4 loops are found")
    parser.add_argument("--expect-no-shadow", action="store_true", help="Fail if any unsuppressed long-cycle observation occurs")
    args = parser.parse_args()
    if (args.expect_chapter4 or args.expect_no_shadow) and not args.pi_session:
        parser.error("--expect-chapter4/--expect-no-shadow requires --pi-session")
    if args.expect_chapter4 and args.expect_no_shadow:
        parser.error("These expectations are mutually exclusive")
    errors = check_synthetic()
    if args.pi_session:
        errors += check_pi(args.pi_session, args.expect_chapter4, args.expect_no_shadow)
    print(f"\n{'PASS' if not errors else 'FAIL'}: {errors} failed replay check(s).", flush=True)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
