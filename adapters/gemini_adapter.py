"""
adapters/gemini_adapter.py - Adaptador para Gemini (Architect, Triage, Security Filter)
con soporte dual: API real y Modo Simulación/Mock para pruebas sin consumo de tokens.
"""

import os
import json
import requests
from typing import Optional
from .contracts import TriageOutput, SecurityFilterOutput
from .network_retry import retry_with_backoff

def clean_json_text(raw_text: str) -> str:
    """Extrae JSON limpio eliminando de forma segura los bloques markdown."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:].strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:].strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()
    return cleaned

class GeminiAdapter:
    def __init__(self, model: str = "gemini-1.5-pro", api_key: Optional[str] = None):
        self.model = model
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.is_simulation = not bool(self.api_key)

    @retry_with_backoff(max_retries=3, initial_delay=1.0)
    def generate_spec(self, task_id: str, title: str, description: str) -> str:
        """Rol Architect: Genera el contrato SPEC.md estructurado."""
        if self.is_simulation:
            return (
                f"# {task_id}: {title}\n\n"
                f"## 1. Alcance y Fronteras\n"
                f"- Archivos permitidos:\n"
                f"  - `src/{task_id.lower()}/main.py`\n"
                f"  - `tests/test_{task_id.lower()}.py`\n"
                f"- Archivos estrictamente prohibidos:\n"
                f"  - `pyproject.toml`\n"
                f"  - `.env`\n\n"
                f"## 2. Criterios de Aceptación (AC)\n"
                f"- [AC-01] {description}\n\n"
                f"## 3. Invariantes de Seguridad (SEC)\n"
                f"- [SEC-01] Validar entradas contra inyecciones y no exponer secretos.\n\n"
                f"## 4. Matriz de Pruebas Requeridas (TEST)\n"
                f"- [TEST-01] Probar funcionalidad principal y seguridad (Cubre: [AC-01], [SEC-01])\n"
            )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        prompt = (
            f"Actúa como Software Architect. Genera la especificación para '{task_id}: {title}'.\n"
            f"Descripción: {description}.\n"
            f"Debes respetar obligatoriamente las 4 secciones:\n"
            f"## 1. Alcance y Fronteras\n## 2. Criterios de Aceptación\n## 3. Invariantes de Seguridad\n## 4. Matriz de Pruebas Requeridas\n"
            f"Todos los [AC-xx] y [SEC-xx] deben estar mapeados en la Matriz a [TEST-xx]."
        )
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

    @retry_with_backoff(max_retries=3, initial_delay=1.0)
    def triage_failure(self, failure_payload: dict) -> TriageOutput:
        """Rol Triage: Analiza el fallo de tests y determina causa raíz."""
        if self.is_simulation:
            return TriageOutput(
                failing_test="tests/test_feature.py::test_run",
                project_file="src/feature/main.py",
                line_number=42,
                expected="Retorno True con token válido",
                received="Retorno False",
                root_cause="Comparación incorrecta de strings en lugar de digest seguro"
            )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        prompt = (
            f"Analiza este reporte de fallo de pruebas y devuelve un JSON conforme a TriageOutput:\n"
            f"{json.dumps(failure_payload, indent=2)}"
        )
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
        cleaned = clean_json_text(raw_text)
        parsed = json.loads(cleaned, strict=False)
        return TriageOutput(**parsed)

    @retry_with_backoff(max_retries=3, initial_delay=1.0)
    def filter_security_finding(self, finding: dict) -> SecurityFilterOutput:
        """Rol Security Filter: Discrimina entre falsos y verdaderos positivos de SAST."""
        if self.is_simulation:
            return SecurityFilterOutput(
                finding_id=finding.get("check_id", "sec-check-1"),
                classification="FALSE_POSITIVE",
                justification="El valor verificado es un mock interno seguro y no una clave productiva expuesta."
            )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        prompt = (
            f"Clasifica este hallazgo SAST como TRUE_POSITIVE, FALSE_POSITIVE o UNCERTAIN:\n"
            f"{json.dumps(finding, indent=2)}"
        )
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
        cleaned = clean_json_text(raw_text)
        parsed = json.loads(cleaned, strict=False)
        return SecurityFilterOutput(**parsed)
