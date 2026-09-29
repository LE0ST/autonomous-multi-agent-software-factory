"""S5: first recovery use consumes authority, even when validation fails."""
import subprocess

import pytest

from orchestrator.state_manager import IllegalStateTransitionError, TerminalStateError
from ._support import git, halted_merge


@pytest.mark.parametrize('failure', [
    'context-drift', 'missing-evidence-read', 'git-error', 'persistence-error', 'transition-error', 'wrong-mode',
])
def test_failed_first_recovery_use_consumes_capability(tmp_path, monkeypatch, failure):
    fixture = halted_merge(tmp_path, monkeypatch)
    sm, root = fixture.sm, fixture.root
    capability, _ = sm.authorize_recovery(root, mode='merge')
    before = sm.data
    spec = root / 'specs/R37.md'
    original = spec.read_bytes()
    hit = []
    try:
        with monkeypatch.context() as fault:
            if failure == 'context-drift':
                spec.write_text('temporary spec drift', encoding='utf-8')
            elif failure == 'missing-evidence-read':
                # Fault only the persistence READ boundary; do not rewrite a snapshot
                # or advance generation (that would mask capability reuse as staleness).
                reload_state = sm._reload

                def missing_evidence():
                    reload_state()
                    sm._data['gate_evidence'].pop()
                    hit.append(failure)

                fault.setattr(sm, '_reload', missing_evidence)
            elif failure == 'git-error':
                check_output = subprocess.check_output

                def git_error(command, *args, **kwargs):
                    if command[:3] == ['git', 'rev-parse', 'refs/heads/dev']:
                        hit.append(failure)
                        raise subprocess.CalledProcessError(128, command, stderr='injected Git read error')
                    return check_output(command, *args, **kwargs)

                fault.setattr(subprocess, 'check_output', git_error)
            elif failure == 'persistence-error':
                def persistence_error():
                    hit.append(failure)
                    raise OSError('injected pre-write persistence error')

                fault.setattr(sm, '_persist', persistence_error)
            elif failure == 'transition-error':
                def transition_error(*args, **kwargs):
                    hit.append(failure)
                    raise IllegalStateTransitionError('injected transition error')

                fault.setattr(sm, '_transition', transition_error)
            with pytest.raises((RuntimeError, OSError)):
                if failure == 'wrong-mode':
                    sm.execute_audit_recovery_transition(capability)
                else:
                    sm.execute_merge_recovery_transition(capability)
    finally:
        spec.write_bytes(original)
    if failure not in ('context-drift', 'wrong-mode'):
        assert hit, 'Required injected failure was not reached'
    assert sm.data == before, 'Failed first attempt must not have transitioned or changed generation'
    assert sm.validate_strict_recovery(root, mode='merge')[0], 'Fixture must be valid again before replay'
    rejected = False
    try:
        sm.execute_merge_recovery_transition(capability)
    except TerminalStateError:
        rejected = True
    observed = sm.data
    assert rejected and observed == before, (
        f'S5 capability reusable after {failure}: rejected={rejected}, '
        f'state={observed["current_state"]}, status={observed["execution_status"]}')
    assert git(root, 'rev-parse', 'dev') == fixture.base
    # Only freshly revalidated authority may reopen recovery.
    fresh, _ = sm.authorize_recovery(root, mode='merge')
    assert fresh is not capability
    sm.execute_merge_recovery_transition(fresh)
    assert sm.data['current_state'] == 'AUTO_MERGE'


def test_successful_first_use_is_one_shot_and_preserves_budgets(tmp_path, monkeypatch):
    fixture = halted_merge(tmp_path, monkeypatch)
    sm = fixture.sm
    before = sm.data
    capability, session = sm.authorize_recovery(fixture.root, mode='merge')
    sm.execute_merge_recovery_transition(capability)
    with pytest.raises(TerminalStateError):
        sm.execute_merge_recovery_transition(capability)
    assert session.merge('dev')[0]
    after = sm.data
    assert after['execution_status'] == 'COMPLETED'
    assert after['budgets'] == before['budgets'] and after['epoch'] == before['epoch']
    assert git(fixture.root, 'rev-parse', 'dev') == fixture.candidate
