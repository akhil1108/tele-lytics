"""Dashboard time-range resolution.

One helper so every endpoint interprets `?days=`, `?from=`, `?to=` the same
way, and so a caller can never accidentally ask for an unbounded range.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

MAX_RANGE_DAYS = 366


def resolve_range(
    *,
    days: int | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> tuple[datetime, datetime]:
    """Return an inclusive-start, exclusive-end UTC window.

    Explicit `start`/`end` win; otherwise the last `days` days ending now.
    """
    now = datetime.now(UTC)

    if start is not None or end is not None:
        resolved_end = (end or now).astimezone(UTC)
        resolved_start = (
            start.astimezone(UTC) if start else resolved_end - timedelta(days=days or 7)
        )
    else:
        resolved_end = now
        resolved_start = now - timedelta(days=days or 7)

    if resolved_start > resolved_end:
        resolved_start, resolved_end = resolved_end, resolved_start

    span = resolved_end - resolved_start
    if span > timedelta(days=MAX_RANGE_DAYS):
        resolved_start = resolved_end - timedelta(days=MAX_RANGE_DAYS)

    return resolved_start, resolved_end


def default_bucket(start: datetime, end: datetime) -> str:
    """Pick a bucket that yields a readable number of points for the range."""
    span = end - start
    if span <= timedelta(days=2):
        return "hour"
    if span <= timedelta(days=90):
        return "day"
    return "week"
