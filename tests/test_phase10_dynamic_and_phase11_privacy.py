"""Focused qualification of pending authority and diagnostic-only privacy."""
from types import SimpleNamespace
import io
import logging
import pytest

from jack_phase10_dynamic_authority import PendingAuthority, DynamicAuthorityUnavailable
from jack_phase11_privacy import PrivacyBoundary, ProtectedDiagnosticFormatter, protect_logging_handlers


def state(call_id="call-a", withheld=("blocked-a",)):
    return SimpleNamespace(
        resume_id="resume-" + call_id, stage_key="stage",
        expected_tool_call_ids=(call_id,), withheld_tool_call_ids=withheld,
        history=[{"tool_calls": [{"id": call_id, "function": {
            "name": "read", "arguments": '{"path":"safe.txt"}'}}]}],
        accepted_tool_results=None, accepted_executor_context=None,
        in_flight=False, created_at=100.0, tools=[], tool_choice=None,
        secondary_system="stage instructions", debugging_run_id=None,
        deferred_tool_rejection_errors=(), frozen_stage1_history=None,
        frozen_stage1_answer=None,
    )


def test_valid_lifecycle_and_retry():
    a = PendingAuthority()
    s = state()
    a.register(s)
    live = {"call-a": s}
    assert a.verify_request(["call-a"], live) == set()
    assert a.verify_request(["blocked-a"], live) == {"blocked-a"}
    results = [{"content": "unchanged evidence"}]
    a.transition(s, in_flight=True, accept=results)
    results[0]["content"] = "external mutation"
    assert s.accepted_tool_results[0]["content"] == "unchanged evidence"
    a.transition(s, in_flight=False)
    a.verify(s)
    assert a.retire(s) == ("call-a",)


@pytest.mark.parametrize("mutation", ["call", "binding", "withheld", "expiry"])
def test_authority_rejects_mutation_without_disabling_independent_transaction(mutation):
    a = PendingAuthority()
    s, other = state(), state("call-b", ("blocked-b",))
    a.register(s)
    a.register(other)
    live = {"call-a": s, "call-b": other}
    if mutation == "call":
        s.history[0]["tool_calls"][0]["function"]["arguments"] = "{}"
    elif mutation == "binding":
        del live["call-a"]
    elif mutation == "withheld":
        s.withheld_tool_call_ids = ()
    else:
        s.created_at = 0
        assert a.expire(50, live) == 0
    with pytest.raises(DynamicAuthorityUnavailable):
        a.verify_request(["call-a"], live)
    assert a.verify_request(["call-b"], live) == set()


def boundary():
    return PrivacyBoundary(
        SimpleNamespace(credentials=[SimpleNamespace(value="TEST-CREDENTIAL-8391")]),
        SimpleNamespace(canaries=SimpleNamespace(_patterns=[
            SimpleNamespace(value="TEST-CANARY-7420")])),
    )


def test_privacy_preserves_clean_data_and_withholds_sensitive_archive():
    b = boundary()
    clean = {"nested": ["ordinary evidence", 3, None]}
    assert b.permits_archive(clean)
    assert b.redact("ordinary evidence") == "ordinary evidence"
    assert not b.permits_archive({"nested": [{"TEST-CANARY-7420": "value"}]})
    assert not b.permits_archive({"nested": ["TEST-CREDENTIAL-8391"]})
    assert not b.permits_archive(object())
    text = b.redact("prefix TEST-CREDENTIAL-8391 TEST-CANARY-7420 suffix")
    assert "TEST-CREDENTIAL-8391" not in text
    assert "TEST-CANARY-7420" not in text
    assert text.startswith("prefix ") and text.endswith(" suffix")


def test_formatter_covers_arguments_exceptions_and_late_handlers():
    b = boundary()
    logger = logging.getLogger("jack.phase11.test")
    sink = io.StringIO()
    handler = logging.StreamHandler(sink)
    original = logging.Formatter("%(message)s")
    handler.setFormatter(original)
    logger.addHandler(handler)
    old_level, old_propagate = logger.level, logger.propagate
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        # Limit handler enumeration to this isolated test logger.
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(logging.getLogger(), "handlers", [])
            mp.setattr(logging.Logger.manager, "loggerDict", {logger.name: logger})
            protect_logging_handlers(b)
            first = handler.formatter
            assert isinstance(first, ProtectedDiagnosticFormatter)
            protect_logging_handlers(b)
            assert handler.formatter is first
            try:
                raise ValueError("TEST-CANARY-7420")
            except ValueError:
                logger.exception("credential %s", "TEST-CREDENTIAL-8391")
            logger.info("ordinary diagnostic")
        actual = sink.getvalue()
        assert "TEST-CANARY-7420" not in actual
        assert "TEST-CREDENTIAL-8391" not in actual
        assert "ordinary diagnostic" in actual
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
        logger.propagate = old_propagate
        handler.close()


@pytest.mark.parametrize("field,value", [
    ("secondary_system", "substituted instructions"),
    ("debugging_run_id", "wrong-run"),
    ("deferred_tool_rejection_errors", ("substituted denial",)),
    ("frozen_stage1_answer", "forged answer"),
])
def test_resume_authority_metadata_tampering_is_denied(field, value):
    a = PendingAuthority()
    s = state()
    a.register(s)
    setattr(s, field, value)
    with pytest.raises(DynamicAuthorityUnavailable):
        a.verify_request(["call-a"], {"call-a": s})


def test_frozen_checkpoint_is_sealed_and_retry_preserved():
    a = PendingAuthority()
    s = state()
    a.register(s)
    a.transition(s, in_flight=True, accept=[{"content": "evidence"}])
    history = [{"role": "assistant", "content": "completed work"}]
    a.freeze(s, history, "completed work")
    history[0]["content"] = "external mutation"
    a.transition(s, in_flight=False)
    a.verify(s)
    assert s.frozen_stage1_history[0]["content"] == "completed work"
    assert s.frozen_stage1_answer == "completed work"
    a.transition(s, in_flight=True)
    with pytest.raises(DynamicAuthorityUnavailable):
        a.freeze(s, [], "replacement")
    s.frozen_stage1_history[0]["content"] = "forged evidence"
    with pytest.raises(DynamicAuthorityUnavailable):
        a.verify(s)


def test_pending_index_cannot_be_mutated_in_place():
    a = PendingAuthority()
    s = state()
    a.register(s)
    with pytest.raises(TypeError):
        a._entries[id(s)] = None
    a.verify(s)


def test_released_id_cannot_collide_with_another_withheld_id():
    a = PendingAuthority()
    a.register(state())
    with pytest.raises(DynamicAuthorityUnavailable):
        a.register(state("blocked-a", ()))
    with pytest.raises(DynamicAuthorityUnavailable):
        a.register(state("call-b", ("call-a",)))
