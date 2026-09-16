"""Lead schemas — the pipeline's per-call lead/other verdict."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.db.enums import LeadStatus
from app.schemas.common import ORMModel


class LeadOut(ORMModel):
    id: str
    org_id: str
    call_id: str
    agent_id: str | None = None
    customer_number: str
    customer_name: str | None = None
    lead_name: str | None = None
    lead_email: str | None = None
    purpose: str | None = None
    intent: str | None = None
    category: str
    confidence: float
    reason: str | None = None
    source_quote: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class LeadListItem(LeadOut):
    """Row shape for the leads table — joins in just enough to render it."""

    agent_name: str | None = None
    call_started_at: datetime | None = None


class LeadUpdate(BaseModel):
    status: LeadStatus
