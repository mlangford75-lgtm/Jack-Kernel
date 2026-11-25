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


def test_phase10c_candidate_real_path_release_and_admission(tmp_path):
    """Actual loaded Phase 4 consumers; no production startup activation."""
    script = r'''
import dataclasses
import json
import jack_kernel as jk
from jack_phase10_path_enforcement import install

jk._install_bundled_runtime_extensions()
original = jk._RUNTIME_PATH_POLICY
assert original.workspace_root is not None
guard = install(jk)

def call(path):
    return {"id": "candidate", "type": "function", "function": {
        "name": "write", "arguments": json.dumps({
            "path": path, "content": "safe"})}}

safe = call(r"D:\Projects\Jack\result.txt")
outside = call(r"D:\Outside\result.txt")
allowed, errors = jk._phase4_partition_structured_tool_calls([safe])
assert len(allowed) == 1 and not errors
allowed, errors = jk._phase4_partition_structured_tool_calls([outside])
assert not allowed and errors

payload = {
    "protocol_version": jk.PHASE4_EXECUTOR_ADMISSION_PROTOCOL_VERSION,
    "runtime_id": jk.RUNTIME_ID, "lane_id": jk.LANE_ID,
    "tool_call_id": "candidate", "tool_name": "write",
    "arguments": {"path": r"D:\Outside\result.txt", "content": "safe"},
    "executor_cwd": r"D:\Projects\Jack", "executor_platform": "win32",
    "command_dialect": "powershell",
}
# Removing the optional holder would bypass the legacy partition's None branch.
jk._RUNTIME_PATH_POLICY = None
allowed, errors = jk._phase4_partition_structured_tool_calls([outside])
assert not allowed and errors
assert "AUTHORITY_POLICY_INTEGRITY_COMPROMISED" in errors[0]
try:
    jk._phase4_executor_admission_decision(payload)
except jk.HTTPException as exc:
    assert exc.status_code == 503
    assert exc.detail == "AUTHORITY_POLICY_INTEGRITY_COMPROMISED"
else:
    raise AssertionError("executor admission did not reject missing policy")
assert jk._phase4_partition_structured_tool_calls([]) == ([], [])
jk._RUNTIME_PATH_POLICY = original
allowed, errors = jk._phase4_partition_structured_tool_calls([safe])
assert not allowed and errors
assert guard.invalidated_labels == ("path-consumer",)
jk._JACK_AUTHORITY_LEDGER.close()
'''
    env = dict(os.environ)
    env.update({
        "JACK_AUTHORITY_LEDGER_DIR": str(tmp_path / "ledger"),
        "JACK_FORENSIC_ARCHIVE_MODE": "off",
        "JACK_BACKEND_MODEL": "test-model",
        "JACK_BACKEND_PROFILE": "lmstudio",
        "JACK_PATH_POLICY_JSON": '{"version":1,"workspace_root":"D:/Projects/Jack","never_paths":[]}',
    })
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=_ROOT, env=env,
        text=True, capture_output=True, check=False, timeout=55,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_phase10c_real_canary_and_credential_consequences(tmp_path):
    script = r'''
import asyncio
import dataclasses
import jack_kernel as jk
from jack_evidence_guard import RuntimeCanaryPolicy
from jack_phase10_canary_enforcement import install as install_canary, policy_cells
from jack_phase10_credential_enforcement import install as install_credential
from jack_policy_integrity import PolicyIntegrityCompromised

jk._install_bundled_runtime_extensions()
cell = policy_cells(jk.KERNEL.run, RuntimeCanaryPolicy)[0]
original = cell.cell_contents
canary = install_canary(jk)
credential = install_credential(jk)
client = jk.BACKEND._client
# Real transport construction without network transmission.
request = client.build_request("POST", "http://127.0.0.1:9/v1/chat/completions",
                               json={"messages": []})
assert request.method == "POST"
old = jk._JACK_RUNTIME_CREDENTIAL_POLICY
jk._JACK_RUNTIME_CREDENTIAL_POLICY = dataclasses.replace(old)
try:
    client.build_request("POST", "http://127.0.0.1:9/v1/chat/completions",
                         json={"messages": []})
except PolicyIntegrityCompromised:
    pass
else:
    raise AssertionError("tampered credential policy allowed request construction")
jk._JACK_RUNTIME_CREDENTIAL_POLICY = old
assert credential.state == "INVALIDATED"

async def exercise():
    try:
        await client.post("http://127.0.0.1:9/v1/chat/completions", json={"messages": []})
    except PolicyIntegrityCompromised:
        pass
    else:
        raise AssertionError("invalidated credentials allowed dispatch")
    try:
        await jk._proxy_pi_control_request(None, "POST", "/v1/tasks")
    except PolicyIntegrityCompromised:
        pass
    else:
        raise AssertionError("invalidated credentials reached Pi dispatch")
    cell.cell_contents = dataclasses.replace(original)
    try:
        await jk.KERNEL.run({})
    except PolicyIntegrityCompromised:
        pass
    else:
        raise AssertionError("tampered Canary allowed model run")
    cell.cell_contents = original
    try:
        async for chunk in jk.KERNEL.stream({}):
            raise AssertionError("invalidated Canary allowed stream release")
    except PolicyIntegrityCompromised:
        pass

asyncio.run(exercise())
assert canary.state == "INVALIDATED"
jk._JACK_AUTHORITY_LEDGER.close()
'''
    env = dict(os.environ)
    env.update({
        "JACK_AUTHORITY_LEDGER_DIR": str(tmp_path / "ledger"),
        "JACK_FORENSIC_ARCHIVE_MODE": "off",
        "JACK_BACKEND_MODEL": "test-model",
        "JACK_BACKEND_PROFILE": "lmstudio",
        "JACK_BACKEND_BASE_URL": "http://127.0.0.1:9/v1",
    })
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=_ROOT, env=env,
        text=True, capture_output=True, check=False, timeout=55,
    )
    assert result.returncode == 0, result.stdout + result.stderr
