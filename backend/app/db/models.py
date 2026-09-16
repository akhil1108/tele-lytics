"""SQLAlchemy models for the Tele-lytics platform.

Every tenant-scoped table carries `org_id` directly (rather than relying on a
join to reach it) so that every query can filter on the tenant boundary with a
single indexed predicate.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    Base,
    UTCDateTime,
    created_at_column,
    fk_column,
    pk_column,
    updated_at_column,
)
from app.db.enums import (
    ActionItemKind,
    ActionItemStatus,
    AgentStatus,
    CallStatus,
    DevicePlatform,
    JobStatus,
    LeadCategory,
    LeadStatus,
    NumberKind,
    Priority,
    ProcessingStage,
    RecordingStatus,
    Sentiment,
    Speaker,
    UserRole,
)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = pk_column()
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata", nullable=False)
    retention_days: Mapped[int] = mapped_column(Integer, default=90, nullable=False)
    settings: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    users: Mapped[list[User]] = relationship(back_populates="organization")
    agents: Mapped[list[Agent]] = relationship(back_populates="organization")


class User(Base):
    """A dashboard login. Agents may or may not have one."""

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("org_id", "email", name="uq_users_org_email"),)

    id: Mapped[str] = pk_column()
    org_id: Mapped[str] = fk_column("organizations.id")
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default=UserRole.AGENT, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    organization: Mapped[Organization] = relationship(back_populates="users")
    agent: Mapped[Agent | None] = relationship(back_populates="user", uselist=False)


class Agent(Base):
    """A person who takes calls, identified to the platform by their phone number."""

    __tablename__ = "agents"
    __table_args__ = (
        UniqueConstraint("org_id", "phone_number", name="uq_agents_org_number"),
        UniqueConstraint("org_id", "employee_code", name="uq_agents_org_code"),
        Index("ix_agents_org_status", "org_id", "status"),
    )

    id: Mapped[str] = pk_column()
    org_id: Mapped[str] = fk_column("organizations.id")
    user_id: Mapped[str | None] = fk_column("users.id", nullable=True, ondelete="SET NULL")
    employee_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    # E.164, e.g. +919876543210. This is the key the mobile app registers with.
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    team: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=AgentStatus.OFFLINE, nullable=False)
    status_changed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    current_call_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    organization: Mapped[Organization] = relationship(back_populates="agents")
    user: Mapped[User | None] = relationship(back_populates="agent")
    calls: Mapped[list[Call]] = relationship(back_populates="agent")
    devices: Mapped[list[Device]] = relationship(back_populates="agent")


class PhoneNumberPolicy(Base):
    """Per-number recording configuration.

    This is what the dashboard means by "is recording set for this number?" and
    what the mobile app consults before it starts capturing audio.
    """

    __tablename__ = "phone_number_policies"
    __table_args__ = (
        UniqueConstraint("org_id", "e164", name="uq_number_policy_org_e164"),
        Index("ix_number_policy_org_enabled", "org_id", "recording_enabled"),
    )

    id: Mapped[str] = pk_column()
    org_id: Mapped[str] = fk_column("organizations.id")
    e164: Mapped[str] = mapped_column(String(20), nullable=False)
    label: Mapped[str | None] = mapped_column(String(160), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), default=NumberKind.AGENT, nullable=False)
    owner_agent_id: Mapped[str | None] = fk_column("agents.id", nullable=True, ondelete="SET NULL")

    recording_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    record_inbound: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    record_outbound: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    consent_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    consent_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_user_id: Mapped[str | None] = fk_column(
        "users.id", nullable=True, ondelete="SET NULL"
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class RatingParameter(Base):
    """A supervisor-defined criterion every call is scored against, e.g. "Politeness".

    Scored by the stage-2 insight model on `[scale_min, scale_max]`. Deleting a
    parameter does not touch past scores — `Analysis.custom_ratings` snapshots
    the name and scale actually used at the time, so history stays readable.
    """

    __tablename__ = "rating_parameters"
    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_rating_parameters_org_name"),
        Index("ix_rating_parameters_org_active", "org_id", "is_active"),
    )

    id: Mapped[str] = pk_column()
    org_id: Mapped[str] = fk_column("organizations.id")
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    scale_min: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    scale_max: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by_user_id: Mapped[str | None] = fk_column(
        "users.id", nullable=True, ondelete="SET NULL"
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class CallCategory(Base):
    """A call type in this org's taxonomy, e.g. "Sales enquiry" or "Vendor call".

    Exactly one active row per org carries `is_default=True` ("Other") — the
    fallback the pipeline assigns when the model's answer matches nothing here,
    and the API refuses to delete it so that fallback always resolves.
    """

    __tablename__ = "call_categories"
    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_call_categories_org_name"),
        Index("ix_call_categories_org_active", "org_id", "is_active"),
    )

    id: Mapped[str] = pk_column()
    org_id: Mapped[str] = fk_column("organizations.id")
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by_user_id: Mapped[str | None] = fk_column(
        "users.id", nullable=True, ondelete="SET NULL"
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class Device(Base):
    """A paired mobile handset. Holds the hash of its long-lived bearer token."""

    __tablename__ = "devices"
    __table_args__ = (Index("ix_devices_org_agent", "org_id", "agent_id"),)

    id: Mapped[str] = pk_column()
    org_id: Mapped[str] = fk_column("organizations.id")
    agent_id: Mapped[str] = fk_column("agents.id")
    platform: Mapped[str] = mapped_column(
        String(16), default=DevicePlatform.ANDROID, nullable=False
    )
    device_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    os_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    app_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    push_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    paired_at: Mapped[datetime] = created_at_column()
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    agent: Mapped[Agent] = relationship(back_populates="devices")

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


class PairingCode(Base):
    """Short-lived code an admin hands an agent to bind their handset."""

    __tablename__ = "pairing_codes"

    id: Mapped[str] = pk_column()
    org_id: Mapped[str] = fk_column("organizations.id")
    agent_id: Mapped[str] = fk_column("agents.id")
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_by_user_id: Mapped[str | None] = fk_column(
        "users.id", nullable=True, ondelete="SET NULL"
    )
    created_at: Mapped[datetime] = created_at_column()


class Call(Base):
    __tablename__ = "calls"
    __table_args__ = (
        UniqueConstraint("org_id", "external_ref", name="uq_calls_org_external_ref"),
        Index("ix_calls_org_started", "org_id", "started_at"),
        Index("ix_calls_org_agent_started", "org_id", "agent_id", "started_at"),
        Index("ix_calls_org_status", "org_id", "status"),
    )

    id: Mapped[str] = pk_column()
    org_id: Mapped[str] = fk_column("organizations.id")
    agent_id: Mapped[str] = fk_column("agents.id")
    # Client-generated identifier; makes the mobile "log a call" call idempotent.
    external_ref: Mapped[str | None] = mapped_column(String(80), nullable=True)

    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    agent_number: Mapped[str] = mapped_column(String(20), nullable=False)
    customer_number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    customer_name: Mapped[str | None] = mapped_column(String(160), nullable=True)

    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(String(20), default=CallStatus.COMPLETED, nullable=False)
    disposition: Mapped[str | None] = mapped_column(String(80), nullable=True)

    # Snapshot of the policy decision made at capture time, for auditability.
    recording_expected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recording_skipped_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    has_recording: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    call_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    agent: Mapped[Agent] = relationship(back_populates="calls")
    recording: Mapped[Recording | None] = relationship(
        back_populates="call", uselist=False, cascade="all, delete-orphan"
    )
    transcript: Mapped[Transcript | None] = relationship(
        back_populates="call", uselist=False, cascade="all, delete-orphan"
    )
    analysis: Mapped[Analysis | None] = relationship(
        back_populates="call", uselist=False, cascade="all, delete-orphan"
    )
    action_items: Mapped[list[ActionItem]] = relationship(
        back_populates="call", cascade="all, delete-orphan"
    )


class Recording(Base):
    __tablename__ = "recordings"
    __table_args__ = (
        UniqueConstraint("call_id", name="uq_recordings_call"),
        Index("ix_recordings_org_status", "org_id", "status"),
    )

    id: Mapped[str] = pk_column()
    org_id: Mapped[str] = fk_column("organizations.id")
    call_id: Mapped[str] = fk_column("calls.id")

    storage_backend: Mapped[str] = mapped_column(String(16), default="local", nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(80), default="audio/mp4", nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), default=RecordingStatus.PENDING_UPLOAD, nullable=False
    )
    consent_captured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    uploaded_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    purge_after: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True, index=True)
    purged_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    call: Mapped[Call] = relationship(back_populates="recording")


class Transcript(Base):
    """Output of stage 1 — speech to text plus per-segment tone."""

    __tablename__ = "transcripts"
    __table_args__ = (UniqueConstraint("call_id", name="uq_transcripts_call"),)

    id: Mapped[str] = pk_column()
    org_id: Mapped[str] = fk_column("organizations.id")
    call_id: Mapped[str] = fk_column("calls.id")

    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    full_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    tone_overall: Mapped[str | None] = mapped_column(String(40), nullable=True)
    processing_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = created_at_column()

    call: Mapped[Call] = relationship(back_populates="transcript")
    segments: Mapped[list[TranscriptSegment]] = relationship(
        back_populates="transcript",
        cascade="all, delete-orphan",
        order_by="TranscriptSegment.idx",
    )


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    __table_args__ = (
        UniqueConstraint("transcript_id", "idx", name="uq_segment_transcript_idx"),
        Index("ix_segments_transcript_start", "transcript_id", "start_ms"),
    )

    id: Mapped[str] = pk_column()
    transcript_id: Mapped[str] = fk_column("transcripts.id")
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[str] = mapped_column(String(16), default=Speaker.UNKNOWN, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Tone as reported by the speech model (stage 1).
    tone_label: Mapped[str | None] = mapped_column(String(40), nullable=True)
    tone_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    valence: Mapped[float | None] = mapped_column(Float, nullable=True)
    arousal: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Sentiment as judged by the analysis model (stage 2).
    sentiment: Mapped[str | None] = mapped_column(String(20), nullable=True)

    transcript: Mapped[Transcript] = relationship(back_populates="segments")


class Analysis(Base):
    """Output of stage 2 — the insight model reading the transcript."""

    __tablename__ = "analyses"
    __table_args__ = (
        UniqueConstraint("call_id", name="uq_analyses_call"),
        Index("ix_analyses_org_created", "org_id", "created_at"),
    )

    id: Mapped[str] = pk_column()
    org_id: Mapped[str] = fk_column("organizations.id")
    call_id: Mapped[str] = fk_column("calls.id")

    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)

    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    sentiment_overall: Mapped[str] = mapped_column(
        String(20), default=Sentiment.NEUTRAL, nullable=False
    )
    # -1.0 (most negative) .. +1.0 (most positive)
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    customer_satisfied: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    csat_score: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1..5
    csat_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    csat_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)

    agent_talk_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    interruption_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resolution_status: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # Snapshot of the matched category's name, kept even if the category row is
    # later renamed or deleted — see `CallCategory`.
    category_id: Mapped[str | None] = fk_column(
        "call_categories.id", nullable=True, ondelete="SET NULL"
    )
    category_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    category_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # [{"parameter_id", "parameter_name", "score", "scale_min", "scale_max", "rationale"}, ...]
    custom_ratings: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    topics: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    keywords: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # {"agent": {"um": 12, ...}, "customer": {...}, "totals": {...}}
    stopword_stats: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    filler_stats: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    risk_flags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    coaching: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    sentiment_timeline: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    tone_summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    token_usage: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    processing_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = created_at_column()

    call: Mapped[Call] = relationship(back_populates="analysis")


class ActionItem(Base):
    """A task to complete or an action to take, extracted from a call."""

    __tablename__ = "action_items"
    __table_args__ = (
        Index("ix_action_items_org_status", "org_id", "status"),
        Index("ix_action_items_org_due", "org_id", "due_at"),
    )

    id: Mapped[str] = pk_column()
    org_id: Mapped[str] = fk_column("organizations.id")
    call_id: Mapped[str] = fk_column("calls.id")
    analysis_id: Mapped[str | None] = fk_column("analyses.id", nullable=True, ondelete="SET NULL")

    kind: Mapped[str] = mapped_column(String(16), default=ActionItemKind.TASK, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    assignee_agent_id: Mapped[str | None] = fk_column(
        "agents.id", nullable=True, ondelete="SET NULL"
    )
    priority: Mapped[str] = mapped_column(String(16), default=Priority.MEDIUM, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    due_hint: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default=ActionItemStatus.OPEN, nullable=False)
    source_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    call: Mapped[Call] = relationship(back_populates="action_items")


class Lead(Base):
    """The pipeline's lead verdict for a call — one row per call, every time.

    Recorded for every analysed call, not only genuine leads: `category`
    distinguishes a real prospect enquiry (`lead`) from everything else
    (`other`), so supervisors can audit what got filtered out as well as see
    what was captured. `status` is worked by hand afterwards.
    """

    __tablename__ = "leads"
    __table_args__ = (
        UniqueConstraint("call_id", name="uq_leads_call"),
        Index("ix_leads_org_category_created", "org_id", "category", "created_at"),
    )

    id: Mapped[str] = pk_column()
    org_id: Mapped[str] = fk_column("organizations.id")
    call_id: Mapped[str] = fk_column("calls.id")
    agent_id: Mapped[str | None] = fk_column("agents.id", nullable=True, ondelete="SET NULL")

    # Denormalised from the call so the leads list needs no join to render.
    customer_number: Mapped[str] = mapped_column(String(20), nullable=False)
    customer_name: Mapped[str | None] = mapped_column(String(160), nullable=True)

    lead_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    lead_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    intent: Mapped[str | None] = mapped_column(Text, nullable=True)

    category: Mapped[str] = mapped_column(String(16), default=LeadCategory.OTHER, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_quote: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(16), default=LeadStatus.NEW, nullable=False)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()


class ProcessingJob(Base):
    """A unit of pipeline work. Doubles as the queue — see services/queue.py."""

    __tablename__ = "processing_jobs"
    __table_args__ = (
        UniqueConstraint("call_id", "stage", name="uq_job_call_stage"),
        Index("ix_jobs_claim", "status", "scheduled_at"),
        Index("ix_jobs_org_status", "org_id", "status"),
    )

    id: Mapped[str] = pk_column()
    org_id: Mapped[str] = fk_column("organizations.id")
    call_id: Mapped[str] = fk_column("calls.id")
    stage: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=JobStatus.QUEUED, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_at: Mapped[datetime] = created_at_column()
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    @property
    def stage_enum(self) -> ProcessingStage:
        return ProcessingStage(self.stage)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_org_created", "org_id", "created_at"),)

    id: Mapped[str] = pk_column()
    org_id: Mapped[str] = fk_column("organizations.id")
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(20), default="user", nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = created_at_column()
