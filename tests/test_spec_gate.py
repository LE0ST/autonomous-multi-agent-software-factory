import pytest
from pathlib import Path
from scripts.spec_gate import validate_spec

def test_valid_spec(tmp_path):
    spec_content = """# TASK-100: Valid Spec

## 1. Alcance y Fronteras
- Archivos permitidos:
  - `src/main.py`
- Archivos estrictamente prohibidos:
  - `pyproject.toml`

## 2. Criterios de Aceptación (AC)
- [AC-01] Primer criterio.
- [AC-02] Segundo criterio.

## 3. Invariantes de Seguridad (SEC)
- [SEC-01] Primer invariante.

## 4. Matriz de Pruebas Requeridas (TEST)
- [TEST-01] Prueba para [AC-01] y [SEC-01]
- [TEST-02] Prueba para [AC-02]
"""
    spec_file = tmp_path / "VALID_SPEC.md"
    spec_file.write_text(spec_content, encoding="utf-8")
    
    valid, msg = validate_spec(spec_file)
    assert valid is True
    assert "ACs: 2, SECs: 1, TESTs: 2" in msg

def test_missing_section(tmp_path):
    spec_content = """# TASK-101: Incomplete Spec

## 1. Alcance y Fronteras
- Archivos permitidos: `src/main.py`

## 2. Criterios de Aceptación (AC)
- [AC-01] Criterio uno.

## 4. Matriz de Pruebas Requeridas (TEST)
- [TEST-01] Test para [AC-01]
"""
    spec_file = tmp_path / "NO_SEC_SECTION.md"
    spec_file.write_text(spec_content, encoding="utf-8")
    
    valid, msg = validate_spec(spec_file)
    assert valid is False
    assert "Sección obligatoria faltante" in msg

def test_uncovered_acceptance_criteria(tmp_path):
    spec_content = """# TASK-102: Missing Coverage

## 1. Alcance y Fronteras
- Archivos permitidos: `src/main.py`

## 2. Criterios de Aceptación (AC)
- [AC-01] Cubierto.
- [AC-02] Sin cobertura en matriz.

## 3. Invariantes de Seguridad (SEC)
- [SEC-01] Invariante cubierto.

## 4. Matriz de Pruebas Requeridas (TEST)
- [TEST-01] Cubre [AC-01] y [SEC-01]
"""
    spec_file = tmp_path / "UNCOVERED.md"
    spec_file.write_text(spec_content, encoding="utf-8")
    
    valid, msg = validate_spec(spec_file)
    assert valid is False
    assert "[AC-02]" in msg

def test_uncovered_security_invariant(tmp_path):
    spec_content = """# TASK-103: Missing Sec Coverage

## 1. Alcance y Fronteras
- Archivos permitidos: `src/main.py`

## 2. Criterios de Aceptación (AC)
- [AC-01] Cubierto.

## 3. Invariantes de Seguridad (SEC)
- [SEC-01] Invariante cubierto.
- [SEC-02] Invariante sin cubrir.

## 4. Matriz de Pruebas Requeridas (TEST)
- [TEST-01] Cubre [AC-01] y [SEC-01]
"""
    spec_file = tmp_path / "UNCOVERED_SEC.md"
    spec_file.write_text(spec_content, encoding="utf-8")
    
    valid, msg = validate_spec(spec_file)
    assert valid is False
    assert "[SEC-02]" in msg

def test_canonical_task_001_file():
    spec_file = Path("specs/TASK-001.md")
    assert spec_file.exists()
    valid, msg = validate_spec(spec_file)
    assert valid is True, f"TASK-001.md falló la validación: {msg}"

def test_permissive_format_table_and_spaces(tmp_path):
    spec_content = """# TASK-104: Permissive Format

### 1) Alcance y Fronteras
* Archivos permitidos:
  * `src/main.py`

### 2) Criterios de Aceptacion
* [ AC-01 ] Primer criterio con espacios.
* [AC_02] Segundo criterio con guion bajo.

### 3) Invariantes de Seguridad
* [ SEC-01 ] Invariante con espacios.

### 4) Matriz de Pruebas
| Test ID | Descripcion | Cobertura |
| :--- | :--- | :--- |
| [ TEST-01 ] | Prueba principal | [AC-01], [SEC-01] |
| [TEST-02] | Prueba secundaria | **[AC-02]** |
"""
    spec_file = tmp_path / "PERMISSIVE_SPEC.md"
    spec_file.write_text(spec_content, encoding="utf-8")
    
    valid, msg = validate_spec(spec_file)
    assert valid is True, f"Spec con formato permisivo falló: {msg}"
    assert "ACs: 2, SECs: 1, TESTs: 2" in msg
