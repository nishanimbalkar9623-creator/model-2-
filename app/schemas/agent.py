"""Agent state / routing schemas."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from enum import Enum

from pydantic import BaseModel, Field


class IntentType(str, Enum):
    GENERAL = "general"
    CLIENT_SPECIFIC = "client_specific"
    ACTION = "action"
    DATA_ANALYSIS = "data_analysis"
    REPORT = "report"
    UNKNOWN = "unknown"


class UserContext(BaseModel):
    user_id: Optional[str] = None
    user_role: Optional[str] = None


class ClientContext(BaseModel):
    """Client context always obtained from the backend, never from user input."""

    client_id: Optional[str] = None
    client_name: Optional[str] = None
    organization_name: Optional[str] = None
    financial_year: Optional[str] = None
    selected_services: List[str] = Field(default_factory=list)
    industry: Optional[str] = None
    current_period: Optional[str] = None
    user_id: Optional[str] = None
    user_role: Optional[str] = None

    def scoped(self) -> bool:
        return bool(self.client_id)


class AgentStep(BaseModel):
    plan: str
    status: str = "pending"
    tool_calls: List[Any] = Field(default_factory=list)
