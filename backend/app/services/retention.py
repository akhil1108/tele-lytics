"""Recording retention.

Audio is the sensitive part of a call record; the transcript and analysis are
what the dashboard needs long-term. So recordings expire on a schedule while
their derived insight is kept, and the row stays behind marked `purged` so the
UI can explain why the player is empty rather than 404-ing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.db.enums import RecordingStatus
from app.db.models import Organization, Recording
from app.services.storage import get_storage

log = get_logger(__name__)


def compute_purge_after(
    *,
    org_retention_days: int | None,
    number_retention_days: int | None,
    uploaded_at: datetime | None = None,
) -> datetime | None:
    """Most specific policy wins: number override, else org, else global default.

    A retention of 0 means "keep indefinitely" and returns None.
    """
    days = number_retention_days
    if days is None:
        days = org_retention_days
    if days is None:
        days = settings.default_retention_days
    if not days or days <= 0:
        return None
    return (uploaded_at or datetime.now(UTC)) + timedelta(days=days)


async def purge_expired_recordings(session: AsyncSession, *, limit: int = 200) -> int:
    """Delete audio whose retention window has closed. Returns the count."""
    now = datetime.now(UTC)
    expired = (
        await session.execute(
            select(Recording)
            .where(
                Recording.status == RecordingStatus.STORED,
                Recording.purge_after.is_not(None),
                Recording.purge_after <= now,
            )
            .limit(limit)
        )
    ).scalars().all()

    if not expired:
        return 0

    storage = get_storage()
    purged = 0
    for recording in expired:
        if recording.storage_key:
            try:
                await storage.delete(recording.storage_key)
            except Exception:
                log.exception(
                    "failed to delete expired audio",
                    extra={"recording_id": recording.id, "key": recording.storage_key},
                )
                continue
        recording.status = RecordingStatus.PURGED
        recording.purged_at = now
        recording.storage_key = None
        purged += 1

    await session.commit()
    return purged


async def org_retention_days(session: AsyncSession, org_id: str) -> int | None:
    org = await session.get(Organization, org_id)
    return org.retention_days if org else None
