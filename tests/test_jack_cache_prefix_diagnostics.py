"""No model calls. Verify privacy, byte offsets, regions, and fail-open behavior."""
import json
from jack_cache_prefix_diagnostics import CacheBytePrefixProbe


def prepare(probe, stage, stage_instruction, source_system, user, extra=()):
    caller = {"role": "system", "content": source_system}
    prepared = [caller, {"role": "user", "content": user}]
    before = [{"role": "system", "content": stage_instruction}, caller, *extra, prepared[1]]
    regions = probe.capture_regions(before, prepared, stage_instruction)
    after = [{"role": "system", "content": "\n\n".join(m["content"] for m in before if m["role"] == "system")}, prepared[1]]
    return probe.observe(after, stage, regions)


def test_first_system_content_change_identifies_caller_region():
    probe = CacheBytePrefixProbe(enabled=True)
    prepare(probe, "Stage 1", "Stage directive", "Caller instructions stable", "hello")
    d = prepare(probe, "Stage 1", "Stage directive", "Caller instructions changed", "hello")
    match = d["same_stage"]
    assert match["relation"] == "first_message_changed"
    assert match["first_changed_message_index"] == 0
    assert match["first_system_content_utf8"]["offset_status"] == "exact_within_capture_cap"
    assert match["pre_fold_system_regions"]["first_changed_pre_fold_region"] == "caller_or_source_system_1"
    assert match["pre_fold_system_regions"]["region_byte_difference"]["first_differing_utf8_byte_offset"] == len("Caller instructions ".encode("utf-8"))
    assert "Caller instructions" not in json.dumps(d)


def test_stage_directive_change_identified_without_exposing_text():
    probe = CacheBytePrefixProbe(enabled=True)
    prepare(probe, "Stage 1", "Alpha directive", "Same caller", "hello")
    d = prepare(probe, "Stage 1", "Aloha directive", "Same caller", "hello")
    assert d["same_stage"]["pre_fold_system_regions"]["first_changed_pre_fold_region"] == "jack_stage_directive"
    assert "Aloha" not in json.dumps(d)


def test_multibyte_utf8_byte_offset_exact():
    probe = CacheBytePrefixProbe(enabled=True)
    prepare(probe, "Stage 1", "system", "Caf\u00e9 X", "u")
    d = prepare(probe, "Stage 1", "system", "Caf\u00e9 Y", "u")
    # multi-byte e-acute contributes 2 bytes, not 1 character
    offset = d["same_stage"]["pre_fold_system_regions"]["region_byte_difference"]["first_differing_utf8_byte_offset"]
    assert offset == len("Caf\u00e9 ".encode("utf-8"))


def test_append_only_does_not_claim_prefix_divergence():
    probe = CacheBytePrefixProbe(enabled=True)
    sys = {"role": "system", "content": "sys"}
    u = {"role": "user", "content": "u"}
    regions = probe.capture_regions([sys, u], [u], "sys")
    probe.observe([sys, u], "Stage 1", regions)
    d = probe.observe([sys, u, {"role": "tool", "content": "failed"}], "Stage 1", regions)
    assert d["same_stage"]["relation"] == "append_only"


def test_disabled_and_cap_limited_diagnostics():
    disabled = CacheBytePrefixProbe(enabled=False)
    assert disabled.observe([], "Stage 1", []) is None
    assert disabled.capture_regions([], [], "") == []
    probe = CacheBytePrefixProbe(enabled=True, byte_cap=1024)
    prepare(probe, "Stage 1", "p", "A" * 2000 + "X", "u")
    d = prepare(probe, "Stage 1", "p", "A" * 2000 + "Y", "u")
    assert d["same_stage"]["first_system_content_utf8"]["offset_status"] == "unknown_beyond_capture_cap"


def test_no_message_mutation():
    probe = CacheBytePrefixProbe(enabled=True)
    msgs = [{"role": "system", "content": "system"}, {"role": "user", "content": "task"}]
    before = json.dumps(msgs)
    regions = probe.capture_regions(msgs, msgs, "")
    probe.observe(msgs, "Stage 1", regions)
    assert json.dumps(msgs) == before


def test_changed_second_message_reports_exact_json_byte_offset():
    probe = CacheBytePrefixProbe(enabled=True)
    first = [{"role": "system", "content": "system"}, {"role": "user", "content": "value-one"}]
    changed = [{"role": "system", "content": "system"}, {"role": "user", "content": "value-two"}]
    probe.observe(first, "Stage 1", [])
    d = probe.observe(changed, "Stage 1", [])
    comp = d["same_stage"]
    assert comp["relation"] == "middle_changed"
    assert comp["first_changed_message_index"] == 1
    assert comp["first_changed_message_json"]["offset_status"] == "exact_within_capture_cap"
    assert "value-one" not in json.dumps(d)
    assert "value-two" not in json.dumps(d)


def test_sensitive_prompt_text_not_retained_by_probe():
    probe = CacheBytePrefixProbe(enabled=True)
    text = "user-secret--unique-string-53f1e5"
    messages = [{"role": "system", "content": text}]
    regions = probe.capture_regions(messages, [], text)
    report = probe.observe(messages, "Stage 1", regions)
    assert text not in repr(probe._last)
    assert text not in repr(regions)
    assert text not in json.dumps(report)


def test_unchanged_signatures_are_reused_without_additional_retention():
    probe = CacheBytePrefixProbe(enabled=True)
    messages = [{"role": "system", "content": "stable"},
                {"role": "user", "content": "previous-secret-" * 1000}]
    prepare_regions = lambda: probe.capture_regions(messages, [], "stable")
    probe.observe(messages, "stage", prepare_regions())
    old = probe._last
    report = probe.observe(messages, "stage", prepare_regions())
    assert report["same_stage"]["relation"] == "identical_messages"
    assert all(new is previous for new, previous in
               zip(probe._last["messages"], old["messages"]))
    assert probe._last["system"] is old["system"]
    assert probe._last["regions"][0]["sig"] is old["regions"][0]["sig"]
    assert "previous-secret-" not in repr(probe._last)
    assert len(probe._last_by_stage) == 1


def test_reused_signature_requires_exact_capture_length():
    probe = CacheBytePrefixProbe(enabled=True, byte_cap=1024)
    wire = b"abc" * 1000
    reuse = {}
    short = probe._signature(wire, 16, reuse=reuse)
    full = probe._signature(wire, reuse=reuse)
    assert len(short["prefix_hashes"]) == 16
    assert len(full["prefix_hashes"]) == 1024
    assert short is not full
    assert probe._signature(wire, 16, reuse=reuse) is short
    assert probe._signature(wire, reuse=reuse) is full
    changed = probe._signature(wire[:500] + b"X" + wire[501:], reuse=reuse)
    assert probe._offset(full, changed)["first_differing_utf8_byte_offset"] == 500


def test_reuse_reports_identical_offsets_to_fresh_signature_generation(monkeypatch):
    import random
    rng = random.Random(174)
    candidate = CacheBytePrefixProbe(enabled=True, byte_cap=1024)
    reference = CacheBytePrefixProbe(enabled=True, byte_cap=1024)
    original = reference._signature
    monkeypatch.setattr(reference, "_signature",
                        lambda wire, capture_limit=None, **kw: original(wire, capture_limit))
    snapshots = []
    for index in range(12):
        system = "stable" if index % 3 else "system-" + str(index)
        historical = [{"role": "user", "content": "history " + str(n) + "é" * 400}
                      for n in range(index % 6)]
        changed = "x" * rng.randrange(100, 1600) + str(index)
        messages = [{"role": "system", "content": system}, *historical,
                    {"role": "assistant", "content": changed}]
        snapshots.append(messages)
    for i, messages in enumerate(snapshots):
        stage = "stage-" + str(i % 2)
        reports = []
        for probe in (candidate, reference):
            regions = probe.capture_regions(messages, [], messages[0]["content"])
            reports.append(probe.observe(messages, stage, regions))
        assert reports[0] == reports[1]


def test_alternating_stage_regions_reuse_exact_own_stage_signature():
    probe = CacheBytePrefixProbe(enabled=True, byte_cap=1024)
    prepare(probe, "Architect", "architect-only", "shared caller", "task")
    first = probe._last["regions"][0]["sig"]
    prepare(probe, "Coder", "coder-only", "shared caller", "task")
    assert probe._last["regions"][0]["sig"] is not first
    report = prepare(probe, "Architect", "architect-only", "shared caller", "task")
    assert probe._last["regions"][0]["sig"] is first
    assert report["same_stage"]["relation"] == "identical_messages"
    assert report["immediately_preceding"]["relation"] == "first_message_changed"


def test_alternating_stage_changed_regions_match_predecessor_algorithm(monkeypatch):
    candidate = CacheBytePrefixProbe(enabled=True, byte_cap=1024)
    predecessor = CacheBytePrefixProbe(enabled=True, byte_cap=1024)
    original = predecessor.capture_regions

    def previous_capture(*args):
        retained = predecessor._last_by_stage
        try:
            predecessor._last_by_stage = {}
            return original(*args)
        finally:
            predecessor._last_by_stage = retained

    monkeypatch.setattr(predecessor, "capture_regions", previous_capture)
    for index in range(16):
        stage = ("Architect", "Coder", "Compactor")[index % 3]
        inputs = (stage, stage + " directive " + "é" * 600,
                  "caller " + str(index // 6), "history " + str(index))
        assert prepare(candidate, *inputs) == prepare(predecessor, *inputs)


def test_exact_prefix_trajectory_matches_original_algorithm():
    import hashlib
    from array import array

    probe = CacheBytePrefixProbe(enabled=True, byte_cap=131072)
    # Every byte value, BLAKE2b block boundaries, multibyte UTF-8, empty
    # fields, and full capture-cap truncation. Compare the digest values,
    # not just the eventual first-difference report.
    for wire in (b"", bytes(range(256)), "é🙂".encode("utf-8") * 100,
                 bytes(range(256)) * 513):
        for limit in (0, 1, 127, 128, 129, 1024, probe.byte_cap):
            h = hashlib.blake2b(digest_size=8, key=probe._key)
            expected = array("Q")
            for item in wire[:limit]:
                h.update(bytes((item,)))
                expected.append(int.from_bytes(h.copy().digest(), "little"))
            actual = probe._signature(wire, limit)
            assert actual["prefix_hashes"] == expected
            assert actual["sha256"] == hashlib.sha256(wire).hexdigest()
            assert actual["byte_length"] == len(wire)
