#!/usr/bin/env python3
"""
scripts/merge_gate.py - Puerta de integración atómica con Fast-Forward merge a la rama base (dev).
Valida que el repositorio esté limpio y ejecuta:
  git checkout <base_branch> && git merge --ff-only task/<task_id>
Exit 0 en éxito, Exit 1 si no es posible el fast-forward o hay cambios sin commitear.
"""

import sys
import subprocess
from pathlib import Path

def is_repo_clean(repo_dir: Path) -> tuple[bool, str]:
    res = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_dir,
        capture_output=True,
        text=True
    )
    clean = res.returncode == 0 and res.stdout.strip() == ""
    return clean, res.stdout.strip()

def execute_fast_forward_merge(repo_dir: Path, task_id: str, base_branch: str = "dev") -> tuple[bool, str]:
    task_branch = f"task/{task_id}"
    
    # 1. Comprobar que no haya cambios sucios en el árbol principal
    clean, dirty_files = is_repo_clean(repo_dir)
    if not clean:
        return False, (
            f"El repositorio principal tiene modificaciones no commiteadas. Merge abortado.\n"
            f"Archivos detectados:\n{dirty_files}"
        )

    # 2. Checkout a la rama base
    co_res = subprocess.run(
        ["git", "checkout", base_branch],
        cwd=repo_dir,
        capture_output=True,
        text=True
    )
    if co_res.returncode != 0:
        return False, f"Fallo al hacer checkout a la rama '{base_branch}': {co_res.stderr.strip()}"

    # 3. Comprobar si base_branch es ancestro directo (condición para Fast-Forward)
    ancestor_check = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base_branch, task_branch],
        cwd=repo_dir,
        capture_output=True,
        text=True
    )
    if ancestor_check.returncode != 0:
        return False, (
            f"DIVERGENCIA DE ÁRBOL DETECTADA: La rama '{base_branch}' recibió commits manuales "
            f"mientras el orquestador trabajaba en '{task_branch}'.\n"
            f"Para resolverlo de forma segura:\n"
            f"  git checkout {task_branch}\n"
            f"  git rebase {base_branch}\n"
            f"  git checkout {base_branch}\n"
            f"  python scripts/merge_gate.py {task_id} {base_branch}"
        )

    # 4. Ejecutar merge Fast-Forward atómico
    merge_res = subprocess.run(
        ["git", "merge", "--ff-only", task_branch],
        cwd=repo_dir,
        capture_output=True,
        text=True
    )
    if merge_res.returncode != 0:
        return False, f"El merge Fast-Forward falló: {merge_res.stderr.strip()}"

    return True, f"Fusión Fast-Forward exitosa de '{task_branch}' hacia '{base_branch}'."

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python scripts/merge_gate.py <task_id> [base_branch]")
        sys.exit(1)
        
    t_id = sys.argv[1]
    b_branch = sys.argv[2] if len(sys.argv) > 2 else "dev"
    root_dir = Path.cwd()
    
    passed, msg = execute_fast_forward_merge(root_dir, t_id, b_branch)
    print(f"[{'PASS' if passed else 'FAIL'}] Merge Gate: {msg}")
    sys.exit(0 if passed else 1)
