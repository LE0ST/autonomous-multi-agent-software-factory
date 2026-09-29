"""Frozen S5 identity counterexamples using authentic recovery conditions."""
import threading

import pytest

from orchestrator.state_manager import TerminalStateError
from tests.security_acceptance.round37._support import halted_merge


class EqualHashAlias:
    def __init__(self, token):
        self.token = token
        self.hash_calls = 0
        self.eq_calls = 0

    def __hash__(self):
        self.hash_calls += 1
        return hash(self.token)

    def __eq__(self, other):
        self.eq_calls += 1
        return True


def test_equal_hash_alias_cannot_consume_authentic_token(tmp_path, monkeypatch):
    f = halted_merge(tmp_path, monkeypatch)
    sm = f.sm
    token, _ = sm.authorize_recovery(f.root, mode='merge')
    alias = EqualHashAlias(token)
    assert alias is not token and hash(alias) == hash(token) and alias == token
    before = sm.data
    with pytest.raises(TerminalStateError, match='authorization'):
        sm.execute_audit_recovery_transition(alias)
    assert sm.data == before
    assert sm.validate_strict_recovery(f.root, mode='merge')[0]
    sm.execute_merge_recovery_transition(token)
    assert sm.data['current_state'] == 'AUTO_MERGE'
    with pytest.raises(TerminalStateError, match='authorization'):
        sm.execute_merge_recovery_transition(token)


def test_equal_hash_alias_cannot_authorize_recovery(tmp_path, monkeypatch):
    f = halted_merge(tmp_path, monkeypatch)
    sm = f.sm
    token, _ = sm.authorize_recovery(f.root, mode='merge')
    alias = EqualHashAlias(token)
    assert alias is not token and hash(alias) == hash(token) and alias == token
    before = sm.data
    with pytest.raises(TerminalStateError, match='authorization'):
        sm.execute_merge_recovery_transition(alias)
    assert sm.data == before
    assert sm.validate_strict_recovery(f.root, mode='merge')[0]
    sm.execute_merge_recovery_transition(token)
    assert sm.data['current_state'] == 'AUTO_MERGE'


def test_actual_wrong_mode_spends_token(tmp_path, monkeypatch):
    f = halted_merge(tmp_path, monkeypatch)
    sm = f.sm
    token, _ = sm.authorize_recovery(f.root, mode='merge')
    with pytest.raises(TerminalStateError, match='authorization'):
        sm.execute_audit_recovery_transition(token)
    assert sm.validate_strict_recovery(f.root, mode='merge')[0]
    with pytest.raises(TerminalStateError, match='authorization'):
        sm.execute_merge_recovery_transition(token)
    fresh, _ = sm.authorize_recovery(f.root, mode='merge')
    sm.execute_merge_recovery_transition(fresh)
    assert sm.data['current_state'] == 'AUTO_MERGE'


def test_unhashable_and_malformed_objects_leave_token_valid(tmp_path, monkeypatch):
    f = halted_merge(tmp_path, monkeypatch)
    sm = f.sm
    token, _ = sm.authorize_recovery(f.root, mode='merge')

    class BadHash:
        def __hash__(self):
            raise RuntimeError('caller hash must not run')

    class BadEquality:
        def __hash__(self):
            return hash(token)

        def __eq__(self, other):
            raise RuntimeError('caller equality must not run')

    for invalid in ([], BadHash(), BadEquality()):
        with pytest.raises(TerminalStateError, match='authorization'):
            sm.execute_merge_recovery_transition(invalid)
        assert sm.validate_strict_recovery(f.root, mode='merge')[0]
    sm.execute_merge_recovery_transition(token)
    assert sm.data['current_state'] == 'AUTO_MERGE'


def test_reentrant_same_token_is_one_shot(tmp_path, monkeypatch):
    f = halted_merge(tmp_path, monkeypatch)
    sm = f.sm
    token, _ = sm.authorize_recovery(f.root, mode='merge')
    entered = []

    def reenter(*args):
        entered.append(True)
        with pytest.raises(TerminalStateError, match='authorization'):
            sm.execute_merge_recovery_transition(token)
        raise OSError('injected validation failure')

    with monkeypatch.context() as m:
        m.setattr(sm, '_recovery_session', reenter)
        with pytest.raises(OSError, match='injected validation failure'):
            sm.execute_merge_recovery_transition(token)
    assert entered == [True]
    assert sm.validate_strict_recovery(f.root, mode='merge')[0]
    with pytest.raises(TerminalStateError, match='authorization'):
        sm.execute_merge_recovery_transition(token)


def test_concurrent_same_token_is_one_shot(tmp_path, monkeypatch):
    f = halted_merge(tmp_path, monkeypatch)
    sm = f.sm
    token, _ = sm.authorize_recovery(f.root, mode='merge')
    entered, release = threading.Event(), threading.Event()
    outcomes = []

    def fail_first(*args):
        entered.set()
        assert release.wait(30)
        raise OSError('injected validation failure')

    def attempt(name):
        try:
            sm.execute_merge_recovery_transition(token)
            outcomes.append((name, 'success'))
        except BaseException as exc:
            outcomes.append((name, type(exc).__name__))

    with monkeypatch.context() as m:
        m.setattr(sm, '_recovery_session', fail_first)
        first = threading.Thread(target=attempt, args=('first',))
        first.start()
        assert entered.wait(30)
        second = threading.Thread(target=attempt, args=('second',))
        second.start()
        release.set()
        first.join(30)
        second.join(30)
        assert not first.is_alive() and not second.is_alive()
    assert sorted(outcomes) == [('first', 'OSError'), ('second', 'TerminalStateError')]
    assert sm.validate_strict_recovery(f.root, mode='merge')[0]
    with pytest.raises(TerminalStateError, match='authorization'):
        sm.execute_merge_recovery_transition(token)
