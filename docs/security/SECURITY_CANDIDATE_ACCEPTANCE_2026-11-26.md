# Security candidate acceptance — 2026-11-26

Status: targeted and differential qualification passed; independent Pi qualification pending. Not a frozen security checkpoint. Candidate production/test baseline: `9fd4ac82a722f9c26683c7c96adee6b2c2be6020`; main comparison: `915b77a119d1790af7c94b615109b08692cde4fc` (diagnostic PR #177, run 45620143464).

## Automated evidence

- [Combined Phase 9B/10/11](https://github.com/mlangford75-lgtm/Jack-Kernel/actions/runs/45775124942), [isolated executable identity](https://github.com/mlangford75-lgtm/Jack-Kernel/actions/runs/45775124807), [Coder Architect isolation](https://github.com/mlangford75-lgtm/Jack-Kernel/actions/runs/45775124849): passed at the candidate baseline.
- [Candidate full regression](https://github.com/mlangford75-lgtm/Jack-Kernel/actions/runs/45775124841): 1547 passed, 218 failed, two warnings. Main diagnostic: 1419 passed, 242 failed, two warnings. Comparing exact failed node IDs: 218 common, 24 main-only, zero candidate-only. All 12 prior differential failures resolved by authenticated fixtures and updated diagnostics, without production code changes. Full CI is still red; this is differential acceptance, not a fully green suite.
- Fresh-clone bootstrap and eight Pi harnesses were skipped by standard CI after Python regression failure. Independent Pi qualification is added without removing or weakening existing CI gates.

## Operator live evidence

Operator-supplied terminal transcripts, not independent filesystem or backend attestation. Workspace Lock and Restricted Paths enabled. A synthetic 32-character Canary with 25% sensitivity required eight contiguous case-sensitive characters; active quarantine seven characters. Nine-character requested fragment triggered a bracketed Architect hard interruption without the requested fragment being displayed. A seven-character repeat completed Architect, Stage 1 and Stage 2 (turn 2f0F6ZTDTaC-gXH5NxnoxA). An earlier seven-character turn emitted an unbracketed interruption-like message and completed Stage 2; actual matching/exception provenance is inconclusive. Do not count model text as a host security event.

Restricted Windows-path requests were denied in the observed transcript. Repeated denied proposals occurred; identical denied-proposal exhaustion was not established because raw rejected argument identity was not captured. This does not establish a loop-detector defect.

Authorized absolute-path write and execution succeeded according to returned executor evidence (turn p0fYhsfIRZawSL6R3HdOfw): two write receipts, file listing and Python execution, with reported 100th prime 541 and verification PASS. Four host-recorded result receipts preserved despite intervening denied proposals. Receipts explicitly label path and executor CWD representations unverified; returned results do not independently prove disk effects. No claim is made that each of the 100 numbers was independently audited from the truncated display. Legitimate work survived intervening model errors and denials.

## Boundaries and release decision

Do not weaken authority to accommodate stochastic cognition. Selected process-local runtime identity, policy and pending transaction integrity, bounded credential/privacy controls and represented-path enforcement are not general OS sandboxing, arbitrary same-process tamper resistance or independent external effects attestation. Partial matching is contiguous and case-sensitive; no transformed-secret coverage is claimed. Phase 8 remains the last frozen/tagged checkpoint. Final merge eligibility requires independent Pi results and review of the inherited CI debt; no full-green or frozen claim is authorized by this report.
