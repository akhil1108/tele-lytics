"""The handset's API surface.

Every endpoint here authenticates with a device token and acts on exactly one
agent — the one the device is paired to. A device can never name a different
agent, so a compromised handset cannot write into someone else's call history.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import DevicePrincipal, get_current_device
from app.core.errors import BadRequest, Conflict, NotFound, PayloadTooLarge
from app.db.enums import (
    CallDirection,
    CallStatus,
    ProcessingStage,
    RecordingStatus,
)
from app.db.models import Analysis, Call, Recording
from app.db.session import get_session
from app.schemas.agents import AgentOut, StatusUpdate
from app.schemas.calls import CallCreate, CallOut, RecordingOut
from app.schemas.common import Ack
from app.schemas.policies import PolicyDecision
from app.services import policies, presence, queue
from app.services.phone import InvalidPhoneNumber, normalize
from app.services.retention import compute_purge_after, org_retention_days
from app.services.storage import (
    SUPPORTED_MIME_TYPES,
    build_key,
    checksum,
    get_storage,
)

router = APIRouter(prefix="/mobile", tags=["mobile"])


@router.get("/me", response_model=AgentOut)
async def whoami(principal: DevicePrincipal = Depends(get_current_device)) -> AgentOut:
    return AgentOut.model_validate(principal.agent)


@router.post("/status", response_model=AgentOut)
async def set_status(
    payload: StatusUpdate,
    principal: DevicePrincipal = Depends(get_current_device),
    session: AsyncSession = Depends(get_session),
) -> AgentOut:
    """Presence heartbeat. Drives the dashboard's live 'on call' counter."""
    agent = await presence.set_status(
        session, principal.agent, payload.status, call_id=payload.call_id
    )
    return AgentOut.model_validate(agent)


@router.get("/recording-policy", response_model=PolicyDecision)
async def recording_policy(
    customer_number: str = Query(..., description="The other party's number"),
    direction: CallDirection = Query(default=CallDirection.OUTBOUND),
    principal: DevicePrincipal = Depends(get_current_device),
    session: AsyncSession = Depends(get_session),
) -> PolicyDecision:
    """Asked before every call: should this one be recorded?

    The handset must call this and honour the answer — it is the enforcement
    point for consent and for per-number opt-outs.
    """
    try:
        normalized = normalize(customer_number)
    except InvalidPhoneNumber as exc:
        raise BadRequest(str(exc)) from exc

    return await policies.decide(
        session,
        org_id=principal.org_id,
        agent_number=principal.agent.phone_number,
        customer_number=normalized,
        direction=direction,
    )


@router.post("/calls", response_model=CallOut, status_code=201)
async def log_call(
    payload: CallCreate,
    principal: DevicePrincipal = Depends(get_current_device),
    session: AsyncSession = Depends(get_session),
) -> CallOut:
    """Record that a call happened. Idempotent on `external_ref`.

    The handset may retry this after a network drop, so a repeat of the same
    `external_ref` returns the existing call rather than creating a duplicate.
    """
    agent = principal.agent

    if payload.external_ref:
        existing = (
            await session.execute(
                select(Call).where(
                    Call.org_id == principal.org_id,
                    Call.external_ref == payload.external_ref,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            if existing.agent_id != agent.id:
                raise Conflict("That call reference belongs to another agent")
            return CallOut.model_validate(existing)

    duration = payload.duration_seconds
    if duration is None and payload.ended_at:
        duration = max(0, int((payload.ended_at - payload.started_at).total_seconds()))

    call = Call(
        org_id=principal.org_id,
        agent_id=agent.id,
        external_ref=payload.external_ref,
        direction=payload.direction,
        agent_number=agent.phone_number,
        customer_number=payload.customer_number,
        customer_name=payload.customer_name,
        started_at=payload.started_at,
        ended_at=payload.ended_at,
        duration_seconds=duration,
        status=payload.status,
        disposition=payload.disposition,
        recording_expected=payload.recording_expected,
        recording_skipped_reason=payload.recording_skipped_reason,
        has_recording=False,
        call_metadata=payload.metadata or {},
    )
    session.add(call)
    await session.commit()

    await presence.notify_call_event(
        session,
        principal.org_id,
        "call.logged",
        {
            "call_id": call.id,
            "agent_id": agent.id,
            "agent_name": agent.display_name,
            "direction": call.direction,
            "customer_number": call.customer_number,
            "started_at": call.started_at.isoformat(),
            "recording_expected": call.recording_expected,
        },
    )
    return CallOut.model_validate(call)


@router.post("/calls/{call_id}/recording", response_model=RecordingOut, status_code=201)
async def upload_recording(
    call_id: str,
    file: UploadFile = File(..., description="The call audio"),
    duration_seconds: float | None = Form(default=None),
    sample_rate: int | None = Form(default=None),
    channels: int | None = Form(default=None),
    consent_captured: bool = Form(default=False),
    principal: DevicePrincipal = Depends(get_current_device),
    session: AsyncSession = Depends(get_session),
) -> RecordingOut:
    """Upload call audio and start the pipeline.

    Re-uploading the same call replaces the stored audio and re-runs processing,
    which is what a handset retrying a failed upload needs.
    """
    call = await session.get(Call, call_id)
    if call is None or call.org_id != principal.org_id:
        raise NotFound("Call")
    if call.agent_id != principal.agent.id:
        raise NotFound("Call")

    mime_type = (file.content_type or "application/octet-stream").split(";")[0].strip().lower()
    if mime_type not in SUPPORTED_MIME_TYPES:
        raise BadRequest(
            f"Unsupported audio type {mime_type!r}. "
            f"Supported: {', '.join(sorted(SUPPORTED_MIME_TYPES))}"
        )

    data = await file.read()
    if not data:
        raise BadRequest("Uploaded file is empty")
    if len(data) > settings.max_recording_bytes:
        raise PayloadTooLarge(
            f"Recording is {len(data) // (1024 * 1024)}MB; "
            f"the limit is {settings.max_recording_mb}MB"
        )

    storage_key = build_key(principal.org_id, call.id, mime_type)
    await get_storage().put(storage_key, data, mime_type)

    now = datetime.now(UTC)
    policy = await policies.get_policy(session, principal.org_id, call.agent_number)
    purge_after = compute_purge_after(
        org_retention_days=await org_retention_days(session, principal.org_id),
        number_retention_days=policy.retention_days if policy else None,
        uploaded_at=now,
    )

    recording = (
        await session.execute(select(Recording).where(Recording.call_id == call.id))
    ).scalar_one_or_none()
    if recording is None:
        recording = Recording(org_id=principal.org_id, call_id=call.id)
        session.add(recording)

    recording.storage_backend = get_storage().name
    recording.storage_key = storage_key
    recording.mime_type = mime_type
    recording.size_bytes = len(data)
    recording.duration_seconds = duration_seconds
    recording.sample_rate = sample_rate
    recording.channels = channels
    recording.checksum_sha256 = checksum(data)
    recording.status = RecordingStatus.STORED
    recording.consent_captured = consent_captured
    recording.uploaded_at = now
    recording.purge_after = purge_after
    recording.purged_at = None

    call.has_recording = True
    if duration_seconds and not call.duration_seconds:
        call.duration_seconds = int(duration_seconds)

    await queue.enqueue(
        session,
        org_id=principal.org_id,
        call_id=call.id,
        stage=ProcessingStage.TRANSCRIBE,
        max_attempts=settings.worker_max_attempts,
    )
    await session.commit()

    await presence.notify_call_event(
        session,
        principal.org_id,
        "recording.uploaded",
        {"call_id": call.id, "agent_id": call.agent_id, "size_bytes": len(data)},
    )
    return RecordingOut.model_validate(recording)


@router.get("/calls", response_model=list[CallOut])
async def my_calls(
    limit: int = Query(default=30, ge=1, le=100),
    principal: DevicePrincipal = Depends(get_current_device),
    session: AsyncSession = Depends(get_session),
) -> list[CallOut]:
    rows = (
        await session.execute(
            select(Call)
            .where(Call.agent_id == principal.agent.id)
            .order_by(Call.started_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [CallOut.model_validate(row) for row in rows]


async def _period_stats(session: AsyncSession, agent_id: str, since: datetime) -> dict:
    """Call counts for one window, split the way an agent thinks about their day."""
    totals = (
        await session.execute(
            select(
                func.count(Call.id),
                func.sum(case((Call.direction == CallDirection.INBOUND, 1), else_=0)),
                func.sum(case((Call.direction == CallDirection.OUTBOUND, 1), else_=0)),
                func.sum(case((Call.status == CallStatus.MISSED, 1), else_=0)),
                func.sum(func.coalesce(Call.duration_seconds, 0)),
                func.sum(case((Call.has_recording.is_(True), 1), else_=0)),
            ).where(Call.agent_id == agent_id, Call.started_at >= since)
        )
    ).one()

    sentiment = (
        await session.execute(
            select(func.avg(Analysis.sentiment_score))
            .join(Call, Call.id == Analysis.call_id)
            .where(Call.agent_id == agent_id, Call.started_at >= since)
        )
    ).scalar_one_or_none()

    calls, inbound, outbound, missed, talk, recorded = (int(v or 0) for v in totals)
    answered = calls - missed
    return {
        "calls": calls,
        "inbound": inbound,
        "outbound": outbound,
        "missed": missed,
        "talk_seconds": talk,
        "recorded": recorded,
        # Missed calls have no talk time; folding them in would drag the average
        # down as missed-call reporting gets more complete.
        "avg_call_seconds": round(talk / answered) if answered else None,
        "avg_sentiment": round(float(sentiment), 3) if sentiment is not None else None,
    }


@router.get("/summary")
async def my_summary(
    tz_offset_minutes: int = Query(
        default=0,
        ge=-14 * 60,
        le=14 * 60,
        description="The handset's offset from UTC, so 'today' is the agent's today",
    ),
    principal: DevicePrincipal = Depends(get_current_device),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Today's and this week's figures for the agent's own home screen."""
    offset = timedelta(minutes=tz_offset_minutes)
    local_now = datetime.now(UTC) + offset
    day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0) - offset
    week_start = day_start - timedelta(days=6)

    agent_id = principal.agent.id
    today = await _period_stats(session, agent_id, day_start)
    week = await _period_stats(session, agent_id, week_start)

    pending = (
        await session.execute(
            select(func.count(Call.id)).where(
                Call.agent_id == agent_id,
                Call.recording_expected.is_(True),
                Call.has_recording.is_(False),
            )
        )
    ).scalar_one()

    return {
        "agent_id": agent_id,
        "agent_name": principal.agent.display_name,
        "status": principal.agent.status,
        "calls_today": today["calls"],
        "talk_seconds_today": today["talk_seconds"],
        "recorded_today": today["recorded"],
        "avg_sentiment_today": today["avg_sentiment"],
        "uploads_outstanding": int(pending or 0),
        "today": today,
        "week": week,
    }


@router.post("/unpair", response_model=Ack)
async def unpair(
    principal: DevicePrincipal = Depends(get_current_device),
    session: AsyncSession = Depends(get_session),
) -> Ack:
    """Let an agent unpair their own handset (device lost, phone swapped)."""
    principal.device.revoked_at = datetime.now(UTC)
    await presence.set_status(session, principal.agent, "offline")
    await session.commit()
    return Ack(message="This device has been unpaired")
