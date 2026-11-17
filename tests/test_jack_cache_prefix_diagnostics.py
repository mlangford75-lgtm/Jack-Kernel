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
