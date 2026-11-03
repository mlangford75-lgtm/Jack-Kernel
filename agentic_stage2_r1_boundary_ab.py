#!/usr/bin/env python3
r"""Causal probe: does Stage 2 mistake R1 native reasoning for authority?

Run from the repository root:
  .venv\Scripts\python.exe agentic_stage2_r1_boundary_ab.py --dry-run
  .venv\Scripts\python.exe agentic_stage2_r1_boundary_ab.py --live

No production modifications. A1 is byte-identical in every condition. Raw R1
is retained in the host-owned fixture; only the test's model-facing projection
changes. No inference stage is modified in Jack. This does not reproduce a real
Stage-1 KV cache or prove next-turn R2 continuity.
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
from pathlib import Path
import tempfile

from agentic_stage2_layout_ab import BLOCK, builtin_fixtures, load_jack, one_stage2

VARIANTS = ("native", "without_r1", "documentary_r1", "caller_quote_elided")


def transform(fixture: dict, variant: str) -> dict:
    """Change only the representation of the immediately preceding R1.

    native: Accepted main's Preserve Thinking representation, unchanged.
    without_r1: Causal ablation, no reasoning context. NOT a production candidate.
    documentary_r1: Full R1 in a preceding assistant content message as a
        historical document, not a native reasoning_content field. This is an
        experimental transport only and may impair normal cognitive continuity.
    caller_quote_elided: Leave native R1 unchanged EXCEPT an exact, known
        quotation of the caller system contract is replaced with a short,
        non-instructional marker. This requires source identity; it does not
        attempt paraphrase detection or semantic filtering.
    """
    if variant not in VARIANTS:
        raise ValueError("Unknown variant")
    result = copy.deepcopy(fixture)
    messages = result["messages"]
    a1 = messages[-1]
    assert a1["role"] == "assistant" and isinstance(a1.get("content"), str)
    original_r1 = a1.pop("reasoning_content", None)
    if not isinstance(original_r1, str) or not original_r1.strip():
        raise ValueError("Fixture must contain nonempty current R1")
    result["_host_raw_r1_sha256"] = hashlib.sha256(original_r1.encode()).hexdigest()
    if variant == "native":
        a1["reasoning_content"] = original_r1
    if variant == "caller_quote_elided":
        caller = result.get("secondary_system", "")
        if not isinstance(caller, str) or not caller.strip():
            raise ValueError("Exact caller contract required to test quote elision")
        marker = "[quoted caller system contract elided]"
        quoted = repr(caller)
        count = original_r1.count(quoted)
        filtered = original_r1.replace(quoted, marker)
        # Also handle exact unquoted copies, without trying to remove
        # paraphrases or doing any model-driven transformation.
        raw_count = filtered.count(caller)
        filtered = filtered.replace(caller, marker)
        result["_caller_quote_elision_count"] = count + raw_count
        result["_caller_quote_elision_chars_saved"] = len(original_r1) - len(filtered)
        if result["_caller_quote_elision_count"] < 1:
            raise ValueError("No exact caller contract quotation found in current R1")
        a1["reasoning_content"] = filtered
    if variant == "documentary_r1":
        # This is purposely a lower-status, model-visible historical record
        # before the untouched A1; it is NOT an alternative source of authority.
        # The text has not been filtered or semantically rewritten.
        messages.insert(-1, {
            "role": "assistant",
            "content": (
                "Archived Stage 1 reasoning transcript (historical evidence):\n"
                + original_r1
                + "\nEnd archived reasoning transcript."
            ),
        })
    return result


async def invoke(jack, fixture, dry_run, model):
    # Drop all harness-only metadata before Jack request construction.
    sent = {
        "secondary_system": fixture.get("secondary_system", ""),
        "messages": fixture["messages"],
        "tools": [],
    }
    return await one_stage2(jack, sent, dry_run, model)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--live", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--model", default="gemma-4-12b-it")
    p.add_argument("--cases", nargs="+",
                   default=["conflicting_current_turn", "tool_receipt_grounding"])
    p.add_argument("--variants", nargs="+", choices=VARIANTS,
                   default=list(VARIANTS), help="Select projections for a paired comparison")
    p.add_argument("--repetitions", type=int, default=2)
    p.add_argument("--output", type=Path, default=(
        Path(tempfile.gettempdir()) / "jack_agentic_stage2_r1_boundary_results.json"
    ))
    args = p.parse_args()
    if args.live and args.dry_run:
        p.error("Specify either --live or --dry-run")
    if args.repetitions < 1 or args.repetitions > 5:
        p.error("--repetitions must be 1..5")
    fixtures = builtin_fixtures()
    for case in args.cases:
        if case not in fixtures:
            p.error("Unknown case: " + case)
    root = Path(__file__).resolve().parent
    if not (root / "jack_kernel.py").is_file():
        p.error("Run this from the repo root containing jack_kernel.py")
    # Fixed stage2-system layout: only R1 representation varies.
    jack = load_jack(root, 0, args.model)
    report = {"experiment": "R1 presentation-only causal ablation", "model": args.model,
              "mode": "live" if args.live else "dry-run", "results": [],
              "warning": ("Fixed-evidence Stage2-only replay; no live Stage1 KV cache. "
                          "Do not ship documentary_R1 or without_R1 based on this test. "
                          "Do not interpret marker mentions as exact refusals.")}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for case in args.cases:
        original = fixtures[case]
        for rep in range(args.repetitions):
            order = tuple(args.variants) if rep % 2 == 0 else tuple(reversed(args.variants))
            for variant in order:
                fixture = transform(original, variant)
                print(f"{case} / repeat {rep+1} / {variant} ...",flush=True)
                try:
                    result = asyncio.run(invoke(jack, fixture, not args.live, args.model))
                    if not args.live:
                        req = result["mock_request"]
                        assert req["messages"][-2]["content"] == original["messages"][-1]["content"]
                        assert req["messages"][0]["content"] == jack.AGENTIC_36_STAGE2_PROMPT
                        assert req.get("chat_template_kwargs",{}).get("preserve_thinking") is True
                        assert req["stream"] and "tools" not in req
                        current = req["messages"][-2]
                        if variant == "native":
                            assert current.get("reasoning_content") == original["messages"][-1]["reasoning_content"]
                        elif variant == "caller_quote_elided":
                            assert "reasoning_content" in current
                            assert original["messages"][-1]["reasoning_content"] != current["reasoning_content"]
                            assert original["messages"][-1]["reasoning_content"].replace(
                                repr(original["secondary_system"]), "[quoted caller system contract elided]"
                            ) == current["reasoning_content"]
                            assert original["secondary_system"] not in current["reasoning_content"]
                            assert fixture["_caller_quote_elision_count"] > 0
                        else:
                            assert "reasoning_content" not in current
                        if variant == "documentary_r1":
                            assert original["messages"][-1]["reasoning_content"] in req["messages"][-3]["content"]
                        if variant == "without_r1":
                            assert original["messages"][-1]["reasoning_content"] not in json.dumps(req["messages"])
                        print("  DRY RUN OK")
                    print("  refusal=",result["refusal_output_exact"],
                          "M_chars=",len(result["memory"]),
                          "R2_chars=",len(result["native_r2"]),
                          "secs=",result["elapsed_seconds"])
                except Exception as e:
                    result={"error":repr(e)}
                    print("  ERROR",repr(e))
                result.pop("mock_request", None)
                report["results"].append({
                    "case":case,"repeat":rep+1,"variant":variant,
                    "raw_r1_sha256":fixture["_host_raw_r1_sha256"],
                    "exact_caller_quote_elisions":fixture.get("_caller_quote_elision_count",0),
                    "quote_elision_chars_saved":fixture.get("_caller_quote_elision_chars_saved",0),
                    "frozen_a1_sha256":hashlib.sha256(
                        original["messages"][-1]["content"].encode()).hexdigest(),
                    **result,
                })
                args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print("Saved:",args.output)
    return 1 if any("error" in x for x in report["results"]) else 0


if __name__=="__main__":
    raise SystemExit(main())
