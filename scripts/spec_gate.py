#!/usr/bin/env python3
"""
scripts/spec_gate.py - Validador determinista de contratos de especificación SPEC.md.
Comprueba secciones requeridas, identificadores [AC-xx], [SEC-xx], [TEST-xx] y trazabilidad 1:1 en la Matriz.
Exit 0 si es válida, Exit 1 si falla.
"""

import re
import sys
from pathlib import Path

def validate_spec(spec_path: str | Path) -> tuple[bool, str]:
    path = Path(spec_path)
    if not path.exists():
        return False, f"El archivo de especificación '{spec_path}' no existe."
    
    content = path.read_text(encoding="utf-8")
    
    # 1. Validar presencia de secciones requeridas
    required_sections = [
        (r"##\s+1\.\s+Alcance y Fronteras", "1. Alcance y Fronteras"),
        (r"##\s+2\.\s+Criterios de Aceptación", "2. Criterios de Aceptación"),
        (r"##\s+3\.\s+Invariantes de Seguridad", "3. Invariantes de Seguridad"),
        (r"##\s+4\.\s+Matriz de Pruebas Requeridas", "4. Matriz de Pruebas Requeridas")
    ]
    for pattern, name in required_sections:
        if not re.search(pattern, content, re.IGNORECASE):
            return False, f"Sección obligatoria faltante: '{name}'"

    # 2. Extraer identificadores
    acs = set(re.findall(r"\[AC-\d+\]", content))
    secs = set(re.findall(r"\[SEC-\d+\]", content))
    tests = set(re.findall(r"\[TEST-\d+\]", content))

    if not acs:
        return False, "Debe existir al menos un criterio de aceptación [AC-xx]."
    if not secs:
        return False, "Debe existir al menos un invariante de seguridad [SEC-xx]."
    if not tests:
        return False, "Debe existir al menos una prueba requerida [TEST-xx]."

    # 3. Validar trazabilidad en la matriz de pruebas (Sección 4)
    matrix_split = re.split(r"##\s+4\.\s+Matriz de Pruebas Requeridas", content, flags=re.IGNORECASE)
    if len(matrix_split) < 2:
        return False, "No se pudo aislar el contenido de la Matriz de Pruebas Requeridas."
        
    matrix_section = matrix_split[-1]
    
    missing_ac = [ac for ac in sorted(acs) if ac not in matrix_section]
    if missing_ac:
        return False, f"Los siguientes Criterios de Aceptación no tienen prueba asociada en la Matriz: {', '.join(missing_ac)}"

    missing_sec = [sec for sec in sorted(secs) if sec not in matrix_section]
    if missing_sec:
        return False, f"Los siguientes Invariantes de Seguridad no tienen prueba asociada en la Matriz: {', '.join(missing_sec)}"

    return True, f"Spec validada exitosamente. ACs: {len(acs)}, SECs: {len(secs)}, TESTs: {len(tests)}"

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python scripts/spec_gate.py <ruta_spec.md>")
        sys.exit(1)
    
    valid, msg = validate_spec(sys.argv[1])
    print(f"[{'PASS' if valid else 'FAIL'}] {msg}")
    sys.exit(0 if valid else 1)
