# Contribution Guidelines — Autonomous Multi-Agent Software Factory

English | [Español](CONTRIBUTING_ES.md)

Thank you for your interest in contributing to **Autonomous Multi-Agent Software Factory**. This project explores autonomous software engineering governed by Finite State Machines (FSM), deterministic verification gates, execution budgets, and strict Git worktree isolation.

---

## 1. Core Project Principles

1. **Determinism over Heuristics:** Quality, security, and integration decisions do not rely on LLM judgment whenever they can be validated deterministically via code (coverage checks, diff gates, SAST linters, fast-forward merges).
2. **Principle of Least Privilege:** No agent (especially the Worker) has access to modify files outside those explicitly authorized in the task technical specification (`specs/TASK-XXX.md`).
3. **Gate Inviolability:** No pipeline verification gate may be disabled or weakened to facilitate code integration.

---

## 2. Development Environment Setup

### Prerequisites
* **Python:** `>= 3.10`
* **Git:** `>= 2.30`
* **Semgrep:** `>= 1.0.0` (for SAST security scanning)

### Virtual Environment Installation

On Windows (PowerShell):
```powershell
# Clone repository and navigate to root
cd autonomous-multi-agent-software-factory

# Create and activate virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install package in editable mode with development dependencies
pip install -e .
```

On Linux / macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Credential Configuration
Copy the template `.env.example` to `.env`:
```powershell
cp .env.example .env
```
Configure your API keys for the model providers you intend to use:
* `GEMINI_API_KEY`: Required for Architect, Triage, Security Filter, and Logic Security.
* `DEEPSEEK_API_KEY`: Required for Worker (code generation and unit test drafting).
* `GLM_API_KEY`: Optional for alternative Logic Security via Zhipu GLM.
* `DASHSCOPE_API_KEY`: Optional for Qwen Logic Security fallback (`qwen3.8-flash`).

> [!CAUTION]
> **Never commit or push `.env` files or real credentials.** The repository actively ignores `.env` and credential files. Any pull request containing plain-text secrets will be rejected immediately.

---

## 3. Workflow and Branching Strategy

* **Base Integration Branch:** `dev`. All code integration occurs exclusively via Fast-Forward merge (`--ff-only`).
* **Task Branches:** `task/TASK-XXX`.
* **Worktree Isolation:** The orchestrator operates inside isolated Git worktrees located at `.worktrees/wt_TASK-XXX`, ensuring the primary working copy remains clean during code generation, test runs, and static analysis.
* **Deterministic Recovery:** If an authorized task suspends during `AUTO_MERGE` (e.g. dirty working tree) or `LOGIC_AUDIT` (e.g. transient HTTP 429/503 rate limits), use the authorized `--resume-merge` or `--resume-audit` commands respectively. Neither recovery path bypasses verification gates nor performs automatic rebases if branch divergence is detected.

---

## 4. Task Structure and Specifications

Every new task must be formally specified in `specs/TASK-XXX.md` using [`specs/TEMPLATE.md`](specs/TEMPLATE.md) as the canonical blueprint:

* **Clear, concise task objective.**
* **Security & Logic Invariants Table (`SEC-XX` / `LOG-XX`):** Inviolable rules that must be verified both by automated unit tests and semantic logic security audits.
* **Allowed Files:** Explicit whitelist of paths the Worker is authorized to create or modify.
* **Forbidden Files:** Protected repository infrastructure paths (root files, configuration, orchestrator core, verification gates).
* **Code Coverage Threshold:** Minimum required line coverage percentage (default $\ge 85\%$).

---

## 5. Validation and Test Suite

Before proposing any changes to the orchestrator, adapters, or system components:

```powershell
# 1. Verify whitespace, formatting, and trailing spaces
git diff --check

# 2. Run the complete unit and integration test suite
python -m pytest -v tests/
```

The 202 existing tests must pass at 100%. Commenting out, skipping, or deleting existing tests to pass CI is strictly prohibited.

---

## 6. Pull Request Process

1. Ensure your local `dev` branch is up-to-date with upstream and your working branch is cleanly rebased on top of `dev`.
2. Verify that `git status --short` returns a completely clean working tree.
3. Submit your PR with a clear, concise description covering:
   * The problem solved or the adapter/gate improved.
   * New unit/integration tests added to verify the functionality.
   * Explicit confirmation that all six verification gates, FSM invariants, and execution budgets remain strictly respected.
