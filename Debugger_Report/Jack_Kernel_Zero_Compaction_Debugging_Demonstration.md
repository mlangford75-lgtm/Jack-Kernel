# Jack Kernel Code Debugging Demonstration

## 1.48 Million Cumulative Tokens, Zero Compaction, a 3-Bit Local 27B Model, and a Real Frontier-Model Regression Found on a Single 16 GB GPU

**Date:** September 10, 2026  
**System:** Jack Kernel — Code Debugging / Code Debugging (Deep)  
**Local model:** ISTA-DASLab Qwen3.8-27B-GSQ-RCO-GGUF, 3-bit class  
**Runtime:** LM Studio, OpenAI-compatible backend  
**Hardware class:** Single 16 GB GPU  
**Evidence package:** complete Medium log, Medium report, original artifact, Medium-repaired artifact, complete Deep log, Deep report, and Deep-repaired artifact

---

## Executive Summary

This demonstration shows what Jack Kernel can do when a highly compressed local model is given a deliberately engineered inference environment instead of being treated as a conventional chat model.

The cognitive engine was a **3-bit Qwen3.8-27B GSQ-RCO model running locally on a single 16 GB GPU**. Jack Kernel wrapped that model in a five-pass forensic debugging topology with controlled reasoning effort, fresh-pass isolation, report-only tool authority, stage-local tool continuation, compact prior-finding memory, duplicate suppression, and a separate final reporting stage.

The result was exceptional.

The original analog-clock artifact was audited by Jack Code Debugging at Medium reasoning effort. The five independent forensic passes confirmed five distinct defects:

1. A **HIGH**-severity clock-hand geometry/orientation defect that prevented the clock from displaying time correctly.
2. A **MEDIUM**-severity failure to implement required content: `Jack Kernel Demo`, `simple clock`, and the current system date.
3. A **MEDIUM**-severity failure to implement the required black/gold/diamond luxury design.
4. A **MEDIUM**-severity animation defect that caused a reverse sweep at angle wraparound.
5. A **LOW**-severity timing defect caused by updates being phase-locked to page load instead of wall-clock second boundaries.

A GPT-5.6 Sol work-agent pass then implemented the Medium repair specification.

That repair corrected the original defects, but it also introduced a new compositional regression.

Jack Code Debugging (Deep), using the same **3-bit local 27B model**, independently found that new regression in Deep Pass 1. It proved that the hour hand would perform a full 360-degree spin every second throughout the entire 12 o'clock hour at both noon and midnight. The local model isolated the exact interaction between an unnormalized hour angle and newly introduced monotonic rotation logic, simulated the failure sequence, classified it correctly, and specified the repair.

The Deep run did not stop there. Because Jack's compact finding registry prevented later passes from wasting their search on already-confirmed defects, Passes 2 through 5 continued moving through new defect territory. They confirmed four additional LOW-severity robustness issues involving browser lifecycle recovery, mobile viewport configuration, accessibility, and short-viewport reachability.

The most important system-level result was not simply the number of defects found.

It was that the **model work never compacted**.

By the end of the demonstration, the Pi agent session counter showed approximately:

```text
↑1.3M ↓179k 71.4%/120k
```

That is approximately **1.479 million cumulative input/output tokens of session traffic** across the demonstration.

At Deep startup, Jack independently detected the currently loaded LM Studio backend context length as **90,112 tokens**.

The cumulative work therefore exceeded the live backend context capacity by well over an order of magnitude.

**No model-work compaction was required. No active forensic pass was summarized to make room. No unfinished reasoning trajectory was collapsed into a lossy replacement.**

Jack achieved this by controlling the lifetime of cognition itself.

Within a forensic pass, active native reasoning, tool calls, and tool results remained available so the model could continue the same investigation without losing its work. At the end of that pass, Jack retired the completed native cognition and carried forward only the small amount of state that the next independent pass was authorized to know, principally the compact identity of confirmed prior findings.

This is the central result of the demonstration:

> **Jack Kernel enabled approximately 1.48 million cumulative tokens of sustained debugging work with a 3-bit 27B local model on a single 16 GB GPU, while keeping every active forensic investigation intact and requiring zero model-work compaction.**

The model did not need a million-token context window.

Jack made a million-token workflow possible by governing cognition as a lifecycle rather than treating the entire history as permanent live context.

---

# 1. Test Configuration

## Local Model

The model used for the demonstration was from:

**ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF**

Model source:

https://huggingface.co/ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF

The repository provides non-uniform GSQ-RCO quantizations of Qwen3.8-27B. Its 3.00-bpw `IQ3_XXS` build is listed at approximately **10.1 GB**, making a 27B-class model practical on 16 GB-class local hardware.

The repository's own benchmark table also shows how much capability is retained at this compression level. The 3.00-bpw build reports:

- AIME25: **100.00**
- GPQA-Diamond: **88.89**
- LiveCodeBench v6: **84.57**

For comparison, the BF16 base is listed at:

- AIME25: **100.00**
- GPQA-Diamond: **89.90**
- LiveCodeBench v6: **85.71**

The demonstration therefore did not rely on a large cloud model hidden behind Jack. It used a heavily quantized, locally hosted 27B model.

## Hardware

The model was run locally in a **single 16 GB GPU environment** through LM Studio.

This is a critical part of the demonstration. Jack's debugger was not being driven by a multi-GPU server, an enterprise inference cluster, or a frontier cloud endpoint.

The high-quality forensic behavior documented in the logs came from a local 3-bit model that fits the practical memory class of a high-end consumer GPU.

## Jack Runtime

The Jack runtime log records:

```text
Backend        : LM Studio
Backend URL    : http://127.0.0.1:1234/v1
Backend model  : qwen3.8-27b-gsq-rco
Agent base URL : http://127.0.0.1:8000/v1
Virtual model  : jack-kernel
Reasoning level  : Code Debugging (Deep)
Preserve thinking: ON
Forensic archive : STAGE
Kernel-side max_tokens limits: NONE
```

For the Deep run, Jack also detected:

```text
Detected loaded LM Studio context length: 90112
Resolved currently loaded LM Studio model: qwen3.8-27b-gsq-rco
```

The model was therefore operating with a finite backend context of 90,112 tokens while participating in a workflow whose cumulative token traffic reached roughly 1.48 million tokens.

---

# 2. What Jack Kernel Changed

Jack did not change the model's weights.

Jack changed the **conditions under which the model was allowed to reason**.

That difference is the point of the system.

A conventional coding agent usually accumulates one large cognitive trajectory:

```text
inspect
→ reason
→ find bug
→ edit
→ inspect own edit
→ defend or revise edit
→ continue from the same accumulated context
```

That structure creates several known practical problems:

- prior findings become cognitive attractors;
- the model repeatedly returns to the same bug;
- old hypotheses remain salient after they should have lost authority;
- the same reasoning trajectory that created a patch often judges the patch;
- tool output accumulates indefinitely;
- context pressure eventually causes truncation or compaction;
- lossy summaries can replace exact prior cognition.

Jack's debugger uses a different topology.

Each forensic pass is a fresh reasoning episode over the current artifact and the exact original authority. A pass may investigate broadly, but it locks onto one strongest new candidate and audits that candidate deeply.

If the candidate is confirmed, Jack registers it.

The next pass receives only a compact prior-finding registry for duplicate avoidance. It does **not** inherit the prior pass's entire reasoning history.

The topology is:

```text
CURRENT ARTIFACT
      |
      v
FRESH FORENSIC PASS 1
      |
      +--> one strongest candidate
      +--> investigate with tools
      +--> confirm / reject
      |
      v
COMPACT CONFIRMED-FINDING REGISTRY
      |
      v
RAW PASS-1 COGNITION RETIRED
      |
      v
FRESH FORENSIC PASS 2
      |
      +--> prior confirmed finding is closed territory
      +--> search somewhere new
      |
      v
...
PASS 5
      |
      v
FRESH FINAL REPORTER
      |
      v
CONSOLIDATED REPAIR SPECIFICATION
```

This architecture does two things at once:

1. It preserves enough state to stop the model from looping over previously confirmed defects.
2. It removes enough state to keep each new pass cognitively independent.

That is why Jack can keep moving through defect space instead of simply accumulating more discussion about the first obvious problem.

---

# 3. Medium Run: Five Passes, Five Distinct Confirmed Defects

The first audit targeted the original `index.html`, a 3,101-byte single-file analog clock.

The target remained unchanged throughout the audit. The debugger was report-only.

The final Medium report recorded five confirmed findings.

| Pass | Severity | Finding |
|---|---|---|
| 1 | HIGH | Clock hands used the wrong pivot and base orientation, preventing correct time display |
| 2 | MEDIUM | Required `Jack Kernel Demo`, `simple clock`, and current system date content was missing |
| 3 | MEDIUM | Required black/gold/diamond luxury styling was absent |
| 4 | MEDIUM | CSS transition produced a reverse sweep during angle wraparound |
| 5 | LOW | Timer updates were aligned to page-load phase rather than real second boundaries |

This is important because the five passes did not collapse onto the same defect.

Pass 5 still found a new timing problem after four prior findings had already been established.

Jack's compact registry was performing exactly the function it was designed for: **preserve established search state without preserving the old cognitive trajectory**.

The Medium report also preserved residual observations that were not promoted to findings. Some of those later became relevant during the Deep run. That is another sign that the debugger was not simply promoting every observation it encountered.

---

# 4. The Frontier-Model Repair

After the Medium report was complete, GPT-5.6 Sol was used as the work agent.

The work agent received the report and the broken HTML and implemented the required fixes.

The repaired file became `index_medium.html`.

This stage is important because it created a realistic verification problem.

The Deep debugger was not merely handed the original intentionally imperfect file again.

It was handed a file that had already been:

- audited by Jack Medium;
- repaired according to a detailed forensic report;
- implemented by a frontier model;
- statically checked after repair.

That is exactly the point where many coding workflows stop.

Jack did not stop.

The repaired artifact became the new ground truth and was attacked again.

---

# 5. Deep Pass 1 Found a Real Regression Introduced by GPT-5.6 Sol

The most important individual finding in the entire demonstration came immediately in Deep Pass 1.

The frontier-model repair had introduced a subtle interaction between the preserved hour-angle calculation and the new monotonic rotation mechanism.

The repaired code retained:

```javascript
const h = now.getHours() % 12 || 12;
const hourDeg = (h / 12) * 360 + (m / 60) * 30;
```

At twelve o'clock, `h` becomes 12.

That makes `hourDeg` occupy approximately:

```text
[360°, 389.5°)
```

instead of:

```text
[0°, 29.5°)
```

The new monotonic wrapper used the previous accumulated angle as a rotation base and assumed the incoming raw target remained below 360 degrees.

The interaction produced a genuine runtime defect.

Deep reconstructed the sequence:

```text
11:59:59 → 12:00:00
359.5° → 360°
delta = +0.5°      correct

12:00:01
stored angle = 720°
delta = +360°      incorrect full spin

12:00:02
stored angle = 1080°
delta = +360°      incorrect full spin
```

The same full rotation would repeat every second for the entire 12 o'clock hour.

The report calculated approximately 3,599 full-spin ticks before normal behavior recovered at 13:00:00. The same defect existed at midnight.

The static resting position remained correct modulo 360 degrees, which made the bug particularly subtle: the clock still pointed to the right time when sampled statically, but the CSS transition visibly animated every unnecessary full revolution.

The Deep model correctly identified:

- the exact affected code;
- the mathematical cause;
- the runtime manifestation;
- the affected time windows;
- why minute and second hands were unaffected;
- why the defect self-recovered;
- the correct severity;
- the minimal repair.

This was not a superficial code-style observation.

It was a **real functional regression introduced by a frontier model and independently discovered by a 3-bit local 27B model running through Jack Kernel**.

That is an extraordinary demonstration of what inference topology can contribute.

Jack did not make the local model larger.

Jack gave the local model a better forensic job.

---

# 6. Deep Continued Into New Defect Territory

After Deep Pass 1 confirmed the regression, Jack placed it into the compact prior-finding registry.

Pass 2 did not spend its reasoning rediscovering it.

Neither did Pass 3, Pass 4, or Pass 5.

The completed Deep run confirmed five distinct findings:

| Pass | Severity | Finding |
|---|---|---|
| 1 | MEDIUM | Hour hand performs a false 360° spin every second throughout the 12 o'clock hour |
| 2 | LOW | Background-tab lifecycle/timer behavior can leave stale time and animate catch-up |
| 3 | LOW | Missing mobile viewport metadata produces poor mobile scaling |
| 4 | LOW | The displayed time has no accessible representation for assistive technology |
| 5 | LOW | `body { overflow: hidden }` makes content unreachable on sufficiently short viewports |

The fifth pass is especially significant because it escalated a plausible static concern into runtime evidence.

The model tested the actual page in headless Chrome/Blink and recorded:

- fixed content height: approximately **299 px**;
- tested CSS viewport height: **149 px**;
- document scroll height: **299 px**;
- user wheel input failed to move `window.scrollY` from zero;
- the date remained entirely below the fold;
- part of the clock was permanently unreachable.

The pass used controls to isolate the behavior to the overflow rule.

This is the kind of work expected from a serious forensic debugger: form a hypothesis, obtain evidence, isolate the mechanism, and only then confirm the defect.

---

# 7. The Anti-Looping Result

A major purpose of Jack's debugger is to prevent repeated model calls from circling the same salient problem.

This demonstration shows that mechanism working.

By Deep Pass 5, the pass had a compact registry containing four already-confirmed defects.

It nevertheless found a fifth, distinct issue.

The reason is architectural.

Jack does not merely tell the model to "look again."

It changes the next inference's search state.

The next pass knows:

```text
Finding A is already established.
Finding B is already established.
Finding C is already established.
Finding D is already established.
```

But it does not receive the entire probabilistic reasoning history that made those findings salient in the first place.

The result is a controlled form of independent review.

Jack preserves **what has been established** while discarding **the cognitive path that established it**.

This is one of the strongest differences between Jack and ordinary iterative self-review loops.

---

# 8. Report-Only Authority Was Enforced by the Kernel

The debugger was not merely prompted to avoid editing.

Jack physically removed direct mutation tools from the forensic tool surface.

The runtime records:

```text
Code Debugging report-only policy removed direct mutation tools: edit, write
```

This matters because it separates **forensic authority** from **repair authority**.

The debugging model could inspect, search, run commands, simulate behavior, test hypotheses, and collect evidence.

It could not silently repair the artifact and then inspect its own modified target as though nothing had changed.

The artifact remained stable through each audit.

That makes the evidence chain much cleaner.

The sequence becomes:

```text
audit immutable artifact
→ report
→ separate work agent repairs
→ new artifact identity
→ fresh audit
```

The frontier-model regression was discoverable precisely because the repaired file became a new artifact to attack rather than an extension of the patcher's own reasoning trajectory.

---

# 9. Stage-Local Tool Continuation Preserved Full Active Work

Jack's zero-compaction result does not come from starving the model of context.

Within each active forensic pass, Jack preserved the work that still mattered.

The runtime log repeatedly records:

```text
Code Debugging Pass N checkpointed for stage-local tool resume
```

followed by:

```text
Resuming Code Debugging Pass N transaction in place
```

This happened throughout the run.

Pass 1 used many stage-local tool continuations.

Pass 2 continued through multiple tool interactions.

Passes 3 and 4 did the same.

Pass 5 became particularly extensive, continuing through repeated tool calls, runtime experiments, controls, and evidence gathering before finally committing its result.

The important property is:

> **A tool call did not destroy the active forensic stage.**

The result came back into the same governed investigation.

The model could continue reasoning with the evidence it had already accumulated.

Jack therefore preserved cognition where continuity was valuable.

Then, when the pass ended, Jack retired that completed cognition before the next independent pass began.

That selective continuity is central to the design.

---

# 10. Zero Compaction Across a ~1.48 Million Token Workflow

This is the most important long-horizon result in the demonstration.

Near the end of the full workflow, the Pi status line showed:

```text
↑1.3M ↓179k 71.4%/120k
```

Approximately:

```text
1,300,000 input
+ 179,000 output
----------------
≈1,479,000 cumulative tokens
```

At Deep startup, Jack detected the actual loaded LM Studio backend context length as:

```text
90,112 tokens
```

These are different measurement layers: Pi was displaying its session accounting and host context budget, while Jack was measuring the loaded local backend context.

The important fact is that the cumulative work dwarfed both.

The workflow crossed roughly **1.48 million cumulative tokens** while the local backend remained a bounded-context model.

And the model work **never compacted**.

There was no emergency summary of an unfinished pass.

There was no lossy replacement of active native reasoning.

There was no "conversation too long, summarize what happened and continue."

There was no need to compress a live investigation to keep it running.

The full logs are preserved specifically so this behavior can be inspected end to end.

The Jack runtime log runs from Deep initialization through the final report commit and contains the complete sequence of stage-local continuation events. It records no model-work compaction event, no context-overflow recovery, and no truncation boundary replacing active debugging cognition.

This is not accidental.

It is a direct consequence of Jack's cognitive lifecycle architecture.

---

# 11. Jack Prunes Completed Cognition Instead of Compacting Active Cognition

The distinction between **pruning** and **compaction** is fundamental.

Compaction means taking a body of still-relevant active work and replacing it with a shorter, probabilistically generated approximation because the context is becoming too large.

Jack does not need to do that here.

Jack instead gives cognition an explicit lifetime.

During Pass 3, Pass 3's reasoning and evidence are active.

Pass 3 is allowed to keep them.

When Pass 3 completes, its raw native cognition no longer has authority over Pass 4.

Jack retires it.

Only the exact state explicitly authorized to cross the boundary survives.

For Code Debugging, that includes the compact confirmed-finding registry needed to prevent duplication.

So Jack's lifecycle is:

```text
PASS ACTIVE
    |
    | preserve full active reasoning and evidence
    v
PASS COMPLETES
    |
    | commit supported finding
    | archive forensic history
    | retire raw live cognition
    v
PROJECT ONLY AUTHORIZED STATE FORWARD
    |
    v
NEW FRESH PASS
```

This is not a workaround for a small context window.

It is a better use of a context window.

The model's live memory is reserved for the problem it is actually solving now.

---

# 12. Why the 16 GB GPU Result Matters

Large-context, multi-agent, high-effort debugging systems are often associated with expensive cloud models or large accelerator configurations.

This demonstration was run with a **single 16 GB GPU**.

The local cognitive engine was a **3-bit 27B model**.

The 3.00-bpw GSQ-RCO build is approximately 10.1 GB according to the publisher's repository.

Despite that severe compression and modest hardware envelope, Jack drove the model through sustained, high-effort forensic work involving:

- exact source inspection;
- multi-step tool use;
- stage-local continuation;
- runtime simulation;
- browser testing;
- hypothesis rejection;
- evidence qualification;
- severity classification;
- independent multi-pass search;
- duplicate suppression;
- final repair-spec synthesis.

The system did not collapse into shallow one-shot review.

It sustained deep work for more than an hour during the Deep run alone.

The runtime was started for the Deep audit at approximately 03:59 and the final report was committed at 05:12.

That is more than an hour of continuous governed forensic work from a local, 3-bit, 27B model on a 16 GB GPU.

Jack allowed the model to spend compute instead of requiring it to retain every previous thought forever.

That is a major practical advantage.

A small-memory machine can participate in an extremely long cognitive workflow as long as the inference system knows what information must remain live and what information has reached the end of its useful lifetime.

---

# 13. The Performance Is a System Result, Not Just a Model Result

Qwen3.8-27B is a capable model.

The 3-bit GSQ-RCO quantization preserves a remarkable amount of that capability.

But the behavior in this demonstration cannot be understood by looking only at the base model.

The same model in a conventional single-threaded agent loop would not automatically gain:

- independent fresh forensic passes;
- strict one-candidate focus;
- compact duplicate-avoidance state;
- removal of prior native reasoning between passes;
- stage-local tool continuation;
- report-only enforcement;
- stable artifact boundaries;
- controlled reasoning effort;
- temperature diversity;
- final-report authority separation;
- deterministic state retirement;
- zero-compaction long-horizon operation.

Those properties came from Jack Kernel.

The model provided the intelligence.

**Jack organized that intelligence into a system.**

That is the reason the 16 GB GPU result is so important.

Jack does not require the user to solve the problem by simply scaling the model upward.

It extracts more useful work from a model that can already run locally.

The demonstration shows a heavily quantized local model performing work that included discovering a real regression introduced by a frontier model.

The correct lesson is not that model scale is irrelevant.

The lesson is that **model scale is not the whole system**.

Inference topology matters.

Context topology matters.

Authority matters.

State lifetime matters.

Independent search matters.

Jack makes those variables programmable.

---

# 14. The Strongest Event in the Demonstration

The clearest single event can be stated plainly:

> **GPT-5.6 Sol repaired the clock according to the Medium debugging report and introduced a new regression. Jack Kernel then placed a 3-bit local Qwen3.8-27B model into a fresh Deep forensic topology, and that local model found, reproduced, explained, and correctly repaired the regression.**

This is significant because the bug was not deliberately planted for Deep.

It emerged from the repair itself.

Deep was therefore evaluating a genuine new artifact.

The local model had no authorship commitment to defend.

Jack gave it independence from the patcher's cognitive trajectory.

That independent topology paid off immediately.

---

# 15. Evidence Package

The complete demonstration was preserved.

The GitHub evidence directory contains:

```text
Debugging_Deep_Report_2026-09-10_03-59-52_259234_9921f398.md
Debugging_Medium_Report_2026-09-10_03-16-34_890468_ac4d35d6.md
Deep_Full_Log.txt
Medium_Full_Log.md
index.html
index_medium.html
index_deep.html
```

Observed file sizes at preservation time:

| File | Bytes |
|---|---:|
| Debugging Deep Report | 76,887 |
| Debugging Medium Report | 71,874 |
| Deep Full Log | 627,588 |
| Medium Full Log | 341,274 |
| Original HTML | 3,101 |
| Medium-repaired HTML | 6,448 |
| Deep-repaired HTML | 8,016 |

This matters because the result is not represented only by a final summary.

The complete model work is available.

A reviewer can inspect:

- the original broken artifact;
- every Medium forensic pass;
- the Medium final report;
- the exact repaired artifact;
- every Deep forensic pass;
- the Deep final report;
- the final repaired artifact;
- the progression of prior-finding registries;
- the model's tool-driven investigations;
- the regression discovery;
- the final repair instructions.

The evidence exists at the level needed to audit the demonstration rather than simply trust a claim about it.

---

# 16. What This Demonstration Establishes

This demonstration establishes several concrete properties of Jack Kernel's Code Debugging architecture.

## 16.1 A local 3-bit 27B model can perform deep forensic debugging on a single 16 GB GPU

The work was not limited to syntax checking or trivial code review.

The model performed sustained reasoning, simulation, browser-level validation, evidence gathering, and multi-pass search.

## 16.2 Jack can force repeated inference into new defect territory

Confirmed findings were carried forward as compact exclusion state.

Later passes continued finding materially different defects instead of looping over the most salient earlier problem.

## 16.3 Jack can separate forensic authority from repair authority

The debugger's direct mutation tools were removed by the kernel.

Audits operated against stable artifacts.

Repairs created new artifacts that could then be independently challenged.

## 16.4 Jack can preserve an active investigation across many tool calls

Stage-local checkpoint/resume kept a pass intact while tools were used repeatedly.

The model did not have to restart its reasoning after each tool call.

## 16.5 Jack can retire cognition at semantic boundaries

When a forensic pass finished, its raw cognition did not remain live merely because it existed historically.

Only explicitly authorized state crossed into the next pass.

## 16.6 Jack can sustain cumulative work far beyond the physical context window

The session reached approximately **1.479 million cumulative tokens** while the actual loaded LM Studio backend context was detected at **90,112 tokens**.

## 16.7 Jack required zero model-work compaction

This is the core long-horizon result.

**No active forensic pass was compacted.**

Jack kept active cognition intact until its work was complete, then retired it cleanly at the stage boundary.

The workflow scaled by **cognitive lifecycle control**, not by lossy compression.

## 16.8 Jack enabled a local model to catch a frontier-model regression

A 3-bit Qwen3.8-27B model, running locally, identified a real bug introduced by GPT-5.6 Sol during repair.

That result demonstrates the practical value of independent inference topology.

---

# 17. Why Zero Compaction Is the Key Result

The easiest way to misunderstand this demonstration is to focus only on the 1.48 million-token number.

Jack did not create a 1.48 million-token context window.

It did something more useful.

It allowed approximately 1.48 million tokens of cumulative cognitive work to occur **without forcing approximately 1.48 million tokens to remain alive at once**.

That is the architectural achievement.

Traditional long-running chat systems tend toward:

```text
history grows
→ context grows
→ context becomes full
→ summarize / compact / truncate
→ continue from a lossy representation
```

Jack's debugger instead does:

```text
fresh pass
→ keep all active work while needed
→ finish pass
→ preserve exact authorized result
→ retire completed cognition
→ start fresh pass
```

The model never had to trade away the fidelity of its unfinished investigation just to survive the context limit.

That is why **zero compaction** is not merely an implementation detail.

It is evidence that Jack's context-lifecycle thesis works in practice.

> **Cumulative cognition does not need to equal live context.**

> **History does not need to equal working memory.**

> **Completed reasoning does not need permanent authority over future reasoning.**

Jack Kernel turns those principles into runtime behavior.

---

# 18. Final Result

This demonstration combined:

- a **3-bit Qwen3.8-27B** local model;
- a **single 16 GB GPU**;
- LM Studio;
- Jack Kernel;
- five-pass Medium forensic debugging;
- a frontier-model repair;
- five-pass Deep forensic debugging;
- approximately **1.48 million cumulative session tokens**;
- an actual backend context detected at **90,112 tokens**;
- **zero model-work compaction**;
- ten confirmed findings across the Medium and Deep audits;
- and a genuine frontier-model regression discovered by the local model.

The defining result is not that Jack made a small model magically infallible.

It is that Jack created a disciplined cognitive runtime in which a highly compressed local model could perform an amount and quality of sustained forensic work that would normally be associated with much larger inference infrastructure.

The local model was allowed to reason deeply when deep reasoning mattered.

Its active work was preserved while it remained active.

Its completed cognition was retired when its authority ended.

Confirmed findings survived in compact form.

Later passes were prevented from wasting themselves on already-solved territory.

Repair and verification were separated.

And despite a cumulative workflow approaching **1.5 million tokens**, **the model work never compacted once**.

That is what Jack Kernel made possible.

---

## One-Sentence Demonstration Result

> **Jack Kernel drove a 3-bit Qwen3.8-27B model on a single 16 GB GPU through roughly 1.48 million cumulative tokens of independent, tool-using forensic debugging with zero model-work compaction, and the local model ultimately discovered and proved a real regression introduced by GPT-5.6 Sol.**
