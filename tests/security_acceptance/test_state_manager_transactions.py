import os
import time
import threading
from pathlib import Path
import pytest
from orchestrator.state_manager import StateLock, StateManager, CorruptStateError

def test_statelock_mutual_exclusion(tmp_path):
    lock_file = tmp_path / "test.lock"
    lock = StateLock(lock_file, timeout=5.0)

    events = []

    def worker1():
        with lock:
            events.append("A_enter")
            time.sleep(0.5)
            events.append("A_exit")

    def worker2():
        time.sleep(0.1)
        # B should not be able to enter until A releases
        try:
            with lock:
                events.append("B_enter")
                events.append("B_exit")
        except Exception as e:
            events.append(f"B_error: {e}")

    t1 = threading.Thread(target=worker1)
    t2 = threading.Thread(target=worker2)

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert events == ["A_enter", "A_exit", "B_enter", "B_exit"]

def test_missing_state_fails_closed(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    sm = StateManager("TASK-123", state_dir=str(state_dir))

    sm.state_file.unlink()

    with pytest.raises(CorruptStateError):
        sm.transition("TESTING", "test")
