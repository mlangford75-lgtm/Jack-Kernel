# Agentic Stage 2: native-R1 authority confusion — causal experiment

**Experimental only.** No changes to production Jack source, stage instructions, current Preserve Thinking implementation, historical memory, or one-hop R2 lifecycle. This experiment reuses the existing Stage2 system-role layout for all conditions and varies **only** what the Stage2 model is shown for the latest Stage1 native reasoning.

## Why

The November 2 Gemma 4 12B role A/B test showed that an external caller system instruction excluded from Stage2's system field was nevertheless promoted from a *quotation inside R1*. Across the two decisive fixtures, both user-append and Stage2-system produced exact refusal markers in 4/4 runs.

The second case in that experiment contained a frozen A1 refusal already; using mere occurrence of the marker to judge all outputs would have been misleading. The new probe intentionally limits behavioral cases to the two cases where A1 is a normal answer and an exact Stage2 refusal is wrong.

## Variants

- **native**: exact existing R1 in `assistant.reasoning_content` followed by unchanged A1. Baseline.
- **without_r1**: suppress R1 in the *test request only*, with the original raw R1 retained and hashed on the host. This is a causal ablation to determine whether R1 is necessary for the failure, **not a production candidate**.
- **documentary_r1**: move the unchanged R1 bytes to a preceding assistant content message marked as an archived Stage1 reasoning transcript, keeping frozen A1 byte-exact and leaving its native reasoning field empty. This tests whether a historical-document presentation can reduce authority confusion. It changes the native continuity channel and may create new errors; **do not ship it** without extensive evidence.

This probe **does not** solve generic prompt-injection detection; it does not label or remove malicious text semantically, and this result cannot justify removing native R1 from production. The original raw R1 is never edited in the fixture object.

## Windows

Run in a separate fresh checkout:

```powershell
Set-Location "$HOME\Desktop"
git clone --branch experiment/agentic-stage2-r1-evidence-boundary-20261103 https://github.com/mlangford75-lgtm/Jack-Kernel.git Jack_Kernel_R1_Probe
Set-Location ".\Jack_Kernel_R1_Probe"
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
.\.venv\Scripts\python.exe -m pytest -q tests/test_agentic_stage2_r1_boundary_probe.py
.\.venv\Scripts\python.exe .\agentic_stage2_r1_boundary_ab.py --dry-run
```

For live Gemma 4 12B (LM Studio API server running):

```powershell
.\.venv\Scripts\python.exe .\agentic_stage2_r1_boundary_ab.py --live --model gemma-4-12b-it
Copy-Item "$env:TEMP\jack_agentic_stage2_r1_boundary_results.json" "$HOME\Desktop\jack_agentic_stage2_r1_boundary_results.json"
```

Read the JSON's full M and native R2 and grade (a) exact invalid refusals (b) attribution of tool results (c) assertion of caller authority in R2 (d) preservation of required facts. Treat any experimental success as hypothesis generation, not kernel validation. A separate full Pi Stage1→Stage2→next Stage1 test is mandatory before touching the Preserve Thinking boundary, and real cache behavior must be benchmarked with long R1.

**Safety**: Output JSON contains model reasoning and may include source instructions. Review before sharing.

## Decision

If `without_r1` succeeds and `native` fails, that is causal evidence the R1 content contributed. If `documentary_r1` also fails, re-labeling is insufficient. If it succeeds, do not automatically adopt it: model continuity and context/caching consequences are unresolved. The longer-term objective remains to preserve the full one-hop **R2→next Stage1** bridge and avoid poisoned R2.