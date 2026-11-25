"""Phase 10-A actual runtime consumer/closure proof in a fresh Jack process.

Measurement-only. Proves policy snapshots are the exact objects consumed by
the existing path gate, protected output closures, and backend transport.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


_ROOT = Path(__file__).resolve().parents[1]


def test_real_loaded_kernel_policy_holders_and_closure_consumers(tmp_path):
    script = r'''
import dataclasses
import types

import jack_kernel as jk
from jack_evidence_guard import RuntimeCanaryPolicy
from jack_credential_guard import RuntimeCredentialPolicy
from jack_policy_integrity import RuntimePolicyAuthority, PolicyIntegrityCompromised

jk._install_bundled_runtime_extensions()


def cells_of_type(root, typ):
    visited = set()
    found = []

    def visit(value):
        if isinstance(value, types.MethodType):
            value = value.__func__
        if not isinstance(value, types.FunctionType):
            return
        if id(value) in visited:
            return
        visited.add(id(value))
        for cell in value.__closure__ or ():
            try:
                item = cell.cell_contents
            except ValueError:
                continue
            if type(item) is typ:
                found.append(cell)
            elif isinstance(item, (types.FunctionType, types.MethodType)):
                visit(item)

    visit(root)
    return found


path_policy = jk._RUNTIME_PATH_POLICY
assert path_policy is jk._runtime_path_policy()
assert path_policy is not None

canary_run_cells = cells_of_type(jk.KERNEL.run, RuntimeCanaryPolicy)
canary_stream_cells = cells_of_type(jk.KERNEL.stream, RuntimeCanaryPolicy)
assert canary_run_cells, "No real Canary output-run closure found"
assert canary_stream_cells, "No real Canary output-stream closure found"
canary_policy = canary_run_cells[0].cell_contents
canary_stream_cell = next(
    cell for cell in canary_stream_cells
    if cell.cell_contents is canary_policy
)

credential_policy = jk._JACK_RUNTIME_CREDENTIAL_POLICY
assert type(credential_policy) is RuntimeCredentialPolicy
credential_post_cells = cells_of_type(
    jk.BACKEND._client.post, RuntimeCredentialPolicy
)
assert credential_post_cells, "Protected backend transport has no credential-policy closure"
assert any(cell.cell_contents is credential_policy for cell in credential_post_cells)
credential_build_cells = cells_of_type(
    jk.BACKEND._client.build_request, RuntimeCredentialPolicy
)
assert credential_build_cells, "Protected backend request builder has no policy closure"
credential_build_cell = next(
    cell for cell in credential_build_cells
    if cell.cell_contents is credential_policy
)

guard = RuntimePolicyAuthority()
guard.register_attribute(
    label="path-consumer", kind="path", holder=jk,
    attribute="_RUNTIME_PATH_POLICY",
)
guard.register_attribute(
    label="credential-holder", kind="credential", holder=jk,
    attribute="_JACK_RUNTIME_CREDENTIAL_POLICY",
)
guard.register_cell(
    label="canary-real-run-closure", kind="canary",
    cell=canary_run_cells[0],
)
guard.register_cell(
    label="canary-real-stream-closure", kind="canary",
    cell=canary_stream_cell,
)
guard.register_cell(
    label="credential-real-transport", kind="credential",
    cell=credential_post_cells[0],
)
guard.register_cell(
    label="credential-real-build-request", kind="credential",
    cell=credential_build_cell,
)
guard.seal()
for label in (
    "path-consumer", "credential-holder",
    "canary-real-run-closure", "canary-real-stream-closure",
    "credential-real-transport", "credential-real-build-request",
):
    guard.verify_for(label)

# The two binding classes must not silently mask tampering with one of them.
replacement = dataclasses.replace(credential_policy)
assert replacement is not credential_policy
jk._JACK_RUNTIME_CREDENTIAL_POLICY = replacement
try:
    guard.verify_for("credential-holder")
except PolicyIntegrityCompromised:
    pass
else:
    raise AssertionError("Replacing effective credential holder was not detected")
# The transport retained the original policy and is still accurately observed.
guard.verify_for("credential-real-transport")
guard.verify_for("credential-real-build-request")
assert guard.invalidated_labels == ("credential-holder",)

# A second independent attack changes the actual streaming DLP policy cell.
# Even if the run guard remains intact, the stream boundary must not be
# considered trusted with a different policy captured at release time.
canary_stream_cell.cell_contents = dataclasses.replace(canary_policy)
try:
    guard.verify_for("canary-real-stream-closure")
except PolicyIntegrityCompromised:
    pass
else:
    raise AssertionError("Replacing active streaming Canary closure was not detected")
assert "canary-real-stream-closure" in guard.invalidated_labels
jk._JACK_AUTHORITY_LEDGER.close()
'''

    env = dict(os.environ)
    env.update({
        "JACK_AUTHORITY_LEDGER_DIR": str(tmp_path / "ledger"),
        "JACK_FORENSIC_ARCHIVE_MODE": "off",
        "JACK_BACKEND_MODEL": "test-model",
        "JACK_BACKEND_PROFILE": "lmstudio",
    })
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=_ROOT, env=env, text=True,
        capture_output=True, check=False, timeout=55,
    )
    assert result.returncode == 0, (
        f"real policy consumer qualification failed ({result.returncode})\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
