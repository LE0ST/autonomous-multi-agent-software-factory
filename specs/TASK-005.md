# TASK-005: Implement a multi-tenant authorization policy engine

## 1. Scope and Boundaries
- Allowed files:
  - `src/security/authorization_policy.py`
  - `tests/test_authorization_policy.py`
- Strictly forbidden files:
  - `orchestrator/`
  - `adapters/`
  - `scripts/`
  - `specs/`
  - `pyproject.toml`
  - `.env`
  - `RULES.md`

## 2. Acceptance Criteria (AC)
- [AC-01] Implement a class `AuthorizationPolicy` that evaluates whether a subject is authorized to perform an action on a resource.
- [AC-02] Expose:
  `is_allowed(subject_tenant: str, resource_tenant: str, roles: set[str], action: str) -> bool`.
- [AC-03] Default deny: anything not explicitly allowed returns `False`.
- [AC-04] Access is allowed only when `subject_tenant == resource_tenant`.
- [AC-05] Tenant isolation applies to every role, including `admin`.
- [AC-06] Permissions:
  - `viewer`: `read`
  - `editor`: `read`, `write`
  - `admin`: `read`, `write`, `delete`
- [AC-07] Unknown roles grant no permissions.
- [AC-08] Unknown actions are always denied.
- [AC-09] Multiple roles may combine permissions only after tenant isolation is validated.
- [AC-10] Empty role sets always deny.

## 3. Security Invariants (SEC)
- [SEC-01] Cross-tenant access must always be denied, including for `admin`.
- [SEC-02] Authorization must fail closed on missing, malformed, unknown, or unsupported inputs.
- [SEC-03] No hidden bypasses, wildcard permissions, admin tenant overrides, or default-allow paths.
- [SEC-04] Tenant identifiers, roles, and decisions must not be written to disk, logs, stdout, or stderr.
- [SEC-05] No mutable global authorization state.
- [SEC-06] No `eval`, `exec`, subprocesses, network access, or external persistence.

## 4. Required Test Matrix (TEST)
- [TEST-01] Verify `viewer` can read but cannot write/delete within the same tenant. (Covers: [AC-01], [AC-02], [AC-06])
- [TEST-02] Verify `editor` can read/write but cannot delete. (Covers: [AC-06])
- [TEST-03] Verify `admin` can read/write/delete within the same tenant. (Covers: [AC-06])
- [TEST-04] Verify every role, including `admin`, is denied across tenants. (Covers: [AC-04], [AC-05], [SEC-01])
- [TEST-05] Verify unknown roles/actions and empty role sets are denied. (Covers: [AC-03], [AC-07], [AC-08], [AC-10], [SEC-02], [SEC-03])
- [TEST-06] Verify multiple roles combine permissions only within the same tenant. (Covers: [AC-09], [SEC-01])
- [TEST-07] Verify malformed or missing authorization inputs fail closed. (Covers: [SEC-02])
- [TEST-08] Verify tenant IDs, roles, and decisions are never emitted or persisted. (Covers: [SEC-04])
- [TEST-09] Verify no mutable global authorization state exists. (Covers: [SEC-05])
- [TEST-10] Verify no `eval`, `exec`, subprocesses, network access, or external persistence. (Covers: [SEC-06])