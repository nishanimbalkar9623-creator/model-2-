"""Workflow-aware tools: pending work, deadlines, client requests."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.tools import PermissionLevel, ToolDefinition, ToolKind


class GetPendingWorkInput(BaseModel):
    client_id: Optional[str] = Field(default=None, description="Scope to one client if provided")
    due_before: Optional[str] = Field(default=None, description="ISO date")


class GetUpcomingDeadlinesInput(BaseModel):
    days_ahead: int = Field(default=30, ge=1, le=365)
    client_id: Optional[str] = Field(default=None)


class GetClientRequestsInput(BaseModel):
    client_id: Optional[str] = Field(default=None)
    status: Optional[str] = Field(default=None, description="open | pending | closed")


class CreateClientRequestInput(BaseModel):
    client_id: str = Field(..., description="AOS client identifier")
    subject: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = Field(default=None)


class RunGstReconciliationInput(BaseModel):
    client_id: str = Field(..., description="AOS client identifier")
    period: Optional[str] = Field(default=None)


def register_workflow_tools(reg) -> None:
    from app.tools.registry import ToolDefinition

    reg.register(
        ToolDefinition(
            name="get_pending_work",
            description="List outstanding work items for a client (or all clients).",
            input_model=GetPendingWorkInput,
            kind=ToolKind.READ,
            permission=PermissionLevel.VIEW,
        )
    )
    reg.register(
        ToolDefinition(
            name="get_upcoming_deadlines",
            description="List upcoming compliance / filing deadlines.",
            input_model=GetUpcomingDeadlinesInput,
            kind=ToolKind.READ,
            permission=PermissionLevel.VIEW,
        )
    )
    reg.register(
        ToolDefinition(
            name="get_client_requests",
            description="Client requests / help tickets raised against the client.",
            input_model=GetClientRequestsInput,
            kind=ToolKind.READ,
            permission=PermissionLevel.VIEW,
        )
    )
    reg.register(
        ToolDefinition(
            name="create_client_request",
            description="Raise a client request / note (non-destructive).",
            input_model=CreateClientRequestInput,
            kind=ToolKind.ACTION,
            permission=PermissionLevel.MANAGE,
            requires_confirmation=False,
        )
    )
    reg.register(
        ToolDefinition(
            name="run_gst_reconciliation",
            description="Trigger a GST reconciliation job for a client. This is high-impact.",
            input_model=RunGstReconciliationInput,
            kind=ToolKind.ACTION,
            permission=PermissionLevel.MANAGE,
            requires_confirmation=True,
        )
    )
