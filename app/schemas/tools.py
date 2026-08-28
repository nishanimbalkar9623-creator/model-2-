"""Tool descriptor and validation schemas for the tool registry."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ToolKind(str, Enum):
    READ = "read"
    ACTION = "action"


class PermissionLevel(str, Enum):
    VIEW = "view"
    MANAGE = "manage"
    ADMIN = "admin"


class ToolStatus(str, Enum):
    OK = "ok"
    BLOCKED = "blocked"
    ERROR = "error"
    NEEDS_CONFIRMATION = "needs_confirmation"


class ToolDescriptor(BaseModel):
    name: str
    description: str
    parameters_schema: Dict[str, Any] = Field(default_factory=dict)
    kind: ToolKind
    permission: PermissionLevel = PermissionLevel.VIEW
    requires_confirmation: bool = False
    destructive: bool = False


class ToolResult(BaseModel):
    name: str
    status: ToolStatus = ToolStatus.OK
    data: Any = None
    error: Optional[str] = None


class ToolDefinition:
    """A concrete tool the agent can invoke.

    Kept here to avoid circular imports between app/tools modules.
    """

    def __init__(
        self,
        name: str,
        description: str,
        input_model,
        kind: ToolKind,
        *,
        permission: PermissionLevel = PermissionLevel.VIEW,
        requires_confirmation: bool = False,
        destructive: bool = False,
        handler=None,
    ):
        self.name = name
        self.description = description
        self.input_model = input_model
        self.kind = kind
        self.permission = permission
        self.requires_confirmation = requires_confirmation
        self.destructive = destructive
        self.handler = handler

    @property
    def descriptor(self) -> ToolDescriptor:
        return ToolDescriptor(
            name=self.name,
            description=self.description,
            parameters_schema=(
                self.input_model.model_json_schema() if self.input_model else {}
            ),
            kind=self.kind,
            permission=self.permission,
            requires_confirmation=self.requires_confirmation,
            destructive=self.destructive,
        )

    async def execute(self, args, **kwargs):
        """Default handler — subclasses / callers override."""
        if self.handler:
            return await self.handler(args, **kwargs)
        return {}


class ToolCall(BaseModel):
    name: str
    args: Dict[str, Any] = Field(default_factory=dict)
