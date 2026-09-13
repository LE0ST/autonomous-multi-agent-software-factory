"""
adapters/glm_adapter.py - Adaptador para GLM (Logic Security Audit)
con soporte dual: API real y Modo Simulación/Mock para auditoría sin consumo de tokens.
"""

import os
import json
import requests
from typing import Optional
from .contracts import LogicAuditOutput
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

class GLMAdapter:
    def __init__(self, model: str = "glm-4", api_key: Optional[str] = None):
        self.model = model
        self.api_key = api_key or os.getenv("GLM_API_KEY")
        self.is_simulation = not bool(self.api_key)

    @retry_with_backoff(max_retries=3, initial_delay=1.0)
    def audit_logic_and_security(
        self,
        spec_content: str,
        code_diff: str
    ) -> LogicAuditOutput:
        """Rol Logic Security: Audita violaciones de invariantes [SEC-xx] y fallos de lógica."""
        if self.is_simulation:
            # La simulación NUNCA finge un PASS real para evitar falsas aprobaciones de seguridad
            return LogicAuditOutput(
                status="SIMULATED",
                violated_invariants=[],
                exploit_poc=None,
                justification="Auditoría simulada en entorno de pruebas local. No representa una validación real de producción."
            )

        url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "Actúa como Principal Security Auditor. Evalúa si el código viola invariantes [SEC-xx] de la spec.\n"
                    "Debes responder EXCLUSIVAMENTE un JSON válido con este esquema:\n"
                    "{\n"
                    '  "status": "PASS" | "FAIL" | "UNCERTAIN",\n'
                    '  "violated_invariants": ["SEC-xx"],\n'
                    '  "exploit_poc": null | "código de exploit",\n'
                    '  "justification": "análisis detallado"\n'
                    "}"
                )
            },
            {"role": "user", "content": f"Spec:\n{spec_content}\n\nDiff implementado:\n{code_diff}"}
        ]
        resp = requests.post(url, json={"model": self.model, "messages": messages}, headers=headers, timeout=45)
        resp.raise_for_status()
        raw_text = resp.json()["choices"][0]["message"]["content"]
        cleaned = clean_json_text(raw_text)
        parsed = json.loads(cleaned, strict=False)
        return LogicAuditOutput(**parsed)
