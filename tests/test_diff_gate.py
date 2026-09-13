import pytest
from pathlib import Path
from scripts.diff_gate import (
    parse_spec_boundaries,
    matches_any_pattern,
    PROTECTED_ROOT_PATTERNS
)

def test_parse_spec_boundaries(tmp_path):
    spec_content = """# TASK-200: Boundary Test

## 1. Alcance y Fronteras
- Archivos permitidos:
  - `src/services/payment.py`
  - `tests/test_payment.py`
- Archivos estrictamente prohibidos:
  - `src/config/secrets.py`
  - `keys/**`

## 2. Criterios de Aceptación (AC)
- [AC-01] Validar pago.

## 3. Invariantes de Seguridad (SEC)
- [SEC-01] Sin logs de tarjeta.

## 4. Matriz de Pruebas Requeridas (TEST)
- [TEST-01] Cobertura [AC-01], [SEC-01]
"""
    spec_path = tmp_path / "SPEC_BOUNDARY.md"
    spec_path.write_text(spec_content, encoding="utf-8")
    
    allowed, forbidden = parse_spec_boundaries(spec_path)
    assert "src/services/payment.py" in allowed
    assert "tests/test_payment.py" in allowed
    assert "src/config/secrets.py" in forbidden
    assert "keys/**" in forbidden

def test_protected_root_patterns():
    # Proteger pyproject.toml
    assert matches_any_pattern("pyproject.toml", PROTECTED_ROOT_PATTERNS) is True
    # Proteger .env
    assert matches_any_pattern(".env", PROTECTED_ROOT_PATTERNS) is True
    assert matches_any_pattern(".env.production", PROTECTED_ROOT_PATTERNS) is True
    # Proteger orchestrator
    assert matches_any_pattern("orchestrator/state_manager.py", PROTECTED_ROOT_PATTERNS) is True
    assert matches_any_pattern("scripts/diff_gate.py", PROTECTED_ROOT_PATTERNS) is True
    # Archivos regulares de código no deben ser bloqueados por patrones raíz
    assert matches_any_pattern("src/app.py", PROTECTED_ROOT_PATTERNS) is False

def test_forbidden_file_matching():
    forbidden = ["src/config/secrets.py", "keys/**"]
    assert matches_any_pattern("src/config/secrets.py", forbidden) is True
    assert matches_any_pattern("keys/private.pem", forbidden) is True
    assert matches_any_pattern("src/services/payment.py", forbidden) is False
