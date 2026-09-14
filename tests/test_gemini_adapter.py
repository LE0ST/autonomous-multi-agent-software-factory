import pytest
from unittest.mock import patch, MagicMock
import requests
from adapters.gemini_adapter import GeminiAdapter

FAKE_GEMINI_KEY = "dummy-fake-gemini-key-9876543210"

@pytest.fixture
def gemini_adapter():
    return GeminiAdapter(model="gemini-3.8-flash", api_key=FAKE_GEMINI_KEY)

def test_generate_spec_uses_header_and_no_key_in_url(gemini_adapter):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": "# SPEC content"}]}}]
    }
    mock_resp.status_code = 200

    with patch("requests.post", return_value=mock_resp) as mock_post:
        result = gemini_adapter.generate_spec("TASK-099", "Test Title", "Test description")

    assert result == "# SPEC content"
    assert mock_post.call_count == 1

    called_url = mock_post.call_args[0][0]
    called_headers = mock_post.call_args[1]["headers"]

    # Invariant: API key must NOT be present in the URL
    assert FAKE_GEMINI_KEY not in called_url
    assert "?key=" not in called_url
    assert "&key=" not in called_url
    assert called_url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent"

    # Invariant: API key must be transmitted via x-goog-api-key header
    assert called_headers.get("x-goog-api-key") == FAKE_GEMINI_KEY
    assert called_headers.get("Content-Type") == "application/json"

def test_triage_failure_uses_header_and_no_key_in_url(gemini_adapter):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "candidates": [{
            "content": {
                "parts": [{
                    "text": '{"failing_test": "t.py", "project_file": "p.py", "line_number": 1, "expected": "a", "received": "b", "root_cause": "c"}'
                }]
            }
        }]
    }
    mock_resp.status_code = 200

    with patch("requests.post", return_value=mock_resp) as mock_post:
        result = gemini_adapter.triage_failure({"stdout": "error"})

    assert result.failing_test == "t.py"
    called_url = mock_post.call_args[0][0]
    called_headers = mock_post.call_args[1]["headers"]

    assert FAKE_GEMINI_KEY not in called_url
    assert "?key=" not in called_url
    assert called_headers.get("x-goog-api-key") == FAKE_GEMINI_KEY

def test_filter_security_finding_uses_header_and_no_key_in_url(gemini_adapter):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "candidates": [{
            "content": {
                "parts": [{
                    "text": '{"finding_id": "sec-1", "classification": "FALSE_POSITIVE", "justification": "Safe test mock"}'
                }]
            }
        }]
    }
    mock_resp.status_code = 200

    with patch("requests.post", return_value=mock_resp) as mock_post:
        result = gemini_adapter.filter_security_finding({"check_id": "sec-1"})

    assert result.classification == "FALSE_POSITIVE"
    called_url = mock_post.call_args[0][0]
    called_headers = mock_post.call_args[1]["headers"]

    assert FAKE_GEMINI_KEY not in called_url
    assert "?key=" not in called_url
    assert called_headers.get("x-goog-api-key") == FAKE_GEMINI_KEY

def test_audit_logic_and_security_uses_header_and_no_key_in_url(gemini_adapter):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "candidates": [{
            "content": {
                "parts": [{
                    "text": '{"status": "PASS", "violated_invariants": [], "exploit_poc": null, "justification": "All invariants satisfied"}'
                }]
            }
        }]
    }
    mock_resp.status_code = 200

    with patch("requests.post", return_value=mock_resp) as mock_post:
        result = gemini_adapter.audit_logic_and_security("spec text", "diff text")

    assert result.status == "PASS"
    called_url = mock_post.call_args[0][0]
    called_headers = mock_post.call_args[1]["headers"]

    assert FAKE_GEMINI_KEY not in called_url
    assert "?key=" not in called_url
    assert called_headers.get("x-goog-api-key") == FAKE_GEMINI_KEY
