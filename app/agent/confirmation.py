"""Confirmation flow management."""

from __future__ import annotations

from app.memory.conversation import get_conversation_memory
from app.schemas.chat import ConfirmResponse, ToolCallResult


def create_confirmation_gate(
    conversation_id: str,
    tool_name: str,
    args: dict | None = None,
    requires_confirmation: bool = False,
) -> bool:
    """Record a pending action that awaits explicit user confirmation.

    Returns True if the action was gated (i.e. confirmation is now pending),
    False when no gating is needed.
    """
    if not requires_confirmation:
        return False
    memory = get_conversation_memory()
    memory.set_pending_action(
        conversation_id,
        {"tool": tool_name, "args": args or {}},
    )
    return True


async def handle_confirmation(
    *,
    conversation_id: str,
    decision: bool,
    executor,
) -> ConfirmResponse:
    memory = get_conversation_memory()
    pending = memory.get_pending_action(conversation_id)
    if pending is None:
        return ConfirmResponse(
            conversation_id=conversation_id,
            message="No action is currently pending confirmation.",
        )

    tool_name = pending.get("tool")
    args = pending.get("args", {})
    memory.clear_pending_action(conversation_id)

    if not decision:
        return ConfirmResponse(
            conversation_id=conversation_id,
            message=f"Action '{tool_name}' was NOT executed.",
        )

    result = await executor.execute(tool_name, args, explicit_intent=True)
    tc = ToolCallResult(
        name=tool_name,
        arguments=args,
        status=result.status.value if hasattr(result.status, "value") else str(result.status),
        result=result.data if hasattr(result, "data") else None,
        error=result.error if hasattr(result, "error") else None,
    )
    if (getattr(tc, "status", "") == "ok"):
        msg = f"Action '{tool_name}' completed successfully."
    else:
        msg = f"Action '{tool_name}' failed: {tc.error}"
    return ConfirmResponse(
        conversation_id=conversation_id,
        message=msg,
        tool_results=[tc],
    )
