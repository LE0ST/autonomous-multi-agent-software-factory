#!/usr/bin/env python3
"""
scripts/diff_gate.py - Enforzamiento duro de fronteras de código (Boundary Enforcement).
Verifica:
1. modified_files ⊆ allowed_files (definidos en la SPEC)
2. forbidden_files ∩ modified_files == ∅
3. Ningún archivo crítico de infraestructura raíz modificado (pyproject.toml, .env, orchestrator/, scripts/, RULES.md)
Exit 0 si cumple, Exit 1 si hay violaciones (vuelca a orchestrator/payloads/diff_violation.json).
"""

import re
import sys
import json
import fnmatch
import subprocess
from pathlib import Path

PROTECTED_ROOT_PATTERNS = [
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    ".env*",
    ".gitignore",
    ".semgrepignore",
    "RULES.md",
    "orchestrator/**",
    "scripts/**",
    "specs/TEMPLATE.md"
]

def normalize_path(p: str) -> str:
    return p.replace("\\", "/").strip().lstrip("./")

def parse_spec_boundaries(spec_path: Path) -> tuple[list[str], list[str]]:
    if not spec_path.exists():
        return [], []
    
    content = spec_path.read_text(encoding="utf-8")
    
    # Extraer sección 1. Alcance y Fronteras
    sec1_match = re.search(
        r"##\s+1\.\s+Alcance y Fronteras(.*?)(?=##\s+2\.\s+Criterios de Aceptación|$)",
        content,
        re.DOTALL | re.IGNORECASE
    )
    if not sec1_match:
        return [], []
        
    sec1_text = sec1_match.group(1)
    
    # Extraer permitidos
    allowed = []
    allowed_match = re.search(
        r"-\s+Archivos permitidos:(.*?)(?=-\s+Archivos estrictamente prohibidos:|$)",
        sec1_text,
        re.DOTALL | re.IGNORECASE
    )
    if allowed_match:
        for line in allowed_match.group(1).splitlines():
            # Buscar patrones en backticks o texto de viñeta
            m = re.findall(r"`([^`]+)`", line)
            if m:
                allowed.extend([normalize_path(x) for x in m])
            elif line.strip().startswith("-") or line.strip().startswith("*"):
                cleaned = normalize_path(line.strip().lstrip("-* \t"))
                if cleaned:
                    allowed.append(cleaned)

    # Extraer prohibidos
    forbidden = []
    forbidden_match = re.search(
        r"-\s+Archivos estrictamente prohibidos:(.*)",
        sec1_text,
        re.DOTALL | re.IGNORECASE
    )
    if forbidden_match:
        for line in forbidden_match.group(1).splitlines():
            m = re.findall(r"`([^`]+)`", line)
            if m:
                forbidden.extend([normalize_path(x) for x in m])
            elif line.strip().startswith("-") or line.strip().startswith("*"):
                cleaned = normalize_path(line.strip().lstrip("-* \t"))
                if cleaned:
                    forbidden.append(cleaned)
                    
    return allowed, forbidden

def get_modified_files(worktree_dir: Path, base_branch: str = "dev") -> list[str]:
    # Archivos modificados o agregados respecto a la rama base
    diff_res = subprocess.run(
        ["git", "diff", "--name-only", f"{base_branch}...HEAD"],
        cwd=worktree_dir,
        capture_output=True,
        text=True
    )
    
    # Si HEAD y base_branch no tienen ancestro o falla el triple punto, probar diff directo
    if diff_res.returncode != 0 or not diff_res.stdout.strip():
        diff_res = subprocess.run(
            ["git", "diff", "--name-only", base_branch],
            cwd=worktree_dir,
            capture_output=True,
            text=True
        )

    # También considerar cambios en el árbol de trabajo actual (staged o unstaged)
    status_res = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=worktree_dir,
        capture_output=True,
        text=True
    )
    
    modified = set()
    if diff_res.stdout:
        for line in diff_res.stdout.splitlines():
            if line.strip():
                modified.add(normalize_path(line))
                
    if status_res.stdout:
        for line in status_res.stdout.splitlines():
            # Formato porcelain: XY PATH o XY "PATH"
            parts = line.strip().split(maxsplit=1)
            if len(parts) == 2:
                raw_p = parts[1].strip().strip('"')
                if " -> " in raw_p: # Rename
                    raw_p = raw_p.split(" -> ")[1].strip().strip('"')
                modified.add(normalize_path(raw_p))

    # Filtrar archivos del worktree que no son de código (ej: .git)
    return [p for p in sorted(modified) if not p.startswith(".git/")]

def matches_any_pattern(file_path: str, patterns: list[str]) -> bool:
    for pat in patterns:
        if fnmatch.fnmatch(file_path, pat) or file_path == pat:
            return True
        if pat.endswith("/") and file_path.startswith(pat):
            return True
    return False

def validate_diff(worktree_dir: Path, spec_path: Path, base_branch: str = "dev") -> tuple[bool, dict]:
    allowed, forbidden = parse_spec_boundaries(spec_path)
    modified = get_modified_files(worktree_dir, base_branch)
    
    violations = []
    
    for f in modified:
        # Excluir bytecode compilado generado en runtime por el intérprete/pytest
        if f.endswith(".pyc") or "/__pycache__/" in f or f.startswith("__pycache__/"):
            continue
            
        # 1. Regla de protección de infraestructura raíz
        if matches_any_pattern(f, PROTECTED_ROOT_PATTERNS):
            violations.append(f"Archivo de infraestructura o gobernanza protegido modificado: '{f}'")
            continue
            
        # 2. Regla de archivos prohibidos
        if matches_any_pattern(f, forbidden):
            violations.append(f"Archivo estrictamente prohibido por la SPEC modificado: '{f}'")
            continue
            
        # 3. Regla de archivos permitidos
        if allowed and not matches_any_pattern(f, allowed):
            violations.append(f"Archivo fuera del alcance permitido modificado: '{f}'")
            
    payload = {
        "status": "PASS" if not violations else "FAIL",
        "modified_files": modified,
        "allowed_files": allowed,
        "forbidden_files": forbidden,
        "violations": violations
    }
    
    return len(violations) == 0, payload

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Enforzador duro de fronteras de código")
    parser.add_argument("--worktree", default=".", help="Directorio del worktree o repositorio")
    parser.add_argument("--spec", required=True, help="Ruta al archivo SPEC.md")
    parser.add_argument("--base", default="dev", help="Rama base de comparación")
    args = parser.parse_args()
    
    wt_dir = Path(args.worktree).resolve()
    sp_path = Path(args.spec).resolve()
    
    passed, report = validate_diff(wt_dir, sp_path, args.base)
    
    payloads_dir = Path(".orchestrator/payloads") if Path(".orchestrator").exists() else Path("orchestrator/payloads")
    payloads_dir.mkdir(parents=True, exist_ok=True)
    violation_file = payloads_dir / "diff_violation.json"
    
    if not passed:
        violation_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[FAIL] Diff Gate violado. Se encontraron {len(report['violations'])} infracciones:")
        for v in report["violations"]:
            print(f"  - {v}")
        sys.exit(1)
        
    print(f"[PASS] Diff Gate superado. {len(report['modified_files'])} archivos dentro del alcance permitido.")
    sys.exit(0)
