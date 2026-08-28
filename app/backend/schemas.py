"""Schemas for the Backend API contract.

The Backend Repo (FastAPI + PostgreSQL) is authoritative for all business
data. The AI Engine only ever talks to it through these shaped payloads.
These must match what the backend exposes — see docs/integration.md.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Client(BaseModel):
    id: str
    name: str
    organization_name: Optional[str] = None
    financial_year: Optional[str] = None
    industry: Optional[str] = None
    current_period: Optional[str] = None


class ClientServiceConfig(BaseModel):
    client_id: str
    selected_services: List[str] = Field(default_factory=list)
    services: Dict[str, Any] = Field(default_factory=dict)


class ClientStatus(BaseModel):
    client_id: str
    status: str
    current_period: Optional[str] = None
    summary: Optional[str] = None


class Activity(BaseModel):
    id: str
    client_id: Optional[str] = None
    type: str
    description: str
    occurred_at: Optional[str] = None
    actor_user_id: Optional[str] = None


class Document(BaseModel):
    id: str
    client_id: Optional[str] = None
    title: str
    doc_type: Optional[str] = None
    created_at: Optional[str] = None
    url: Optional[str] = None


class PendingItem(BaseModel):
    id: str
    client_id: Optional[str] = None
    title: str
    due: Optional[str] = None
    status: str = "pending"


class Deadline(BaseModel):
    id: str
    client_id: Optional[str] = None
    title: str
    due_date: str
    category: Optional[str] = None


class Meeting(BaseModel):
    id: str
    client_id: Optional[str] = None
    title: str
    scheduled_at: str
    status: Optional[str] = None


class ReconciliationSummary(BaseModel):
    client_id: str
    overall_status: str
    total_transactions: int = 0
    matched: int = 0
    mismatches: int = 0
    period: Optional[str] = None


class ReconciliationException(BaseModel):
    id: str
    client_id: Optional[str] = None
    description: str
    amount: Optional[float] = None
    status: str = "open"


class BankTransaction(BaseModel):
    id: str
    client_id: Optional[str] = None
    date: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[float] = None
    status: str = "unreviewed"


class ClientRequest(BaseModel):
    id: str
    client_id: Optional[str] = None
    subject: str
    status: str
    created_at: Optional[str] = None


class AuthContext(BaseModel):
    user_id: str
    user_role: str = "user"
    permissions: List[str] = Field(default_factory=list)
    accessible_client_ids: List[str] = Field(default_factory=list)
