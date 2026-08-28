"""Client-scoped read tools."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.tools import PermissionLevel, ToolDefinition, ToolKind


class ListClientsInput(BaseModel):
    query: str = Field(default="", description="Optional free-text filter")


class GetClientInput(BaseModel):
    client_id: str = Field(..., description="AOS client identifier")


class GetClientServicesInput(BaseModel):
    client_id: str = Field(..., description="AOS client identifier")


class GetClientStatusInput(BaseModel):
    client_id: str = Field(..., description="AOS client identifier")


class GetClientActivitiesInput(BaseModel):
    client_id: str = Field(..., description="AOS client identifier")
    limit: int = Field(default=20, ge=1, le=100)


class GetClientMeetingsInput(BaseModel):
    client_id: str = Field(..., description="AOS client identifier")
    status: Optional[str] = Field(default=None, description="scheduled | done | cancelled")
    limit: int = Field(default=20, ge=1, le=100)


def register_client_tools(reg) -> None:
    from app.backend.client import BackendClient
    from app.tools.registry import ToolDefinition

    def _h(backend: BackendClient):
        return backend

    reg.register(
        ToolDefinition(
            name="list_clients",
            description="List clients the current user is authorised to view.",
            input_model=ListClientsInput,
            kind=ToolKind.READ,
            permission=PermissionLevel.VIEW,
        )
    )
    reg.register(
        ToolDefinition(
            name="get_client",
            description="Fetch a specific client's identity/org details.",
            input_model=GetClientInput,
            kind=ToolKind.READ,
            permission=PermissionLevel.VIEW,
        )
    )
    reg.register(
        ToolDefinition(
            name="get_client_services",
            description="Get the service configuration (GST, TDS, Books, etc.) for a client.",
            input_model=GetClientServicesInput,
            kind=ToolKind.READ,
            permission=PermissionLevel.VIEW,
        )
    )
    reg.register(
        ToolDefinition(
            name="get_client_status",
            description="Get the current work status / state of a client.",
            input_model=GetClientStatusInput,
            kind=ToolKind.READ,
            permission=PermissionLevel.VIEW,
        )
    )
    reg.register(
        ToolDefinition(
            name="get_client_activities",
            description="Recent activities / events for a client (audit trail).",
            input_model=GetClientActivitiesInput,
            kind=ToolKind.READ,
            permission=PermissionLevel.VIEW,
        )
    )
    reg.register(
        ToolDefinition(
            name="get_client_meetings",
            description="Get upcoming or past meetings for a client.",
            input_model=GetClientMeetingsInput,
            kind=ToolKind.READ,
            permission=PermissionLevel.VIEW,
        )
    )
