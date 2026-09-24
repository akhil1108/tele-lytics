"""Dashboard aggregate endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_staff
from app.db.models import User
from app.db.session import get_session
from app.schemas.analytics import (
    LeaderboardRow,
    OverviewMetrics,
    RiskSummary,
    SentimentBreakdown,
    TermCount,
    TimeseriesPoint,
)
from app.services import metrics
from app.services.timerange import default_bucket, resolve_range

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview", response_model=OverviewMetrics)
async def overview(
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
    days: int = Query(default=7, ge=1, le=366),
    start: datetime | None = None,
    end: datetime | None = None,
) -> OverviewMetrics:
    range_start, range_end = resolve_range(days=days, start=start, end=end)
    return await metrics.overview(session, user.org_id, range_start, range_end)


@router.get("/timeseries", response_model=list[TimeseriesPoint])
async def timeseries(
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
    days: int = Query(default=7, ge=1, le=366),
    start: datetime | None = None,
    end: datetime | None = None,
    bucket: str | None = Query(default=None, pattern="^(hour|day|week)$"),
) -> list[TimeseriesPoint]:
    range_start, range_end = resolve_range(days=days, start=start, end=end)
    resolved = bucket or default_bucket(range_start, range_end)
    return await metrics.timeseries(session, user.org_id, range_start, range_end, resolved)  # type: ignore[arg-type]


@router.get("/sentiment", response_model=list[SentimentBreakdown])
async def sentiment(
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
    days: int = Query(default=7, ge=1, le=366),
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[SentimentBreakdown]:
    range_start, range_end = resolve_range(days=days, start=start, end=end)
    return await metrics.sentiment_breakdown(session, user.org_id, range_start, range_end)


@router.get("/agents", response_model=list[LeaderboardRow])
async def leaderboard(
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
    days: int = Query(default=7, ge=1, le=366),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[LeaderboardRow]:
    range_start, range_end = resolve_range(days=days)
    return await metrics.agent_leaderboard(session, user.org_id, range_start, range_end, limit)


@router.get("/fillers", response_model=list[TermCount])
async def fillers(
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
    days: int = Query(default=7, ge=1, le=366),
    speaker: str = Query(default="agent", pattern="^(agent|customer|totals)$"),
    limit: int = Query(default=12, ge=1, le=50),
) -> list[TermCount]:
    range_start, range_end = resolve_range(days=days)
    return await metrics.top_fillers(
        session, user.org_id, range_start, range_end, speaker=speaker, limit=limit
    )


@router.get("/risks", response_model=list[RiskSummary])
async def risks(
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
    days: int = Query(default=7, ge=1, le=366),
) -> list[RiskSummary]:
    range_start, range_end = resolve_range(days=days)
    return await metrics.risk_summary(session, user.org_id, range_start, range_end)


@router.get("/recording-coverage")
async def recording_coverage(
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
    days: int = Query(default=7, ge=1, le=366),
    limit: int = Query(default=25, ge=1, le=100),
) -> list[dict]:
    """Per-number: calls made, calls recorded, and whether recording is on."""
    range_start, range_end = resolve_range(days=days)
    return await metrics.recording_coverage_by_number(
        session, user.org_id, range_start, range_end, limit
    )
