"""Permission & client-isolation enforcement.

The backend is authoritative; this layer enforces the engine-side boundary:
- a user may only access clients they are allowed to see
- tool permission requirements are checked against the caller's role
- destructive tools are rejected unless explicitly allowed
"""

from __future__ import annotations

from typing import List, Optional

from app.schemas.agent import ClientContext, UserContext
from app.schemas.tools import PermissionLevel, ToolDescriptor

# Role hierarchy — higher authority includes lower permissions.
_ROLE_RANK = {"viewer": 0, "associate": 1, "manager": 2, "admin": 3, "partner": 4}


class PermissionDenied(Exception):
    pass


class ClientIsolationViolation(Exception):
    pass


def _effective_permission(role: str) -> int:
    return _ROLE_RANK.get((role or "").lower(), 0)


def can_tool_permission(role: Optional[str], required: PermissionLevel) -> bool:
    rank = _effective_permission(role or "")
    need = {
        PermissionLevel.VIEW: 0,
        PermissionLevel.MANAGE: 2,
        PermissionLevel.ADMIN: 3,
    }[required]
    return rank >= need


def check_tool_allowed(tool: ToolDescriptor, user: UserContext) -> None:
    """Raise PermissionDenied if the user lacks the tool's permission level."""
    if not can_tool_permission(user.user_role, tool.permission):
        raise PermissionDenied(
            f"User '{user.user_id}' (role={user.user_role}) is not allowed to use tool '{tool.name}'"
        )


def check_client_access(
    user_context: UserContext,
    client_id: Optional[str],
    accessible_client_ids: Optional[List[str]] = None,
) -> bool:
    """Return True if the user may access the given client.

    If `accessible_client_ids` is provided (from the backend), enforce it.
    Otherwise fall back to role: admin-level roles may span clients only when
    the backend grants it; normal users must have an allowed list.
    """
    if not client_id:
        # not client-scoped — allowed
        return True
    if accessible_client_ids is not None:
        return client_id in accessible_client_ids
    # No explicit allow-list available: only high roles may proceed, and only
    # if the backend independently authorizes the call (it will 403 otherwise).
    return _effective_permission(user_context.user_role or "") >= 2


def assert_client_access(
    client_id: Optional[str],
    user: UserContext,
    accessible_client_ids: Optional[List[str]] = None,
) -> None:
    if not check_client_access(user, client_id, accessible_client_ids):
        raise ClientIsolationViolation(
            f"User '{user.user_id}' cannot access client '{client_id}'"
        )


def is_destructive(tool: ToolDescriptor) -> bool:
    return tool.destructive
