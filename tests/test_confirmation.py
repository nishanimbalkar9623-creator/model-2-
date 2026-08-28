"""Tests for confirmation flow and mutating-action gating."""

from __future__ import annotations

from unittest.mock import AsyncMock

from app.memory.conversation import ConversationMemory, get_conversation_memory
from app.schemas.chat import ConfirmResponse


def test_confirmation_gate_persists_pending():
    from app.agent.confirmation import create_confirmation_gate

    memory = ConversationMemory()
    # use a locally isolated memory by monkeypatching getter via module state
    from app.agent import confirmation as conf

    conf.get_conversation_memory = lambda: memory

    create_confirmation_gate("c1", "create_task", {"title": "x"}, True)
    pending = memory.get_pending_action("c1")
    assert pending["tool"] == "create_task"


async def test_confirmation_deny_does_not_execute():
    from app.agent.confirmation import handle_confirmation

    memory = ConversationMemory()
    from app.agent import confirmation as conf

    conf.get_conversation_memory = lambda: memory
    memory.set_pending_action("c1", {"tool": "generate_tally_export", "args": {"client_id": "x"}})

    executor = AsyncMock()
    result = await handle_confirmation(
        conversation_id="c1",
        decision=False,
        executor=executor,
    )
    assert isinstance(result, ConfirmResponse)
    executor.execute.assert_not_called()


async def test_confirmation_yes_executes():
    from app.agent.confirmation import handle_confirmation
    from app.schemas.tools import ToolResult, ToolStatus

    memory = ConversationMemory()
    from app.agent import confirmation as conf

    conf.get_conversation_memory = lambda: memory
    memory.set_pending_action("c1", {"tool": "create_task", "args": {"title": "t"}})

    executor = AsyncMock()
    executor.execute.return_value = ToolResult(name="create_task", status=ToolStatus.OK, data={"id": 1})
    result = await handle_confirmation(
        conversation_id="c1",
        decision=True,
        executor=executor,
    )
    executor.execute.assert_awaited_once()
    assert result.tool_results[0].status == "ok"


def test_no_pending_action():
    from app.agent.confirmation import handle_confirmation
    import asyncio

    memory = ConversationMemory()
    from app.agent import confirmation as conf

    conf.get_conversation_memory = lambda: memory
    result = asyncio.run(
        handle_confirmation(conversation_id="c9", decision=True, executor=AsyncMock())
    )
    assert result.message
