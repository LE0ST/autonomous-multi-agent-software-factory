"""Additional S5 boundaries using genuinely issued merge recovery capabilities."""

import pytest

from orchestrator.state_manager import TerminalStateError
from tests.security_acceptance.round37._support import halted_merge


@pytest.mark.parametrize('boundary', ['validation', 'persistence'])
def test_reentrant_presentation_cannot_reuse_capability(tmp_path, monkeypatch, boundary):
    fixture = halted_merge(tmp_path, monkeypatch)
    sm = fixture.sm
    capability, _ = sm.authorize_recovery(fixture.root, mode='merge')
    before = sm.data
    reached = []
    original = sm._recovery_session

    def reenter_validation(*args):
        if not reached:
            reached.append('validation')
            with pytest.raises(TerminalStateError, match='authorization'):
                sm.execute_merge_recovery_transition(capability)
            raise OSError('injected validation failure')
        return original(*args)

    def reenter_persistence():
        reached.append('persistence')
        with pytest.raises(TerminalStateError, match='authorization'):
            sm.execute_merge_recovery_transition(capability)
        raise OSError('injected persistence failure')

    with monkeypatch.context() as fault:
        if boundary == 'validation':
            fault.setattr(sm, '_recovery_session', reenter_validation)
        else:
            fault.setattr(sm, '_persist', reenter_persistence)
        with pytest.raises(OSError, match=f'injected {boundary} failure'):
            sm.execute_merge_recovery_transition(capability)
    assert reached == [boundary], 'The injected recovery boundary must execute exactly once'
    assert sm.data == before
    assert sm.validate_strict_recovery(fixture.root, mode='merge')[0]
    with pytest.raises(TerminalStateError, match='authorization'):
        sm.execute_merge_recovery_transition(capability)
    fresh, _ = sm.authorize_recovery(fixture.root, mode='merge')
    sm.execute_merge_recovery_transition(fresh)
    assert sm.data['current_state'] == 'AUTO_MERGE'


def test_new_issue_requires_fresh_strict_validation_and_invalid_object_does_not_spend_issued_capability(
        tmp_path, monkeypatch):
    fixture = halted_merge(tmp_path, monkeypatch)
    sm = fixture.sm
    capability, _ = sm.authorize_recovery(fixture.root, mode='merge')
    before = sm.data
    with pytest.raises(TerminalStateError, match='authorization'):
        sm.execute_merge_recovery_transition([])
    spec = fixture.root / 'specs/R37.md'
    original = spec.read_bytes()
    try:
        spec.write_text('changed recovery context', encoding='utf-8')
        assert not sm.validate_strict_recovery(fixture.root, mode='merge')[0]
        with pytest.raises(RuntimeError):
            sm.execute_merge_recovery_transition(capability)
        with pytest.raises(RuntimeError):
            sm.authorize_recovery(fixture.root, mode='merge')
    finally:
        spec.write_bytes(original)
    assert sm.data == before
    assert sm.validate_strict_recovery(fixture.root, mode='merge')[0]
    with pytest.raises(TerminalStateError, match='authorization'):
        sm.execute_merge_recovery_transition(capability)
    fresh, _ = sm.authorize_recovery(fixture.root, mode='merge')
    assert fresh is not capability
    sm.execute_merge_recovery_transition(fresh)
    assert sm.data['current_state'] == 'AUTO_MERGE'
