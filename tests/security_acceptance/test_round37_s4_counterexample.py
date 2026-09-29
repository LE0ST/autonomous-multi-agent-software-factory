"""Frozen counterexamples for completion authority exposed to general transactions."""
import hashlib
import time

import pytest

from orchestrator.state_manager import StateManager
from .round37._support import git, make_session, run_prefix


def _setup(tmp_path, monkeypatch):
    fixture = make_session(tmp_path, monkeypatch)
    run_prefix(fixture, 4)
    fixture.sm.transition('AUTO_MERGE')
    assert fixture.session.verify_evidence()
    assert len(fixture.sm.data['gate_evidence']) == 4
    assert git(fixture.root, 'rev-parse', 'dev') == fixture.base
    return fixture


def _forge(fixture, *, token=None, reached=None):
    sm = fixture.sm
    reached = reached if reached is not None else []
    token = token or object()

    def arm():
        reached.append('general callback armed authority')
        sm._integration_authority = token

    sm._transaction(arm)
    current = sm.data
    context = fixture.session.context.to_dict()
    body = dict(schema=37, phase='pending', task=sm.task_id,
        repository=str(fixture.root.resolve()), base_branch='dev',
        B=context['B'], C=context['C'], tree=context['tree'], M=context['M'],
        context=context, attempt=fixture.session.attempt,
        candidate_ref_at_freeze=fixture.session._candidate_ref_at_freeze,
        gate_signatures=[r['signature'] for r in current['gate_evidence']],
        key_id=current['evidence_key_id'], nonce='a' * 64,
        generation=current['generation'] + 1, cas='exact-ref B-to-C')
    reached.append('direct pending signer attempt')
    pending = dict(body, signature=sm._sign_integration(body, current))
    reached.append('forged pending transaction attempt')
    sm._transaction(lambda: sm._data.__setitem__('integration_pending', pending),
        _integration_authorization=token)

    def finish():
        reached.append('general completion callback')
        state = sm._data
        state['history'].append(dict(timestamp='2026-09-25T00:00:00+00:00',
            **{'from': 'AUTO_MERGE', 'to': 'COMPLETED'}, details='forged without CAS',
            epoch=state['epoch']))
        receipt = dict(body, phase='completed', generation=state['generation'] + 1,
            integrated_at=time.time(),
            history_digest=hashlib.sha256(sm._integration_bytes(state['history'])).hexdigest())
        reached.append('direct completion signer attempt')
        receipt['signature'] = sm._sign_integration(receipt, state)
        state['integration_pending'] = None
        state['integration_receipt'] = receipt
        state['execution_status'] = 'COMPLETED'

    reached.append('forged completion transaction attempt')
    sm._transaction(finish, _integration_authorization=token)
    return reached


@pytest.mark.parametrize('ref_case', ['B', 'third'])
def test_callback_cannot_sign_and_complete_without_exact_cas(tmp_path, monkeypatch, ref_case):
    fixture = _setup(tmp_path, monkeypatch)
    if ref_case == 'third':
        tree = git(fixture.root, 'rev-parse', fixture.candidate + '^{tree}')
        third = git(fixture.root, 'commit-tree', tree, '-p', fixture.base, '-m', 'third')
        git(fixture.root, 'update-ref', 'refs/heads/dev', third, fixture.base)
        assert git(fixture.root, 'rev-parse', 'dev') == third != fixture.candidate
    before_ref = git(fixture.root, 'rev-parse', 'dev')
    trace = []

    def observed_attack():
        trace.append('attack entered')
        return _forge(fixture, reached=trace)

    with pytest.raises((RuntimeError, AttributeError, TypeError)):
        observed_attack()
    assert trace[:3] == ['attack entered', 'general callback armed authority',
        'direct pending signer attempt']
    assert fixture.sm.data['execution_status'] != 'COMPLETED'
    assert git(fixture.root, 'rev-parse', 'dev') == before_ref
    assert StateManager('R37', state_dir=str(fixture.root / 'orchestrator/state')).data['execution_status'] != 'COMPLETED'


def test_direct_signer_is_not_a_general_receipt_oracle(tmp_path, monkeypatch):
    fixture = _setup(tmp_path, monkeypatch)
    attempted = []
    with pytest.raises((RuntimeError, AttributeError, TypeError)):
        attempted.append('direct signer call')
        fixture.sm._sign_integration({'phase': 'completed', 'cas': 'exact-ref B-to-C'}, fixture.sm.data)
    assert attempted == ['direct signer call']
    assert git(fixture.root, 'rev-parse', 'dev') == fixture.base


def test_observed_authority_reuse_cannot_clear_unresolved_intent(tmp_path, monkeypatch):
    import scripts.merge_gate as merge_gate
    fixture = _setup(tmp_path, monkeypatch)
    with monkeypatch.context() as fault:
        fault.setattr(merge_gate, 'execute_fast_forward_merge',
            lambda *args: (_ for _ in ()).throw(OSError('crash before CAS')))
        with pytest.raises(OSError, match='crash before CAS'):
            fixture.session.merge('dev')
    assert fixture.sm.data['integration_pending'] is not None
    before = fixture.sm.data
    token = object()
    entered = []
    fixture.sm._transaction(lambda: (entered.append('arm'),
        setattr(fixture.sm, '_integration_authority', token)))
    with pytest.raises((RuntimeError, AttributeError, TypeError)):
        fixture.sm._transaction(lambda: (entered.append('clear'),
            fixture.sm._data.__setitem__('integration_pending', None)),
            _integration_authorization=token)
    assert entered == ['arm', 'clear']
    assert fixture.sm.data['integration_pending'] == before['integration_pending']
    assert git(fixture.root, 'rev-parse', 'dev') == fixture.base


def test_reentrant_transaction_cannot_complete(tmp_path, monkeypatch):
    fixture = _setup(tmp_path, monkeypatch)
    entered = []

    def outer():
        entered.append('outer callback')
        fixture.sm._transaction(lambda: entered.append('nested callback'))

    with pytest.raises(RuntimeError, match='Nested'):
        fixture.sm._transaction(outer)
    assert entered == ['outer callback']
    assert fixture.sm.data['execution_status'] != 'COMPLETED'
    assert git(fixture.root, 'rev-parse', 'dev') == fixture.base
