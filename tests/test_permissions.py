"""Tests for client context resolution and client-data isolation."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path for direct execution
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.safety.permissions import (
    ClientIsolationViolation,
    PermissionDenied,
    assert_client_access,
    check_client_access,
    check_tool_allowed,
)
from app.schemas.agent import ClientContext, UserContext


def test_client_context_schema():
    ctx = ClientContext(
        client_id="abc",
        client_name="ABC Co",
        financial_year="FY2024-25",
        selected_services=["gst", "tds"],
    )
    assert ctx.client_id == "abc"
    assert ctx.scoped()


def test_client_scope_not_set_denies_low_role():
    # An associate cannot access arbitrary clients without an allow-list
    user = UserContext(user_id="u1", user_role="associate")
    assert check_client_access(user, "other-client") is False


def test_admin_scope_allowed():
    user = UserContext(user_id="u1", user_role="admin")
    assert check_client_access(user, "other-client") is True


def test_allowlist_enforced():
    user = UserContext(user_id="u1", user_role="associate")
    assert check_client_access(user, "abc", ["abc"]) is True
    assert check_client_access(user, "xyz", ["abc"]) is False


def test_assert_client_access_raises():
    user = UserContext(user_id="u1", user_role="associate")
    try:
        assert_client_access("abc", user, ["xyz"])
        raised = False
    except ClientIsolationViolation:
        raised = True
    assert raised


def test_permission_denied():
    from app.schemas.tools import PermissionLevel, ToolDefinition, ToolKind

    tool = ToolDefinition(
        name="x",
        description="x",
        input_model=None,
        kind=ToolKind.ACTION,
        permission=PermissionLevel.ADMIN,
    )
    user = UserContext(user_id="u1", user_role="viewer")
    try:
        check_tool_allowed(tool.descriptor, user)
        raised = False
    except PermissionDenied:
        raised = True
    assert raised


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__]))
