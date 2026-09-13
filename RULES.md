# WORKER GOVERNANCE RULES & DIRECTIVES

As a Worker agent in the Autonomous Multi-Agent Software Factory, you are subject to the following unbreakable execution rules and authority limits:

## 1. Principle of Least Authority
- You are only authorized to create or modify files explicitly listed in the `Allowed files` / `Archivos permitidos` section of the active technical specification (`specs/TASK-XXX.md`).
- You are **strictly forbidden** from accessing, creating, or modifying any file listed in `Strictly forbidden files` / `Archivos estrictamente prohibidos`.
- Any modification outside authorized boundaries will be immediately rejected by `diff_gate.py` before the testing phase.

## 2. Inviolability of Root and Configuration Files
- You are strictly prohibited from modifying core repository configuration files, including but not limited to:
  - `pyproject.toml`
  - `package.json`
  - `.env*`
  - `.gitignore`
  - `RULES.md`
  - Files inside `orchestrator/` or `scripts/`

## 3. Code Quality and Testing
- Every new feature or fix must include associated unit tests.
- Global code coverage must not fall below the configured threshold (85%).
- Existing tests must not be deleted, commented out, or weakened to force pipeline passage.

## 4. Security and Invariants
- Introducing insecure system API calls (`eval`, `exec`, unsanitized shell command injections, plaintext credentials) is strictly forbidden.
- Any finding reported by `sast_runner.py` with critical severity will halt the pipeline and require mandatory remediation.
