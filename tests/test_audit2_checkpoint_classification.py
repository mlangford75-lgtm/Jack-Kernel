import pytest

from jack_evidence_guard import checkpoint_retiring_failure, terminal_stream_failure
from jack_policy_integrity import PolicyIntegrityUnavailable, PolicyIntegrityCompromised
from jack_runtime_code_guard import RuntimeCodeIntegrityUnavailable, RuntimeCodeIntegrityCompromised
from jack_source_drift_guard import SourceAuthorityUnavailable, SourceAuthorityInvalidated


@pytest.mark.parametrize("failure", [PolicyIntegrityUnavailable, RuntimeCodeIntegrityUnavailable, SourceAuthorityUnavailable])
def test_uncertainty_blocks_release_but_does_not_retire_checkpoint(failure):
    exc = failure("synthetic measurement unavailable")
    assert terminal_stream_failure(exc)
    assert not checkpoint_retiring_failure(exc)


@pytest.mark.parametrize("failure", [PolicyIntegrityCompromised, RuntimeCodeIntegrityCompromised, SourceAuthorityInvalidated])
def test_confirmed_compromise_blocks_release_and_retires_checkpoint(failure):
    exc = failure("synthetic confirmed mismatch")
    assert terminal_stream_failure(exc)
    assert checkpoint_retiring_failure(exc)
