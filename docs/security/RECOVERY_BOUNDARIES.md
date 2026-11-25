# Recovery boundaries

Native reasoning cycle detection is configurable (4, 6, 8, 12, 16, 24, 32,
48, 64, 128 repetitions; default 12). Minimum exact cycle length is 64 words.
The streamed stage retains its detector across no-progress recursive corrections,
but a deliberate loop retry and a new tool-result resume start a fresh detector.
No historical prompt or tool-result text is fed into the detector.

Recoverable immutable represented-path denials receive explicit no-retry
guidance. Three consecutive identical all-denied proposals end tool recovery
with a tools-off incomplete handoff, retaining successful tool evidence.
Different proposals are still authorized independently; mixed batches keep
authorized siblings. Ordinary tool recovery retains the existing 25-attempt
ceiling. Positive NEVER matches remain hard interrupts; their policy scope
has not been weakened.

User-facing hard Restricted Paths and Canary interrupts are security events,
not internal stage failures. Internal legacy class and protocol names remain.
