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
    
    # 1. Validar presencia de secciones requeridas con flexibilidad (#, ##, ###, puntos, paréntesis, acentos)
    required_sections = [
        (r"#+\s*1[\.\):\-]?\s*Alcance\s+y\s+Fronteras", "1. Alcance y Fronteras"),
        (r"#+\s*2[\.\):\-]?\s*Criterios\s+de\s+Aceptaci[oó]n", "2. Criterios de Aceptación"),
        (r"#+\s*3[\.\):\-]?\s*Invariantes\s+de\s+Seguridad", "3. Invariantes de Seguridad"),
        (r"#+\s*4[\.\):\-]?\s*Matriz\s+de\s+Pruebas(?:\s+Requeridas)?", "4. Matriz de Pruebas Requeridas")
    ]
    for pattern, name in required_sections:
        if not re.search(pattern, content, re.IGNORECASE):
            return False, f"Sección obligatoria faltante: '{name}'"

    # 2. Extraer identificadores con flexibilidad en espacios y formato de número
    raw_acs = re.findall(r"\[\s*AC[_-]?(\d+)\s*\]", content, re.IGNORECASE)
    raw_secs = re.findall(r"\[\s*SEC[_-]?(\d+)\s*\]", content, re.IGNORECASE)
    raw_tests = re.findall(r"\[\s*TEST[_-]?(\d+)\s*\]", content, re.IGNORECASE)

    # Normalizar canónicamente a AC-01, SEC-01, TEST-01
    acs = {f"AC-{int(n):02d}" for n in raw_acs}
    secs = {f"SEC-{int(n):02d}" for n in raw_secs}
    tests = {f"TEST-{int(n):02d}" for n in raw_tests}

    if not acs:
        return False, "Debe existir al menos un criterio de aceptación [AC-xx]."
    if not secs:
        return False, "Debe existir al menos un invariante de seguridad [SEC-xx]."
    if not tests:
        return False, "Debe existir al menos una prueba requerida [TEST-xx]."

    # 3. Aislar la sección 4 (Matriz de Pruebas)
    matrix_split = re.split(r"#+\s*4[\.\):\-]?\s*Matriz\s+de\s+Pruebas", content, flags=re.IGNORECASE)
    if len(matrix_split) < 2:
        return False, "No se pudo aislar el contenido de la Matriz de Pruebas Requeridas."
        
    matrix_section = matrix_split[-1]
    
    # 4. Validar trazabilidad en la matriz (soporta tablas, listas con -, *, o texto libre)
    missing_ac = []
    for ac in sorted(acs):
        num = int(ac.split("-")[1])
        # Busca variantes: [AC-01], [AC-1], [ AC-01 ], **[AC-01]**, AC-01, AC-1
        pattern = rf"(?:\[\s*|\b)AC[_-]?0*{num}(?:\s*\]|\b)"
        if not re.search(pattern, matrix_section, re.IGNORECASE):
            missing_ac.append(ac)
            
    if missing_ac:
        missing_ac_str = ", ".join(f"[{ac}]" for ac in missing_ac)
        return False, f"Los siguientes Criterios de Aceptación no tienen prueba asociada en la Matriz: {missing_ac_str}"

    missing_sec = []
    for sec in sorted(secs):
        num = int(sec.split("-")[1])
        pattern = rf"(?:\[\s*|\b)SEC[_-]?0*{num}(?:\s*\]|\b)"
        if not re.search(pattern, matrix_section, re.IGNORECASE):
            missing_sec.append(sec)
            
    if missing_sec:
        missing_sec_str = ", ".join(f"[{sec}]" for sec in missing_sec)
        return False, f"Los siguientes Invariantes de Seguridad no tienen prueba asociada en la Matriz: {missing_sec_str}"

    return True, f"Spec validada exitosamente. ACs: {len(acs)}, SECs: {len(secs)}, TESTs: {len(tests)}"

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python scripts/spec_gate.py <ruta_spec.md>")
        sys.exit(1)
    
    valid, msg = validate_spec(sys.argv[1])
    print(f"[{'PASS' if valid else 'FAIL'}] {msg}")
    sys.exit(0 if valid else 1)
