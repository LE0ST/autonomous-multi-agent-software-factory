#!/usr/bin/env python3
"""
orchestrator.py - Motor Orquestador de la Autonomous Multi-Agent Software Factory.
Coordina el ciclo completo:
  INIT -> SPEC_DESIGN -> SPEC_GATE -> BUILDING -> DIFF_GATE -> TESTING ->
  TRIAGING -> SAST_SCAN -> SAST_FILTER -> LOGIC_AUDIT -> AUTO_MERGE
"""

import sys
import json
import argparse
import subprocess
from pathlib import Path

from orchestrator.state_manager import StateManager
from orchestrator.env_loader import load_api_keys
from scripts.discovery import run_discovery
from scripts.spec_gate import validate_spec
from scripts.diff_gate import validate_diff
from scripts.test_runner import run_tests
from scripts.sast_runner import run_sast, EXIT_NO_FINDINGS, EXIT_FINDINGS
from scripts.merge_gate import execute_fast_forward_merge
from scripts.worktree_manager import create_worktree, remove_worktree
from adapters import GeminiAdapter, DeepSeekAdapter, GLMAdapter, NetworkTransportError

def load_orchestrator_config(repo_root: Path) -> dict:
    cfg_file = repo_root / "orchestrator" / "config.json"
    if cfg_file.exists():
        return json.loads(cfg_file.read_text(encoding="utf-8"))
    return {}

def run_pipeline(task_id: str, base_branch: str = "dev", simulate: bool = False):
    repo_root = Path.cwd()
    # Cargar automáticamente credenciales desde apis.txt o .env
    load_api_keys(repo_root)

    print(f"\n========================================================")
    print(f"[*] INICIANDO PIPELINE: {task_id} (Base: {base_branch})")
    print(f"========================================================\n")

    # 1. FASE DISCOVERY
    print("[+] Ejecutando pre-vuelo determinista (Discovery)...")
    disc_passed, disc_logs = run_discovery(repo_root, base_branch)
    for log in disc_logs:
        print(f"    {log}")
    if not disc_passed:
        print("[!] Pre-vuelo falló. Abortando ejecución.")
        sys.exit(1)

    # 2. INICIALIZAR FSM
    config = load_orchestrator_config(repo_root)
    sm = StateManager(task_id, config_path="orchestrator/config.json", raise_on_halt=False)
    sm.transition("INIT", "Inicialización completada y entorno validado.")

    # Inicializar Adaptadores con configuración de roles
    roles = config.get("roles", {})
    architect_model = roles.get("architect", {}).get("model", "gemini-1.5-pro")
    worker_model = roles.get("worker", {}).get("model", "deepseek-chat")
    triage_model = roles.get("triage", {}).get("model", "gemini-1.5-flash")
    sec_model = roles.get("logic_security", {}).get("model", "glm-4")

    gemini_client = GeminiAdapter(model=architect_model)
    worker_client = DeepSeekAdapter(model=worker_model)
    glm_client = GLMAdapter(model=sec_model)

    if simulate:
        gemini_client.is_simulation = True
        worker_client.is_simulation = True
        glm_client.is_simulation = True

    # 3. SPEC DESIGN & SPEC GATE
    spec_path = repo_root / "specs" / f"{task_id}.md"
    if not spec_path.exists():
        sm.transition("SPEC_DESIGN", "Generando especificación con Architect...")
        generated_spec = gemini_client.generate_spec(
            task_id=task_id,
            title=f"Tarea {task_id}",
            description="Implementación con contratos deterministas y cobertura >= 85%"
        )
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(generated_spec, encoding="utf-8")

    sm.transition("SPEC_GATE", "Validando contrato SPEC.md...")
    spec_valid, spec_msg = validate_spec(spec_path)
    if not spec_valid:
        print(f"[!] Fallo en Spec Gate: {spec_msg}")
        if not sm.consume_spec_syntax_retry(spec_msg):
            return
        # Regenerar spec si hay reintentos disponibles
        spec_valid, spec_msg = validate_spec(spec_path)
        if not spec_valid:
            sm.halt_human(f"Spec no superó la compuerta tras reintento: {spec_msg}")
            return

    # 4. AISLAMIENTO WORKTREE
    print(f"[+] Creando Git Worktree aislado para {task_id}...")
    wt_ok, wt_dir_str = create_worktree(repo_root, task_id, base_branch)
    if not wt_ok:
        sm.halt_human(f"Fallo al crear worktree: {wt_dir_str}")
        return
    wt_path = Path(wt_dir_str)

    # 5. CICLO DE CONSTRUCCIÓN Y PRUEBAS (BUILDING -> DIFF -> TESTING -> SAST -> LOGIC)
    pipeline_completed = False
    triage_info = None

    while not pipeline_completed:
        sm.transition("BUILDING", f"Época {sm.data['epoch']} - Intento Worker {sm.data['budgets']['worker_attempts_in_epoch'] + 1}")
        if not sm.register_worker_run():
            return

        # Worker genera/modifica código
        worker_client.generate_code_and_tests(
            spec_content=spec_path.read_text(encoding="utf-8"),
            worktree_path=wt_path,
            triage_feedback=triage_info
        )

        # Commitear cambios en worktree
        subprocess.run(["git", "add", "."], cwd=wt_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", f"feat({task_id}): epoch {sm.data['epoch']} build"],
            cwd=wt_path,
            capture_output=True
        )

        # DIFF GATE
        sm.transition("DIFF_GATE", "Verificando fronteras de modificación permitidas...")
        diff_passed, diff_rep = validate_diff(wt_path, spec_path, base_branch)
        if not diff_passed:
            print("[!] Diff Gate violado:")
            for v in diff_rep.get("violations", []):
                print(f"    - {v}")
            if sm.can_worker_retry_in_epoch():
                triage_info = {"diff_violations": diff_rep.get("violations")}
                continue
            else:
                sm.consume_logic_replan("Violación persistente de fronteras de código (Diff Gate).")
                continue

        # TESTING GATE
        sm.transition("TESTING", "Ejecutando suite de pruebas con análisis de cobertura...")
        tests_passed, t_stdout, t_stderr, t_code = run_tests(wt_path, repo_root)
        if not tests_passed:
            sm.transition("TRIAGING", "Analizando fallo con Triage Model...")
            triage_payload = {"stdout": t_stdout, "stderr": t_stderr, "exit_code": t_code}
            triage_res = gemini_client.triage_failure(triage_payload)
            print(f"[!] Causa raíz diagnosticada: {triage_res.root_cause}")
            triage_info = triage_res.model_dump()

            if sm.can_worker_retry_in_epoch():
                print(f"[+] Reintentando con Worker en la misma época...")
                continue
            else:
                print(f"[!] Intentos locales de época agotados. Consumiendo logic_replan...")
                if not sm.consume_logic_replan(f"Fallo de tests: {triage_res.root_cause}"):
                    return
                continue

        # SAST SCAN
        sm.transition("SAST_SCAN", "Ejecutando análisis estático de seguridad (SAST)...")
        sast_code, sast_rep = run_sast(wt_path)
        if sast_code == EXIT_FINDINGS:
            sm.transition("SAST_FILTER", "Filtrando hallazgos SAST...")
            findings = sast_rep.get("results", [])
            has_true_positive = False
            for f in findings:
                filt_res = gemini_client.filter_security_finding(f)
                if filt_res.classification == "TRUE_POSITIVE":
                    has_true_positive = True
                    print(f"[!] Vulnerabilidad crítica confirmada: {filt_res.justification}")
                    break

            if has_true_positive:
                if not sm.consume_security_replan("Vulnerabilidad SAST crítica confirmada"):
                    return
                continue

        # LOGIC AUDIT
        sm.transition("LOGIC_AUDIT", "Ejecutando auditoría de invariantes de seguridad (GLM)...")
        diff_output = subprocess.check_output(["git", "diff", f"{base_branch}...HEAD"], cwd=wt_path, text=True)
        
        try:
            audit_res = glm_client.audit_logic_and_security(spec_path.read_text(encoding="utf-8"), diff_output)
        except NetworkTransportError as e:
            print(f"\n[!] Servicio de Auditoría de Seguridad no disponible: {e}")
            sm.request_human_review(
                reason=f"Logic Security LLM no disponible tras reintentos (HTTP {e.status_code or 'red'}). "
                       f"Detalle: {e}",
                gate="LOGIC_AUDIT"
            )
            return
        except Exception as e:
            print(f"\n[!] Error inesperado durante la auditoría de seguridad: {e}")
            sm.halt_human(f"Fallo no recuperable en Logic Security Audit: {e}")
            return

        if audit_res.status == "FAIL":
            print(f"[!] Auditoría de lógica falló. Invariantes violados: {audit_res.violated_invariants}")
            if not sm.consume_security_replan(f"Violación de invariantes: {audit_res.justification}"):
                return
            continue

        if audit_res.status in ("UNAVAILABLE", "UNCERTAIN"):
            print(f"[!] Auditoría no concluyente ({audit_res.status}): {audit_res.justification}")
            sm.request_human_review(
                reason=f"Auditoría no concluyente ({audit_res.status}): {audit_res.justification}",
                gate="LOGIC_AUDIT"
            )
            return

        if audit_res.status == "SIMULATED":
            if not simulate:
                print(f"[!] ALERTA CRÍTICA: Se recibió auditoría simulada pero el pipeline está en modo real.")
                sm.halt_human("Auditoría simulada recibida en ejecución real. Merge bloqueado.")
                return
            print(f"[i] Auditoría simulada (--simulate activo). Procediendo a prueba de compuertas.")

        # Todas las compuertas superadas
        pipeline_completed = True

    # 6. AUTO MERGE & CLEANUP
    sm.transition("AUTO_MERGE", "Compuertas aprobadas. Desvinculando worktree y fusionando a dev...")
    remove_worktree(repo_root, task_id)
    merge_passed, merge_msg = execute_fast_forward_merge(repo_root, task_id, base_branch)
    if not merge_passed:
        sm.halt_human(f"Fallo durante el merge Fast-Forward: {merge_msg}")
        return

    sm.set_execution_status("COMPLETED")
    print(f"\n[PASS] PIPELINE COMPLETADO EXITOSAMENTE PARA {task_id}!")
    print(f"       Rama 'task/{task_id}' fusionada Fast-Forward en '{base_branch}'.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Orquestador Autónomo de Software Multi-Agente")
    parser.add_argument("task_id", help="Identificador de la tarea (ej: TASK-001)")
    parser.add_argument("--base", default="dev", help="Rama base de integración (por defecto: dev)")
    parser.add_argument("--simulate", action="store_true", help="Modo simulación / dry-run sin gastar tokens de API")
    args = parser.parse_args()

    run_pipeline(args.task_id, args.base, args.simulate)
