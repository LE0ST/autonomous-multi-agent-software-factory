"""
adapters/gemini_adapter.py - Adapter for Gemini (Architect, Triage, Security Filter, Logic Audit)
with dual support: live API and Mock/Simulation mode for test execution without token consumption.
"""

import os
import json
import requests
from typing import Optional
from .contracts import TriageOutput, SecurityFilterOutput, LogicAuditOutput
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

class GeminiAdapter:
    def __init__(self, model: str = "gemini-1.5-pro", api_key: Optional[str] = None):
        self.model = model
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.is_simulation = not bool(self.api_key)

    @retry_with_backoff(max_retries=3, initial_delay=1.0)
    def generate_spec(self, task_id: str, title: str, description: str) -> str:
        """Architect Role: Generate structured SPEC.md contract."""
        if self.is_simulation:
            return (
                f"# {task_id}: {title}\n\n"
                f"## 1. Scope and Boundaries\n"
                f"- Allowed files:\n"
                f"  - `src/{task_id.lower()}/main.py`\n"
                f"  - `tests/test_{task_id.lower()}.py`\n"
                f"- Strictly forbidden files:\n"
                f"  - `pyproject.toml`\n"
                f"  - `.env`\n\n"
                f"## 2. Acceptance Criteria (AC)\n"
                f"- [AC-01] {description}\n\n"
                f"## 3. Security Invariants (SEC)\n"
                f"- [SEC-01] Validate input against injections and do not leak secrets.\n\n"
                f"## 4. Required Test Matrix (TEST)\n"
                f"- [TEST-01] Test core functionality and security (Covers: [AC-01], [SEC-01])\n"
            )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json"
        }
        prompt = (
            f"Act as Software Architect. Generate the specification for '{task_id}: {title}'.\n"
            f"Description: {description}.\n"
            f"You must strictly include the 4 sections:\n"
            f"## 1. Scope and Boundaries\n## 2. Acceptance Criteria\n## 3. Security Invariants\n## 4. Required Test Matrix\n"
            f"All [AC-xx] and [SEC-xx] must be mapped in the Matrix to [TEST-xx]."
        )
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

    @retry_with_backoff(max_retries=3, initial_delay=1.0)
    def triage_failure(self, failure_payload: dict) -> TriageOutput:
        """Triage Role: Analyze test failure and determine root cause."""
        if self.is_simulation:
            return TriageOutput(
                failing_test="tests/test_feature.py::test_run",
                project_file="src/feature/main.py",
                line_number=42,
                expected="Return True with valid token",
                received="Return False",
                root_cause="Incorrect string comparison instead of constant-time digest comparison"
            )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json"
        }
        prompt = (
            "Act as Senior Test Failure Triage Engineer. Analyze this pytest failure report.\n"
            "You must respond EXCLUSIVELY with valid JSON matching this exact schema:\n"
            "{\n"
            '  "failing_test": "path/to/test.py::test_name",\n'
            '  "project_file": "path/to/file_with_error.py",\n'
            '  "line_number": 123,\n'
            '  "expected": "expected behavior or value",\n'
            '  "received": "received behavior or value",\n'
            '  "root_cause": "clear textual explanation of the root cause"\n'
            "}\n\n"
            f"Failure report:\n{json.dumps(failure_payload, indent=2)}"
        )
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
        cleaned = clean_json_text(raw_text)
        parsed = json.loads(cleaned, strict=False)
        return TriageOutput(**parsed)

    @retry_with_backoff(max_retries=3, initial_delay=1.0)
    def filter_security_finding(self, finding: dict) -> SecurityFilterOutput:
        """Security Filter Role: Discriminate between false and true positive SAST findings."""
        if self.is_simulation:
            return SecurityFilterOutput(
                finding_id=finding.get("check_id", "sec-check-1"),
                classification="FALSE_POSITIVE",
                justification="The analyzed value is a safe internal mock and not an exposed production credential."
            )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json"
        }
        prompt = (
            "Act as AppSec Engineer. Classify this SAST finding.\n"
            "You must respond EXCLUSIVELY with valid JSON matching this exact schema:\n"
            "{\n"
            '  "finding_id": "finding_identifier",\n'
            '  "classification": "TRUE_POSITIVE" | "FALSE_POSITIVE" | "UNCERTAIN",\n'
            '  "justification": "technical analysis of the classification"\n'
            "}\n\n"
            f"SAST Finding:\n{json.dumps(finding, indent=2)}"
        )
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
        cleaned = clean_json_text(raw_text)
        parsed = json.loads(cleaned, strict=False)
        return SecurityFilterOutput(**parsed)

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

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json"
        }
        prompt = (
            "Act as Principal Security Auditor. Evaluate whether the code violates [SEC-xx] invariants from the spec.\n"
            "You must respond EXCLUSIVELY with valid JSON matching this schema:\n"
            "{\n"
            '  "status": "PASS" | "FAIL" | "UNCERTAIN",\n'
            '  "violated_invariants": ["SEC-xx"],\n'
            '  "exploit_poc": null | "exploit code",\n'
            '  "justification": "detailed analysis"\n'
            "}\n\n"
            f"Spec:\n{spec_content}\n\nImplemented Diff:\n{code_diff}"
        )
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, headers=headers, timeout=45)
        resp.raise_for_status()
        data = resp.json()
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
        cleaned = clean_json_text(raw_text)
        parsed = json.loads(cleaned, strict=False)
        return LogicAuditOutput(**parsed)

