"""Call, transcript and analysis schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.db.enums import ActionItemStatus, CallDirection, CallStatus, Priority
from app.schemas.common import ORMModel
from app.services.phone import InvalidPhoneNumber, normalize


class CallCreate(BaseModel):
    """Posted by the handset when a call ends."""

    external_ref: str | None = Field(default=None, max_length=80)
    direction: CallDirection
    customer_number: str
    customer_name: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: int | None = Field(default=None, ge=0)
    status: CallStatus = CallStatus.COMPLETED
    disposition: str | None = Field(default=None, max_length=80)
    recording_expected: bool = False
    recording_skipped_reason: str | None = Field(default=None, max_length=120)
    metadata: dict = Field(default_factory=dict)

    @field_validator("customer_number")
    @classmethod
    def _e164(cls, value: str) -> str:
        try:
            return normalize(value)
        except InvalidPhoneNumber as exc:
            raise ValueError(str(exc)) from exc


class CallOut(ORMModel):
    id: str
    org_id: str
    agent_id: str
    external_ref: str | None = None
    direction: str
    agent_number: str
    customer_number: str
    customer_name: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: int | None = None
    status: str
    disposition: str | None = None
    recording_expected: bool
    recording_skipped_reason: str | None = None
    has_recording: bool
    created_at: datetime


class CallListItem(CallOut):
    """Row shape for the calls table — joins in just enough to render it."""

    agent_name: str | None = None
    agent_team: str | None = None
    sentiment_overall: str | None = None
    sentiment_score: float | None = None
    customer_satisfied: bool | None = None
    csat_score: int | None = None
    has_transcript: bool = False
    has_analysis: bool = False
    processing_status: str = "pending"
    open_tasks: int = 0


class SegmentOut(ORMModel):
    id: str
    idx: int
    speaker: str
    start_ms: int
    end_ms: int
    text: str
    confidence: float | None = None
    tone_label: str | None = None
    tone_confidence: float | None = None
    valence: float | None = None
    arousal: float | None = None
    sentiment: str | None = None


class TranscriptOut(ORMModel):
    id: str
    call_id: str
    provider: str
    model: str | None = None
    language: str | None = None
    full_text: str
    word_count: int
    confidence: float | None = None
    tone_overall: str | None = None
    created_at: datetime
    segments: list[SegmentOut] = Field(default_factory=list)


class ActionItemOut(ORMModel):
    id: str
    call_id: str
    kind: str
    title: str
    description: str | None = None
    owner_role: str | None = None
    assignee_agent_id: str | None = None
    priority: str
    due_at: datetime | None = None
    due_hint: str | None = None
    status: str
    source_quote: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class ActionItemWithCall(ActionItemOut):
    agent_name: str | None = None
    customer_number: str | None = None
    call_started_at: datetime | None = None


class ActionItemUpdate(BaseModel):
    status: ActionItemStatus | None = None
    priority: Priority | None = None
    assignee_agent_id: str | None = None
    due_at: datetime | None = None


class AnalysisOut(ORMModel):
    id: str
    call_id: str
    provider: str
    model: str | None = None
    summary: str
    sentiment_overall: str
    sentiment_score: float
    customer_satisfied: bool | None = None
    csat_score: int | None = None
    csat_confidence: float | None = None
    csat_evidence: str | None = None
    agent_talk_ratio: float | None = None
    interruption_count: int | None = None
    resolution_status: str | None = None
    topics: list = Field(default_factory=list)
    keywords: list = Field(default_factory=list)
    stopword_stats: dict = Field(default_factory=dict)
    filler_stats: dict = Field(default_factory=dict)
    risk_flags: list = Field(default_factory=list)
    coaching: dict = Field(default_factory=dict)
    sentiment_timeline: list = Field(default_factory=list)
    tone_summary: dict = Field(default_factory=dict)
    processing_ms: int | None = None
    created_at: datetime


class RecordingOut(ORMModel):
    id: str
    call_id: str
    status: str
    mime_type: str
    size_bytes: int | None = None
    duration_seconds: float | None = None
    consent_captured: bool
    uploaded_at: datetime | None = None
    purge_after: datetime | None = None
    purged_at: datetime | None = None


class JobOut(ORMModel):
    id: str
    stage: str
    status: str
    attempts: int
    max_attempts: int
    last_error: str | None = None
    scheduled_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class CallDetail(CallOut):
    agent_name: str | None = None
    agent_team: str | None = None
    recording: RecordingOut | None = None
    transcript: TranscriptOut | None = None
    analysis: AnalysisOut | None = None
    action_items: list[ActionItemOut] = Field(default_factory=list)
    jobs: list[JobOut] = Field(default_factory=list)
