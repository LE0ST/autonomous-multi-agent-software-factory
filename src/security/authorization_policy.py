"""Multi-tenant authorization policy engine (TASK-005).

The engine answers one question: may a subject belonging to
``subject_tenant`` perform ``action`` on a resource owned by
``resource_tenant``?

Design rules, all mandatory:

* **Deny by default** - only explicitly granted ``(role, action)`` pairs are
  ever allowed. Everything else is denied.
* **Tenant isolation** - a subject may only act inside its own tenant. The
  isolation check runs *before* any role is consulted, therefore it applies
  to every role, including ``admin``. There is no wildcard, no tenant
  override and no bypass path.
* **Fail closed** - missing, malformed, unknown or unsupported inputs are
  denied instead of raising or falling through to a default allow.
* **No observable side effects** - tenant identifiers, roles and decisions
  are never logged, printed, persisted or transmitted.
* **No mutable global state** - the policy is stateless (``__slots__``) and
  the permission table is an immutable mapping of ``frozenset`` values.
* **No dynamic execution** - no ``eval``, ``exec``, subprocesses, network
  access or external persistence.
"""

from __future__ import annotations

from collections.abc import Set as AbstractSet
from types import MappingProxyType
from typing import Mapping

__all__ = ["AuthorizationPolicy"]


class AuthorizationPolicy:
    """Stateless, deny-by-default, tenant-isolated authorization policy."""

    __slots__ = ()

    #: Immutable ``role -> granted actions`` table. Never mutable state.
    _PERMISSIONS: Mapping[str, frozenset[str]] = MappingProxyType(
        {
            "viewer": frozenset(("read",)),
            "editor": frozenset(("read", "write")),
            "admin": frozenset(("read", "write", "delete")),
        }
    )

    def is_allowed(
        self,
        subject_tenant: str,
        resource_tenant: str,
        roles: set[str],
        action: str,
    ) -> bool:
        """Return ``True`` only when ``action`` is explicitly permitted.

        The decision is deny-by-default and fail-closed: anything that is not
        an explicit ``(same tenant, known role, known action)`` grant returns
        ``False``. No tenant identifier, role or decision is ever emitted.
        """
        try:
            return self._decide(subject_tenant, resource_tenant, roles, action)
        except Exception:  # any unexpected error must never fail open
            return False

    def _decide(
        self,
        subject_tenant: object,
        resource_tenant: object,
        roles: object,
        action: object,
    ) -> bool:
        # --- 1. Missing or malformed inputs are denied outright ------------
        if not self._is_tenant_id(subject_tenant):
            return False
        if not self._is_tenant_id(resource_tenant):
            return False
        if not isinstance(action, str) or not action.strip():
            return False
        if not isinstance(roles, AbstractSet) or len(roles) == 0:
            return False

        # --- 2. Tenant isolation first: applies to every role, incl. admin -
        if subject_tenant != resource_tenant:
            return False

        # --- 3. Reject malformed role entries up-front so that the outcome
        #        never depends on set iteration order -----------------------
        for role in roles:
            if not isinstance(role, str):
                return False

        # --- 4. Combine permissions of the known roles only ----------------
        permissions = type(self)._PERMISSIONS
        for role in roles:
            granted = permissions.get(role)
            if granted is not None and action in granted:
                return True
        return False

    @staticmethod
    def _is_tenant_id(value: object) -> bool:
        """A tenant identifier must be a non-empty, non-blank string."""
        return isinstance(value, str) and bool(value.strip())
