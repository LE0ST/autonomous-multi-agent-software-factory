#!/usr/bin/env python3
"""
orchestrator.py - Orchestrator Engine for the Autonomous Multi-Agent Software Factory.
Coordinates the full lifecycle:
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
from scripts.merge_gate import execute_fast_forward_merge, is_repo_clean
from scripts.worktree_manager import create_worktree, remove_worktree
from adapters import (
    GeminiAdapter,
    DeepSeekAdapter,
    GLMAdapter,
    QwenAdapter,
    LogicAuditOutput,
    NetworkTransportError,
    sanitize_secret_text
)
from adapters.network_retry import is_transient_network_error

def load_orchestrator_config(repo_root: Path) -> dict:
    cfg_file = repo_root / "orchestrator" / "config.json"
    if cfg_file.exists():
        return json.loads(cfg_file.read_text(encoding="utf-8"))
    return {}

def create_security_adapter(provider: str, model: str, simulate: bool = False):
    """
    Factory creating a security logic audit adapter for supported providers.
    Supported: 'gemini', 'deepseek', 'qwen', 'glm'.
    Fails closed (raises ValueError) for unknown providers.
    """
    p = str(provider).lower().strip()
    if p == "gemini":
        client = GeminiAdapter(model=model)
    elif p == "deepseek":
        client = DeepSeekAdapter(model=model)
    elif p in ("qwen", "dashscope"):
        client = QwenAdapter(model=model)
    elif p in ("glm", "zhipu"):
        client = GLMAdapter(model=model)
    else:
        raise ValueError(
            f"Unsupported security logic audit provider: '{provider}'. "
            f"Supported providers are: 'gemini', 'deepseek', 'qwen', 'glm'."
        )

    if simulate:
        client.is_simulation = True
    return client

def execute_logic_security_audit(
    sm: StateManager,
    spec_path: Path,
    diff_output: str,
    sec_role: dict,
    simulate: bool = False,
    exit_process: bool = True
) -> tuple[bool, LogicAuditOutput | None, dict | None]:
    """
    Executes the Logic Security Audit with a strict, deterministic multi-provider fallback policy.

    Candidates:
      Primary: sec_role["provider"] / sec_role["model"]
      Fallbacks: sec_role.get("fallbacks", [])

    Rules:
      1. Sequential iteration over candidates starting with primary.
      2. Fallback ONLY on provider availability failures (NetworkTransportError, HTTP 429/502/503/504, timeout, connection).
      3. Never fall back on semantic FAIL (invariants violated): consumes security replan and stops.
      4. Never fall back on semantic UNCERTAIN / UNAVAILABLE status in LogicAuditOutput: requests human review and stops.
      5. Never fall back on JSON parsing or validation errors: halts human review and stops.
      6. On PASS: records audit_model_used and stops immediately.
      7. On exhaustion of all candidates by availability errors: requests human review and stops.
    """
    primary_provider = sec_role.get("provider", "gemini")
    primary_model = sec_role.get("model", "gemini-3.8-flash")
    candidates = [{"provider": primary_provider, "model": primary_model, "is_fallback": False}]

    for fb in sec_role.get("fallbacks", []):
        fb_prov = fb.get("provider")
        fb_mod = fb.get("model")
        if fb_prov and fb_mod:
            candidates.append({"provider": fb_prov, "model": fb_mod, "is_fallback": True})

    spec_content = spec_path.read_text(encoding="utf-8")
    availability_errors = []

    for candidate in candidates:
        provider = candidate["provider"]
        model = candidate["model"]
        is_fallback = candidate["is_fallback"]

        if is_fallback:
            msg = f"Falling back to Logic Security Auditor: {provider.upper()}:{model}..."
            print(f"[i] {msg}")
            sm.transition("LOGIC_AUDIT", msg)

        try:
            client = create_security_adapter(provider, model, simulate=simulate)
        except ValueError as e:
            clean_err = sanitize_secret_text(str(e))
            print(f"[!] Security adapter initialization failed: {clean_err}")
            sm.halt_human(f"Security adapter initialization failed: {clean_err}", exit_process=exit_process)
            return False, None, None

        try:
            audit_res = client.audit_logic_and_security(spec_content, diff_output)
        except NetworkTransportError as e:
            clean_err = sanitize_secret_text(str(e))
            code_info = f"HTTP {e.status_code}" if e.status_code else "transport/network"
            err_msg = f"{provider}:{model} unavailable ({code_info}): {clean_err}"
            print(f"[!] {err_msg}")
            availability_errors.append(err_msg)
            continue
        except Exception as e:
            is_retryable, reason, code, _ = is_transient_network_error(e)
            if is_retryable:
                clean_err = sanitize_secret_text(str(e))
                code_info = f"HTTP {code}" if code else "transport/network"
                err_msg = f"{provider}:{model} unavailable ({code_info}): {clean_err}"
                print(f"[!] {err_msg}")
                availability_errors.append(err_msg)
                continue

            clean_err = sanitize_secret_text(str(e))
            print(f"\n[!] Non-retryable error during logic security audit with {provider}:{model}: {clean_err}")
            sm.halt_human(
                f"Non-availability failure in Logic Security Audit ({provider}:{model}): {clean_err}",
                exit_process=exit_process
            )
            return False, None, None

        # Evaluates semantic verdicts
        if audit_res.status == "FAIL":
            print(f"[!] Logic audit failed under {provider}:{model}. Violated invariants: {audit_res.violated_invariants}")
            sm.consume_security_replan(f"Invariant violation ({provider}:{model}): {audit_res.justification}")
            return False, audit_res, None

        if audit_res.status in ("UNAVAILABLE", "UNCERTAIN"):
            print(f"[!] Inconclusive audit ({audit_res.status}) from {provider}:{model}: {audit_res.justification}")
            sm.request_human_review(
                reason=f"Inconclusive audit ({audit_res.status}) from {provider}:{model}: {audit_res.justification}",
                gate="LOGIC_AUDIT",
                exit_process=exit_process
            )
            return False, audit_res, None

        if audit_res.status == "SIMULATED":
            if not simulate:
                print(f"[!] CRITICAL ALERT: Received simulated audit from {provider}:{model} but pipeline is in live mode.")
                sm.halt_human(
                    f"Simulated audit received from {provider}:{model} in live run. Merge blocked.",
                    exit_process=exit_process
                )
                return False, None, None
            print(f"[i] Simulated audit (--simulate active) from {provider}:{model}. Proceeding.")

        model_info = {"provider": provider, "model": model}
        sm.record_audit_model(provider, model)
        print(f"\n[PASS] Logic security audit passed successfully using model: {model} ({provider.upper()})")
        return True, audit_res, model_info

    summary_details = " | ".join(availability_errors)
    print(f"\n[!] All configured Logic Security audit models ({len(candidates)} attempted) failed due to availability errors.")
    sm.request_human_review(
        reason=f"All logic security audit models unavailable after retries ({len(candidates)} model(s) attempted). Details: {summary_details}",
        gate="LOGIC_AUDIT",
        exit_process=exit_process
    )
    return False, None, None

def run_pipeline(task_id: str, base_branch: str = "dev", simulate: bool = False):
    repo_root = Path.cwd()
    # Automatically load credentials from apis.txt or .env
    load_api_keys(repo_root)

    print(f"\n========================================================")
    print(f"[*] STARTING PIPELINE: {task_id} (Base: {base_branch})")
    print(f"========================================================\n")

    # 1. DISCOVERY PHASE
    print("[+] Running deterministic pre-flight checks (Discovery)...")
    disc_passed, disc_logs = run_discovery(repo_root, base_branch)
    for log in disc_logs:
        print(f"    {log}")
    if not disc_passed:
        print("[!] Pre-flight checks failed. Aborting execution.")
        sys.exit(1)

    # 2. INITIALIZE FSM
    config = load_orchestrator_config(repo_root)
    sm = StateManager(task_id, config_path="orchestrator/config.json", raise_on_halt=False)
    sm.transition("INIT", "Initialization completed and environment validated.")

    # Initialize Adapters with role configurations
    roles = config.get("roles", {})
    architect_model = roles.get("architect", {}).get("model", "gemini-3.8-flash")
    worker_model = roles.get("worker", {}).get("model", "deepseek-flash")
    triage_model = roles.get("triage", {}).get("model", "gemini-3.5-flash-lite")
    
    sec_role = roles.get("logic_security", {})

    gemini_client = GeminiAdapter(model=architect_model)
    worker_client = DeepSeekAdapter(model=worker_model)

    if simulate:
        gemini_client.is_simulation = True
        worker_client.is_simulation = True

    # 3. SPEC DESIGN & SPEC GATE
    spec_path = repo_root / "specs" / f"{task_id}.md"
    if not spec_path.exists():
        sm.transition("SPEC_DESIGN", "Generating specification with Architect...")
        generated_spec = gemini_client.generate_spec(
            task_id=task_id,
            title=f"Task {task_id}",
            description="Implementation with deterministic contracts and coverage >= 85%"
        )
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(generated_spec, encoding="utf-8")

    sm.transition("SPEC_GATE", "Validating SPEC.md contract...")
    spec_valid, spec_msg = validate_spec(spec_path)
    if not spec_valid:
        print(f"[!] Spec Gate failure: {spec_msg}")
        if not sm.consume_spec_syntax_retry(spec_msg):
            return
        # Regenerate spec if retries are available
        spec_valid, spec_msg = validate_spec(spec_path)
        if not spec_valid:
            sm.halt_human(f"Spec failed gate after retry: {spec_msg}")
            return

    # 4. WORKTREE ISOLATION
    print(f"[+] Creating isolated Git Worktree for {task_id}...")
    wt_ok, wt_dir_str = create_worktree(repo_root, task_id, base_branch)
    if not wt_ok:
        sm.halt_human(f"Failed to create worktree: {wt_dir_str}")
        return
    wt_path = Path(wt_dir_str)

    # 5. BUILD AND TEST CYCLE (BUILDING -> DIFF -> TESTING -> SAST -> LOGIC)
    pipeline_completed = False
    triage_info = None

    while not pipeline_completed:
        sm.transition("BUILDING", f"Epoch {sm.data['epoch']} - Worker attempt {sm.data['budgets']['worker_attempts_in_epoch'] + 1}")
        if not sm.register_worker_run():
            return

        # Worker generates/modifies code
        worker_client.generate_code_and_tests(
            spec_content=spec_path.read_text(encoding="utf-8"),
            worktree_path=wt_path,
            triage_feedback=triage_info
        )

        # Commit changes in worktree
        subprocess.run(["git", "add", "."], cwd=wt_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", f"feat({task_id}): epoch {sm.data['epoch']} build"],
            cwd=wt_path,
            capture_output=True
        )

        # DIFF GATE
        sm.transition("DIFF_GATE", "Verifying allowed modification boundaries...")
        diff_passed, diff_rep = validate_diff(wt_path, spec_path, base_branch)
        if not diff_passed:
            print("[!] Diff Gate violated:")
            for v in diff_rep.get("violations", []):
                print(f"    - {v}")
            if sm.can_worker_retry_in_epoch():
                triage_info = {"diff_violations": diff_rep.get("violations")}
                continue
            else:
                sm.consume_logic_replan("Persistent code boundary violation (Diff Gate).")
                continue

        # TESTING GATE
        sm.transition("TESTING", "Running test suite with coverage analysis...")
        tests_passed, t_stdout, t_stderr, t_code = run_tests(wt_path, repo_root)
        if not tests_passed:
            sm.transition("TRIAGING", "Analyzing failure with Triage Model...")
            triage_payload = {"stdout": t_stdout, "stderr": t_stderr, "exit_code": t_code}
            triage_res = gemini_client.triage_failure(triage_payload)
            print(f"[!] Diagnosed root cause: {triage_res.root_cause}")
            triage_info = triage_res.model_dump()

            if sm.can_worker_retry_in_epoch():
                print(f"[+] Retrying with Worker in the same epoch...")
                continue
            else:
                print(f"[!] Local epoch attempts exhausted. Consuming logic_replan...")
                if not sm.consume_logic_replan(f"Test failure: {triage_res.root_cause}"):
                    return
                continue

        # SAST SCAN
        sm.transition("SAST_SCAN", "Running static application security testing (SAST)...")
        sast_code, sast_rep = run_sast(wt_path)
        if sast_code == EXIT_FINDINGS:
            sm.transition("SAST_FILTER", "Filtering SAST findings...")
            findings = sast_rep.get("results", [])
            has_true_positive = False
            for f in findings:
                filt_res = gemini_client.filter_security_finding(f)
                if filt_res.classification == "TRUE_POSITIVE":
                    has_true_positive = True
                    print(f"[!] Confirmed critical vulnerability: {filt_res.justification}")
                    break

            if has_true_positive:
                if not sm.consume_security_replan("Confirmed critical SAST vulnerability"):
                    return
                continue

        # LOGIC AUDIT
        diff_output = subprocess.check_output(["git", "diff", f"{base_branch}...HEAD"], cwd=wt_path, text=True)
        audit_passed, audit_res, model_info = execute_logic_security_audit(
            sm=sm,
            spec_path=spec_path,
            diff_output=diff_output,
            sec_role=sec_role,
            simulate=simulate,
            exit_process=not sm.raise_on_halt
        )
        if not audit_passed:
            if audit_res and audit_res.status == "FAIL":
                continue
            return

        # All gates passed
        pipeline_completed = True

    # 6. AUTO MERGE & CLEANUP
    sm.transition("AUTO_MERGE", f"Gates passed (audit verified by {model_info['provider']}:{model_info['model']}). Detaching worktree and merging into dev...")
    remove_worktree(repo_root, task_id)
    merge_passed, merge_msg = execute_fast_forward_merge(repo_root, task_id, base_branch)
    if not merge_passed:
        sm.halt_human(f"Fast-Forward merge failed: {merge_msg}")
        return

    sm.set_execution_status("COMPLETED")
    print(f"\n[PASS] PIPELINE COMPLETED SUCCESSFULLY FOR {task_id}!")
    print(f"       Branch 'task/{task_id}' Fast-Forward merged into '{base_branch}'.")

def resume_merge(task_id: str, base_branch: str = "dev", repo_root: Path | None = None) -> bool:
    """
    Deterministic merge recovery pathway.
    Does not run agents, increment budgets, invoke LLMs, or create epochs.
    """
    root = repo_root or Path.cwd()
    config_file = root / "orchestrator" / "config.json"
    state_dir = root / "orchestrator" / "state"

    # 1. Load StateManager
    sm = StateManager(
        task_id,
        config_path=str(config_file),
        state_dir=str(state_dir),
        raise_on_halt=False
    )

    # 2. Validate recovery authorization (read-only)
    can_resume, reason = sm.can_resume_merge()
    if not can_resume:
        print(f"[!] MERGE RECOVERY DENIED for {task_id}: {reason}")
        return False

    # 3. Verify that branch task/<task_id> exists
    task_branch = f"task/{task_id}"
    branch_check = subprocess.run(
        ["git", "branch", "--list", task_branch],
        cwd=root,
        capture_output=True,
        text=True
    )
    branch_names = [b.strip().lstrip("*+ ") for b in branch_check.stdout.splitlines()]
    if task_branch not in branch_names:
        print(f"[!] MERGE RECOVERY DENIED: Branch '{task_branch}' does not exist.")
        return False

    # 4. Verify that main repository is clean
    clean, dirty_files = is_repo_clean(root)
    if not clean:
        print(
            f"[!] MERGE RECOVERY DENIED: The main repository has uncommitted changes.\n"
            f"Detected files:\n{dirty_files}"
        )
        return False

    # 5. Execute Fast-Forward merge by delegating to existing merge_gate
    print(f"[+] Executing Fast-Forward merge recovery for {task_id} into '{base_branch}'...")
    merge_passed, merge_msg = execute_fast_forward_merge(root, task_id, base_branch)
    if not merge_passed:
        print(f"[!] Fast-Forward merge failed: {merge_msg}")
        return False

    # 6. Mark as COMPLETED only after success
    sm.transition("AUTO_MERGE", f"Fast-Forward merge successfully recovered into '{base_branch}'.")
    sm.set_execution_status("COMPLETED")
    print(f"\n[PASS] MERGE RECOVERY COMPLETED SUCCESSFULLY FOR {task_id}!")
    print(f"       Branch '{task_branch}' Fast-Forward merged into '{base_branch}'.")
    return True

def resume_audit(
    task_id: str,
    base_branch: str = "dev",
    simulate: bool = False,
    repo_root: Path | None = None,
    raise_on_halt: bool = False
) -> bool:
    """
    Deterministic audit recovery pathway.
    Reuses existing code in worktree without running Worker, Architect, Triage,
    or earlier gates (SPEC, DIFF, TESTING, SAST). Does not consume worker budgets.
    Executes exclusively the pending LOGIC_AUDIT and proceeds to AUTO_MERGE if clean.
    """
    root = repo_root or Path.cwd()
    load_api_keys(root)
    config_file = root / "orchestrator" / "config.json"
    state_dir = root / "orchestrator" / "state"

    # 1. Load StateManager
    sm = StateManager(
        task_id,
        config_path=str(config_file),
        state_dir=str(state_dir),
        raise_on_halt=raise_on_halt
    )

    # 2. Validate recovery authorization (read-only checks on FSM, git branch, worktree, repo cleanliness, ancestor check)
    can_resume, reason = sm.can_resume_audit(repo_root=root, base_branch=base_branch)
    if not can_resume:
        print(f"[!] AUDIT RECOVERY DENIED for {task_id}: {reason}")
        return False

    spec_path = root / "specs" / f"{task_id}.md"
    if not spec_path.exists():
        print(f"[!] AUDIT RECOVERY DENIED for {task_id}: Specification '{spec_path}' does not exist.")
        return False

    wt_path = root / ".worktrees" / f"wt_{task_id}"

    # 3. Transition FSM: HUMAN_REVIEW -> LOGIC_AUDIT
    config = load_orchestrator_config(root)
    sec_role = config.get("roles", {}).get("logic_security", {})
    primary_provider = sec_role.get("provider", "gemini")
    primary_model = sec_role.get("model", "gemini-3.8-flash")

    sm.transition("LOGIC_AUDIT", f"Resuming security invariant audit ({primary_provider.upper()}:{primary_model})...")

    # 4. Extract diff from preserved worktree
    try:
        diff_output = subprocess.check_output(
            ["git", "diff", f"{base_branch}...HEAD"],
            cwd=wt_path,
            text=True
        )
    except Exception as e:
        clean_err = sanitize_secret_text(e)
        print(f"[!] Error calculating diff in worktree: {clean_err}")
        sm.halt_human(f"Diff calculation failed in worktree: {clean_err}", exit_process=False)
        return False

    # 5. Run exclusive Logic Security LLM Audit with deterministic fallback policy
    audit_passed, audit_res, model_info = execute_logic_security_audit(
        sm=sm,
        spec_path=spec_path,
        diff_output=diff_output,
        sec_role=sec_role,
        simulate=simulate,
        exit_process=False
    )
    if not audit_passed:
        return False

    # 6. Proceed to AUTO_MERGE using existing protections (no automatic rebase)
    # TOCTOU protection: verify Fast-Forward ancestor condition BEFORE removing worktree
    ancestor_check = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base_branch, f"task/{task_id}"],
        cwd=root,
        capture_output=True,
        text=True
    )
    if ancestor_check.returncode != 0:
        msg = (
            f"TREE DIVERGENCE DETECTED: The branch '{base_branch}' received commits "
            f"after audit started. Worktree preserved. Manual reconciliation required."
        )
        print(f"[!] {msg}")
        sm.halt_human(f"Fast-Forward merge blocked: {msg}", exit_process=False)
        return False

    sm.transition("AUTO_MERGE", f"Audit passed ({model_info['provider']}:{model_info['model']}). Detaching worktree and merging into dev...")
    remove_worktree(root, task_id)
    merge_passed, merge_msg = execute_fast_forward_merge(root, task_id, base_branch)
    if not merge_passed:
        sm.halt_human(f"Fast-Forward merge failed: {merge_msg}", exit_process=False)
        return False

    sm.set_execution_status("COMPLETED")
    print(f"\n[PASS] AUDIT RECOVERY COMPLETED SUCCESSFULLY FOR {task_id}!")
    print(f"       Branch 'task/{task_id}' Fast-Forward merged into '{base_branch}'.")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Autonomous Multi-Agent Software Factory Orchestrator")
    parser.add_argument("task_id", help="Task identifier (e.g. TASK-001)")
    parser.add_argument("--base", default="dev", help="Base integration branch (default: dev)")
    parser.add_argument("--simulate", action="store_true", help="Simulation / dry-run mode without consuming API tokens")
    parser.add_argument("--resume-merge", action="store_true", help="Deterministically recover merge for an authorized task")
    parser.add_argument("--resume-audit", action="store_true", help="Deterministically recover pending logic audit for an authorized task in HUMAN_REVIEW")
    args = parser.parse_args()

    if args.resume_merge:
        success = resume_merge(args.task_id, args.base)
        sys.exit(0 if success else 1)

    if args.resume_audit:
        success = resume_audit(args.task_id, args.base, args.simulate)
        sys.exit(0 if success else 1)

    run_pipeline(args.task_id, args.base, args.simulate)
