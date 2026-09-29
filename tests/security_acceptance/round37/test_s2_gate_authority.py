"""S2: naming gates cannot mint evidence or authorize the real Git CAS."""
import pytest

from ._support import GATES, STATES, git, make_session, run_prefix


@pytest.mark.parametrize('index', range(4), ids=GATES)
def test_direct_issuer_cannot_append_for_any_mandatory_gate(tmp_path, monkeypatch, index):
    fixture = make_session(tmp_path, monkeypatch)
    run_prefix(fixture, index)
    sm, session = fixture.sm, fixture.session
    sm.transition(STATES[index])
    before = sm.data['gate_evidence']
    issuer = getattr(session, '_record_success', None)
    if issuer is not None:
        try:
            issuer(GATES[index])
        except (RuntimeError, TypeError):
            pass
    observed = sm.data['gate_evidence']
    assert observed == before, f'S2 direct issuance appended {GATES[index]} without executing it'
    assert git(fixture.root, 'rev-parse', 'dev') == fixture.base


def test_issuer_only_fsm_traversal_cannot_authorize_real_cas(tmp_path, monkeypatch):
    fixture = make_session(tmp_path, monkeypatch)
    sm, session = fixture.sm, fixture.session
    calls = []

    def forbidden_gate(*args, **kwargs):
        calls.append('executed')
        pytest.fail('This attack must execute zero concrete gates')

    for name in ('run_diff', 'run_testing', 'run_sast', 'run_audit'):
        monkeypatch.setattr(session, name, forbidden_gate)
    issuer = getattr(session, '_record_success', None)
    if issuer is not None:
        for gate, state in zip(GATES, STATES):
            try:
                sm.transition(state)
                issuer(gate)
            except (RuntimeError, TypeError):
                break
    accepted = session.verify_evidence()
    try:
        merged = session.merge('dev')[0]
    except RuntimeError:
        merged = False
    ref = git(fixture.root, 'rev-parse', 'dev')
    records = [record['gate'] for record in sm.data['gate_evidence']]
    assert calls == [] and fixture.trace == []
    assert not accepted and not merged and ref == fixture.base and records == [], (
        f'S2 unauthorized path: evidence_accepted={accepted}, merged={merged}, '
        f'base_ref_is_candidate={ref == fixture.candidate}, records={records}')
    assert sm.data['execution_status'] != 'COMPLETED'


def test_real_four_gate_path_appends_once_in_order_and_integrates_exact_c(tmp_path, monkeypatch):
    fixture = make_session(tmp_path, monkeypatch)
    run_prefix(fixture, 4)
    assert fixture.boundary.calls == 1
    assert fixture.trace == ['MATERIALIZE', 'TESTING', 'MATERIALIZE', 'SAST', 'LOGIC_AUDIT']
    records = fixture.sm.data['gate_evidence']
    assert fixture.session.merge('dev')[0]
    assert fixture.sm.data['gate_evidence'] == records
    assert git(fixture.root, 'rev-parse', 'dev') == fixture.candidate
    assert fixture.sm.data['execution_status'] == 'COMPLETED'


@pytest.mark.parametrize('index', range(4), ids=GATES)
def test_reordered_gate_appends_no_evidence(tmp_path, monkeypatch, index):
    fixture = make_session(tmp_path, monkeypatch)
    # For DIFF_GATE, a duplicate is the invalid order; later gates lack predecessors.
    if index == 0:
        run_prefix(fixture, 1)
    calls = (fixture.session.run_diff, fixture.session.run_testing,
             fixture.session.run_sast, fixture.session.run_audit)
    before = fixture.sm.data['gate_evidence']
    with pytest.raises(RuntimeError):
        calls[index]()
    assert fixture.sm.data['gate_evidence'] == before


def test_simulated_audit_cannot_append_evidence(tmp_path, monkeypatch):
    fixture = make_session(tmp_path, monkeypatch)
    run_prefix(fixture, 3)
    before = fixture.sm.data['gate_evidence']
    with pytest.raises(RuntimeError, match='Simulation'):
        fixture.session.run_audit(simulate=True)
    assert fixture.sm.data['gate_evidence'] == before
    assert git(fixture.root, 'rev-parse', 'dev') == fixture.base
