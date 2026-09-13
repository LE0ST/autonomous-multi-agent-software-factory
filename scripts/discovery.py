#!/usr/bin/env python3
"""
scripts/discovery.py - Verificador pre-vuelo determinista para la Autonomous Multi-Agent Software Factory.
Valida:
1. Versión de Python >= 3.10
2. Git inicializado (.git)
3. Existencia de la rama base (dev)
4. Disponibilidad de pytest en el entorno
Exit 0 si todo es válido, Exit 1 si hay errores.
"""

import sys
import subprocess
from pathlib import Path

def check_python_version() -> tuple[bool, str]:
    v = sys.version_info
    if v.major == 3 and v.minor >= 10:
        return True, f"Python {v.major}.{v.minor}.{v.micro} cumple el requisito (>= 3.10)."
    return False, f"Python {v.major}.{v.minor}.{v.micro} no cumple el requisito (se requiere >= 3.10)."

def check_git_initialized(repo_dir: Path) -> tuple[bool, str]:
    res = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=repo_dir,
        capture_output=True,
        text=True
    )
    if res.returncode == 0 and res.stdout.strip() == "true":
        return True, "Repositorio Git inicializado correctamente."
    return False, "El directorio no es un repositorio Git válido (.git no encontrado)."

def check_base_branch(repo_dir: Path, base_branch: str = "dev") -> tuple[bool, str]:
    res = subprocess.run(
        ["git", "branch", "--list", base_branch],
        cwd=repo_dir,
        capture_output=True,
        text=True
    )
    if res.returncode == 0 and base_branch in res.stdout:
        return True, f"Rama base '{base_branch}' verificada."
    return False, f"La rama base '{base_branch}' no existe en el repositorio."

def check_pytest_available() -> tuple[bool, str]:
    try:
        import pytest  # noqa: F401
        return True, f"pytest está instalado ({pytest.__version__})."
    except ImportError:
        return False, "pytest no está disponible en el entorno Python."

def run_discovery(repo_dir: Path, base_branch: str = "dev") -> tuple[bool, list[str]]:
    checks = [
        ("Python Version", check_python_version()),
        ("Git Repository", check_git_initialized(repo_dir)),
        ("Base Branch", check_base_branch(repo_dir, base_branch)),
        ("Pytest Availability", check_pytest_available()),
    ]
    
    all_passed = True
    messages = []
    for name, (passed, msg) in checks:
        status = "PASS" if passed else "FAIL"
        messages.append(f"[{status}] {name}: {msg}")
        if not passed:
            all_passed = False
            
    return all_passed, messages

if __name__ == "__main__":
    repo_path = Path.cwd()
    base_br = "dev"
    if len(sys.argv) > 1:
        base_br = sys.argv[1]
        
    passed, logs = run_discovery(repo_path, base_br)
    for line in logs:
        print(line)
        
    sys.exit(0 if passed else 1)
