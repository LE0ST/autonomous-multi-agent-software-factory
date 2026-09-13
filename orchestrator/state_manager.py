#!/usr/bin/env python3
"""
orchestrator/state_manager.py - Controlador FSM y Circuit Breaker desacoplado para la Software Factory.
Gestiona épocas, estados formales, presupuestos independientes y recuperación ante fallos.
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
            # Fallback a .orchestrator si fuera invocado en modo legacy
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
            # Detección de recuperación de interrupción
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
            raise ValueError(f"Estado '{new_state}' inválido. Debe ser uno de: {VALID_STATES}")
            
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
        """Registra un intento de compilación/código del Worker."""
        # 1. Comprobación del límite por época antes de incrementar
        if self.data["budgets"]["worker_attempts_in_epoch"] >= self.data["budgets"]["max_worker_per_epoch"]:
            self.halt_human(
                f"Límite de intentos del Worker por época superado "
                f"({self.data['budgets']['max_worker_per_epoch']} intentos por época)."
            )
            return False

        # 2. Comprobación del techo global acumulado antes de incrementar
        if self.data["budgets"]["total_cumulative_worker_runs"] >= self.data["budgets"]["max_cumulative_worker_runs"]:
            self.halt_human("Presupuesto global acumulado de compilaciones superado (techo de 5 runs).")
            return False

        self.data["budgets"]["total_cumulative_worker_runs"] += 1
        self.data["budgets"]["worker_attempts_in_epoch"] += 1
        self.save()
        return True

    def can_worker_retry_in_epoch(self) -> bool:
        return self.data["budgets"]["worker_attempts_in_epoch"] < self.data["budgets"]["max_worker_per_epoch"]

    def consume_spec_syntax_retry(self, reason: str) -> bool:
        """Consume reintento para corregir sintaxis o regex de la spec sin penalizar lógica."""
        self.data["budgets"]["spec_syntax_retries_used"] += 1
        self.save()
        if self.data["budgets"]["spec_syntax_retries_used"] > self.data["budgets"]["max_spec_syntax_retries"]:
            self.halt_human(f"Presupuesto de corrección de sintaxis de SPEC agotado: {reason}")
            return False
        return True

    def consume_logic_replan(self, reason: str) -> bool:
        """Consume replanificación lógica tras agotar intentos locales del Worker."""
        self.data["budgets"]["logic_replans_used"] += 1
        self.save()
        if self.data["budgets"]["logic_replans_used"] > self.data["budgets"]["max_logic_replans"]:
            self.halt_human(f"Presupuesto de replanificación lógica agotado: {reason}")
            return False
        self._new_epoch()
        return True

    def consume_security_replan(self, reason: str) -> bool:
        """Consume replanificación de seguridad tras vulnerabilidad o violación de invariante."""
        self.data["budgets"]["security_replans_used"] += 1
        self.save()
        if self.data["budgets"]["security_replans_used"] > self.data["budgets"]["max_security_replans"]:
            self.halt_human(f"Presupuesto de rediseño de seguridad agotado: {reason}")
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
            f"# CIRCUIT BREAKER ACTIVADO - {self.task_id}\n\n"
            f"- **Fecha:** {datetime.now(timezone.utc).isoformat()}\n"
            f"- **Motivo:** {reason}\n"
            f"- **Época final:** {self.data['epoch']}\n"
            f"- **Total Builds Worker:** {self.data['budgets']['total_cumulative_worker_runs']}/{self.data['budgets']['max_cumulative_worker_runs']}\n"
            f"- **Logic Replans Utilizados:** {self.data['budgets']['logic_replans_used']}/{self.data['budgets']['max_logic_replans']}\n"
            f"- **Security Replans Utilizados:** {self.data['budgets']['security_replans_used']}/{self.data['budgets']['max_security_replans']}\n"
            f"- **Spec Syntax Retries Utilizados:** {self.data['budgets']['spec_syntax_retries_used']}/{self.data['budgets']['max_spec_syntax_retries']}\n\n"
            f"El worktree de la tarea ha sido congelado para preservación y análisis forense.\n"
        )
        report_path.write_text(content, encoding="utf-8")
        print(f"\n[CIRCUIT BREAKER] Detención forzada. Ver {report_path.name}")
        
        if self.raise_on_halt:
            raise RuntimeError(f"Circuit Breaker activado: {reason}")
        sys.exit(1)

    def request_human_review(self, reason: str, gate: str = "LOGIC_AUDIT"):
        """Suspende el pipeline de forma controlada sin consumir replans del Worker."""
        self.transition("HUMAN_REVIEW", f"Revisión humana / servicio no disponible en {gate}: {reason}")
        self.set_execution_status("NEEDS_HUMAN_REVIEW")
        self.data["blocked_reason"] = {
            "gate": gate,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.save()

        report_path = Path(f"HUMAN_REVIEW_{self.task_id}.md")
        content = (
            f"# REVISIÓN HUMANA REQUERIDA - {self.task_id}\n\n"
            f"- **Fecha:** {datetime.now(timezone.utc).isoformat()}\n"
            f"- **Compuerta:** {gate}\n"
            f"- **Motivo:** {reason}\n"
            f"- **Estado de la tarea:** Las compuertas previas (SPEC, DIFF, TESTS, SAST) fueron superadas exitosamente.\n"
            f"- **Acción de Presupuesto:** NO se consumieron intentos del Worker ni replans de lógica/seguridad.\n"
            f"- **Worktree:** El código generado en `.worktrees/wt_{self.task_id}` está preservado e intacto.\n\n"
            f"El pipeline ha quedado pausado en un estado seguro (`NEEDS_HUMAN_REVIEW`).\n"
        )
        report_path.write_text(content, encoding="utf-8")
        print(f"\n[HUMAN REVIEW] Pipeline pausado en estado controlado. Ver {report_path.name}")
        
        if self.raise_on_halt:
            raise RuntimeError(f"Revisión humana requerida ({gate}): {reason}")
        sys.exit(0)
