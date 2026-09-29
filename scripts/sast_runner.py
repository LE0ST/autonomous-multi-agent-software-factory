#!/usr/bin/env python3
"""Fail-closed SAST gate with bounded scanner invocations.

Deployment must still pin scanner versions and Semgrep's auto rules for
reproducibility. Bandit is used only when Semgrep is not installed.
"""

import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

EXIT_NO_FINDINGS = 0
EXIT_FINDINGS = 1
EXIT_TOOL_ERROR = 2
PROBE_TIMEOUT_SECONDS = 10
DEFAULT_SCAN_TIMEOUT_SECONDS = 120
MAX_SCAN_TIMEOUT_SECONDS = 1800
MAX_REPORT_BYTES = 10 * 1024 * 1024


def _find_scanner(name: str) -> list[str] | None:
    # Always use the controller's Python installation, whose distribution identity
    # is bound into evidence. PATH-selected executables are not trusted scanners.
    command = [sys.executable, "-I", "-m", name]
    result = subprocess.run(
        command + ["--version"], capture_output=True, text=True,
        cwd=Path(__file__).resolve().parent, timeout=PROBE_TIMEOUT_SECONDS,
    )
    if result.returncode == 0:
        return command
    if f"No module named {name}" in result.stderr:
        return None
    raise RuntimeError(f"{name} installation probe failed with code {result.returncode}")


def find_semgrep_cmd() -> list[str] | None:
    return _find_scanner("semgrep")


def find_bandit_cmd() -> list[str] | None:
    return _find_scanner("bandit")


def _tool_error(engine: str, message: str, stderr: str = "") -> tuple[int, dict]:
    return EXIT_TOOL_ERROR, {"engine": engine, "error": message, "stderr": stderr[:4096]}


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate report key: {key}")
        result[key] = value
    return result


def _positive_line(value: object) -> bool:
    return type(value) is int and value > 0


def _validate_report(engine: str, result: subprocess.CompletedProcess) -> dict:
    # Scanner errors often include valid JSON with an empty results array.
    if result.returncode not in (0, 1):
        raise ValueError(f"Scanner returned error code {result.returncode}")
    if not result.stdout or not result.stdout.strip():
        raise ValueError("Scanner returned no JSON report")
    if len(result.stdout.encode("utf-8")) > MAX_REPORT_BYTES:
        raise ValueError("Scanner report exceeds the permitted size")
    data = json.loads(result.stdout, object_pairs_hook=_unique_object)
    if not isinstance(data, dict):
        raise ValueError("Scanner report must be an object")
    if not isinstance(data.get("results"), list) or not all(
        isinstance(finding, dict) for finding in data["results"]
    ):
        raise ValueError("Scanner report must contain a results array of objects")
    if not isinstance(data.get("errors"), list):
        raise ValueError("Scanner report must contain an errors array")
    if data["errors"]:
        raise ValueError("Scanner reported errors; scan completeness is unverified")

    if engine == "semgrep":
        skipped_rules = data.get("skipped_rules", [])
        if not isinstance(skipped_rules, list) or skipped_rules:
            raise ValueError("Semgrep skipped rules; scan completeness is unverified")
        paths = data.get("paths")
        if not isinstance(paths, dict) or not isinstance(paths.get("scanned"), list):
            raise ValueError("Semgrep report does not identify scanned files")
        if not paths["scanned"] or not all(isinstance(p, str) and p for p in paths["scanned"]):
            raise ValueError("Semgrep did not scan any valid file paths")
        skipped_paths = paths.get("skipped", [])
        if not isinstance(skipped_paths, list) or not all(isinstance(p, dict) for p in skipped_paths):
            raise ValueError("Semgrep skipped-file metadata is malformed")
        incomplete_reasons = ("timeout", "error", "exceed", "permission", "failed")
        if any(
            any(reason in str(path.get("reason", "")).lower() for reason in incomplete_reasons)
            for path in skipped_paths
        ):
            raise ValueError("Semgrep skipped files due to analysis limits or failures")
        for finding in data["results"]:
            if not all(isinstance(finding.get(key), str) and finding[key] for key in ("check_id", "path")):
                raise ValueError("Semgrep finding lacks a rule ID or source path")
            if not isinstance(finding.get("start"), dict) or not _positive_line(finding["start"].get("line")):
                raise ValueError("Semgrep finding lacks a valid source line")
    else:
        metrics = data.get("metrics")
        if not isinstance(metrics, dict) or not isinstance(metrics.get("_totals"), dict):
            raise ValueError("Bandit report lacks scan metrics")
        if not any(key != "_totals" and isinstance(value, dict) for key, value in metrics.items()):
            raise ValueError("Bandit did not report any scanned files")
        for finding in data["results"]:
            if finding.get("issue_severity") not in ("LOW", "MEDIUM", "HIGH"):
                raise ValueError("Bandit finding has an invalid severity")
            if not all(isinstance(finding.get(key), str) and finding[key] for key in ("test_id", "filename")):
                raise ValueError("Bandit finding lacks a rule ID or source path")
            if not _positive_line(finding.get("line_number")):
                raise ValueError("Bandit finding lacks a valid source line")

    # Both scanners are invoked with findings => exit 1. A contradiction
    # indicates a failed scan even if one half appears successful.
    if bool(data["results"]) != (result.returncode == 1):
        raise ValueError("Scanner exit code contradicts its findings")
    return data


def run_sast(
    worktree_dir: Path, *, timeout_seconds: float = DEFAULT_SCAN_TIMEOUT_SECONDS,
) -> tuple[int, dict]:
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(timeout_seconds)
        or not 0 < timeout_seconds <= MAX_SCAN_TIMEOUT_SECONDS
    ):
        return _tool_error("none", "Invalid SAST timeout; require 0 < seconds <= 1800")
    worktree_dir = Path(worktree_dir).resolve()
    if not worktree_dir.is_dir():
        return _tool_error("none", "Worktree directory does not exist")

    engine = "semgrep"
    try:
        scanner = find_semgrep_cmd()
        if scanner is not None:
            command = scanner + [
                "scan", "--config", str(Path(__file__).with_name('semgrep_rules.yml')), "--severity", "ERROR", "--json",
                "--error", "--strict", "--disable-nosem", "--metrics", "off",
            ]
        else:
            engine = "bandit_fallback"
            scanner = find_bandit_cmd()
            if scanner is None:
                return _tool_error("none", "No operational SAST tools found (Semgrep or Bandit)")
            source = worktree_dir / "src"
            target = str(source if source.is_dir() else worktree_dir)
            command = scanner + ["-r", target, "-f", "json", "-ll", "--ignore-nosec"]
        result = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8",
            errors="strict", cwd=worktree_dir, timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return _tool_error(engine, "SAST scanner or installation probe exceeded its timeout")
    except (OSError, RuntimeError, UnicodeError) as exc:
        return _tool_error(engine, f"Failed to execute scanner: {exc}")

    try:
        data = _validate_report(engine, result)
    except (ValueError, RecursionError) as exc:
        return _tool_error(engine, str(exc), result.stderr)

    findings = data["results"]
    return (EXIT_FINDINGS if findings else EXIT_NO_FINDINGS), {
        "engine": engine, "results": findings, "raw": data,
    }


if __name__ == "__main__":
    try:
        worktree_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
        code, report = run_sast(worktree_path)
        payloads_dir = Path.cwd() / "orchestrator" / "payloads"
        payloads_dir.mkdir(parents=True, exist_ok=True)
        report_file = payloads_dir / "semgrep_report.json"
        report_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
        if code == EXIT_NO_FINDINGS:
            print(f"[PASS] SAST Gate: PASSED (Zero critical findings via {report['engine']})")
        elif code == EXIT_FINDINGS:
            print(f"[FAIL] SAST Gate: FINDINGS ({len(report['results'])} findings via {report['engine']})")
        else:
            print(f"[ERROR] SAST Gate: TOOL_ERROR ({report.get('error', 'unknown scanner error')})")
        sys.exit(code)
    except Exception as exc:
        print(f"[ERROR] SAST Gate: Unexpected fatal exception: {exc}", file=sys.stderr)
        sys.exit(EXIT_TOOL_ERROR)
