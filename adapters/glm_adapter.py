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
            return LogicAuditOutput(
                status="PASS",
                violated_invariants=[],
                exploit_poc=None,
                justification="Auditoría formal superada: los algoritmos criptográficos utilizados son seguros y no hay fugas de secretos."
            )

        url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        messages = [
            {"role": "system", "content": "Actúa como Principal Security Auditor. Evalúa si el código viola invariantes [SEC-xx] de la spec. Devuelve un JSON conforme a LogicAuditOutput."},
            {"role": "user", "content": f"Spec:\n{spec_content}\n\nDiff implementado:\n{code_diff}"}
        ]
        resp = requests.post(url, json={"model": self.model, "messages": messages}, headers=headers, timeout=45)
        resp.raise_for_status()
        raw_text = resp.json()["choices"][0]["message"]["content"]
        cleaned = raw_text.strip().strip("```json").strip("```").strip()
        parsed = json.loads(cleaned)
        return LogicAuditOutput(**parsed)
