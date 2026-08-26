"""Database-backed job queue for the processing pipeline.

Deliberately not Celery/Redis: the queue is low-volume (one or two jobs per
call), the jobs are long and idempotent, and keeping them in Postgres means the
job row and the call row commit together — a call can never be marked ready for
processing without its job existing, which is the failure mode a separate broker
introduces.

Claiming is portable across Postgres and SQLite: the `UPDATE ... WHERE
status = 'queued'` is itself the atomic guard, so two workers racing for the
same row cannot both win.
"""

from __future__ import annotations

import socket
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.enums import JobStatus, ProcessingStage
from app.db.models import ProcessingJob

log = get_logger(__name__)

# A job whose worker died is reclaimed after this long.
STALE_LOCK_AFTER = timedelta(minutes=30)
# Backoff between attempts, indexed by attempt number.
RETRY_BACKOFF = (timedelta(seconds=30), timedelta(minutes=2), timedelta(minutes=10))


def worker_identity() -> str:
    return f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"


async def enqueue(
    session: AsyncSession,
    *,
    org_id: str,
    call_id: str,
    stage: ProcessingStage | str,
    max_attempts: int = 3,
    delay: timedelta | None = None,
) -> ProcessingJob:
    """Queue a stage for a call, or re-arm the existing job for that stage.

    One row per (call, stage) — re-running a stage resets the same row rather
    than creating a second one, so history stays readable and the unique
    constraint holds.
    """
    stage_value = str(stage)
    existing = (
        await session.execute(
            select(ProcessingJob).where(
                ProcessingJob.call_id == call_id, ProcessingJob.stage == stage_value
            )
        )
    ).scalar_one_or_none()

    scheduled_at = datetime.now(UTC) + (delay or timedelta(0))

    if existing is not None:
        if existing.status == JobStatus.RUNNING:
            return existing  # already in flight; leave it alone
        existing.status = JobStatus.QUEUED
        existing.attempts = 0
        existing.last_error = None
        existing.scheduled_at = scheduled_at
        existing.started_at = None
        existing.finished_at = None
        existing.locked_by = None
        existing.locked_at = None
        existing.max_attempts = max_attempts
        await session.flush()
        return existing

    job = ProcessingJob(
        org_id=org_id,
        call_id=call_id,
        stage=stage_value,
        status=JobStatus.QUEUED,
        max_attempts=max_attempts,
        scheduled_at=scheduled_at,
    )
    session.add(job)
    await session.flush()
    return job


async def claim(session: AsyncSession, *, worker_id: str, limit: int = 4) -> list[ProcessingJob]:
    """Atomically take up to `limit` due jobs for this worker."""
    now = datetime.now(UTC)

    candidates = (
        await session.execute(
            select(ProcessingJob.id)
            .where(
                ProcessingJob.status == JobStatus.QUEUED,
                ProcessingJob.scheduled_at <= now,
            )
            .order_by(ProcessingJob.scheduled_at)
            .limit(limit)
        )
    ).scalars().all()

    if not candidates:
        return []

    # The status predicate is the lock: a row already taken by another worker
    # no longer matches, so the UPDATE simply skips it.
    await session.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.id.in_(candidates),
            ProcessingJob.status == JobStatus.QUEUED,
        )
        .values(
            status=JobStatus.RUNNING,
            locked_by=worker_id,
            locked_at=now,
            started_at=now,
            attempts=ProcessingJob.attempts + 1,
        )
    )
    await session.commit()

    jobs = (
        await session.execute(
            select(ProcessingJob).where(
                ProcessingJob.id.in_(candidates),
                ProcessingJob.locked_by == worker_id,
                ProcessingJob.status == JobStatus.RUNNING,
            )
        )
    ).scalars().all()
    return list(jobs)


async def mark_succeeded(session: AsyncSession, job: ProcessingJob) -> None:
    job.status = JobStatus.SUCCEEDED
    job.finished_at = datetime.now(UTC)
    job.last_error = None
    job.locked_by = None
    job.locked_at = None
    await session.commit()


async def mark_failed(
    session: AsyncSession,
    job: ProcessingJob,
    error: str,
    *,
    retryable: bool = True,
) -> None:
    """Reschedule with backoff, or park the job once attempts are exhausted."""
    job.last_error = error[:4000]
    job.locked_by = None
    job.locked_at = None

    if retryable and job.attempts < job.max_attempts:
        backoff = RETRY_BACKOFF[min(job.attempts - 1, len(RETRY_BACKOFF) - 1)]
        job.status = JobStatus.QUEUED
        job.scheduled_at = datetime.now(UTC) + backoff
        job.started_at = None
        log.warning(
            "job failed, will retry",
            extra={
                "job_id": job.id, "stage": job.stage, "attempt": job.attempts,
                "retry_in_s": int(backoff.total_seconds()), "error": error[:200],
            },
        )
    else:
        job.status = JobStatus.FAILED
        job.finished_at = datetime.now(UTC)
        log.error(
            "job failed permanently",
            extra={
                "job_id": job.id, "stage": job.stage, "call_id": job.call_id,
                "attempts": job.attempts, "error": error[:200],
            },
        )
    await session.commit()


async def reclaim_stale(session: AsyncSession) -> int:
    """Requeue jobs whose worker died holding the lock."""
    cutoff = datetime.now(UTC) - STALE_LOCK_AFTER
    result = await session.execute(
        update(ProcessingJob)
        .where(
            ProcessingJob.status == JobStatus.RUNNING,
            ProcessingJob.locked_at < cutoff,
        )
        .values(
            status=JobStatus.QUEUED,
            locked_by=None,
            locked_at=None,
            scheduled_at=datetime.now(UTC),
            last_error="reclaimed after worker went away",
        )
    )
    await session.commit()
    count = result.rowcount or 0
    if count:
        log.warning("reclaimed stale jobs", extra={"count": count})
    return count
