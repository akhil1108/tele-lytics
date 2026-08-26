"""Dashboard aggregate shapes."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class OverviewMetrics(BaseModel):
    range_start: datetime
    range_end: datetime

    # Live counters
    agents_total: int = 0
    agents_online: int = 0
    agents_on_call: int = 0

    # Volume
    calls_total: int = 0
    calls_inbound: int = 0
    calls_outbound: int = 0
    calls_missed: int = 0
    total_talk_seconds: int = 0
    avg_duration_seconds: float | None = None

    # Recording coverage
    calls_recorded: int = 0
    recording_coverage: float | None = Field(
        default=None, description="Share of eligible calls that produced a recording."
    )
    numbers_with_recording_enabled: int = 0
    numbers_total: int = 0

    # Insight
    calls_analysed: int = 0
    avg_sentiment: float | None = None
    satisfied_count: int = 0
    unsatisfied_count: int = 0
    unknown_satisfaction_count: int = 0
    satisfaction_rate: float | None = None
    avg_csat: float | None = None
    avg_agent_talk_ratio: float | None = None
    avg_filler_rate: float | None = None

    # Follow-up
    open_tasks: int = 0
    overdue_tasks: int = 0
    risk_flag_count: int = 0

    # Pipeline health
    pipeline_queued: int = 0
    pipeline_running: int = 0
    pipeline_failed: int = 0


class TimeseriesPoint(BaseModel):
    bucket: datetime
    calls: int = 0
    recorded: int = 0
    analysed: int = 0
    avg_sentiment: float | None = None
    satisfied: int = 0
    unsatisfied: int = 0
    talk_seconds: int = 0


class SentimentBreakdown(BaseModel):
    label: str
    count: int
    share: float


class LeaderboardRow(BaseModel):
    agent_id: str
    agent_name: str
    team: str | None = None
    calls: int
    avg_sentiment: float | None = None
    satisfaction_rate: float | None = None
    avg_duration_seconds: float | None = None
    filler_rate: float | None = None
    open_tasks: int = 0


class TermCount(BaseModel):
    term: str
    count: int
    speaker: str | None = None


class RiskSummary(BaseModel):
    kind: str
    count: int
    severity_high: int = 0
