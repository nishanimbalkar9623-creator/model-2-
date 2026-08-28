"""Document search & fetch tools."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.tools import PermissionLevel, ToolDefinition, ToolKind


class GetClientDocumentsInput(BaseModel):
    client_id: str = Field(..., description="AOS client identifier")
    doc_type: Optional[str] = Field(
        default=None, description="Optional filter: invoice, gstr, tally, bank, notice, etc."
    )
    limit: int = Field(default=20, ge=1, le=100)


class SearchClientDocumentsInput(BaseModel):
    client_id: str = Field(..., description="AOS client identifier")
    query: str = Field(..., description="Full-text search query over document metadata/content")
    top_k: int = Field(default=5, ge=1, le=20)


def register_document_tools(reg) -> None:
    from app.tools.registry import ToolDefinition

    reg.register(
        ToolDefinition(
            name="get_client_documents",
            description="Fetch the list of documents uploaded against a client.",
            input_model=GetClientDocumentsInput,
            kind=ToolKind.READ,
            permission=PermissionLevel.VIEW,
        )
    )
    reg.register(
        ToolDefinition(
            name="search_client_documents",
            description="Search inside client documents (GST returns, Tally exports, notices).",
            input_model=SearchClientDocumentsInput,
            kind=ToolKind.READ,
            permission=PermissionLevel.VIEW,
        )
    )
