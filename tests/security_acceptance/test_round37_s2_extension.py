"""S2 execution provenance checks, separately frozen from the Stage 1 suites."""
import re
from dataclasses import replace

import pytest

from .round37._support import GATES, STATES, SPEC, make_session, run_prefix


@pytest.mark.parametrize('index', range(4), ids=GATES)
def test_caller_supplied_pass_object_cannot_mint_evidence(tmp_path, monkeypatch, index):
    fixture = make_session(tmp_path, monkeypatch)
    run_prefix(fixture, index)
    fixture.sm.transition(STATES[index])
    before = fixture.sm.data['gate_evidence']
    issuer = getattr(fixture.session, '_record_success', None)
    if issuer is not None:
        try:
            issuer(GATES[index], detail={'status': 'PASS', 'gate': GATES[index]})
        except (RuntimeError, TypeError):
            pass
    assert fixture.sm.data['gate_evidence'] == before


@pytest.mark.parametrize('index', range(4), ids=GATES)
@pytest.mark.parametrize('mode', ('failure', 'exception'))
def test_each_gate_failure_or_exception_cannot_append(tmp_path, monkeypatch, index, mode):
    import orchestrator.gate_controller as gates
    import orchestrator.logic_audit as audit

    fixture = make_session(tmp_path, monkeypatch)
    run_prefix(fixture, index)
    before = fixture.sm.data['gate_evidence']
    observed = []
    # Isolate S2 result handling from S3's separate code-identity rejection.
    frozen_identities = fixture.session.identities
    monkeypatch.setattr(gates, 'implementation_identities',
                        lambda backend_type=None: frozen_identities)

    def boundary(*args, **kwargs):
        observed.append(GATES[index])
        if mode == 'exception':
            raise ValueError('injected gate exception')
        if index == 0:
            return False, {'status': 'FAIL'}
        if index == 1:
            return False, '', 'failed', 1, {'trusted_verifier_result': 'FAIL'}
        if index == 2:
            return 2, {'engine': 'tool_error', 'error': 'injected'}
        return False, None, None

    if index == 0:
        monkeypatch.setattr(gates, 'validate_diff', boundary)
    elif index == 1:
        monkeypatch.setattr(gates.TestSupervisor, 'verify_candidate', boundary)
    elif index == 2:
        monkeypatch.setattr(gates, 'run_sast', boundary)
    else:
        monkeypatch.setattr(audit, 'execute_logic_security_audit', boundary)
    if mode == 'exception':
        with pytest.raises(ValueError, match='injected gate exception'):
            (fixture.session.run_diff, fixture.session.run_testing,
             fixture.session.run_sast, fixture.session.run_audit)[index]()
    else:
        result = (fixture.session.run_diff, fixture.session.run_testing,
                  fixture.session.run_sast, fixture.session.run_audit)[index]()
        assert result[0] is False if index != 2 else result[0] == 2
    assert observed == [GATES[index]]
    assert fixture.sm.data['gate_evidence'] == before


@pytest.mark.parametrize('index', range(4), ids=GATES)
def test_real_success_becomes_ineligible_if_spec_changes_before_signing(
        tmp_path, monkeypatch, index):
    import orchestrator.gate_controller as gates
    import orchestrator.logic_audit as audit

    fixture = make_session(tmp_path, monkeypatch)
    run_prefix(fixture, index)
    before = fixture.sm.data['gate_evidence']
    spec_path = fixture.root / 'specs/R37.md'
    observed = []
    frozen_identities = fixture.session.identities
    monkeypatch.setattr(gates, 'implementation_identities',
                        lambda backend_type=None: frozen_identities)
    if index == 0:
        original = gates.validate_diff
    elif index == 1:
        original = gates.TestSupervisor.verify_candidate
    elif index == 2:
        original = gates.run_sast
    else:
        original = audit.execute_logic_security_audit

    def execute_then_drift(*args, **kwargs):
        result = original(*args, **kwargs)
        observed.append(result)
        assert (result[0] == 0 if index == 2 else result[0] is True)
        spec_path.write_text(SPEC + '\nchanged after execution\n', encoding='utf-8')
        return result

    if index == 0:
        monkeypatch.setattr(gates, 'validate_diff', execute_then_drift)
    elif index == 1:
        monkeypatch.setattr(gates.TestSupervisor, 'verify_candidate', execute_then_drift)
    elif index == 2:
        monkeypatch.setattr(gates, 'run_sast', execute_then_drift)
    else:
        monkeypatch.setattr(audit, 'execute_logic_security_audit', execute_then_drift)
    with pytest.raises(RuntimeError, match='Context changed'):
        (fixture.session.run_diff, fixture.session.run_testing,
         fixture.session.run_sast, fixture.session.run_audit)[index]()
    assert len(observed) == 1
    assert fixture.sm.data['gate_evidence'] == before


def test_candidate_identity_change_after_real_diff_cannot_sign(tmp_path, monkeypatch):
    import orchestrator.gate_controller as gates

    fixture = make_session(tmp_path, monkeypatch)
    original = gates.validate_diff
    before = fixture.sm.data['gate_evidence']
    frozen_identities = fixture.session.identities
    monkeypatch.setattr(gates, 'implementation_identities',
                        lambda backend_type=None: frozen_identities)

    def execute_then_change_candidate(*args, **kwargs):
        result = original(*args, **kwargs)
        assert result[0] is True
        fixture.session.context = replace(fixture.session.context, C=fixture.base)
        return result

    monkeypatch.setattr(gates, 'validate_diff', execute_then_change_candidate)
    with pytest.raises(RuntimeError):
        fixture.session.run_diff()
    assert fixture.sm.data['gate_evidence'] == before


def test_replayed_success_cannot_authorize_the_next_gate(tmp_path, monkeypatch):
    fixture = make_session(tmp_path, monkeypatch)
    run_prefix(fixture, 1)
    before = fixture.sm.data['gate_evidence']
    fixture.sm.transition('TESTING')
    issuer = getattr(fixture.session, '_record_success', None)
    if issuer is not None:
        try:
            issuer('TESTING', detail={'reused': before[0]})
        except (RuntimeError, TypeError):
            pass
    assert fixture.sm.data['gate_evidence'] == before


def test_each_signed_success_carries_an_execution_result_digest(tmp_path, monkeypatch):
    fixture = make_session(tmp_path, monkeypatch)
    run_prefix(fixture, 4)
    records = fixture.sm.data['gate_evidence']
    assert [record['gate'] for record in records] == list(GATES)
    for record in records:
        value = record['supplemental'].get('execution_result_sha256')
        assert isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value)
    assert fixture.session.verify_evidence()
