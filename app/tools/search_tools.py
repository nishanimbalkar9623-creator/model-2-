"""Search tools (read-only)."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.tools import PermissionLevel, ToolDefinition, ToolKind


class SearchTasksInput(BaseModel):
    client_id: str = Field(..., description="AOS client identifier")
    query: Optional[str] = Field(default=None)
    status: Optional[str] = Field(default=None)


def register_search_tools(reg) -> None:
    from app.tools.registry import ToolDefinition

    reg.register(
        ToolDefinition(
            name="search_tasks",
            description="Search tasks belonging to a client.",
            input_model=SearchTasksInput,
            kind=ToolKind.READ,
            permission=PermissionLevel.VIEW,
        )
    )
