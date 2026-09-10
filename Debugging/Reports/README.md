# Debugging Run Reports

Jack creates one new report file here for every Code Debugging invocation.

Runtime-generated report filenames are based on local date/time and include a short collision-resistant suffix. Existing run reports are never selected as the output file for a new run.

Do not use prior run reports as live-pass model context. A prior report may be analyzed only as ordinary input outside an active Code Debugging pass.

Pass 0 contains user-origin diagnostic input only. Pre-stage model reasoning and assistant intake dialogue are intentionally excluded from durable run state.

Live-pass context is intentionally narrower than this durable file. Every fresh pass receives exact user-origin Pass 0 authority; Passes 2–5 also receive only a compact host-derived confirmed prior-finding registry from already committed outcomes. Full pass handoffs remain durable here for final synthesis and are never projected into later live audit passes.
