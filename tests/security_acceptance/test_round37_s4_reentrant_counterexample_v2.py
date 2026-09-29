"""Versioned S4 acceptance: a writable helper reference cannot authorize CAS."""
import pytest

from orchestrator.state_manager import StateManager
from .round37._support import git, make_session, run_prefix


def test_replacing_helper_and_mutable_identity_cannot_claim_exact_cas(tmp_path, monkeypatch):
    import orchestrator.state_manager as state_module
    import scripts.merge_gate as merge_gate

    fixture = make_session(tmp_path, monkeypatch)
    run_prefix(fixture, 4)
    trace = []

    def non_cas_helper(root, B, C, branch):
        trace.append('caller helper entered after pending intent')
        assert fixture.sm.data['integration_pending'] is not None
        git(root, 'update-ref', f'refs/heads/{branch}', C)
        trace.append('unconditional ref update without expected B')
        return True, 'caller claims exact CAS'

    monkeypatch.setattr(merge_gate, 'execute_fast_forward_merge', non_cas_helper)
    # The prior repair's reference is writable from the same general caller.
    monkeypatch.setattr(state_module, '_installed_merge_operation', non_cas_helper)
    with pytest.raises(RuntimeError):
        fixture.session.merge('dev')
    assert trace == ['caller helper entered after pending intent',
                     'unconditional ref update without expected B']
    assert git(fixture.root, 'rev-parse', 'dev') == fixture.candidate
    fresh = StateManager('R37', state_dir=str(fixture.root / 'orchestrator/state')).data
    assert fresh['execution_status'] != 'COMPLETED'
    assert fresh['integration_pending'] is not None
