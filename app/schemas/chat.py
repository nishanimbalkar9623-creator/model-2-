"""Chat-related request/response schemas for the AI Engine."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000, description="User message")
    client_id: Optional[str] = None
    conversation_id: Optional[str] = None
    user_id: Optional[str] = None
    user_role: Optional[str] = None


class ToolCallResult(BaseModel):
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    status: str = Field(..., description="ok | blocked | error | needs_confirmation")
    result: Any = None
    error: Optional[str] = None


class Source(BaseModel):
    source_type: str = Field(..., description="knowledge | client_document | backend")
    client_id: Optional[str] = None
    document_id: Optional[str] = None
    title: Optional[str] = None
    page: Optional[int] = None
    url: Optional[str] = None
    created_at: Optional[str] = None


class SuggestedAction(BaseModel):
    label: str
    tool: Optional[str] = None
    arguments: Dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    conversation_id: str = ""
    user_id: Optional[str] = None
    message: str = ""
    tool_calls: List[ToolCallResult] = Field(default_factory=list)
    requires_confirmation: bool = False
    pending_confirmation: Optional[str] = Field(
        None, description="tool name awaiting confirmation"
    )
    pending_confirmation_args: Dict[str, Any] = Field(default_factory=dict)
    suggested_actions: List[SuggestedAction] = Field(default_factory=list)
    sources: List[Source] = Field(default_factory=list)
    request_id: str = ""


class ConfirmationRequest(BaseModel):
    """Payload to confirm/deny a pending action in a conversation."""

    conversation_id: str
    decision: bool
    confirmation_id: Optional[str] = None


class ConfirmResponse(BaseModel):
    conversation_id: str = ""
    message: str = ""
    tool_results: List[ToolCallResult] = Field(default_factory=list)
