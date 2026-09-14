"""Test suite for TASK-005: the multi-tenant authorization policy engine.

Coverage map:
    [TEST-01] viewer permissions within a tenant
    [TEST-02] editor permissions within a tenant
    [TEST-03] admin permissions within a tenant
    [TEST-04] cross-tenant denial for every role (including admin)
    [TEST-05] unknown roles/actions and empty role sets are denied
    [TEST-06] roles combine only after tenant isolation is validated
    [TEST-07] malformed or missing inputs fail closed
    [TEST-08] tenants, roles and decisions are never emitted or persisted
    [TEST-09] no mutable global authorization state
    [TEST-10] no eval/exec/subprocess/network/external persistence
"""

from __future__ import annotations

import ast
import builtins
import importlib
import io
import logging
import socket
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.security.authorization_policy import AuthorizationPolicy  # noqa: E402

_MODULE_NAME = "src.security.authorization_policy"

_TENANT_A = "tenant-alpha"
_TENANT_B = "tenant-beta"
_SECRET_TENANT = "tenant-secret-8f31"
_SECRET_ROLE = "role-secret-4b7d"

_ALL_ACTIONS = ("read", "write", "delete")
_KNOWN_ROLES = ("viewer", "editor", "admin")


def _policy() -> AuthorizationPolicy:
    """Return a fresh policy instance (never shared mutable state)."""
    return AuthorizationPolicy()


# ---------------------------------------------------------------------------
# [TEST-01] viewer
# ---------------------------------------------------------------------------
def test_viewer_can_read_but_not_write_or_delete_within_tenant():
    policy = _policy()
    assert policy.is_allowed(_TENANT_A, _TENANT_A, {"viewer"}, "read") is True
    assert policy.is_allowed(_TENANT_A, _TENANT_A, {"viewer"}, "write") is False
    assert policy.is_allowed(_TENANT_A, _TENANT_A, {"viewer"}, "delete") is False


# ---------------------------------------------------------------------------
# [TEST-02] editor
# ---------------------------------------------------------------------------
def test_editor_can_read_and_write_but_not_delete_within_tenant():
    policy = _policy()
    assert policy.is_allowed(_TENANT_A, _TENANT_A, {"editor"}, "read") is True
    assert policy.is_allowed(_TENANT_A, _TENANT_A, {"editor"}, "write") is True
    assert policy.is_allowed(_TENANT_A, _TENANT_A, {"editor"}, "delete") is False


# ---------------------------------------------------------------------------
# [TEST-03] admin
# ---------------------------------------------------------------------------
def test_admin_can_read_write_and_delete_within_tenant():
    policy = _policy()
    assert policy.is_allowed(_TENANT_A, _TENANT_A, {"admin"}, "read") is True
    assert policy.is_allowed(_TENANT_A, _TENANT_A, {"admin"}, "write") is True
    assert policy.is_allowed(_TENANT_A, _TENANT_A, {"admin"}, "delete") is True
    assert policy.is_allowed(_TENANT_B, _TENANT_B, {"admin"}, "delete") is True


# ---------------------------------------------------------------------------
# [TEST-04] tenant isolation for every role, including admin
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("role", _KNOWN_ROLES)
@pytest.mark.parametrize("action", _ALL_ACTIONS)
def test_every_role_including_admin_is_denied_across_tenants(role, action):
    policy = _policy()
    assert policy.is_allowed(_TENANT_A, _TENANT_B, {role}, action) is False
    assert policy.is_allowed(_TENANT_B, _TENANT_A, {role}, action) is False


def test_admin_has_no_cross_tenant_override_and_no_wildcard():
    policy = _policy()
    for action in _ALL_ACTIONS:
        assert policy.is_allowed(_TENANT_A, _TENANT_B, {"admin"}, action) is False
    assert policy.is_allowed(_TENANT_A, _TENANT_B, {"admin"}, "*") is False
    assert policy.is_allowed(_TENANT_A, _TENANT_B, {"admin"}, "all") is False
    assert policy.is_allowed(_TENANT_A, _TENANT_B, {"admin"}, "read_all") is False


# ---------------------------------------------------------------------------
# [TEST-05] unknown roles, unknown actions, empty role sets
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "role",
    ("owner", "superuser", "root", "Admin", "ADMIN", "VIEWER", "", " viewer", "viewer "),
)
def test_unknown_roles_grant_no_permissions(role):
    policy = _policy()
    for action in _ALL_ACTIONS:
        assert policy.is_allowed(_TENANT_A, _TENANT_A, {role}, action) is False


@pytest.mark.parametrize("role", _KNOWN_ROLES)
@pytest.mark.parametrize(
    "action",
    ("", " ", "*", "read_all", "READ", "Write", "DELETE", "delete_all", "admin", "purge"),
)
def test_unknown_actions_are_always_denied(role, action):
    policy = _policy()
    assert policy.is_allowed(_TENANT_A, _TENANT_A, {role}, action) is False


def test_empty_role_sets_are_always_denied():
    policy = _policy()
    for roles in (set(), frozenset()):
        for action in _ALL_ACTIONS:
            assert policy.is_allowed(_TENANT_A, _TENANT_A, roles, action) is False
        assert policy.is_allowed(_TENANT_A, _TENANT_B, roles, "read") is False


# ---------------------------------------------------------------------------
# [TEST-06] role combination only after tenant isolation
# ---------------------------------------------------------------------------
def test_multiple_roles_combine_permissions_within_a_tenant():
    policy = _policy()

    roles = {"viewer", "editor"}
    assert policy.is_allowed(_TENANT_A, _TENANT_A, roles, "read") is True
    assert policy.is_allowed(_TENANT_A, _TENANT_A, roles, "write") is True
    assert policy.is_allowed(_TENANT_A, _TENANT_A, roles, "delete") is False

    roles = {"viewer", "editor", "admin"}
    assert policy.is_allowed(_TENANT_A, _TENANT_A, roles, "delete") is True

    frozen_roles = frozenset({"editor", "admin"})
    assert policy.is_allowed(_TENANT_A, _TENANT_A, frozen_roles, "delete") is True


def test_multiple_roles_do_not_combine_across_tenants():
    policy = _policy()
    roles = {"viewer", "editor", "admin"}
    for action in _ALL_ACTIONS:
        assert policy.is_allowed(_TENANT_A, _TENANT_B, roles, action) is False
        assert policy.is_allowed(_TENANT_B, _TENANT_A, roles, action) is False
    assert policy.is_allowed(_TENANT_A, "", roles, "read") is False


def test_unknown_role_neither_grants_nor_blocks_a_known_role():
    policy = _policy()
    roles = {"viewer", "mystery-role"}
    assert policy.is_allowed(_TENANT_A, _TENANT_A, roles, "read") is True
    assert policy.is_allowed(_TENANT_A, _TENANT_A, roles, "write") is False
    assert policy.is_allowed(_TENANT_A, _TENANT_A, roles, "delete") is False


# ---------------------------------------------------------------------------
# [TEST-07] malformed or missing inputs fail closed
# ---------------------------------------------------------------------------
def test_malformed_or_missing_inputs_fail_closed():
    policy = _policy()
    cases = (
        (None, _TENANT_A, frozenset({"admin"}), "read"),
        (_TENANT_A, None, frozenset({"admin"}), "read"),
        (None, None, frozenset({"admin"}), "read"),
        ("", _TENANT_A, frozenset({"admin"}), "read"),
        (_TENANT_A, "", frozenset({"admin"}), "read"),
        ("   ", _TENANT_A, frozenset({"admin"}), "read"),
        (_TENANT_A, "\t", frozenset({"admin"}), "read"),
        (123, _TENANT_A, frozenset({"admin"}), "read"),
        (_TENANT_A, 456, frozenset({"admin"}), "read"),
        (_TENANT_A, _TENANT_A, None, "read"),
        (_TENANT_A, _TENANT_A, object(), "read"),
        (_TENANT_A, _TENANT_A, ["admin"], "read"),
        (_TENANT_A, _TENANT_A, ("admin",), "read"),
        (_TENANT_A, _TENANT_A, "admin", "read"),
        (_TENANT_A, _TENANT_A, {"admin"}, None),
        (_TENANT_A, _TENANT_A, {"admin"}, ""),
        (_TENANT_A, _TENANT_A, {"admin"}, "   "),
        (_TENANT_A, _TENANT_A, {"admin"}, 42),
        (_TENANT_A, _TENANT_A, {"admin"}, b"read"),
        (_TENANT_A, _TENANT_A, {"admin"}, ["read"]),
        (_TENANT_A, _TENANT_A, {None}, "read"),
        (_TENANT_A, _TENANT_A, {42}, "read"),
        (_TENANT_A, _TENANT_A, {b"admin"}, "read"),
        (_TENANT_A, _TENANT_A, frozenset(), "read"),
        (_TENANT_A, _TENANT_A, frozenset({42, "admin"}), "read"),
    )
    for subject_tenant, resource_tenant, roles, action in cases:
        assert (
            policy.is_allowed(subject_tenant, resource_tenant, roles, action) is False
        ), f"expected deny for {subject_tenant!r}, {resource_tenant!r}, {roles!r}, {action!r}"


def test_missing_arguments_never_produce_an_allow_decision():
    policy = _policy()
    with pytest.raises(TypeError):
        policy.is_allowed()  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        policy.is_allowed(_TENANT_A, _TENANT_A, {"admin"})  # type: ignore[call-arg]


def test_decision_is_always_a_plain_boolean():
    policy = _policy()
    for subject_tenant, resource_tenant, roles, action in (
        (_TENANT_A, _TENANT_A, {"viewer"}, "read"),
        (_TENANT_A, _TENANT_A, {"viewer"}, "write"),
        (_TENANT_A, _TENANT_B, {"admin"}, "delete"),
        (_TENANT_A, _TENANT_A, {"nobody"}, "read"),
    ):
        result = policy.is_allowed(subject_tenant, resource_tenant, roles, action)
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# [TEST-08] no emission and no persistence
# ---------------------------------------------------------------------------
def test_tenants_roles_and_decisions_are_never_emitted(capfd):
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    policy = _policy()

    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        assert policy.is_allowed(_SECRET_TENANT, _SECRET_TENANT, {"admin"}, "read") is True
        assert policy.is_allowed(_SECRET_TENANT, _TENANT_B, {"admin"}, "delete") is False
        assert policy.is_allowed(_SECRET_TENANT, _SECRET_TENANT, {_SECRET_ROLE}, "read") is False

    assert stdout_buffer.getvalue() == ""
    assert stderr_buffer.getvalue() == ""

    captured = capfd.readouterr()
    assert captured.out == ""
    assert captured.err == ""

    emitted = captured.out + captured.err
    assert _SECRET_TENANT not in emitted
    assert _SECRET_ROLE not in emitted
    assert "allowed" not in emitted
    assert "denied" not in emitted


def test_tenants_roles_and_decisions_are_never_logged(caplog):
    caplog.clear()
    policy = _policy()
    with caplog.at_level(logging.DEBUG):
        assert policy.is_allowed(_SECRET_TENANT, _SECRET_TENANT, {"admin"}, "read") is True
        assert policy.is_allowed(_SECRET_TENANT, _TENANT_B, {"admin"}, "delete") is False
        assert policy.is_allowed(_SECRET_TENANT, _SECRET_TENANT, {_SECRET_ROLE}, "read") is False

    assert caplog.records == []
    assert caplog.text == ""


def test_tenants_roles_and_decisions_are_never_persisted(monkeypatch):
    write_attempts = []
    real_open = builtins.open

    def guarded_open(file, mode="r", *args, **kwargs):
        if isinstance(mode, str) and any(flag in mode for flag in ("w", "a", "x", "+")):
            write_attempts.append((str(file), mode))
            raise AssertionError("authorization policy must never write to disk")
        return real_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)

    policy = _policy()
    assert policy.is_allowed(_SECRET_TENANT, _SECRET_TENANT, {"admin"}, "read") is True
    assert policy.is_allowed(_SECRET_TENANT, _SECRET_TENANT, {"viewer"}, "delete") is False
    assert policy.is_allowed(_SECRET_TENANT, _TENANT_B, {"admin"}, "delete") is False
    assert write_attempts == []


# ---------------------------------------------------------------------------
# [TEST-09] no mutable global authorization state
# ---------------------------------------------------------------------------
def test_no_mutable_module_level_authorization_state():
    module = importlib.import_module(_MODULE_NAME)
    mutable_types = (dict, list, set, bytearray)

    offenders = [
        name
        for name, value in vars(module).items()
        if not name.startswith("__") and isinstance(value, mutable_types)
    ]
    assert offenders == []


def test_permission_table_is_not_mutable_state():
    table = AuthorizationPolicy._PERMISSIONS
    assert not isinstance(table, dict)
    with pytest.raises(TypeError):
        table["viewer"] = frozenset()  # type: ignore[index]


def test_policy_instances_hold_no_mutable_state():
    first = _policy()
    second = _policy()

    if hasattr(first, "__dict__"):
        assert vars(first) == {}
    if hasattr(second, "__dict__"):
        assert vars(second) == {}

    assert first.is_allowed(_TENANT_A, _TENANT_A, {"admin"}, "delete") is True
    assert second.is_allowed(_TENANT_A, _TENANT_A, {"admin"}, "delete") is True
    assert second.is_allowed(_TENANT_A, _TENANT_B, {"admin"}, "delete") is False
    assert first.is_allowed(_TENANT_A, _TENANT_B, {"admin"}, "delete") is False


def test_policy_exposes_only_read_only_operations():
    public_callables = {
        name
        for name, value in vars(AuthorizationPolicy).items()
        if not name.startswith("_") and callable(value)
    }
    assert public_callables == {"is_allowed"}


def test_repeated_evaluation_is_deterministic():
    policy = _policy()
    roles = {"viewer"}
    for _ in range(50):
        assert policy.is_allowed(_TENANT_A, _TENANT_A, roles, "read") is True
        assert policy.is_allowed(_TENANT_A, _TENANT_A, roles, "delete") is False
        assert policy.is_allowed(_TENANT_A, _TENANT_B, roles, "read") is False


# ---------------------------------------------------------------------------
# [TEST-10] no dynamic execution, subprocesses, network or persistence
# ---------------------------------------------------------------------------
def _implementation_source() -> str:
    module = importlib.import_module(_MODULE_NAME)
    module_file = getattr(module, "__file__", None)
    assert module_file, "authorization policy module has no source file"
    return Path(module_file).read_text(encoding="utf-8")


def test_source_uses_no_forbidden_constructs():
    tree = ast.parse(_implementation_source())

    forbidden_call_names = {"eval", "exec", "compile", "__import__", "input", "open"}
    forbidden_attribute_calls = {
        "system",
        "popen",
        "spawn",
        "spawnl",
        "spawnv",
        "fork",
        "execv",
        "execve",
        "execl",
        "execlp",
        "execlpe",
    }
    forbidden_modules = {
        # process / dynamic-code execution
        "subprocess",
        "multiprocessing",
        "ctypes",
        "pty",
        # networking
        "socket",
        "ssl",
        "http",
        "urllib",
        "urllib2",
        "requests",
        "ftplib",
        "smtplib",
        "telnetlib",
        "poplib",
        "imaplib",
        "xmlrpc",
        # persistence / file I/O / emission
        "pickle",
        "shelve",
        "sqlite3",
        "dbm",
        "marshal",
        "tempfile",
        "shutil",
        "pathlib",
        "io",
        "logging",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root not in forbidden_modules, f"forbidden import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            assert root not in forbidden_modules, f"forbidden import: {node.module}"
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                assert func.id not in forbidden_call_names, f"forbidden call: {func.id}"
            elif isinstance(func, ast.Attribute):
                assert (
                    func.attr not in forbidden_attribute_calls
                ), f"forbidden call: {func.attr}"


def test_no_dynamic_execution_at_runtime(monkeypatch):
    def _forbidden(*args, **kwargs):
        raise AssertionError("authorization policy must not evaluate dynamic code")

    monkeypatch.setattr(builtins, "eval", _forbidden)
    monkeypatch.setattr(builtins, "exec", _forbidden)
    monkeypatch.setattr(builtins, "compile", _forbidden)

    policy = _policy()
    assert policy.is_allowed(_SECRET_TENANT, _SECRET_TENANT, {"admin"}, "read") is True
    assert policy.is_allowed(_SECRET_TENANT, _SECRET_TENANT, {"admin"}, "delete") is True
    assert policy.is_allowed(_SECRET_TENANT, _TENANT_B, {"admin"}, "delete") is False


def test_no_subprocess_or_network_usage_at_runtime(monkeypatch):
    def _forbidden(*args, **kwargs):
        raise AssertionError("authorization policy must not use subprocesses or the network")

    monkeypatch.setattr(subprocess, "Popen", _forbidden)
    monkeypatch.setattr(subprocess, "run", _forbidden)
    monkeypatch.setattr(subprocess, "call", _forbidden)
    monkeypatch.setattr(subprocess, "check_call", _forbidden)
    monkeypatch.setattr(subprocess, "check_output", _forbidden)
    monkeypatch.setattr(socket, "socket", _forbidden)
    monkeypatch.setattr(socket, "create_connection", _forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", _forbidden)

    policy = _policy()
    assert policy.is_allowed(_TENANT_A, _TENANT_A, {"admin"}, "delete") is True
    assert policy.is_allowed(_TENANT_A, _TENANT_B, {"admin"}, "delete") is False
    assert policy.is_allowed(_TENANT_A, _TENANT_A, {"viewer"}, "read") is True
