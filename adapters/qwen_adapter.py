"""
adapters/qwen_adapter.py - Adapter for Qwen (Logic Security Audit)
via official DashScope OpenAI-compatible HTTP endpoint.
"""

import os
import json
import requests
from typing import Optional
from .contracts import LogicAuditOutput
from .network_retry import retry_with_backoff

def clean_json_text(raw_text: str) -> str:
    """Extract clean JSON by safely stripping Markdown code fences."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:].strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:].strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()
    return cleaned

class QwenAdapter:
    DEFAULT_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

    def __init__(
        self,
        model: str = "qwen3.8-flash",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        self.model = model
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")
        self.base_url = (base_url or os.getenv("DASHSCOPE_BASE_URL") or self.DEFAULT_BASE_URL).rstrip("/")
        self.is_simulation = not bool(self.api_key)

    @retry_with_backoff(max_retries=3, initial_delay=1.0)
    def audit_logic_and_security(
        self,
        spec_content: str,
        code_diff: str
    ) -> LogicAuditOutput:
        """Logic Security Role: Audit [SEC-xx] invariant violations and business logic flaws."""
        if self.is_simulation:
            return LogicAuditOutput(
                status="SIMULATED",
                violated_invariants=[],
                exploit_poc=None,
                justification="Simulated audit in local test environment. Does not represent production validation."
            )

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "Act as Principal Security Auditor. Evaluate whether the code violates [SEC-xx] invariants from the spec.\n"
                    "You must respond EXCLUSIVELY with valid JSON matching this schema:\n"
                    "{\n"
                    '  "status": "PASS" | "FAIL" | "UNCERTAIN",\n'
                    '  "violated_invariants": ["SEC-xx"],\n'
                    '  "exploit_poc": null | "exploit code",\n'
                    '  "justification": "detailed analysis"\n'
                    "}"
                )
            },
            {"role": "user", "content": f"Spec:\n{spec_content}\n\nImplemented Diff:\n{code_diff}"}
        ]
        resp = requests.post(
            url,
            json={"model": self.model, "messages": messages},
            headers=headers,
            timeout=45
        )
        resp.raise_for_status()
        raw_text = resp.json()["choices"][0]["message"]["content"]
        cleaned = clean_json_text(raw_text)
        parsed = json.loads(cleaned, strict=False)
        return LogicAuditOutput(**parsed)
