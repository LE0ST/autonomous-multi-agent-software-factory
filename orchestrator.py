#!/usr/bin/env python3
"""Software-factory controller with one frozen context and authenticated gate chain."""
import argparse
import json
import subprocess
import sys
from pathlib import Path
from orchestrator.state_manager import StateManager
from orchestrator.verification_context import VerificationContext
from orchestrator.gate_controller import VerificationSession
from orchestrator.env_loader import load_api_keys
from orchestrator.logic_audit import create_security_adapter, execute_logic_security_audit
from scripts.discovery import run_discovery
from scripts.spec_gate import validate_spec
from scripts.worktree_manager import create_worktree, remove_worktree
from scripts.merge_gate import execute_fast_forward_merge, is_repo_clean
from scripts.diff_gate import validate_diff
from scripts.test_runner import run_tests
from scripts.sast_runner import run_sast, EXIT_NO_FINDINGS, EXIT_FINDINGS
from adapters import GeminiAdapter, DeepSeekAdapter, GLMAdapter, QwenAdapter, LogicAuditOutput, NetworkTransportError, sanitize_secret_text


def load_orchestrator_config(repo_root):
    path = Path(repo_root) / 'orchestrator/config.json'
    return json.loads(path.read_bytes()) if path.exists() else {}


def run_pipeline(task_id, base_branch='dev', simulate=False):
    try:
        return _run_pipeline_core(task_id, base_branch, simulate)
    except SystemExit:
        raise
    except Exception as exc:
        # Reopen authoritative state, never save a stale instance after an exception.
        sm = StateManager(task_id, raise_on_halt=False)
        sm.halt_human(f'Pipeline failed closed: {exc}', exit_process=True)


def _run_pipeline_core(task_id, base_branch='dev', simulate=False):
    root = Path.cwd()
    load_api_keys(root)
    passed, logs = run_discovery(root, base_branch)
    for line in logs:
        print(line)
    if not passed:
        raise SystemExit(1)
    config = load_orchestrator_config(root)
    sm = StateManager(task_id)
    sm.transition('INIT', 'Preflight completed')
    roles = config.get('roles', {})
    architect = GeminiAdapter(model=roles.get('architect', {}).get('model', 'gemini-3.8-flash'))
    worker = DeepSeekAdapter(model=roles.get('worker', {}).get('model', 'deepseek-flash'))
    if simulate:
        architect.is_simulation = worker.is_simulation = True
    spec_path = root / 'specs' / f'{task_id}.md'
    if not spec_path.exists():
        sm.transition('SPEC_DESIGN')
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(architect.generate_spec(task_id=task_id, title=f'Task {task_id}',
            description='Implement the specified behavior and security invariants'), encoding='utf-8')
    sm.transition('SPEC_GATE')
    valid, reason = validate_spec(spec_path)
    if not valid:
        sm.halt_human(f'Specification failed validation: {reason}')
        return False
    created, worktree = create_worktree(root, task_id, base_branch)
    if not created:
        sm.halt_human(f'Cannot create candidate worktree: {worktree}')
        return False
    worktree = Path(worktree)
    feedback = None
    while True:
        sm.transition('BUILDING')
        if not sm.register_worker_run():
            return False
        worker.generate_code_and_tests(spec_content=spec_path.read_text(encoding='utf-8'),
                                       worktree_path=worktree, triage_feedback=feedback)
        subprocess.run(['git', 'add', '.'], cwd=worktree, check=True, capture_output=True, timeout=30)
        staged = subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=worktree, timeout=30)
        if staged.returncode == 1:
            subprocess.run(['git', 'commit', '-m', f'feat({task_id}): epoch {sm.data["epoch"]} build'],
                           cwd=worktree, check=True, capture_output=True, timeout=30)
        elif staged.returncode != 0:
            raise RuntimeError('Cannot inspect staged candidate')
        # The only symbolic reads used for selection. All subsequent consumers use B and C.
        candidate = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=worktree, text=True, timeout=30).strip()
        base = subprocess.check_output(['git', 'rev-parse', f'refs/heads/{base_branch}'], cwd=root, text=True, timeout=30).strip()
        context = VerificationContext.capture(root, task_id, base, candidate)
        session = VerificationSession(root, sm, context)
        passed, report = session.run_diff()
        if not passed:
            feedback = report
            if not sm.can_worker_retry_in_epoch() and not sm.consume_logic_replan('Diff boundary failure'):
                return False
            continue
        passed, stdout, stderr, code, _ = session.run_testing()
        if not passed:
            sm.transition('TRIAGING', 'Trusted behavior verification failed')
            feedback = {'stdout': stdout, 'stderr': stderr, 'exit_code': code}
            if not sm.can_worker_retry_in_epoch() and not sm.consume_logic_replan('Trusted behavior failure'):
                return False
            continue
        code, report = session.run_sast()
        if code != EXIT_NO_FINDINGS:
            sm.halt_human(f'SAST did not complete cleanly (exit {code}): {report.get("error", "findings require review")}')
            return False
        passed, result, model = session.run_audit(simulate=simulate)
        if not passed:
            if result is not None and result.status == 'FAIL':
                continue
            return False
        passed, reason = session.merge(base_branch)
        if not passed:
            sm.halt_human(f'Fast-Forward merge failed: {reason}')
            return False
        print(f'[PASS] Integrated exact candidate {context.C} for {task_id}')
        return True


def _resume_state(task_id, root, raise_on_halt=False):
    return StateManager(task_id, config_path=str(root / 'orchestrator/config.json'),
                        state_dir=str(root / 'orchestrator/state'), raise_on_halt=raise_on_halt)


def resume_merge(task_id, base_branch='dev', repo_root=None):
    root = Path(repo_root or Path.cwd()).resolve()
    try:
        sm = _resume_state(task_id, root)
        capability, session = sm.authorize_recovery(root, base_branch, mode='merge')
        sm.execute_merge_recovery_transition(capability, 'Authorized merge recovery')
        passed, reason = session.merge(base_branch)
        if not passed:
            sm.halt_human(f'Fast-Forward merge recovery failed: {reason}', exit_process=False)
        return passed
    except (OSError, ValueError, RuntimeError, TypeError, KeyError) as exc:
        print(f'[DENIED] Merge recovery: {exc}')
        return False


def resume_audit(task_id, base_branch='dev', simulate=False, repo_root=None, raise_on_halt=False):
    root = Path(repo_root or Path.cwd()).resolve()
    try:
        sm = _resume_state(task_id, root, raise_on_halt)
        capability, session = sm.authorize_recovery(root, base_branch, mode='audit')
        sm.execute_audit_recovery_transition(capability, 'Authorized audit recovery')
        passed, result, model = session.run_audit(simulate=simulate)
        if not passed:
            return False
        passed, reason = session.merge(base_branch)
        if not passed:
            sm.halt_human(f'Fast-Forward merge failed: {reason}', exit_process=False)
        return passed
    except (OSError, ValueError, RuntimeError, TypeError, KeyError) as exc:
        print(f'[DENIED] Audit recovery: {exc}')
        return False


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task_id')
    parser.add_argument('--base', default='dev')
    parser.add_argument('--simulate', action='store_true')
    recovery = parser.add_mutually_exclusive_group()
    recovery.add_argument('--resume-merge', action='store_true')
    recovery.add_argument('--resume-audit', action='store_true')
    args = parser.parse_args()
    if args.resume_merge:
        sys.exit(0 if resume_merge(args.task_id, args.base) else 1)
    if args.resume_audit:
        sys.exit(0 if resume_audit(args.task_id, args.base, args.simulate) else 1)
    sys.exit(0 if run_pipeline(args.task_id, args.base, args.simulate) else 1)
