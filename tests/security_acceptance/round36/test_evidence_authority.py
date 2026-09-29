"""Synthetic persisted claims are attacks, never setup for valid authorization."""
import json
import pytest
from orchestrator.state_manager import StateManager
from .test_context_binding import repo_fixture


def setup_session(tmp_path):
    from orchestrator.verification_context import VerificationContext
    from orchestrator.gate_controller import VerificationSession
    root, base, candidate = repo_fixture(tmp_path)
    spec = root / 'specs/R36.md'
    spec.write_text('## 1. Scope and Boundaries\n- Allowed files:\n  - `file.py`\n- Strictly forbidden files:\n  - `.env`\n## 2. Acceptance\n')
    sm = StateManager('R36', state_dir=str(root / 'orchestrator/state'))
    for state in ('SPEC_GATE', 'BUILDING'):
        sm.transition(state)
    context = VerificationContext.capture(root, 'R36', base, candidate)
    return VerificationSession(root, sm, context), sm, root


def test_successful_diff_gate_immediately_issues_bound_evidence(tmp_path):
    session, sm, root = setup_session(tmp_path)
    assert not session.verify_evidence()
    assert session.run_diff()[0]
    record = sm.data['gate_evidence'][0]
    assert record['gate'] == 'DIFF_GATE'
    assert record['context'] == session.context.to_dict()
    assert record['result'] == 'PASS'
    assert session.verify_evidence(required=('DIFF_GATE',))
    assert not session.verify_evidence()


def test_generic_issuer_cannot_sign_caller_metadata(tmp_path):
    session, sm, root = setup_session(tmp_path)
    with pytest.raises(RuntimeError):
        sm.issue_gate_evidence('LOGIC_AUDIT', 'PASS', {'schema': 36, 'C': 'f' * 40})
    assert sm.data['gate_evidence'] == []


@pytest.mark.parametrize('attack', ['signature', 'relabel', 'duplicate', 'context', 'schema', 'fail', 'attempt', 'sequence', 'identity', 'expired'])
def test_tampered_evidence_rejected(tmp_path, attack):
    session, sm, root = setup_session(tmp_path)
    assert session.run_diff()[0]
    state = json.loads(sm.state_file.read_bytes())
    ev = state['gate_evidence'][0]
    if attack == 'signature': ev.pop('signature')
    elif attack == 'relabel': ev['gate'] = 'TESTING'
    elif attack == 'duplicate': state['gate_evidence'].append(dict(ev))
    elif attack == 'context': ev['context']['C'] = 'f' * 40
    elif attack == 'schema': ev['schema'] = 999
    elif attack == 'fail': ev['result'] = 'FAIL'
    elif attack == 'attempt': ev['attempt'] = 'old-attempt'
    elif attack == 'sequence': ev['sequence'] = 999
    elif attack == 'identity': ev['implementations'] = {'suite': 'fake'}
    elif attack == 'expired': ev['issued_at'] = 0
    sm.state_file.write_text(json.dumps(state))
    assert not session.verify_evidence(required=('DIFF_GATE',))


@pytest.mark.parametrize('attack', ['delete', 'replace'])
def test_key_loss_or_replacement_is_not_repaired(tmp_path, attack):
    session, sm, root = setup_session(tmp_path)
    assert session.run_diff()[0]
    key = session.key_path
    if attack == 'delete': key.unlink()
    else: key.write_bytes(b'x' * 32)
    assert not session.verify_evidence(required=('DIFF_GATE',))
    assert key.exists() is (attack != 'delete')


def test_context_recomputed_on_evidence_validation(tmp_path):
    session, sm, root = setup_session(tmp_path)
    assert session.run_diff()[0]
    (root / 'specs/R36.md').write_text('changed spec')
    assert not session.verify_evidence(required=('DIFF_GATE',))


def test_duplicate_execution_is_rejected(tmp_path):
    session, sm, root = setup_session(tmp_path)
    assert session.run_diff()[0]
    with pytest.raises(RuntimeError):
        session.run_diff()


def test_direct_recovery_with_boolean_or_string_is_rejected(tmp_path):
    session, sm, root = setup_session(tmp_path)
    sm.halt_human('merge failed', exit_process=False)
    for fake in (True, 'authorized', object(), {'authorized': True}):
        with pytest.raises(RuntimeError):
            sm.execute_merge_recovery_transition(fake)
