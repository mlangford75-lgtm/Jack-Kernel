"""Pi's Jack extension must insist on verified write/edit outcomes without prompt growth."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "Pi" / "jack-kernel.ts"


def test_verification_guideline_is_stable_and_deduplicated():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the Pi extension behavior test")
    source = EXTENSION.read_text(encoding="utf-8")
    start = source.index("const FILE_MUTATION_VERIFICATION_GUIDELINE =")
    end = source.index("const STRUCTURED_PATH_TOOLS =", start)
    implementation = source[start:end]
    script = implementation + """
const assert = require('node:assert/strict');
const rule = FILE_MUTATION_VERIFICATION_GUIDELINE;
assert.match(rule, /write or edit/);
assert.match(rule, /read back/);
assert.match(rule, /Never claim/);
const event = { systemPrompt: 'PI_BASE', systemPromptOptions: {promptGuidelines: []} };
assert.equal(addFileMutationVerificationGuideline(event), undefined);
assert.deepEqual(event.systemPromptOptions.promptGuidelines, [rule]);
assert.equal(addFileMutationVerificationGuideline(event), undefined);
assert.deepEqual(event.systemPromptOptions.promptGuidelines, [rule]);
// Compatibility fallback remains deterministic and adds no conversation message.
const oldHost = {systemPrompt: 'PI_BASE'};
assert.deepEqual(addFileMutationVerificationGuideline(oldHost),
    {systemPrompt: 'PI_BASE\\n\\n' + rule});
oldHost.systemPrompt += '\\n\\n' + rule;
assert.equal(addFileMutationVerificationGuideline(oldHost), undefined);
"""
    completed = subprocess.run(
        [node, "-e", script],
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
    )
    assert completed.returncode == 0, completed.stderr


def test_jack_provider_scoping_and_before_agent_start_integration():
    text = EXTENSION.read_text(encoding="utf-8")
    assert 'pi.on("before_agent_start", async (event, ctx) => {' in text
    assert 'if (String(ctx?.model?.provider || "") !== PROVIDER_NAME) return undefined;' in text
    assert "return addFileMutationVerificationGuideline(event);" in text
    assert "pi.on(\"tool_call\"" in text
