#!/usr/bin/env python3
"""
scripts/worktree_manager.py - Gestor defensivo de Git Worktrees con soporte robusto para Windows.
Maneja bloqueos de archivo (WinError 5 / PermissionError) mediante reintentos y desmarcado de solo-lectura.
"""

import os
import sys
import time
import stat
import shutil
import subprocess
from pathlib import Path

def _remove_readonly(func, path, excinfo):
    """Callback de error para shutil.rmtree: desmarca atributos de solo lectura en Windows."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass

def get_worktree_path(repo_dir: Path, task_id: str) -> Path:
    return repo_dir / ".worktrees" / f"wt_{task_id}"

def create_worktree(repo_dir: Path, task_id: str, base_branch: str = "dev") -> tuple[bool, str]:
    branch_name = f"task/{task_id}"
    target_path = get_worktree_path(repo_dir, task_id)
    
    if target_path.exists():
        remove_worktree(repo_dir, task_id)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Verificar si la rama task/<task_id> ya existe
    check_branch = subprocess.run(
        ["git", "branch", "--list", branch_name],
        cwd=repo_dir,
        capture_output=True,
        text=True
    )
    
    if branch_name in check_branch.stdout:
        # Si ya existe, añadir worktree reutilizando la rama
        cmd = ["git", "worktree", "add", str(target_path), branch_name]
    else:
        # Si no existe, crear rama desde base_branch
        cmd = ["git", "worktree", "add", "-b", branch_name, str(target_path), base_branch]
        
    res = subprocess.run(cmd, cwd=repo_dir, capture_output=True, text=True)
    if res.returncode == 0:
        return True, str(target_path)
    return False, f"Fallo al crear worktree: {res.stderr.strip() or res.stdout.strip()}"

def remove_worktree(repo_dir: Path, task_id: str, delete_branch: bool = False, max_retries: int = 3) -> tuple[bool, str]:
    target_path = get_worktree_path(repo_dir, task_id)
    branch_name = f"task/{task_id}"
    
    # 1. Intentar desvincular vía git worktree remove
    subprocess.run(
        ["git", "worktree", "remove", "--force", str(target_path)],
        cwd=repo_dir,
        capture_output=True,
        text=True
    )
    
    # 2. Si el directorio sigue existiendo (típico bloqueo en Windows), limpieza defensiva con reintentos
    backoff = [0.1, 0.3, 1.0]
    if target_path.exists():
        for attempt in range(max_retries):
            try:
                shutil.rmtree(target_path, onerror=_remove_readonly)
                break
            except (PermissionError, OSError):
                if attempt < len(backoff):
                    time.sleep(backoff[attempt])
                else:
                    time.sleep(1.0)
                    
    # 3. Prune worktrees en git
    subprocess.run(["git", "worktree", "prune"], cwd=repo_dir, capture_output=True, text=True)
    
    # 4. Eliminar rama opcionalmente
    if delete_branch:
        subprocess.run(["git", "branch", "-D", branch_name], cwd=repo_dir, capture_output=True, text=True)
        
    if target_path.exists():
        return False, f"No se pudo eliminar completamente el directorio de worktree {target_path} tras {max_retries} intentos."
        
    return True, f"Worktree para {task_id} eliminado exitosamente."

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso:")
        print("  python scripts/worktree_manager.py create <task_id> [base_branch]")
        print("  python scripts/worktree_manager.py remove <task_id> [--delete-branch]")
        sys.exit(1)
        
    action = sys.argv[1].lower()
    t_id = sys.argv[2]
    repo_root = Path.cwd()
    
    if action == "create":
        b_branch = sys.argv[3] if len(sys.argv) > 3 else "dev"
        success, msg = create_worktree(repo_root, t_id, b_branch)
        print(f"[{'PASS' if success else 'FAIL'}] {msg}")
        sys.exit(0 if success else 1)
    elif action == "remove":
        del_b = "--delete-branch" in sys.argv
        success, msg = remove_worktree(repo_root, t_id, del_b)
        print(f"[{'PASS' if success else 'FAIL'}] {msg}")
        sys.exit(0 if success else 1)
    else:
        print(f"Acción desconocida: {action}")
        sys.exit(1)
