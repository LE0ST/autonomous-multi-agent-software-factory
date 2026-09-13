#!/usr/bin/env python3
"""
orchestrator/state_manager.py - Decoupled FSM and Circuit Breaker controller for Software Factory.
Manages epochs, formal states, independent budgets, and failure recovery.
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Literal

VALID_STATES = [
    "INIT",
    "SPEC_DESIGN",
    "SPEC_GATE",
    "BUILDING",
    "DIFF_GATE",
    "TESTING",
    "TRIAGING",
    "SAST_SCAN",
    "SAST_FILTER",
    "LOGIC_AUDIT",
    "AUTO_MERGE",
    "HUMAN_REVIEW",
    "HALT_HUMAN"
]

ExecutionStatus = Literal["RUNNING", "INTERRUPTED", "COMPLETED", "FAILED", "NEEDS_HUMAN_REVIEW"]

class StateManager:
    def __init__(
        self,
        task_id: str,
        config_path: str = "orchestrator/config.json",
        state_dir: str = "orchestrator/state",
        raise_on_halt: bool = False
    ):
        self.task_id = task_id
        self.raise_on_halt = raise_on_halt
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / f"state_{task_id}.json"
        
        cfg_file = Path(config_path)
        if not cfg_file.exists():
            # Fallback to .orchestrator if invoked in legacy mode
            cfg_file = Path(".orchestrator/config.json")
            
        if cfg_file.exists():
            self.config = json.loads(cfg_file.read_text(encoding="utf-8"))
        else:
            self.config = {
                "budgets": {
                    "max_logic_replans": 2,
                    "max_security_replans": 1,
                    "max_spec_syntax_retries": 1,
                    "max_worker_per_epoch": 2,
                    "max_cumulative_worker_runs": 5
                }
            }

        if self.state_file.exists():
            self.data = json.loads(self.state_file.read_text(encoding="utf-8"))
            # Interrupted recovery detection
            if self.data.get("execution_status") == "RUNNING":
                self.data["execution_status"] = "INTERRUPTED"
                self.save()
        else:
            self.data = self._init_state()
            self.save()

    def _init_state(self) -> dict:
        b = self.config.get("budgets", {})
        return {
            "task_id": self.task_id,
            "epoch": 1,
            "current_state": "INIT",
            "execution_status": "RUNNING",
            "budgets": {
                "logic_replans_used": 0,
                "max_logic_replans": b.get("max_logic_replans", 2),
                "security_replans_used": 0,
                "max_security_replans": b.get("max_security_replans", 1),
                "spec_syntax_retries_used": 0,
                "max_spec_syntax_retries": b.get("max_spec_syntax_retries", 1),
                "worker_attempts_in_epoch": 0,
                "max_worker_per_epoch": b.get("max_worker_per_epoch", 2),
                "total_cumulative_worker_runs": 0,
                "max_cumulative_worker_runs": b.get("max_cumulative_worker_runs", 5)
            },
            "history": []
        }

    def save(self):
        self.state_file.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    def transition(self, new_state: str, details: str = ""):
        if new_state not in VALID_STATES:
            raise ValueError(f"Invalid state '{new_state}'. Must be one of: {VALID_STATES}")
            
        old_state = self.data["current_state"]
        self.data["current_state"] = new_state
        self.data["history"].append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "from": old_state,
            "to": new_state,
            "details": details,
            "epoch": self.data["epoch"]
        })
        self.save()
        print(f"[FSM] {old_state} -> {new_state} | {details}")

    def set_execution_status(self, status: ExecutionStatus):
        self.data["execution_status"] = status
        self.save()

    def register_worker_run(self) -> bool:
        """Registers a Worker build/code attempt."""
        # 1. Check epoch limit before incrementing
        if self.data["budgets"]["worker_attempts_in_epoch"] >= self.data["budgets"]["max_worker_per_epoch"]:
            self.halt_human(
                f"Worker attempt limit per epoch exceeded "
                f"({self.data['budgets']['max_worker_per_epoch']} attempts per epoch)."
            )
            return False

        # 2. Check cumulative global ceiling before incrementing
        if self.data["budgets"]["total_cumulative_worker_runs"] >= self.data["budgets"]["max_cumulative_worker_runs"]:
            self.halt_human("Global cumulative worker build budget exceeded (ceiling of 5 runs).")
            return False

        self.data["budgets"]["total_cumulative_worker_runs"] += 1
        self.data["budgets"]["worker_attempts_in_epoch"] += 1
        self.save()
        return True

    def can_worker_retry_in_epoch(self) -> bool:
        return self.data["budgets"]["worker_attempts_in_epoch"] < self.data["budgets"]["max_worker_per_epoch"]

    def consume_spec_syntax_retry(self, reason: str) -> bool:
        """Consumes a retry to correct spec syntax or regex without penalizing logic."""
        self.data["budgets"]["spec_syntax_retries_used"] += 1
        self.save()
        if self.data["budgets"]["spec_syntax_retries_used"] > self.data["budgets"]["max_spec_syntax_retries"]:
            self.halt_human(f"SPEC syntax retry budget exhausted: {reason}")
            return False
        return True

    def consume_logic_replan(self, reason: str) -> bool:
        """Consumes a logic replan after exhausting Worker's local attempts."""
        self.data["budgets"]["logic_replans_used"] += 1
        self.save()
        if self.data["budgets"]["logic_replans_used"] > self.data["budgets"]["max_logic_replans"]:
            self.halt_human(f"Logic replanning budget exhausted: {reason}")
            return False
        self._new_epoch()
        return True

    def consume_security_replan(self, reason: str) -> bool:
        """Consumes a security replan after a vulnerability or invariant violation."""
        self.data["budgets"]["security_replans_used"] += 1
        self.save()
        if self.data["budgets"]["security_replans_used"] > self.data["budgets"]["max_security_replans"]:
            self.halt_human(f"Security redesign budget exhausted: {reason}")
            return False
        self._new_epoch()
        return True

    def _new_epoch(self):
        self.data["epoch"] += 1
        self.data["budgets"]["worker_attempts_in_epoch"] = 0
        self.save()

    def halt_human(self, reason: str):
        self.transition("HALT_HUMAN", reason)
        self.set_execution_status("FAILED")
        
        report_path = Path(f"CRASH_REPORT_{self.task_id}.md")
        content = (
            f"# CIRCUIT BREAKER TRIGGERED - {self.task_id}\n\n"
            f"- **Date:** {datetime.now(timezone.utc).isoformat()}\n"
            f"- **Reason:** {reason}\n"
            f"- **Final Epoch:** {self.data['epoch']}\n"
            f"- **Total Worker Builds:** {self.data['budgets']['total_cumulative_worker_runs']}/{self.data['budgets']['max_cumulative_worker_runs']}\n"
            f"- **Logic Replans Used:** {self.data['budgets']['logic_replans_used']}/{self.data['budgets']['max_logic_replans']}\n"
            f"- **Security Replans Used:** {self.data['budgets']['security_replans_used']}/{self.data['budgets']['max_security_replans']}\n"
            f"- **Spec Syntax Retries Used:** {self.data['budgets']['spec_syntax_retries_used']}/{self.data['budgets']['max_spec_syntax_retries']}\n\n"
            f"The task worktree has been frozen for preservation and forensic analysis.\n"
        )
        report_path.write_text(content, encoding="utf-8")
        print(f"\n[CIRCUIT BREAKER] Forced halt. See {report_path.name}")
        
        if self.raise_on_halt:
            raise RuntimeError(f"Circuit Breaker triggered: {reason}")
        sys.exit(1)

    def request_human_review(self, reason: str, gate: str = "LOGIC_AUDIT"):
        """Suspends the pipeline in a controlled manner without consuming Worker replans."""
        self.transition("HUMAN_REVIEW", f"Human review / service unavailable at {gate}: {reason}")
        self.set_execution_status("NEEDS_HUMAN_REVIEW")
        self.data["blocked_reason"] = {
            "gate": gate,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.save()

        report_path = Path(f"HUMAN_REVIEW_{self.task_id}.md")
        content = (
            f"# HUMAN REVIEW REQUIRED - {self.task_id}\n\n"
            f"- **Date:** {datetime.now(timezone.utc).isoformat()}\n"
            f"- **Gate:** {gate}\n"
            f"- **Reason:** {reason}\n"
            f"- **Task Status:** Prior gates (SPEC, DIFF, TESTS, SAST) passed successfully.\n"
            f"- **Budget Action:** NO Worker attempts or logic/security replans were consumed.\n"
            f"- **Worktree:** Code generated in `.worktrees/wt_{self.task_id}` is preserved and intact.\n\n"
            f"Pipeline paused in a safe state (`NEEDS_HUMAN_REVIEW`).\n"
        )
        report_path.write_text(content, encoding="utf-8")
        print(f"\n[HUMAN REVIEW] Pipeline paused in controlled state. See {report_path.name}")
        
        if self.raise_on_halt:
            raise RuntimeError(f"Human review required ({gate}): {reason}")
        sys.exit(0)

    def can_resume_merge(self) -> tuple[bool, str]:
        """
        Validates in read-only mode if the task is authorized for merge recovery.
        Required conditions:
          - current_state == 'HALT_HUMAN'
          - execution_status == 'FAILED'
          - Last transition in history: from 'AUTO_MERGE' to 'HALT_HUMAN'
          - Failure reason in last transition corresponds to a merge failure
        """
        curr_state = self.data.get("current_state")
        if curr_state != "HALT_HUMAN":
            return False, f"current_state must be 'HALT_HUMAN', actual: '{curr_state}'"

        exec_status = self.data.get("execution_status")
        if exec_status != "FAILED":
            return False, f"execution_status must be 'FAILED', actual: '{exec_status}'"

        history = self.data.get("history", [])
        if not history:
            return False, "Transition history is empty."

        last_trans = history[-1]
        from_state = last_trans.get("from")
        to_state = last_trans.get("to")
        if from_state != "AUTO_MERGE" or to_state != "HALT_HUMAN":
            return False, (
                f"Last transition must be 'AUTO_MERGE -> HALT_HUMAN', "
                f"actual: '{from_state} -> {to_state}'"
            )

        details = last_trans.get("details", "")
        if "merge" not in details.lower():
            return False, f"Failure cause does not correspond to a merge failure: '{details}'"

        return True, "Task authorized for merge recovery."
