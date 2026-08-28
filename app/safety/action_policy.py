"""Action policy: decides whether a tool call needs confirmation.

Confirmation rules:
- The system prompt instructs the LLM to ask for a clear directive.
- Mutating tools always require confirmation unless:
    - the user's intent was explicit AND the tool is low risk, OR
    - the tool is explicitly allowlisted as low risk AND intent was strong.
- Destructive tools (deletions, high-impact) ALWAYS require confirmation.
"""

from __future__ import annotations

from typing import Optional

from app.config import settings
from app.schemas.tools import ToolDescriptor, ToolKind

# Tools that, even as mutations, may proceed without confirmation only when the
# user gave an explicit, unambiguous instruction.
LOW_RISK_MUTATIONS = {
    "create_task",
    "create_meeting",
    "create_client_request",
}

# Destructive / irreversible operations — always confirm.
HIGH_IMPACT = {
    "delete_client",      # not even in registry — hard deny
    "delete_document",
    "update_meeting",     # default-conservative; can be loosen later
}


def requires_confirmation(
    tool: ToolDescriptor,
    *,
    explicit_intent: bool = False,
    contextual_default: Optional[bool] = None,
) -> bool:
    if tool.kind == ToolKind.READ:
        return False

    if tool.destructive:
        return True

    default = contextual_default if contextual_default is not None else settings.require_confirmation_default

    if tool.name in HIGH_IMPACT:
        return True

    if tool.name in LOW_RISK_MUTATIONS:
        # proceed if user was explicit; otherwise confirm
        return not explicit_intent

    return default
