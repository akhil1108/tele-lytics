"""Call browsing, detail, transcripts and reprocessing."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.deps import require_admin, require_staff
from app.core.errors import BadRequest, NotFound
from app.db.enums import ActionItemStatus, JobStatus, ProcessingStage, RecordingStatus
from app.db.models import (
    ActionItem,
    Agent,
    Analysis,
    Call,
    ProcessingJob,
    Recording,
    Transcript,
    User,
)
from app.db.session import get_session
from app.schemas.calls import (
    ActionItemOut,
    AnalysisOut,
    CallDetail,
    CallListItem,
    CallOut,
    JobOut,
    RecordingOut,
    TranscriptOut,
)
from app.schemas.common import Ack, Page
from app.services import queue
from app.services.phone import try_normalize
from app.services.storage import get_storage
from app.services.timerange import resolve_range

router = APIRouter(prefix="/calls", tags=["calls"])


def _processing_status(
    has_recording: bool, has_transcript: bool, has_analysis: bool, job_status: str | None
) -> str:
    if has_analysis:
        return "complete"
    if job_status == JobStatus.FAILED:
        return "failed"
    if has_transcript:
        return "analysing"
    if has_recording:
        return "transcribing"
    return "no_recording"


@router.get("", response_model=Page[CallListItem])
async def list_calls(
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
    days: int = Query(default=7, ge=1, le=366),
    start: datetime | None = None,
    end: datetime | None = None,
    agent_id: str | None = None,
    team: str | None = None,
    direction: str | None = None,
    status: str | None = None,
    sentiment: str | None = None,
    satisfied: bool | None = None,
    category: str | None = None,
    has_recording: bool | None = None,
    search: str | None = Query(default=None, description="Customer number or name"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[CallListItem]:
    range_start, range_end = resolve_range(days=days, start=start, end=end)

    filters = [
        Call.org_id == user.org_id,
        Call.started_at >= range_start,
        Call.started_at < range_end,
    ]
    if agent_id:
        filters.append(Call.agent_id == agent_id)
    if direction:
        filters.append(Call.direction == direction)
    if status:
        filters.append(Call.status == status)
    if has_recording is not None:
        filters.append(Call.has_recording.is_(has_recording))
    if search:
        # A search box is used for both numbers and names; try the number
        # interpretation first so partial dialling formats still match.
        normalized = try_normalize(search)
        pattern = f"%{search.strip()}%"
        clauses = [Call.customer_number.ilike(pattern), Call.customer_name.ilike(pattern)]
        if normalized:
            clauses.append(Call.customer_number == normalized)
        filters.append(or_(*clauses))

    stmt = (
        select(Call, Agent, Analysis)
        .join(Agent, Agent.id == Call.agent_id)
        .outerjoin(Analysis, Analysis.call_id == Call.id)
        .where(*filters)
    )
    if team:
        stmt = stmt.where(Agent.team == team)
    if sentiment:
        stmt = stmt.where(Analysis.sentiment_overall == sentiment)
    if satisfied is not None:
        stmt = stmt.where(Analysis.customer_satisfied.is_(satisfied))
    if category:
        stmt = stmt.where(Analysis.category_name == category)

    total = (
        await session.execute(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        )
    ).scalar_one()

    rows = (
        await session.execute(
            stmt.order_by(Call.started_at.desc()).limit(limit).offset(offset)
        )
    ).all()

    call_ids = [row[0].id for row in rows]
    transcripts = set(
        (
            await session.execute(
                select(Transcript.call_id).where(Transcript.call_id.in_(call_ids))
            )
        ).scalars()
    ) if call_ids else set()
    failed_jobs = set(
        (
            await session.execute(
                select(ProcessingJob.call_id).where(
                    ProcessingJob.call_id.in_(call_ids),
                    ProcessingJob.status == JobStatus.FAILED,
                )
            )
        ).scalars()
    ) if call_ids else set()
    task_counts = dict(
        (
            await session.execute(
                select(ActionItem.call_id, func.count(ActionItem.id))
                .where(
                    ActionItem.call_id.in_(call_ids),
                    ActionItem.status.in_([ActionItemStatus.OPEN, ActionItemStatus.IN_PROGRESS]),
                )
                .group_by(ActionItem.call_id)
            )
        ).all()
    ) if call_ids else {}

    items: list[CallListItem] = []
    for call, agent, analysis in rows:
        item = CallListItem.model_validate(call)
        item.agent_name = agent.display_name
        item.agent_team = agent.team
        item.has_transcript = call.id in transcripts
        item.has_analysis = analysis is not None
        item.open_tasks = int(task_counts.get(call.id, 0))
        if analysis is not None:
            item.sentiment_overall = analysis.sentiment_overall
            item.sentiment_score = analysis.sentiment_score
            item.customer_satisfied = analysis.customer_satisfied
            item.csat_score = analysis.csat_score
            item.category_name = analysis.category_name
        item.processing_status = _processing_status(
            call.has_recording,
            item.has_transcript,
            item.has_analysis,
            JobStatus.FAILED if call.id in failed_jobs else None,
        )
        items.append(item)

    return Page[CallListItem](items=items, total=total, limit=limit, offset=offset)


@router.get("/{call_id}", response_model=CallDetail)
async def get_call(
    call_id: str,
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
) -> CallDetail:
    call = await session.get(Call, call_id)
    if call is None or call.org_id != user.org_id:
        raise NotFound("Call")

    agent = await session.get(Agent, call.agent_id)
    recording = (
        await session.execute(select(Recording).where(Recording.call_id == call_id))
    ).scalar_one_or_none()
    transcript = (
        await session.execute(
            select(Transcript)
            .where(Transcript.call_id == call_id)
            .options(selectinload(Transcript.segments))
        )
    ).scalar_one_or_none()
    analysis = (
        await session.execute(select(Analysis).where(Analysis.call_id == call_id))
    ).scalar_one_or_none()
    action_items = (
        await session.execute(
            select(ActionItem)
            .where(ActionItem.call_id == call_id)
            .order_by(ActionItem.kind, ActionItem.created_at)
        )
    ).scalars().all()
    jobs = (
        await session.execute(
            select(ProcessingJob)
            .where(ProcessingJob.call_id == call_id)
            .order_by(ProcessingJob.created_at)
        )
    ).scalars().all()

    # Built field-by-field rather than validated straight off the ORM object:
    # `CallDetail` names four relationships, and validating from attributes
    # would lazy-load each one outside the async context.
    return CallDetail(
        **CallOut.model_validate(call).model_dump(),
        agent_name=agent.display_name if agent else None,
        agent_team=agent.team if agent else None,
        call_metadata=call.call_metadata or {},
        recording=RecordingOut.model_validate(recording) if recording else None,
        transcript=TranscriptOut.model_validate(transcript) if transcript else None,
        analysis=AnalysisOut.model_validate(analysis) if analysis else None,
        action_items=[ActionItemOut.model_validate(item) for item in action_items],
        jobs=[JobOut.model_validate(job) for job in jobs],
    )


@router.get("/{call_id}/transcript", response_model=TranscriptOut)
async def get_transcript(
    call_id: str,
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
) -> TranscriptOut:
    call = await session.get(Call, call_id)
    if call is None or call.org_id != user.org_id:
        raise NotFound("Call")

    transcript = (
        await session.execute(
            select(Transcript)
            .where(Transcript.call_id == call_id)
            .options(selectinload(Transcript.segments))
        )
    ).scalar_one_or_none()
    if transcript is None:
        raise NotFound("Transcript")
    return TranscriptOut.model_validate(transcript)


@router.get("/{call_id}/audio")
async def stream_audio(
    call_id: str,
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Serve the recording for the dashboard's player.

    Streamed through the API rather than via a public URL so that access is
    checked against the caller's tenancy on every play.
    """
    call = await session.get(Call, call_id)
    if call is None or call.org_id != user.org_id:
        raise NotFound("Call")

    recording = (
        await session.execute(select(Recording).where(Recording.call_id == call_id))
    ).scalar_one_or_none()
    if recording is None or not recording.storage_key:
        if recording is not None and recording.status == RecordingStatus.PURGED:
            raise NotFound("Recording (purged under the retention policy)")
        raise NotFound("Recording")

    data = await get_storage().get(recording.storage_key)
    return Response(
        content=data,
        media_type=recording.mime_type,
        headers={
            "Content-Disposition": f'inline; filename="call-{call_id}"',
            "Cache-Control": "private, max-age=300",
            "Accept-Ranges": "none",
        },
    )


@router.post("/{call_id}/reprocess", response_model=Ack)
async def reprocess(
    call_id: str,
    stage: str = Query(default="transcribe", pattern="^(transcribe|analyze)$"),
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Ack:
    """Re-run a pipeline stage — after swapping models, or to clear a failure."""
    call = await session.get(Call, call_id)
    if call is None or call.org_id != admin.org_id:
        raise NotFound("Call")

    if stage == ProcessingStage.TRANSCRIBE and not call.has_recording:
        raise BadRequest("This call has no recording to transcribe")
    if stage == ProcessingStage.ANALYZE:
        exists = (
            await session.execute(select(Transcript.id).where(Transcript.call_id == call_id))
        ).scalar_one_or_none()
        if exists is None:
            raise BadRequest("This call has no transcript to analyse")

    await queue.enqueue(session, org_id=call.org_id, call_id=call.id, stage=stage)
    await session.commit()
    return Ack(message=f"Queued {stage} for this call")
