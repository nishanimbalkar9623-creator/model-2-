"""Report generation & export tools."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.tools import PermissionLevel, ToolDefinition, ToolKind


class GenerateClientReportInput(BaseModel):
    client_id: str = Field(..., description="AOS client identifier")
    report_type: str = Field(
        ...,
        description="e.g. monthly-work-summary, reconciliation-report, compliance-status",
    )
    period: str = Field(..., description="e.g. FY2024-25, Apr-2025")
    include_ai_generated: bool = Field(
        default=True,
        description="Whether the report may include an AI-written section.",
    )


class GenerateTallyExportInput(BaseModel):
    client_id: str = Field(..., description="AOS client identifier")
    financial_year: str = Field(..., description="e.g. FY2024-25")


def register_report_tools(reg) -> None:
    from app.tools.registry import ToolDefinition

    reg.register(
        ToolDefinition(
            name="generate_client_report",
            description="Ask the backend to generate a report for a client.",
            input_model=GenerateClientReportInput,
            kind=ToolKind.ACTION,
            permission=PermissionLevel.MANAGE,
            requires_confirmation=False,
        )
    )
    reg.register(
        ToolDefinition(
            name="generate_tally_export",
            description="Ask the backend to prepare a Tally-compatible export. High-impact.",
            input_model=GenerateTallyExportInput,
            kind=ToolKind.ACTION,
            permission=PermissionLevel.MANAGE,
            requires_confirmation=True,
        )
    )
