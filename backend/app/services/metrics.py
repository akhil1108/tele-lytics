"""Dashboard aggregation.

Every figure the admin dashboard shows is computed here with grouped SQL rather
than by loading rows and counting in Python — the calls table is the one that
grows without bound, so anything that walks it per-request stops working in
month three.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import Select, and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import (
    ActionItemStatus,
    AgentStatus,
    CallDirection,
    CallStatus,
    JobStatus,
    Sentiment,
)
from app.db.models import (
    ActionItem,
    Agent,
    Analysis,
    Call,
    PhoneNumberPolicy,
    ProcessingJob,
)
from app.schemas.analytics import (
    LeaderboardRow,
    OverviewMetrics,
    RiskSummary,
    SentimentBreakdown,
    TermCount,
    TimeseriesPoint,
)

Bucket = Literal["hour", "day", "week"]

_SENTIMENT_ORDER = (
    Sentiment.VERY_NEGATIVE,
    Sentiment.NEGATIVE,
    Sentiment.NEUTRAL,
    Sentiment.POSITIVE,
    Sentiment.VERY_POSITIVE,
)


def _in_range(stmt: Select, org_id: str, start: datetime, end: datetime) -> Select:
    """Scope a statement to one tenant and one window.

    Every aggregate here is rooted at `calls`, so the FROM is pinned explicitly:
    a select list made only of aggregates over joined tables gives SQLAlchemy no
    left side to infer, and it raises rather than guessing.
    """
    return stmt.select_from(Call).where(
        Call.org_id == org_id, Call.started_at >= start, Call.started_at < end
    )


async def overview(
    session: AsyncSession, org_id: str, start: datetime, end: datetime
) -> OverviewMetrics:
    metrics = OverviewMetrics(range_start=start, range_end=end)

    # ---- call volume, one pass ----
    volume = (
        await session.execute(
            _in_range(
                select(
                    func.count(Call.id),
                    func.sum(case((Call.direction == CallDirection.INBOUND, 1), else_=0)),
                    func.sum(case((Call.direction == CallDirection.OUTBOUND, 1), else_=0)),
                    func.sum(case((Call.status == CallStatus.MISSED, 1), else_=0)),
                    func.sum(func.coalesce(Call.duration_seconds, 0)),
                    # Averaged over connected calls only. A missed call has zero
                    # duration, and folding those in would make average call
                    # length drop as missed-call reporting gets more complete —
                    # exactly backwards.
                    func.avg(
                        case(
                            (Call.status == CallStatus.MISSED, None),
                            else_=Call.duration_seconds,
                        )
                    ),
                    func.sum(case((Call.has_recording.is_(True), 1), else_=0)),
                    func.sum(case((Call.recording_expected.is_(True), 1), else_=0)),
                ),
                org_id, start, end,
            )
        )
    ).one()

    (
        metrics.calls_total,
        inbound, outbound, missed, talk_seconds, avg_duration,
        recorded, expected,
    ) = (
        volume[0] or 0, volume[1] or 0, volume[2] or 0, volume[3] or 0,
        volume[4] or 0, volume[5], volume[6] or 0, volume[7] or 0,
    )
    metrics.calls_inbound = int(inbound)
    metrics.calls_outbound = int(outbound)
    metrics.calls_missed = int(missed)
    metrics.total_talk_seconds = int(talk_seconds)
    metrics.avg_duration_seconds = round(float(avg_duration), 1) if avg_duration else None
    metrics.calls_recorded = int(recorded)
    # Coverage measures the pipeline's reliability: of the calls policy said to
    # record, how many actually produced audio. Calls the policy excluded are
    # not failures and must not drag the figure down.
    if expected:
        metrics.recording_coverage = round(min(1.0, recorded / expected), 3)

    # ---- live presence ----
    presence_rows = (
        await session.execute(
            select(Agent.status, func.count(Agent.id))
            .where(Agent.org_id == org_id, Agent.is_active.is_(True))
            .group_by(Agent.status)
        )
    ).all()
    presence = {status: count for status, count in presence_rows}
    metrics.agents_total = sum(presence.values())
    metrics.agents_on_call = presence.get(AgentStatus.ON_CALL, 0)
    metrics.agents_online = metrics.agents_total - presence.get(AgentStatus.OFFLINE, 0)

    # ---- recording policy coverage ----
    policy_rows = (
        await session.execute(
            select(
                func.count(PhoneNumberPolicy.id),
                func.sum(case((PhoneNumberPolicy.recording_enabled.is_(True), 1), else_=0)),
            ).where(PhoneNumberPolicy.org_id == org_id)
        )
    ).one()
    metrics.numbers_total = int(policy_rows[0] or 0)
    metrics.numbers_with_recording_enabled = int(policy_rows[1] or 0)

    # ---- insight ----
    insight = (
        await session.execute(
            _in_range(
                select(
                    func.count(Analysis.id),
                    func.avg(Analysis.sentiment_score),
                    func.sum(case((Analysis.customer_satisfied.is_(True), 1), else_=0)),
                    func.sum(case((Analysis.customer_satisfied.is_(False), 1), else_=0)),
                    func.avg(Analysis.csat_score),
                    func.avg(Analysis.agent_talk_ratio),
                ).join(Analysis, Analysis.call_id == Call.id),
                org_id, start, end,
            )
        )
    ).one()

    metrics.calls_analysed = int(insight[0] or 0)
    metrics.avg_sentiment = round(float(insight[1]), 3) if insight[1] is not None else None
    metrics.satisfied_count = int(insight[2] or 0)
    metrics.unsatisfied_count = int(insight[3] or 0)
    metrics.unknown_satisfaction_count = max(
        0, metrics.calls_analysed - metrics.satisfied_count - metrics.unsatisfied_count
    )
    metrics.avg_csat = round(float(insight[4]), 2) if insight[4] is not None else None
    metrics.avg_agent_talk_ratio = round(float(insight[5]), 3) if insight[5] is not None else None

    # Rate is over calls that produced a verdict. Including abstentions in the
    # denominator would make a quiet day look like a bad one.
    decided = metrics.satisfied_count + metrics.unsatisfied_count
    if decided:
        metrics.satisfaction_rate = round(metrics.satisfied_count / decided, 3)

    metrics.avg_filler_rate = await _avg_agent_filler_rate(session, org_id, start, end)

    # ---- follow-up ----
    now = datetime.now(UTC)
    task_rows = (
        await session.execute(
            select(
                func.count(ActionItem.id),
                func.sum(
                    case(
                        (
                            and_(
                                ActionItem.due_at.is_not(None),
                                ActionItem.due_at < now,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
            ).where(
                ActionItem.org_id == org_id,
                ActionItem.status.in_([ActionItemStatus.OPEN, ActionItemStatus.IN_PROGRESS]),
            )
        )
    ).one()
    metrics.open_tasks = int(task_rows[0] or 0)
    metrics.overdue_tasks = int(task_rows[1] or 0)

    # ---- pipeline health ----
    job_rows = (
        await session.execute(
            select(ProcessingJob.status, func.count(ProcessingJob.id))
            .where(ProcessingJob.org_id == org_id)
            .group_by(ProcessingJob.status)
        )
    ).all()
    jobs = {status: count for status, count in job_rows}
    metrics.pipeline_queued = jobs.get(JobStatus.QUEUED, 0)
    metrics.pipeline_running = jobs.get(JobStatus.RUNNING, 0)
    metrics.pipeline_failed = jobs.get(JobStatus.FAILED, 0)

    risk_rows = (
        await session.execute(
            _in_range(
                select(Analysis.risk_flags).join(Analysis, Analysis.call_id == Call.id),
                org_id, start, end,
            )
        )
    ).scalars().all()
    metrics.risk_flag_count = sum(len(flags or []) for flags in risk_rows)

    return metrics


async def _avg_agent_filler_rate(
    session: AsyncSession, org_id: str, start: datetime, end: datetime
) -> float | None:
    """Mean agent filler rate. Stored inside a JSON column, so it is averaged in
    Python — the row count here is one per analysed call in the window, which
    stays small enough at dashboard ranges."""
    rows = (
        await session.execute(
            _in_range(
                select(Analysis.stopword_stats).join(Analysis, Analysis.call_id == Call.id),
                org_id, start, end,
            )
        )
    ).scalars().all()

    rates = [
        float(stats["agent"]["filler_rate_per_100_words"])
        for stats in rows
        if isinstance(stats, dict)
        and isinstance(stats.get("agent"), dict)
        and stats["agent"].get("filler_rate_per_100_words") is not None
    ]
    return round(sum(rates) / len(rates), 2) if rates else None


async def timeseries(
    session: AsyncSession,
    org_id: str,
    start: datetime,
    end: datetime,
    bucket: Bucket = "day",
) -> list[TimeseriesPoint]:
    """Call volume and sentiment over time, gap-filled so the chart has no holes."""
    rows = (
        await session.execute(
            _in_range(
                select(
                    Call.started_at,
                    Call.has_recording,
                    Call.duration_seconds,
                    Analysis.sentiment_score,
                    Analysis.customer_satisfied,
                ).outerjoin(Analysis, Analysis.call_id == Call.id),
                org_id, start, end,
            )
        )
    ).all()

    buckets: dict[datetime, TimeseriesPoint] = {}
    sentiment_sums: dict[datetime, list[float]] = {}

    for moment in _bucket_range(start, end, bucket):
        buckets[moment] = TimeseriesPoint(bucket=moment)
        sentiment_sums[moment] = []

    for started_at, has_recording, duration, sentiment, satisfied in rows:
        key = _floor(started_at, bucket)
        point = buckets.get(key)
        if point is None:
            point = buckets.setdefault(key, TimeseriesPoint(bucket=key))
            sentiment_sums.setdefault(key, [])
        point.calls += 1
        point.talk_seconds += int(duration or 0)
        if has_recording:
            point.recorded += 1
        if sentiment is not None:
            point.analysed += 1
            sentiment_sums[key].append(float(sentiment))
        if satisfied is True:
            point.satisfied += 1
        elif satisfied is False:
            point.unsatisfied += 1

    for key, scores in sentiment_sums.items():
        if scores:
            buckets[key].avg_sentiment = round(sum(scores) / len(scores), 3)

    return [buckets[key] for key in sorted(buckets)]


def _floor(moment: datetime, bucket: Bucket) -> datetime:
    moment = moment.astimezone(UTC)
    if bucket == "hour":
        return moment.replace(minute=0, second=0, microsecond=0)
    day = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    if bucket == "week":
        return day - timedelta(days=day.weekday())
    return day


def _bucket_range(start: datetime, end: datetime, bucket: Bucket) -> list[datetime]:
    step = {
        "hour": timedelta(hours=1),
        "day": timedelta(days=1),
        "week": timedelta(weeks=1),
    }[bucket]
    cursor = _floor(start, bucket)
    stop = _floor(end, bucket)
    out: list[datetime] = []
    # Guard against a pathological range producing millions of empty buckets.
    while cursor <= stop and len(out) < 1000:
        out.append(cursor)
        cursor += step
    return out


async def sentiment_breakdown(
    session: AsyncSession, org_id: str, start: datetime, end: datetime
) -> list[SentimentBreakdown]:
    rows = (
        await session.execute(
            _in_range(
                select(Analysis.sentiment_overall, func.count(Analysis.id))
                .join(Analysis, Analysis.call_id == Call.id)
                .group_by(Analysis.sentiment_overall),
                org_id, start, end,
            )
        )
    ).all()

    counts = {label: count for label, count in rows}
    total = sum(counts.values())
    # Fixed order so the chart's colour assignment never shifts between loads.
    return [
        SentimentBreakdown(
            label=str(label),
            count=counts.get(label, 0),
            share=round(counts.get(label, 0) / total, 3) if total else 0.0,
        )
        for label in _SENTIMENT_ORDER
    ]


async def agent_leaderboard(
    session: AsyncSession, org_id: str, start: datetime, end: datetime, limit: int = 20
) -> list[LeaderboardRow]:
    rows = (
        await session.execute(
            _in_range(
                select(
                    Agent.id,
                    Agent.display_name,
                    Agent.team,
                    func.count(Call.id),
                    func.avg(Analysis.sentiment_score),
                    func.avg(
                        case(
                            (Call.status == CallStatus.MISSED, None),
                            else_=Call.duration_seconds,
                        )
                    ),
                    func.sum(case((Analysis.customer_satisfied.is_(True), 1), else_=0)),
                    func.sum(case((Analysis.customer_satisfied.is_(False), 1), else_=0)),
                )
                .join(Agent, Agent.id == Call.agent_id)
                .outerjoin(Analysis, Analysis.call_id == Call.id)
                .group_by(Agent.id, Agent.display_name, Agent.team)
                .order_by(func.count(Call.id).desc())
                .limit(limit),
                org_id, start, end,
            )
        )
    ).all()

    open_tasks = dict(
        (
            await session.execute(
                select(ActionItem.assignee_agent_id, func.count(ActionItem.id))
                .where(
                    ActionItem.org_id == org_id,
                    ActionItem.assignee_agent_id.is_not(None),
                    ActionItem.status.in_([ActionItemStatus.OPEN, ActionItemStatus.IN_PROGRESS]),
                )
                .group_by(ActionItem.assignee_agent_id)
            )
        ).all()
    )

    out: list[LeaderboardRow] = []
    for agent_id, name, team, calls, avg_sentiment, avg_duration, satisfied, unsatisfied in rows:
        decided = int(satisfied or 0) + int(unsatisfied or 0)
        out.append(
            LeaderboardRow(
                agent_id=agent_id,
                agent_name=name,
                team=team,
                calls=int(calls or 0),
                avg_sentiment=round(float(avg_sentiment), 3) if avg_sentiment is not None else None,
                satisfaction_rate=round(int(satisfied or 0) / decided, 3) if decided else None,
                avg_duration_seconds=round(float(avg_duration), 1) if avg_duration else None,
                filler_rate=None,
                open_tasks=int(open_tasks.get(agent_id, 0)),
            )
        )
    return out


async def top_fillers(
    session: AsyncSession,
    org_id: str,
    start: datetime,
    end: datetime,
    speaker: str = "agent",
    limit: int = 12,
) -> list[TermCount]:
    """Most-used filler words across the window, for the coaching panel."""
    rows = (
        await session.execute(
            _in_range(
                select(Analysis.stopword_stats).join(Analysis, Analysis.call_id == Call.id),
                org_id, start, end,
            )
        )
    ).scalars().all()

    counter: Counter[str] = Counter()
    for stats in rows:
        if not isinstance(stats, dict):
            continue
        bucket = stats.get(speaker)
        if not isinstance(bucket, dict):
            continue
        for item in bucket.get("top_fillers") or []:
            if isinstance(item, dict) and item.get("term"):
                counter[str(item["term"])] += int(item.get("count") or 0)

    return [
        TermCount(term=term, count=count, speaker=speaker)
        for term, count in counter.most_common(limit)
    ]


async def risk_summary(
    session: AsyncSession, org_id: str, start: datetime, end: datetime
) -> list[RiskSummary]:
    rows = (
        await session.execute(
            _in_range(
                select(Analysis.risk_flags).join(Analysis, Analysis.call_id == Call.id),
                org_id, start, end,
            )
        )
    ).scalars().all()

    counts: Counter[str] = Counter()
    high: Counter[str] = Counter()
    for flags in rows:
        for flag in flags or []:
            if not isinstance(flag, dict):
                continue
            kind = str(flag.get("kind", "other"))
            counts[kind] += 1
            if str(flag.get("severity")) in ("high", "urgent"):
                high[kind] += 1

    return [
        RiskSummary(kind=kind, count=count, severity_high=high.get(kind, 0))
        for kind, count in counts.most_common()
    ]


async def recording_coverage_by_number(
    session: AsyncSession, org_id: str, start: datetime, end: datetime, limit: int = 25
) -> list[dict]:
    """Per-number call volume alongside whether recording is switched on.

    This is the "is recording set for this number?" view: it pairs configuration
    with what actually happened, which is how a misconfigured number is spotted.
    """
    call_rows = (
        await session.execute(
            _in_range(
                select(
                    Call.agent_number,
                    func.count(Call.id),
                    func.sum(case((Call.has_recording.is_(True), 1), else_=0)),
                )
                .group_by(Call.agent_number)
                .order_by(func.count(Call.id).desc())
                .limit(limit),
                org_id, start, end,
            )
        )
    ).all()

    policies = {
        policy.e164: policy
        for policy in (
            await session.execute(
                select(PhoneNumberPolicy).where(PhoneNumberPolicy.org_id == org_id)
            )
        ).scalars()
    }

    out: list[dict] = []
    for number, calls, recorded in call_rows:
        policy = policies.get(number)
        out.append(
            {
                "number": number,
                "label": policy.label if policy else None,
                "calls": int(calls or 0),
                "recorded": int(recorded or 0),
                "coverage": (
                    round(int(recorded or 0) / int(calls), 3) if calls else 0.0
                ),
                "recording_enabled": bool(policy.recording_enabled) if policy else False,
                "policy_id": policy.id if policy else None,
                "configured": policy is not None,
            }
        )
    return out
