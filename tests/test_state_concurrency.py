"""Unit tests for StateManager concurrency control, locking, and atomic persistence."""

import json
import time
import threading
import pytest
from pathlib import Path

from orchestrator.state_manager import StateManager, StateLock


def test_statelock_reentrancy(tmp_path):
    lock_file = tmp_path / "test.lock"
    lock = StateLock(lock_file, timeout=1.0)

    with lock:
        assert lock._depth == 1
        with lock:
            assert lock._depth == 2
        assert lock._depth == 1
    assert lock._depth == 0


def test_statelock_timeout_on_contention(tmp_path):
    lock_file = tmp_path / "contended.lock"
    lock1 = StateLock(lock_file, timeout=1.0)
    lock2 = StateLock(lock_file, timeout=0.2, poll_interval=0.02)

    lock1.acquire()
    try:
        with pytest.raises(TimeoutError, match="Timed out acquiring state lock"):
            lock2.acquire()
    finally:
        lock1.release()

    # Once lock1 is released, lock2 can acquire successfully
    lock2.acquire()
    lock2.release()


def test_state_manager_atomic_save_and_reload(tmp_path):
    state_dir = tmp_path / "state"
    sm = StateManager("TASK-ATOMIC", state_dir=str(state_dir), raise_on_halt=True)

    sm.transition("SPEC_DESIGN", "Test transition")
    state_path = state_dir / "state_TASK-ATOMIC.json"
    assert state_path.exists()

    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert data["current_state"] == "SPEC_DESIGN"
    # Verify no temporary files remain
    tmp_files = list(state_dir.glob(".*.tmp.*"))
    assert len(tmp_files) == 0


def test_state_manager_nested_calls_do_not_deadlock(tmp_path):
    state_dir = tmp_path / "state"
    sm = StateManager("TASK-NESTED", state_dir=str(state_dir), raise_on_halt=True)

    # consume_logic_replan internally calls self._new_epoch() which calls self.save()
    sm.register_worker_run()
    assert sm.can_worker_retry_in_epoch() is True

    # This must execute without deadlock
    assert sm.consume_logic_replan("Test replan nested") is True
    assert sm.data["epoch"] == 2
    assert sm.data["budgets"]["worker_attempts_in_epoch"] == 0
    assert sm.data["budgets"]["logic_replans_used"] == 1


def test_concurrent_worker_runs_serialize(tmp_path):
    state_dir = tmp_path / "state"
    task_id = "TASK-CONCURRENCY"

    # Initialize state
    sm_init = StateManager(task_id, state_dir=str(state_dir), raise_on_halt=False)

    errors = []

    def worker_attempt():
        try:
            sm = StateManager(task_id, state_dir=str(state_dir), raise_on_halt=False, lock_timeout=5.0)
            sm.register_worker_run()
        except Exception as e:
            errors.append(e)

    # Launch 2 concurrent worker runs (max_worker_per_epoch is 2)
    t1 = threading.Thread(target=worker_attempt)
    t2 = threading.Thread(target=worker_attempt)

    t1.start()
    t2.start()
    t1.join(timeout=5.0)
    t2.join(timeout=5.0)

    assert len(errors) == 0
    sm_final = StateManager(task_id, state_dir=str(state_dir), raise_on_halt=False)
    assert sm_final.data["budgets"]["worker_attempts_in_epoch"] == 2
    assert sm_final.data["budgets"]["total_cumulative_worker_runs"] == 2
