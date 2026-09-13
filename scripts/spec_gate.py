#!/usr/bin/env python3
"""
scripts/spec_gate.py - Deterministic specification contract validator for SPEC.md.
Checks required sections, identifiers [AC-xx], [SEC-xx], [TEST-xx], and 1:1 traceability in the Matrix.
Exit 0 if valid, Exit 1 if validation fails.
"""

import re
import sys
from pathlib import Path

def validate_spec(spec_path: str | Path) -> tuple[bool, str]:
    path = Path(spec_path)
    if not path.exists():
        return False, f"Specification file '{spec_path}' does not exist."
    
    content = path.read_text(encoding="utf-8")
    
    # 1. Validate required sections with flexibility (#, ##, ###, dots, parens, English/Spanish)
    required_sections = [
        (r"#+\s*1[\.\):\-]?\s*(?:Alcance\s+y\s+Fronteras|Scope\s+and\s+Boundaries)", "1. Scope and Boundaries"),
        (r"#+\s*2[\.\):\-]?\s*(?:Criterios\s+de\s+Aceptaci[oó]n|Acceptance\s+Criteria)", "2. Acceptance Criteria"),
        (r"#+\s*3[\.\):\-]?\s*(?:Invariantes\s+de\s+Seguridad|Security\s+Invariants)", "3. Security Invariants"),
        (r"#+\s*4[\.\):\-]?\s*(?:Matriz\s+de\s+Pruebas(?:\s+Requeridas)?|Required\s+Test\s+Matrix|Test\s+Matrix)", "4. Test Matrix")
    ]
    for pattern, name in required_sections:
        if not re.search(pattern, content, re.IGNORECASE):
            return False, f"Missing required section: '{name}'"

    # 2. Extract identifiers with flexibility in whitespace and number formatting
    raw_acs = re.findall(r"\[\s*AC[_-]?(\d+)\s*\]", content, re.IGNORECASE)
    raw_secs = re.findall(r"\[\s*SEC[_-]?(\d+)\s*\]", content, re.IGNORECASE)
    raw_tests = re.findall(r"\[\s*TEST[_-]?(\d+)\s*\]", content, re.IGNORECASE)

    # Canonically normalize to AC-01, SEC-01, TEST-01
    acs = {f"AC-{int(n):02d}" for n in raw_acs}
    secs = {f"SEC-{int(n):02d}" for n in raw_secs}
    tests = {f"TEST-{int(n):02d}" for n in raw_tests}

    if not acs:
        return False, "At least one acceptance criterion [AC-xx] must be defined."
    if not secs:
        return False, "At least one security invariant [SEC-xx] must be defined."
    if not tests:
        return False, "At least one required test [TEST-xx] must be defined."

    # 3. Isolate Section 4 (Test Matrix)
    matrix_split = re.split(
        r"#+\s*4[\.\):\-]?\s*(?:Matriz\s+de\s+Pruebas|Test\s+Matrix|Required\s+Test\s+Matrix)",
        content,
        flags=re.IGNORECASE
    )
    if len(matrix_split) < 2:
        return False, "Unable to isolate Test Matrix section."
        
    matrix_section = matrix_split[-1]
    
    # 4. Validate traceability in the matrix (supports tables, lists with -, *, or free text)
    missing_ac = []
    for ac in sorted(acs):
        num = int(ac.split("-")[1])
        # Look for variations: [AC-01], [AC-1], [ AC-01 ], **[AC-01]**, AC-01, AC-1
        pattern = rf"(?:\[\s*|\b)AC[_-]?0*{num}(?:\s*\]|\b)"
        if not re.search(pattern, matrix_section, re.IGNORECASE):
            missing_ac.append(ac)
            
    if missing_ac:
        missing_ac_str = ", ".join(f"[{ac}]" for ac in missing_ac)
        return False, f"The following Acceptance Criteria have no associated test in the Matrix: {missing_ac_str}"

    missing_sec = []
    for sec in sorted(secs):
        num = int(sec.split("-")[1])
        pattern = rf"(?:\[\s*|\b)SEC[_-]?0*{num}(?:\s*\]|\b)"
        if not re.search(pattern, matrix_section, re.IGNORECASE):
            missing_sec.append(sec)
            
    if missing_sec:
        missing_sec_str = ", ".join(f"[{sec}]" for sec in missing_sec)
        return False, f"The following Security Invariants have no associated test in the Matrix: {missing_sec_str}"

    return True, f"Spec validated successfully. ACs: {len(acs)}, SECs: {len(secs)}, TESTs: {len(tests)}"

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/spec_gate.py <path_to_spec.md>")
        sys.exit(1)
    
    valid, msg = validate_spec(sys.argv[1])
    print(f"[{'PASS' if valid else 'FAIL'}] {msg}")
    sys.exit(0 if valid else 1)
