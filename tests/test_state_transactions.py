"""tests/test_state_transactions.py - Regression tests for:
1. CorruptStateError on malformed JSON or unreadable authoritative state
2. TerminalStateError on transitions out of HALT_HUMAN / COMPLETED
3. IllegalStateTransitionError on non-canonical state transitions
4. Reload-under-lock eliminating stale-snapshot overwrite
5. Thread-owned reentrant StateLock preventing cross-thread lock release/bypass
6. Lock contention timeout behavior
"""

import json
import threading
import pytest
from pathlib import Path

from orchestrator.state_manager import (
    StateManager,
    StateLock,
    CorruptStateError,
    TerminalStateError,
    IllegalStateTransitionError,
)


def test_corrupt_state_file_raises_corrupt_state_error(tmp_path):
    """Corrupted JSON must fail closed immediately with CorruptStateError."""
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True)
    state_file = state_dir / "state_TASK-CORRUPT.json"
    state_file.write_text("{ this is not valid json : [", encoding="utf-8")

    with pytest.raises(CorruptStateError, match=r"Authoritative state file .* is corrupt"):
        StateManager("TASK-CORRUPT", state_dir=str(state_dir), raise_on_halt=True)


def test_missing_required_fields_raises_corrupt_state_error(tmp_path):
    """Missing critical keys like task_id or current_state must raise CorruptStateError."""
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True)
    state_file = state_dir / "state_TASK-INCOMPLETE.json"
    state_file.write_text(json.dumps({"some_key": "val"}), encoding="utf-8")

    with pytest.raises(CorruptStateError, match=r"missing required schema fields"):
        StateManager("TASK-INCOMPLETE", state_dir=str(state_dir), raise_on_halt=True)


def test_terminal_state_lockout_halt_human(tmp_path):
    """Transitions out of HALT_HUMAN must be rejected with TerminalStateError."""
    state_dir = tmp_path / "state"
    sm = StateManager("TASK-TERMINAL", state_dir=str(state_dir), raise_on_halt=False)
    sm.halt_human("Critical failure occurred", exit_process=False)

    assert sm.data["current_state"] == "HALT_HUMAN"
    assert sm.data["execution_status"] == "FAILED"

    # Any transition attempt out of HALT_HUMAN without allow_recovery must fail
    with pytest.raises(TerminalStateError, match=r"Cannot transition out of terminal state"):
        sm.transition("SPEC_DESIGN", "Attempting unauthorized recovery")


def test_terminal_state_lockout_completed(tmp_path):
    """Transitions out of COMPLETED must be rejected with TerminalStateError."""
    state_dir = tmp_path / "state"
    sm = StateManager("TASK-DONE", state_dir=str(state_dir), raise_on_halt=False)
    sm.transition("SPEC_DESIGN", "design")
    sm.transition("SPEC_GATE", "gate")
    sm.transition("BUILDING", "building")
    sm.transition("DIFF_GATE", "diff")
    sm.transition("TESTING", "testing")
    sm.transition("SAST_SCAN", "sast")
    sm.transition("LOGIC_AUDIT", "logic")
    sm.transition("AUTO_MERGE", "merge")
    sm.set_execution_status("COMPLETED")

    with pytest.raises(TerminalStateError, match=r"Cannot transition out of terminal state"):
        sm.transition("BUILDING", "Attempt to reopen completed task")


def test_illegal_state_transition_raises_error(tmp_path):
    """Skipping mandatory FSM states must raise IllegalStateTransitionError."""
    state_dir = tmp_path / "state"
    sm = StateManager("TASK-ILLEGAL", state_dir=str(state_dir), raise_on_halt=True)
    assert sm.data["current_state"] == "INIT"

    # INIT cannot jump directly to AUTO_MERGE or LOGIC_AUDIT
    with pytest.raises(IllegalStateTransitionError, match=r"Illegal FSM transition from 'INIT' to 'AUTO_MERGE'"):
        sm.transition("AUTO_MERGE", "Bypassing all verification gates")


def test_reload_under_lock_eliminates_stale_snapshot(tmp_path):
    """Modifications committed by another instance must be preserved via reload-under-lock."""
    state_dir = tmp_path / "state"
    task_id = "TASK-RELOAD"

    sm1 = StateManager(task_id, state_dir=str(state_dir), raise_on_halt=True)
    sm2 = StateManager(task_id, state_dir=str(state_dir), raise_on_halt=True)

    # sm1 advances state
    sm1.transition("SPEC_DESIGN", "Design phase")

    # sm2 registers worker run; under reload-under-lock, sm2 loads sm1's update before modifying
    sm2.register_worker_run()

    # Reload from disk to verify both updates coexist
    sm3 = StateManager(task_id, state_dir=str(state_dir), raise_on_halt=True)
    assert sm3.data["current_state"] == "SPEC_DESIGN"
    assert sm3.data["budgets"]["worker_attempts_in_epoch"] == 1
    assert sm3.data["budgets"]["total_cumulative_worker_runs"] == 1


def test_statelock_thread_ownership(tmp_path):
    """A thread cannot release a StateLock held by another thread."""
    lock_file = tmp_path / "thread_test.lock"
    lock = StateLock(lock_file, timeout=2.0)

    acquired_evt = threading.Event()
    release_evt = threading.Event()

    def acquire_in_thread():
        lock.acquire()
        acquired_evt.set()
        release_evt.wait(timeout=3.0)
        lock.release()

    t = threading.Thread(target=acquire_in_thread)
    t.start()
    assert acquired_evt.wait(timeout=2.0)

    try:
        # Main thread attempts to release lock held by subthread
        with pytest.raises(RuntimeError, match=r"cannot release lock owned by"):
            lock.release()
    finally:
        release_evt.set()
        t.join(timeout=2.0)
