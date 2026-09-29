"""Adversarial scanner responses must never authorize a successful SAST gate."""

import json
import subprocess

import pytest

from scripts import sast_runner as sast


def report(engine="semgrep", findings=None):
    data = {"results": findings or [], "errors": []}
    if engine == "semgrep":
        data["paths"] = {"scanned": ["src/main.py"]}
    else:
        data["metrics"] = {"_totals": {"loc": 1}, "src/main.py": {"loc": 1}}
    return data


def install_scanner(monkeypatch, engine, *, returncode=0, output=None, error=None):
    monkeypatch.setattr(sast, "find_semgrep_cmd", lambda: ["semgrep"] if engine == "semgrep" else None)
    monkeypatch.setattr(sast, "find_bandit_cmd", lambda: ["bandit"])
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        if error:
            raise error
        return subprocess.CompletedProcess(command, returncode, output, "diagnostic")

    monkeypatch.setattr(sast.subprocess, "run", run)
    return calls


@pytest.mark.parametrize("engine", ["semgrep", "bandit"])
def test_accepts_only_complete_clean_scan(tmp_path, monkeypatch, engine):
    calls = install_scanner(monkeypatch, engine, output=json.dumps(report(engine)))
    code, data = sast.run_sast(tmp_path, timeout_seconds=12)
    assert code == sast.EXIT_NO_FINDINGS
    assert data["results"] == []
    assert calls[0][1]["timeout"] == 12
    assert "--disable-nosem" in calls[0][0] or "--ignore-nosec" in calls[0][0]


@pytest.mark.parametrize("engine", ["semgrep", "bandit"])
@pytest.mark.parametrize("returncode", [2, 7, -9])
def test_error_status_cannot_pass_with_clean_json(tmp_path, monkeypatch, engine, returncode):
    install_scanner(monkeypatch, engine, returncode=returncode, output=json.dumps(report(engine)))
    code, data = sast.run_sast(tmp_path)
    assert code == sast.EXIT_TOOL_ERROR
    assert "error code" in data["error"]


@pytest.mark.parametrize("engine", ["semgrep", "bandit"])
@pytest.mark.parametrize("output", ["", " ", "not json", "[]", "{}", '{"results": null, "errors": []}', '{"results": [], "results": [], "errors": []}'])
def test_missing_or_malformed_report_fails_closed(tmp_path, monkeypatch, engine, output):
    install_scanner(monkeypatch, engine, output=output)
    assert sast.run_sast(tmp_path)[0] == sast.EXIT_TOOL_ERROR


@pytest.mark.parametrize("engine", ["semgrep", "bandit"])
def test_reported_errors_cannot_pass(tmp_path, monkeypatch, engine):
    data = report(engine)
    data["errors"] = [{"message": "failed to parse source"}]
    install_scanner(monkeypatch, engine, output=json.dumps(data))
    code, data = sast.run_sast(tmp_path)
    assert code == sast.EXIT_TOOL_ERROR
    assert "completeness" in data["error"]


@pytest.mark.parametrize("engine", ["semgrep", "bandit"])
def test_zero_scanned_files_cannot_pass(tmp_path, monkeypatch, engine):
    data = report(engine)
    if engine == "semgrep":
        data["paths"]["scanned"] = []
    else:
        data["metrics"] = {"_totals": {"loc": 0}}
    install_scanner(monkeypatch, engine, output=json.dumps(data))
    assert sast.run_sast(tmp_path)[0] == sast.EXIT_TOOL_ERROR


@pytest.mark.parametrize("reason", ["exceeded_size_limit", "insufficient_permissions", "analysis_failed"])
def test_semgrep_partial_file_scan_cannot_pass(tmp_path, monkeypatch, reason):
    data = report()
    data["paths"]["skipped"] = [{"path": "src/unsafe.py", "reason": reason}]
    install_scanner(monkeypatch, "semgrep", output=json.dumps(data))
    assert sast.run_sast(tmp_path)[0] == sast.EXIT_TOOL_ERROR


def test_semgrep_skipped_rules_cannot_pass(tmp_path, monkeypatch):
    data = report()
    data["skipped_rules"] = [{"rule_id": "broken-rule"}]
    install_scanner(monkeypatch, "semgrep", output=json.dumps(data))
    assert sast.run_sast(tmp_path)[0] == sast.EXIT_TOOL_ERROR


@pytest.mark.parametrize("engine", ["semgrep", "bandit"])
def test_findings_exit_without_findings_is_error(tmp_path, monkeypatch, engine):
    install_scanner(monkeypatch, engine, returncode=1, output=json.dumps(report(engine)))
    assert sast.run_sast(tmp_path)[0] == sast.EXIT_TOOL_ERROR


@pytest.mark.parametrize("engine", ["semgrep", "bandit"])
def test_valid_finding_is_preserved(tmp_path, monkeypatch, engine):
    finding = (
        {"check_id": "security.eval", "path": "src/main.py", "start": {"line": 1}}
        if engine == "semgrep" else
        {"test_id": "B307", "filename": "src/main.py", "line_number": 1, "issue_severity": "MEDIUM"}
    )
    install_scanner(monkeypatch, engine, returncode=1, output=json.dumps(report(engine, [finding])))
    code, data = sast.run_sast(tmp_path)
    assert code == sast.EXIT_FINDINGS
    assert data["results"] == [finding]


@pytest.mark.parametrize("engine", ["semgrep", "bandit"])
def test_malformed_finding_is_error(tmp_path, monkeypatch, engine):
    install_scanner(monkeypatch, engine, returncode=1, output=json.dumps(report(engine, [{}])))
    assert sast.run_sast(tmp_path)[0] == sast.EXIT_TOOL_ERROR


@pytest.mark.parametrize("error", [OSError("scanner failed"), subprocess.TimeoutExpired("scanner", 1)])
def test_execution_failure_never_falls_back(tmp_path, monkeypatch, error):
    install_scanner(monkeypatch, "semgrep", error=error)
    monkeypatch.setattr(sast, "find_bandit_cmd", lambda: pytest.fail("must not downgrade after scanner failure"))
    code, data = sast.run_sast(tmp_path)
    assert code == sast.EXIT_TOOL_ERROR
    assert data["engine"] == "semgrep"


@pytest.mark.parametrize("seconds", [0, -1, float("nan"), float("inf"), True, 1801, "10"])
def test_invalid_timeout_does_not_launch_scanner(tmp_path, monkeypatch, seconds):
    monkeypatch.setattr(sast, "find_semgrep_cmd", lambda: pytest.fail("invalid budget must fail before launch"))
    assert sast.run_sast(tmp_path, timeout_seconds=seconds)[0] == sast.EXIT_TOOL_ERROR


def test_module_probe_is_isolated_and_bounded(monkeypatch):
    monkeypatch.setattr(sast.shutil, "which", lambda name: None)
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "1.0", "")

    monkeypatch.setattr(sast.subprocess, "run", run)
    assert sast.find_semgrep_cmd() == [sast.sys.executable, "-I", "-m", "semgrep"]
    assert calls[0][1]["timeout"] == sast.PROBE_TIMEOUT_SECONDS


def test_broken_installation_probe_does_not_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(sast.shutil, "which", lambda name: None)
    monkeypatch.setattr(sast.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a[0], 1, "", "import failure"))
    monkeypatch.setattr(sast, "find_bandit_cmd", lambda: pytest.fail("broken scanner must fail closed"))
    assert sast.run_sast(tmp_path)[0] == sast.EXIT_TOOL_ERROR
