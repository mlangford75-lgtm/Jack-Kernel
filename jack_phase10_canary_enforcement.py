"""Experimental Phase 10C Canary integrity at actual Kernel output release."""
from functools import wraps
import types

from jack_evidence_guard import RuntimeCanaryPolicy
from jack_policy_integrity import RuntimePolicyAuthority, PolicyIntegrityUnavailable


def policy_cells(root, policy_type):
    """Discover actual captured policies, not __wrapped__ metadata."""
    visited = set()
    cells = []
    def visit(value):
        if isinstance(value, types.MethodType):
            value = value.__func__
        if not isinstance(value, types.FunctionType) or id(value) in visited:
            return
        visited.add(id(value))
        for cell in value.__closure__ or ():
            try:
                item = cell.cell_contents
            except ValueError:
                continue
            if type(item) is policy_type:
                if not any(cell is old for old in cells):
                    cells.append(cell)
            elif isinstance(item, (types.FunctionType, types.MethodType)):
                visit(item)
    visit(root)
    return cells


def install(jk):
    """Compose before executable sealing; candidate not yet wired into startup."""
    if getattr(jk, "_JACK_RUNTIME_CODE_AUTHORITY", None) is not None:
        raise PolicyIntegrityUnavailable("Canary gate must precede executable seal")
    if getattr(jk, "_JACK_PHASE10_CANARY_AUTHORITY", None) is not None:
        raise PolicyIntegrityUnavailable("Canary gate already installed")
    run, stream = jk.KERNEL.run, jk.KERNEL.stream
    run_cells = policy_cells(run, RuntimeCanaryPolicy)
    stream_cells = policy_cells(stream, RuntimeCanaryPolicy)
    if not run_cells or not stream_cells:
        raise PolicyIntegrityUnavailable("required Canary consumer unavailable")
    policy = run_cells[0].cell_contents
    if policy.runtime_id != jk.RUNTIME_ID or policy.lane_id != jk.LANE_ID:
        raise PolicyIntegrityUnavailable("Canary policy ownership mismatch")
    if any(cell.cell_contents is not policy for cell in run_cells + stream_cells):
        raise PolicyIntegrityUnavailable("conflicting Canary policy consumers")
    guard = RuntimePolicyAuthority()
    labels = []
    for cell in run_cells + stream_cells:
        label = "canary-consumer-" + str(len(labels))
        guard.register_cell(label=label, kind="canary", cell=cell)
        labels.append(label)
    labels = tuple(labels)
    guard.seal()

    def verify():
        guard.verify_for(*labels)
        if jk.RUNTIME_ID != policy.runtime_id or jk.LANE_ID != policy.lane_id:
            raise PolicyIntegrityUnavailable("Canary policy ownership mismatch")

    @wraps(run)
    async def guarded_run(*args, **kwargs):
        verify()
        result = await run(*args, **kwargs)
        verify()
        return result

    @wraps(stream)
    async def guarded_stream(*args, **kwargs):
        verify()
        source = stream(*args, **kwargs)
        try:
            async for chunk in source:
                verify()
                yield chunk
        except PolicyIntegrityUnavailable as exc:
            note = getattr(jk.KERNEL, "_note_outer_stream_failure", None)
            if callable(note):
                note(exc)
            raise
        finally:
            await source.aclose()

    jk.KERNEL.run = guarded_run
    jk.KERNEL.stream = guarded_stream
    jk._JACK_PHASE10_CANARY_AUTHORITY = guard
    return guard
