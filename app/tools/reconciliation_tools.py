"""Reconciliation & bank processing tools."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.tools import PermissionLevel, ToolDefinition, ToolKind


class GetReconciliationSummaryInput(BaseModel):
    client_id: str = Field(..., description="AOS client identifier")
    period: Optional[str] = Field(default=None)


class GetReconciliationExceptionsInput(BaseModel):
    client_id: str = Field(..., description="AOS client identifier")
    status: Optional[str] = Field(default=None, description="open | matched")


class GetUnreviewedBankTransactionsInput(BaseModel):
    client_id: str = Field(..., description="AOS client identifier")
    limit: int = Field(default=50, ge=1, le=200)


class ProcessBankStatementInput(BaseModel):
    client_id: str = Field(..., description="AOS client identifier")
    document_id: Optional[str] = Field(default=None)


def register_reconciliation_tools(reg) -> None:
    from app.tools.registry import ToolDefinition

    reg.register(
        ToolDefinition(
            name="get_reconciliation_summary",
            description="High-level GST / bank reconciliation result for a client.",
            input_model=GetReconciliationSummaryInput,
            kind=ToolKind.READ,
            permission=PermissionLevel.VIEW,
        )
    )
    reg.register(
        ToolDefinition(
            name="get_reconciliation_exceptions",
            description="List mismatches / exceptions found during reconciliation.",
            input_model=GetReconciliationExceptionsInput,
            kind=ToolKind.READ,
            permission=PermissionLevel.VIEW,
        )
    )
    reg.register(
        ToolDefinition(
            name="get_unreviewed_bank_transactions",
            description="Bank statement transactions not yet reviewed by the team.",
            input_model=GetUnreviewedBankTransactionsInput,
            kind=ToolKind.READ,
            permission=PermissionLevel.VIEW,
        )
    )
    reg.register(
        ToolDefinition(
            name="process_bank_statement",
            description="Ask the backend to process a bank statement document.",
            input_model=ProcessBankStatementInput,
            kind=ToolKind.ACTION,
            permission=PermissionLevel.MANAGE,
            requires_confirmation=False,
        )
    )
