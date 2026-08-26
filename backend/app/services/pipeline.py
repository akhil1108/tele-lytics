"""The two-stage processing pipeline.

    recording ──▶ [stage 1: speech model] ──▶ transcript + tone
                                                    │
                                                    ▼
                              [stage 2: insight model] ──▶ analysis + tasks

Both stages are idempotent: re-running one replaces its own output and leaves
everything else alone. That is what makes retries safe and what lets an
operator re-run a single call after swapping models.
"""

from __future__ import annotations

import time

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import NotFound, ProviderError
from app.core.logging import get_logger
from app.db.enums import (
    ActionItemKind,
    ActionItemStatus,
    ProcessingStage,
    RecordingStatus,
)
from app.db.models import (
    ActionItem,
    Agent,
    Analysis,
    Call,
    Recording,
    Transcript,
    TranscriptSegment,
)
from app.llm.analysis.base import AnalysisInput
from app.llm.registry import get_analysis_provider, get_stt_provider
from app.llm.schemas import CallAnalysis, TranscriptionResult
from app.llm.stopwords import analyse_segments, talk_ratio
from app.llm.stt.base import AudioRef, TranscriptionHints
from app.services import queue
from app.services.duedates import resolve_due_date
from app.services.storage import get_storage

log = get_logger(__name__)


# --------------------------------------------------------------- stage 1


async def run_transcription(session: AsyncSession, call_id: str) -> Transcript:
    """Speech to text plus tone. Replaces any existing transcript for the call."""
    call = await session.get(Call, call_id)
    if call is None:
        raise NotFound("Call")

    recording = (
        await session.execute(select(Recording).where(Recording.call_id == call_id))
    ).scalar_one_or_none()

    if recording is None or not recording.storage_key:
        raise ProviderError("call has no stored recording to transcribe", retryable=False)
    if recording.status == RecordingStatus.PURGED:
        raise ProviderError("recording was purged before it could be processed", retryable=False)

    audio_bytes = await get_storage().get(recording.storage_key)
    agent = await session.get(Agent, call.agent_id)

    hints = TranscriptionHints(
        language=None,
        agent_number=call.agent_number,
        customer_number=call.customer_number,
        agent_name=agent.display_name if agent else None,
        direction=call.direction,
        call_id=call.id,
    )
    audio = AudioRef(
        data=audio_bytes,
        mime_type=recording.mime_type,
        filename=recording.storage_key.rsplit("/", 1)[-1],
        duration_seconds=recording.duration_seconds,
        sample_rate=recording.sample_rate,
        channels=recording.channels,
    )

    started = time.monotonic()
    result: TranscriptionResult = await get_stt_provider().transcribe(audio, hints)
    elapsed_ms = int((time.monotonic() - started) * 1000)

    transcript = await _persist_transcript(session, call, result, elapsed_ms)

    # The speech model often measures duration more accurately than the handset.
    if result.duration_seconds:
        recording.duration_seconds = result.duration_seconds
        if not call.duration_seconds:
            call.duration_seconds = int(result.duration_seconds)

    await queue.enqueue(
        session, org_id=call.org_id, call_id=call.id, stage=ProcessingStage.ANALYZE
    )
    await session.commit()

    # Re-read with segments attached: after the commit a lazy relationship
    # cannot load, and callers reasonably expect the segments to be there.
    transcript = (
        await session.execute(
            select(Transcript)
            .where(Transcript.id == transcript.id)
            .options(selectinload(Transcript.segments))
        )
    ).scalar_one()

    log.info(
        "transcription complete",
        extra={
            "call_id": call.id, "segments": len(result.segments),
            "provider": result.provider, "elapsed_ms": elapsed_ms,
        },
    )
    return transcript


async def _persist_transcript(
    session: AsyncSession, call: Call, result: TranscriptionResult, elapsed_ms: int
) -> Transcript:
    existing = (
        await session.execute(select(Transcript).where(Transcript.call_id == call.id))
    ).scalar_one_or_none()

    if existing is not None:
        await session.execute(
            delete(TranscriptSegment).where(TranscriptSegment.transcript_id == existing.id)
        )
        transcript = existing
    else:
        transcript = Transcript(org_id=call.org_id, call_id=call.id, provider=result.provider)
        session.add(transcript)

    full_text = result.rebuild_full_text()
    transcript.provider = result.provider
    transcript.model = result.model
    transcript.language = result.language
    transcript.full_text = full_text
    transcript.word_count = len(full_text.split())
    transcript.confidence = result.confidence
    transcript.tone_overall = result.tone_overall
    transcript.processing_ms = elapsed_ms
    transcript.raw = result.raw or {}
    await session.flush()

    for idx, segment in enumerate(result.segments):
        session.add(
            TranscriptSegment(
                transcript_id=transcript.id,
                idx=idx,
                speaker=segment.speaker,
                start_ms=segment.start_ms,
                end_ms=segment.end_ms,
                text=segment.text,
                confidence=segment.confidence,
                tone_label=segment.tone.label,
                tone_confidence=segment.tone.confidence,
                valence=segment.tone.valence,
                arousal=segment.tone.arousal,
            )
        )
    await session.flush()
    return transcript


# --------------------------------------------------------------- stage 2


async def run_analysis(session: AsyncSession, call_id: str) -> Analysis:
    """Insight extraction. Replaces any existing analysis for the call."""
    call = await session.get(Call, call_id)
    if call is None:
        raise NotFound("Call")

    transcript = (
        await session.execute(
            select(Transcript)
            .where(Transcript.call_id == call_id)
            .options(selectinload(Transcript.segments))
        )
    ).scalar_one_or_none()

    if transcript is None:
        raise ProviderError("call has no transcript to analyse", retryable=False)
    if not transcript.full_text.strip():
        raise ProviderError("transcript is empty", retryable=False)

    segments = list(transcript.segments)
    stopword_stats = analyse_segments(segments)
    agent = await session.get(Agent, call.agent_id)

    payload = AnalysisInput(
        call_id=call.id,
        transcript_text=transcript.full_text,
        segments=[
            {
                "idx": s.idx, "speaker": s.speaker, "start_ms": s.start_ms,
                "end_ms": s.end_ms, "text": s.text, "tone_label": s.tone_label,
            }
            for s in segments
        ],
        call_context={
            "direction": call.direction,
            "duration_seconds": call.duration_seconds,
            "agent_name": agent.display_name if agent else None,
            "agent_team": agent.team if agent else None,
            "language": transcript.language,
            "started_at": call.started_at.isoformat() if call.started_at else None,
        },
        stopword_stats=stopword_stats,
    )

    started = time.monotonic()
    result = await get_analysis_provider().analyse(payload)
    elapsed_ms = int((time.monotonic() - started) * 1000)

    analysis = await _persist_analysis(
        session,
        call=call,
        transcript=transcript,
        segments=segments,
        result_analysis=result.analysis,
        provider=result.provider,
        model=result.model,
        token_usage=result.token_usage,
        raw=result.raw,
        stopword_stats=stopword_stats,
        elapsed_ms=elapsed_ms,
    )
    await session.commit()

    log.info(
        "analysis complete",
        extra={
            "call_id": call.id, "provider": result.provider,
            "sentiment": analysis.sentiment_overall, "tasks": len(result.analysis.tasks),
            "elapsed_ms": elapsed_ms,
        },
    )
    return analysis


async def _persist_analysis(
    session: AsyncSession,
    *,
    call: Call,
    transcript: Transcript,
    segments: list[TranscriptSegment],
    result_analysis: CallAnalysis,
    provider: str,
    model: str | None,
    token_usage: dict,
    raw: dict,
    stopword_stats: dict,
    elapsed_ms: int,
) -> Analysis:
    existing = (
        await session.execute(select(Analysis).where(Analysis.call_id == call.id))
    ).scalar_one_or_none()

    if existing is not None:
        # Action items belong to the analysis that produced them; a re-run
        # replaces them rather than duplicating the same commitments.
        await session.execute(delete(ActionItem).where(ActionItem.call_id == call.id))
        analysis = existing
    else:
        analysis = Analysis(org_id=call.org_id, call_id=call.id, provider=provider)
        session.add(analysis)

    ratio = result_analysis.agent_talk_ratio
    if ratio is None:
        ratio = talk_ratio(segments)

    analysis.provider = provider
    analysis.model = model
    analysis.summary = result_analysis.summary
    analysis.sentiment_overall = result_analysis.sentiment_overall
    analysis.sentiment_score = result_analysis.sentiment_score
    analysis.customer_satisfied = result_analysis.satisfaction.satisfied
    analysis.csat_score = result_analysis.satisfaction.score
    analysis.csat_confidence = result_analysis.satisfaction.confidence
    analysis.csat_evidence = result_analysis.satisfaction.evidence
    analysis.agent_talk_ratio = ratio
    analysis.interruption_count = result_analysis.interruption_count
    analysis.resolution_status = result_analysis.resolution_status
    analysis.topics = result_analysis.topics
    analysis.keywords = result_analysis.keywords
    # Exact counts come from code; the model's prose judgement rides alongside.
    analysis.stopword_stats = stopword_stats
    analysis.filler_stats = {
        "agent": result_analysis.agent_stopwords.model_dump(),
        "customer": result_analysis.customer_stopwords.model_dump(),
    }
    analysis.risk_flags = [flag.model_dump() for flag in result_analysis.risk_flags]
    analysis.coaching = result_analysis.coaching.model_dump()
    analysis.sentiment_timeline = [
        point.model_dump() for point in result_analysis.sentiment_timeline
    ]
    analysis.tone_summary = result_analysis.tone_summary
    analysis.token_usage = token_usage or {}
    analysis.processing_ms = elapsed_ms
    analysis.raw = raw or {}
    await session.flush()

    _apply_segment_sentiment(segments, result_analysis)
    _create_action_items(session, call=call, analysis=analysis, result_analysis=result_analysis)

    await session.flush()
    return analysis


def _apply_segment_sentiment(
    segments: list[TranscriptSegment], result_analysis: CallAnalysis
) -> None:
    """Attach timeline sentiment to the nearest segment at or before each point,
    so the transcript view can colour utterances without a second model call."""
    if not segments or not result_analysis.sentiment_timeline:
        return

    ordered = sorted(segments, key=lambda s: s.start_ms)
    for point in result_analysis.sentiment_timeline:
        match = None
        for segment in ordered:
            if segment.start_ms <= point.at_ms:
                match = segment
            else:
                break
        if match is not None:
            match.sentiment = point.label


def _create_action_items(
    session: AsyncSession,
    *,
    call: Call,
    analysis: Analysis,
    result_analysis: CallAnalysis,
) -> None:
    for task in result_analysis.tasks:
        session.add(
            ActionItem(
                org_id=call.org_id,
                call_id=call.id,
                analysis_id=analysis.id,
                kind=ActionItemKind.TASK,
                title=task.title[:300],
                description=task.description,
                owner_role=task.owner_role,
                # Tasks the agent committed to default to that agent's queue.
                assignee_agent_id=call.agent_id if task.owner_role == "agent" else None,
                priority=task.priority,
                due_hint=task.due_hint,
                due_at=resolve_due_date(task.due_hint),
                status=ActionItemStatus.OPEN,
                source_quote=task.source_quote,
            )
        )

    for action in result_analysis.actions:
        session.add(
            ActionItem(
                org_id=call.org_id,
                call_id=call.id,
                analysis_id=analysis.id,
                kind=ActionItemKind.ACTION,
                title=action.action[:300],
                description=action.rationale,
                owner_role="supervisor",
                priority=action.urgency,
                status=ActionItemStatus.OPEN,
                source_quote=action.source_quote,
            )
        )


# ------------------------------------------------------------- dispatch

STAGE_HANDLERS = {
    ProcessingStage.TRANSCRIBE: run_transcription,
    ProcessingStage.ANALYZE: run_analysis,
}


async def run_stage(session: AsyncSession, stage: str, call_id: str) -> None:
    handler = STAGE_HANDLERS.get(ProcessingStage(stage))
    if handler is None:
        raise ProviderError(f"unknown pipeline stage: {stage}", retryable=False)
    await handler(session, call_id)
