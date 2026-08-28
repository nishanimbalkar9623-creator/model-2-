"""Meeting tools."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.tools import PermissionLevel, ToolDefinition, ToolKind


class CreateMeetingInput(BaseModel):
    client_id: Optional[str] = Field(default=None)
    title: str = Field(..., min_length=2, max_length=200)
    scheduled_at: str = Field(..., description="ISO date-time for the meeting")
    duration_minutes: int = Field(default=60, ge=5, le=480)
    attendees: list[str] = Field(default_factory=list)


class UpdateMeetingInput(BaseModel):
    meeting_id: str = Field(..., min_length=1)
    status: Optional[str] = Field(default=None, pattern="^(scheduled|done|cancelled|rescheduled)$")
    reschedule_to: Optional[str] = Field(default=None, description="ISO date-time")


def register_meeting_tools(reg) -> None:
    from app.tools.registry import ToolDefinition

    reg.register(
        ToolDefinition(
            name="create_meeting",
            description="Schedule a meeting with / for a client.",
            input_model=CreateMeetingInput,
            kind=ToolKind.ACTION,
            permission=PermissionLevel.MANAGE,
            requires_confirmation=False,
        )
    )
    reg.register(
        ToolDefinition(
            name="update_meeting",
            description="Update a meeting's status or reschedule it.",
            input_model=UpdateMeetingInput,
            kind=ToolKind.ACTION,
            permission=PermissionLevel.MANAGE,
            requires_confirmation=False,
        )
    )
