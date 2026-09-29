"""S4: COMPLETED requires authorized integration, not a public setter or transaction."""
import pytest

from orchestrator.state_manager import StateManager, VALID_STATES
from ._support import git, make_session, run_prefix

PATHS = {
    'INIT': (), 'SPEC_DESIGN': ('SPEC_DESIGN',), 'SPEC_GATE': ('SPEC_GATE',),
    'BUILDING': ('SPEC_GATE', 'BUILDING'),
    'DIFF_GATE': ('SPEC_GATE', 'BUILDING', 'DIFF_GATE'),
    'TESTING': ('SPEC_GATE', 'BUILDING', 'DIFF_GATE', 'TESTING'),
    'TRIAGING': ('SPEC_GATE', 'BUILDING', 'DIFF_GATE', 'TESTING', 'TRIAGING'),
    'SAST_SCAN': ('SPEC_GATE', 'BUILDING', 'DIFF_GATE', 'TESTING', 'SAST_SCAN'),
    'SAST_FILTER': ('SPEC_GATE', 'BUILDING', 'DIFF_GATE', 'TESTING', 'SAST_SCAN', 'SAST_FILTER'),
    'LOGIC_AUDIT': ('SPEC_GATE', 'BUILDING', 'DIFF_GATE', 'TESTING', 'SAST_SCAN', 'LOGIC_AUDIT'),
    'AUTO_MERGE': ('SPEC_GATE', 'BUILDING', 'DIFF_GATE', 'TESTING', 'SAST_SCAN', 'LOGIC_AUDIT', 'AUTO_MERGE'),
    'HUMAN_REVIEW': (), 'HALT_HUMAN': (),
}


@pytest.mark.parametrize('state', tuple(PATHS))
def test_general_status_setter_rejects_completed_from_every_state(tmp_path, monkeypatch, state):
    assert set(PATHS) == set(VALID_STATES), 'Extend coverage if FSM states change'
    monkeypatch.chdir(tmp_path)
    sm = StateManager('S4', state_dir=str(tmp_path / 'state'))
    for step in PATHS[state]:
        sm.transition(step)
    if state == 'HALT_HUMAN':
        sm.halt_human('terminal', exit_process=False)
    elif state == 'HUMAN_REVIEW':
        sm.request_human_review('review', exit_process=False)
    assert sm.data['current_state'] == state
    before = sm.data
    rejected = False
    try:
        sm.set_execution_status('COMPLETED')
    except RuntimeError:
        rejected = True
    observed = sm.data
    assert rejected and observed == before, (
        f'S4 general setter: from={state}, rejected={rejected}, '
        f'persisted={observed["current_state"]}/{observed["execution_status"]}, '
        f'evidence_count={len(observed["gate_evidence"])}')


@pytest.mark.parametrize('claim', ['INIT', 'AUTO_MERGE'])
def test_direct_transaction_cannot_persist_completion_without_integration(tmp_path, claim):
    sm = StateManager('S4', state_dir=str(tmp_path / 'state'))
    before = sm.data

    def forged_completion():
        sm._data['current_state'] = claim
        sm._data['execution_status'] = 'COMPLETED'
        if claim == 'AUTO_MERGE':
            sm._data['history'].append(dict(
                timestamp='2026-09-19T00:00:00+00:00', epoch=1,
                **{'from': 'LOGIC_AUDIT', 'to': 'AUTO_MERGE'}, details='caller claims CAS success'))

    rejected = False
    try:
        sm._transaction(forged_completion)
    except RuntimeError:
        rejected = True
    observed = sm.data
    assert rejected and observed == before, (
        f'S4 inconsistent completed transaction accepted: {observed["current_state"]}/'
        f'{observed["execution_status"]}, evidence_count={len(observed["gate_evidence"])}')


def test_real_failed_cas_cannot_produce_completed(tmp_path, monkeypatch):
    fixture = make_session(tmp_path, monkeypatch)
    run_prefix(fixture, 4)
    tree = git(fixture.root, 'rev-parse', fixture.candidate + '^{tree}')
    concurrent = git(fixture.root, 'commit-tree', tree, '-p', fixture.base, '-m', 'concurrent base')
    git(fixture.root, 'update-ref', 'refs/heads/dev', concurrent, fixture.base)
    passed, detail = fixture.session.merge('dev')
    assert passed is False, detail
    assert git(fixture.root, 'rev-parse', 'dev') == concurrent
    assert fixture.sm.data['execution_status'] != 'COMPLETED'


def test_successful_cas_produces_one_completed_integration(tmp_path, monkeypatch):
    fixture = make_session(tmp_path, monkeypatch)
    run_prefix(fixture, 4)
    assert fixture.session.merge('dev')[0]
    state = fixture.sm.data
    assert state['current_state'] == 'AUTO_MERGE' and state['execution_status'] == 'COMPLETED'
    assert len(state['gate_evidence']) == 4
    assert len([entry for entry in state['history'] if entry['to'] == 'AUTO_MERGE']) == 1
    assert git(fixture.root, 'rev-parse', 'dev') == fixture.candidate
    with pytest.raises(RuntimeError):
        fixture.session.merge('dev')
    assert fixture.sm.data == state
