"""Agent and presence schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.db.enums import AgentStatus
from app.schemas.common import ORMModel
from app.services.phone import InvalidPhoneNumber, normalize


class AgentCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=160)
    phone_number: str
    employee_code: str | None = Field(default=None, max_length=40)
    team: str | None = Field(default=None, max_length=80)
    # Optionally provision a dashboard login at the same time.
    email: str | None = None
    password: str | None = Field(default=None, min_length=10, max_length=200)

    @field_validator("phone_number")
    @classmethod
    def _e164(cls, value: str) -> str:
        try:
            return normalize(value)
        except InvalidPhoneNumber as exc:
            raise ValueError(str(exc)) from exc


class AgentUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=160)
    team: str | None = Field(default=None, max_length=80)
    employee_code: str | None = Field(default=None, max_length=40)
    is_active: bool | None = None


class AgentOut(ORMModel):
    id: str
    org_id: str
    display_name: str
    phone_number: str
    employee_code: str | None = None
    team: str | None = None
    status: str
    status_changed_at: datetime | None = None
    last_seen_at: datetime | None = None
    current_call_id: str | None = None
    is_active: bool


class AgentWithStats(AgentOut):
    calls_today: int = 0
    calls_in_range: int = 0
    avg_sentiment: float | None = None
    satisfied_rate: float | None = None
    avg_duration_seconds: float | None = None
    filler_rate: float | None = None
    open_tasks: int = 0


class StatusUpdate(BaseModel):
    status: AgentStatus
    call_id: str | None = None


class PresenceSnapshot(BaseModel):
    total_agents: int
    online: int
    available: int
    on_call: int
    wrap_up: int
    on_break: int
    offline: int
    updated_at: datetime
