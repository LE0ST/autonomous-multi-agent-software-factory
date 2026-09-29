"""S4 adversarial completion and post-CAS durability acceptance."""
import copy

import pytest

from orchestrator.state_manager import StateManager
from .round37._support import git, make_session, run_prefix


@pytest.mark.parametrize('attack', ['missing', 'reordered', 'invalid', 'stale'])
def test_merge_rejects_corrupt_gate_chain_before_cas(tmp_path, monkeypatch, attack):
    fixture = make_session(tmp_path, monkeypatch)
    run_prefix(fixture, 4)
    original_reload = fixture.sm._reload
    reached = []

    def corrupt_read():
        original_reload()
        records = fixture.sm._data['gate_evidence']
        reached.append(attack)
        if attack == 'missing':
            records.pop()
        elif attack == 'reordered':
            records[0], records[1] = records[1], records[0]
        elif attack == 'invalid':
            records[3]['signature'] = '0' * 64
        else:
            records[3]['issued_at'] = 0

    with monkeypatch.context() as fault:
        fault.setattr(fixture.sm, '_reload', corrupt_read)
        with pytest.raises(RuntimeError, match='evidence|authorization'):
            fixture.session.merge('dev')
    assert reached, 'Corrupt evidence was not delivered to merge authorization'
    assert git(fixture.root, 'rev-parse', 'dev') == fixture.base
    assert fixture.sm.data['execution_status'] != 'COMPLETED'


@pytest.mark.parametrize('drift', ['candidate-ref', 'spec'])
def test_merge_rejects_candidate_or_context_drift_before_cas(tmp_path, monkeypatch, drift):
    fixture = make_session(tmp_path, monkeypatch)
    run_prefix(fixture, 4)
    if drift == 'candidate-ref':
        tree = git(fixture.root, 'rev-parse', fixture.candidate + '^{tree}')
        other = git(fixture.root, 'commit-tree', tree, '-p', fixture.candidate, '-m', 'candidate ref drift')
        git(fixture.root, 'update-ref', 'refs/heads/task/R37', other, fixture.candidate)
        assert git(fixture.root, 'rev-parse', 'refs/heads/task/R37') == other
    else:
        spec = fixture.root / 'specs/R37.md'
        spec.write_bytes(spec.read_bytes() + b'\nDrifted context\n')
        assert not fixture.session.context.verify_current(fixture.root, fixture.sm.task_id)
    with pytest.raises(RuntimeError):
        fixture.session.merge('dev')
    assert git(fixture.root, 'rev-parse', 'dev') == fixture.base
    assert fixture.sm.data['execution_status'] != 'COMPLETED'


def test_claimed_success_without_exact_ref_cas_cannot_complete(tmp_path, monkeypatch):
    import scripts.merge_gate as merge_gate

    fixture = make_session(tmp_path, monkeypatch)
    run_prefix(fixture, 4)
    calls = []

    def false_success(*args):
        calls.append(args)
        return True, 'caller claims integration succeeded'

    monkeypatch.setattr(merge_gate, 'execute_fast_forward_merge', false_success)
    with pytest.raises(RuntimeError):
        fixture.session.merge('dev')
    assert len(calls) == 1, 'Claimed-success path was not exercised'
    assert git(fixture.root, 'rev-parse', 'dev') == fixture.base
    assert fixture.sm.data['execution_status'] != 'COMPLETED'


@pytest.mark.parametrize('field', ['task', 'repository', 'B', 'C', 'M', 'attempt', 'gate_signatures', 'signature'])
def test_completed_receipt_binding_is_persistently_validated(tmp_path, monkeypatch, field):
    fixture = make_session(tmp_path, monkeypatch)
    run_prefix(fixture, 4)
    assert fixture.session.merge('dev')[0]
    before = fixture.sm.data
    receipt = before['integration_receipt']
    assert receipt['task'] == fixture.sm.task_id
    assert receipt['repository'] == str(fixture.root.resolve())
    assert receipt['B'] == fixture.base and receipt['C'] == fixture.candidate
    assert receipt['context'] == before['verification_context']
    assert receipt['attempt'] == before['attempt']
    assert receipt['gate_signatures'] == [record['signature'] for record in before['gate_evidence']]

    def tamper():
        value = fixture.sm._data['integration_receipt'][field]
        fixture.sm._data['integration_receipt'][field] = (
            ['0' * 64] * 4 if field == 'gate_signatures' else 'forged-' + str(value))

    with pytest.raises(RuntimeError):
        fixture.sm._transaction(tamper)
    assert fixture.sm.data == before
    assert StateManager('R37', state_dir=str(fixture.root / 'orchestrator/state')).data == before


def test_forged_completion_history_without_cas_is_rejected(tmp_path, monkeypatch):
    fixture = make_session(tmp_path, monkeypatch)
    run_prefix(fixture, 4)
    fixture.sm.transition('AUTO_MERGE')
    before = fixture.sm.data

    def append_forgery():
        fixture.sm._data['history'].append(dict(timestamp='2026-09-25T00:00:00+00:00',
            **{'from': 'AUTO_MERGE', 'to': 'COMPLETED'}, details='caller claim', epoch=1))

    with pytest.raises(RuntimeError):
        fixture.sm._transaction(append_forgery)
    assert fixture.sm.data == before
    assert git(fixture.root, 'rev-parse', 'dev') == fixture.base


def test_completed_task_cannot_reopen_or_duplicate_integration(tmp_path, monkeypatch):
    fixture = make_session(tmp_path, monkeypatch)
    run_prefix(fixture, 4)
    assert fixture.session.merge('dev')[0]
    before = copy.deepcopy(fixture.sm.data)
    with pytest.raises(RuntimeError):
        fixture.sm.transition('BUILDING')
    with pytest.raises(RuntimeError):
        fixture.sm.execute_merge_recovery_transition(object())
    with pytest.raises(RuntimeError):
        fixture.sm.authorize_recovery(fixture.root, mode='merge')
    with pytest.raises(RuntimeError):
        fixture.session.merge('dev')
    assert fixture.sm.data == before


def test_post_cas_persistence_failure_leaves_explicit_fail_closed_intent(tmp_path, monkeypatch):
    fixture = make_session(tmp_path, monkeypatch)
    run_prefix(fixture, 4)
    original_persist = fixture.sm._persist
    reached = []

    def fail_completed_persist():
        if fixture.sm._data['execution_status'] == 'COMPLETED':
            reached.append('after CAS, before durable completed state')
            raise OSError('injected completion persistence failure')
        return original_persist()

    with monkeypatch.context() as fault:
        fault.setattr(fixture.sm, '_persist', fail_completed_persist)
        with pytest.raises(OSError, match='injected completion persistence failure'):
            fixture.session.merge('dev')
    assert reached, 'The fault did not reach completion persistence after CAS'
    assert git(fixture.root, 'rev-parse', 'dev') == fixture.candidate
    reopened = StateManager('R37', state_dir=str(fixture.root / 'orchestrator/state'))
    state = reopened.data
    assert state['execution_status'] != 'COMPLETED'
    assert state['integration_pending']['C'] == fixture.candidate
    assert state['integration_receipt'] is None
    with pytest.raises(RuntimeError):
        reopened.set_execution_status('COMPLETED')
    with pytest.raises(RuntimeError):
        fixture.session.merge('dev')
    assert reopened.reconcile_integration(fixture.root)[0] is False
    assert reopened.data == state
