"""Recording-policy schemas — the per-number configuration."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.db.enums import NumberKind
from app.schemas.common import ORMModel
from app.services.phone import InvalidPhoneNumber, normalize


class PolicyCreate(BaseModel):
    e164: str
    label: str | None = Field(default=None, max_length=160)
    kind: NumberKind = NumberKind.AGENT
    owner_agent_id: str | None = None
    recording_enabled: bool = False
    record_inbound: bool = True
    record_outbound: bool = True
    consent_required: bool = True
    consent_prompt: str | None = None
    retention_days: int | None = Field(default=None, ge=0, le=3650)
    notes: str | None = None

    @field_validator("e164")
    @classmethod
    def _normalize(cls, value: str) -> str:
        try:
            return normalize(value)
        except InvalidPhoneNumber as exc:
            raise ValueError(str(exc)) from exc


class PolicyUpdate(BaseModel):
    label: str | None = None
    kind: NumberKind | None = None
    owner_agent_id: str | None = None
    recording_enabled: bool | None = None
    record_inbound: bool | None = None
    record_outbound: bool | None = None
    consent_required: bool | None = None
    consent_prompt: str | None = None
    retention_days: int | None = Field(default=None, ge=0, le=3650)
    notes: str | None = None


class PolicyOut(ORMModel):
    id: str
    org_id: str
    e164: str
    label: str | None = None
    kind: str
    owner_agent_id: str | None = None
    recording_enabled: bool
    record_inbound: bool
    record_outbound: bool
    consent_required: bool
    consent_prompt: str | None = None
    retention_days: int | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class PolicyDecision(BaseModel):
    """What the handset is told to do for a given number and direction."""

    number: str
    should_record: bool
    reason: str
    consent_required: bool = True
    consent_prompt: str | None = None
    policy_id: str | None = None
    retention_days: int | None = None
