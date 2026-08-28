"""Chat endpoints (non-streaming + SSE streaming)."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from app.schemas.chat import ChatRequest, ChatResponse, ConfirmationRequest, ConfirmResponse

router = APIRouter(prefix="/api/v1")


def _get_orchestrator(request: Request):
    return request.app.state.orchestrator


@router.post("/chat")
async def chat(body: ChatRequest, request: Request) -> ChatResponse:
    orch = _get_orchestrator(request)
    return await orch.run(
        message=body.message,
        client_id=body.client_id,
        conversation_id=body.conversation_id,
        user_id=body.user_id,
        user_role=body.user_role,
    )


@router.post("/chat/stream")
async def chat_stream(body: ChatRequest, request: Request) -> EventSourceResponse:
    orch = _get_orchestrator(request)

    async def event_gen() -> AsyncIterator[Dict[str, Any]]:
        from app.schemas.chat import ChatResponse

        yield {"event": "start", "data": json.dumps({"state": "thinking"})}

        # Stream the agent execution
        async for event in orch.run_stream(
            message=body.message,
            client_id=body.client_id,
            conversation_id=body.conversation_id,
            user_id=body.user_id,
            user_role=body.user_role,
        ):
            yield event

    return EventSourceResponse(event_gen())


@router.post("/chat/confirm")
async def confirm(body: ConfirmationRequest, request: Request) -> ConfirmResponse:
    orch = _get_orchestrator(request)
    from app.agent.confirmation import handle_confirmation

    executor = orch.get_executor()
    return await handle_confirmation(
        conversation_id=body.conversation_id,
        decision=body.decision,
        executor=executor,
    )
