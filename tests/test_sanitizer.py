import os
import pytest
import requests
from pathlib import Path
from adapters.sanitizer import sanitize_secret_text, REDACTED_REPLACEMENT
from adapters.network_retry import retry_with_backoff, NetworkTransportError
from orchestrator.state_manager import StateManager

DUMMY_GEMINI_KEY = "dummy-fake-gemini-key-11111"
DUMMY_DEEPSEEK_KEY = "dummy-fake-deepseek-key-22222"
DUMMY_GLM_KEY = "dummy-fake-glm-key-33333"
DUMMY_DASHSCOPE_KEY = "dummy-fake-dashscope-key-44444"

def test_sanitize_secret_text_exact_env_values(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", DUMMY_GEMINI_KEY)
    monkeypatch.setenv("DEEPSEEK_API_KEY", DUMMY_DEEPSEEK_KEY)
    monkeypatch.setenv("GLM_API_KEY", DUMMY_GLM_KEY)
    monkeypatch.setenv("DASHSCOPE_API_KEY", DUMMY_DASHSCOPE_KEY)

    raw_message = (
        f"Error connecting to Gemini with key {DUMMY_GEMINI_KEY}. "
        f"Fallback DeepSeek {DUMMY_DEEPSEEK_KEY}, GLM {DUMMY_GLM_KEY} and Qwen {DUMMY_DASHSCOPE_KEY} also reported error."
    )
    sanitized = sanitize_secret_text(raw_message)

    assert DUMMY_GEMINI_KEY not in sanitized
    assert DUMMY_DEEPSEEK_KEY not in sanitized
    assert DUMMY_GLM_KEY not in sanitized
    assert DUMMY_DASHSCOPE_KEY not in sanitized
    assert REDACTED_REPLACEMENT in sanitized

def test_sanitize_secret_text_url_query_parameter_pattern():
    raw_url_error = (
        "429 Client Error: Too Many Requests for url: "
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key=AQ.UnconfiguredKeyInUrl123"
    )
    sanitized = sanitize_secret_text(raw_url_error)

    assert "AQ.UnconfiguredKeyInUrl123" not in sanitized
    assert f"?key={REDACTED_REPLACEMENT}" in sanitized

def test_sanitize_secret_text_header_pattern():
    raw_header_log = "Request headers: {'x-goog-api-key': 'random-secret-key-xyz-789', 'Content-Type': 'application/json'}"
    sanitized = sanitize_secret_text(raw_header_log)

    assert "random-secret-key-xyz-789" not in sanitized
    assert REDACTED_REPLACEMENT in sanitized

def test_sanitize_secret_text_bearer_auth_pattern():
    raw_auth_error = "Authentication failed for header Authorization: Bearer sk-deepseek-abcdef1234567890"
    sanitized = sanitize_secret_text(raw_auth_error)

    assert "sk-deepseek-abcdef1234567890" not in sanitized
    assert f"Authorization: Bearer {REDACTED_REPLACEMENT}" in sanitized

def test_crash_report_and_human_review_cannot_leak_keys(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", DUMMY_GEMINI_KEY)
    monkeypatch.setenv("DEEPSEEK_API_KEY", DUMMY_DEEPSEEK_KEY)
    monkeypatch.setenv("GLM_API_KEY", DUMMY_GLM_KEY)
    monkeypatch.setenv("DASHSCOPE_API_KEY", DUMMY_DASHSCOPE_KEY)

    task_id = "TASK-SECURITY-TEST-01"
    state_dir = tmp_path / "state"
    sm = StateManager(task_id, state_dir=str(state_dir), raise_on_halt=True)

    # 1. Test halt_human and CRASH_REPORT
    with pytest.raises(RuntimeError):
        sm.halt_human(f"Fatal crash leaking {DUMMY_GEMINI_KEY} and {DUMMY_DEEPSEEK_KEY} and {DUMMY_DASHSCOPE_KEY}")
    crash_report = Path(f"CRASH_REPORT_{task_id}.md")
    assert crash_report.exists()
    try:
        crash_content = crash_report.read_text(encoding="utf-8")
        assert DUMMY_GEMINI_KEY not in crash_content
        assert DUMMY_DEEPSEEK_KEY not in crash_content
        assert DUMMY_DASHSCOPE_KEY not in crash_content
        assert REDACTED_REPLACEMENT in crash_content
    finally:
        if crash_report.exists():
            crash_report.unlink()

    # 2. Test request_human_review and HUMAN_REVIEW
    with pytest.raises(RuntimeError):
        sm.request_human_review(
            f"Transport failure on https://api.example.com?key={DUMMY_GLM_KEY} with {DUMMY_GEMINI_KEY} and {DUMMY_DASHSCOPE_KEY}",
            gate="LOGIC_AUDIT"
        )
    human_report = Path(f"HUMAN_REVIEW_{task_id}.md")
    assert human_report.exists()
    try:
        human_content = human_report.read_text(encoding="utf-8")
        assert DUMMY_GEMINI_KEY not in human_content
        assert DUMMY_GLM_KEY not in human_content
        assert DUMMY_DASHSCOPE_KEY not in human_content
        assert REDACTED_REPLACEMENT in human_content
    finally:
        if human_report.exists():
            human_report.unlink()

    # 3. Test state JSON history
    state_file = state_dir / f"state_{task_id}.json"
    assert state_file.exists()
    state_content = state_file.read_text(encoding="utf-8")
    assert DUMMY_GEMINI_KEY not in state_content
    assert DUMMY_DEEPSEEK_KEY not in state_content
    assert DUMMY_GLM_KEY not in state_content
    assert DUMMY_DASHSCOPE_KEY not in state_content
    assert REDACTED_REPLACEMENT in state_content

def test_network_retry_redacts_credentials_on_transport_failure(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", DUMMY_GEMINI_KEY)

    @retry_with_backoff(max_retries=2, initial_delay=0.01)
    def failing_api_call():
        resp = requests.Response()
        resp.status_code = 429
        resp.reason = "Rate Limit"
        resp.headers["Retry-After"] = "0.01"
        raise requests.exceptions.HTTPError(
            f"429 Client Error for url: https://generativelanguage.googleapis.com/v1beta/models/gemini:generateContent?key={DUMMY_GEMINI_KEY}",
            response=resp
        )

    with pytest.raises(NetworkTransportError) as exc_info:
        failing_api_call()

    exc_msg = str(exc_info.value)
    assert DUMMY_GEMINI_KEY not in exc_msg
    assert REDACTED_REPLACEMENT in exc_msg
    assert exc_info.value.status_code == 429
