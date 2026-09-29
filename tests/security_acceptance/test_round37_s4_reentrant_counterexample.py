"""Frozen S4 counterexamples: reentrant code cannot own completion persistence."""
import hashlib
import hmac
import time

import pytest

from orchestrator.state_manager import StateManager
from .round37._support import git, make_session, run_prefix


def _forged_direct_completion(fixture, trace):
    sm = fixture.sm
    state = sm._data
    trace.append('callback entered with durable pending' if state.get('integration_pending') else 'callback entered without pending')
    assert state.get('integration_pending') is not None
    body = dict(state['integration_pending'])
    body.pop('signature')
    body['phase'] = 'completed'
    body['generation'] = state['generation'] + 1
    body['integrated_at'] = time.time()
    state['history'].append(dict(timestamp='2026-09-25T00:00:00+00:00',
        **{'from': 'AUTO_MERGE', 'to': 'COMPLETED'}, details='reentrant caller claim',
        epoch=state['epoch']))
    body['history_digest'] = hashlib.sha256(sm._integration_bytes(state['history'])).hexdigest()
    body['signature'] = hmac.new(sm._integration_key(state), sm._integration_bytes(body), hashlib.sha256).hexdigest()
    state['integration_pending'] = None
    state['integration_receipt'] = body
    state['execution_status'] = 'COMPLETED'
    state['generation'] += 1
    sm._tx_depth = 1
    try:
        trace.append('direct persistence attempted')
        try:
            sm._persist()
        except RuntimeError as exc:
            trace.append('direct persistence rejected: ' + type(exc).__name__)
        else:
            trace.append('direct persistence accepted')
    finally:
        sm._tx_depth = 0
    raise RuntimeError('diagnostic abort before controller completion')


@pytest.mark.parametrize('entry', ['post_intent_evidence', 'merge_helper', 'post_cas_evidence'])
def test_reentrant_callback_cannot_persist_completion(entry, tmp_path, monkeypatch):
    import scripts.merge_gate as merge_gate

    fixture = make_session(tmp_path, monkeypatch)
    run_prefix(fixture, 4)
    trace = []
    if entry in ('post_intent_evidence', 'post_cas_evidence'):
        original = fixture.session.verify_evidence
        calls = [0]

        def callback(*args, **kwargs):
            calls[0] += 1
            if calls[0] == (3 if entry == 'post_intent_evidence' else 4):
                _forged_direct_completion(fixture, trace)
            return original(*args, **kwargs)

        fixture.session.verify_evidence = callback
    else:
        def callback(*args):
            _forged_direct_completion(fixture, trace)

        monkeypatch.setattr(merge_gate, 'execute_fast_forward_merge', callback)
    with pytest.raises(RuntimeError, match='diagnostic abort before controller completion'):
        fixture.session.merge('dev')
    assert trace[:2] == ['callback entered with durable pending', 'direct persistence attempted']
    assert trace[2].startswith('direct persistence rejected:'), trace
    assert git(fixture.root, 'rev-parse', 'dev') == (
        fixture.candidate if entry == 'post_cas_evidence' else fixture.base)
    fresh = StateManager('R37', state_dir=str(fixture.root / 'orchestrator/state')).data
    assert fresh['execution_status'] != 'COMPLETED'
    assert fresh['integration_pending'] is not None
    assert fresh['integration_receipt'] is None


def test_substituted_helper_cannot_claim_cas_by_moving_ref_unconditionally(tmp_path, monkeypatch):
    import scripts.merge_gate as merge_gate

    fixture = make_session(tmp_path, monkeypatch)
    run_prefix(fixture, 4)
    trace = []

    def non_cas_helper(root, B, C, branch):
        trace.append(('helper entered', B, C, branch))
        # Deliberately omit the expected B argument: this is not B-to-C CAS.
        git(root, 'update-ref', f'refs/heads/{branch}', C)
        trace.append('unconditional ref update completed')
        return True, 'claimed exact integration'

    monkeypatch.setattr(merge_gate, 'execute_fast_forward_merge', non_cas_helper)
    with pytest.raises(RuntimeError):
        fixture.session.merge('dev')
    assert trace[0][0] == 'helper entered' and trace[1] == 'unconditional ref update completed'
    assert git(fixture.root, 'rev-parse', 'dev') == fixture.candidate
    fresh = StateManager('R37', state_dir=str(fixture.root / 'orchestrator/state')).data
    assert fresh['execution_status'] != 'COMPLETED'
    assert fresh['integration_pending'] is not None
