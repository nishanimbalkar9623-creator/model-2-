"""Task management tools (create/update)."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.tools import PermissionLevel, ToolDefinition, ToolKind


class CreateTaskInput(BaseModel):
    client_id: Optional[str] = Field(default=None, description="Client this task belongs to")
    title: str = Field(..., min_length=2, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    due: Optional[str] = Field(default=None, description="ISO date-time")
    assignee: Optional[str] = Field(default=None, description="user id of assignee")
    priority: str = Field(default="medium", pattern="^(low|medium|high|urgent)$")


class UpdateTaskInput(BaseModel):
    task_id: str = Field(..., min_length=1)
    status: Optional[str] = Field(default=None, pattern="^(todo|in_progress|done|blocked)$")
    title: Optional[str] = Field(default=None, max_length=200)
    assignee: Optional[str] = Field(default=None)
    due: Optional[str] = Field(default=None)


def register_task_tools(reg) -> None:
    from app.tools.registry import ToolDefinition

    reg.register(
        ToolDefinition(
            name="create_task",
            description="Create a new task in AOS.",
            input_model=CreateTaskInput,
            kind=ToolKind.ACTION,
            permission=PermissionLevel.MANAGE,
            requires_confirmation=False,
        )
    )
    reg.register(
        ToolDefinition(
            name="update_task",
            description="Update a task status / fields.",
            input_model=UpdateTaskInput,
            kind=ToolKind.ACTION,
            permission=PermissionLevel.MANAGE,
            requires_confirmation=False,
        )
    )
