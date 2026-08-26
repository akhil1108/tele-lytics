"""Turn a spoken timing phrase into a concrete due date.

The insight model reports timing the way the customer said it ("by Friday",
"end of day"), because paraphrasing a commitment into a date is exactly the
kind of silent error that erodes trust in the extracted tasks. Resolving that
phrase to a timestamp is done here, in code, where the rules are inspectable —
and anything unrecognised stays unresolved rather than being guessed at.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}
_END_OF_DAY = (17, 0)  # 5pm local business close


def resolve_due_date(hint: str | None, *, now: datetime | None = None) -> datetime | None:
    """Return a UTC datetime for `hint`, or None when it cannot be resolved."""
    if not hint:
        return None

    reference = (now or datetime.now(UTC)).astimezone(UTC)
    text = hint.strip().lower()

    if re.search(r"\b(right away|immediately|asap|now)\b", text):
        return reference + timedelta(hours=1)
    if re.search(r"\b(today|end of day|eod|by close|this evening|within the hour)\b", text):
        if "within the hour" in text:
            return reference + timedelta(hours=1)
        return _at_time(reference, *_END_OF_DAY)
    if re.search(r"\btomorrow\b", text):
        return _at_time(reference + timedelta(days=1), *_END_OF_DAY)

    if match := re.search(r"\b(?:in|within)\s+(\d+)\s*(minute|hour|day|week)s?\b", text):
        amount = int(match.group(1))
        unit = match.group(2)
        delta = {
            "minute": timedelta(minutes=amount),
            "hour": timedelta(hours=amount),
            "day": timedelta(days=amount),
            "week": timedelta(weeks=amount),
        }[unit]
        return reference + delta

    for name, index in _WEEKDAYS.items():
        if re.search(rf"\b{name}\b", text):
            ahead = (index - reference.weekday()) % 7
            # "Friday" said on a Friday means the next one, not five minutes ago.
            if ahead == 0:
                ahead = 7 if re.search(r"\bnext\b", text) else 0
            target = reference + timedelta(days=ahead)
            return _at_time(target, *_END_OF_DAY)

    if re.search(r"\b(this week|end of (the )?week)\b", text):
        ahead = (4 - reference.weekday()) % 7  # Friday
        return _at_time(reference + timedelta(days=ahead), *_END_OF_DAY)
    if re.search(r"\bnext week\b", text):
        ahead = (0 - reference.weekday()) % 7 or 7  # next Monday
        return _at_time(reference + timedelta(days=ahead), *_END_OF_DAY)

    return None


def _at_time(moment: datetime, hour: int, minute: int) -> datetime:
    return moment.replace(hour=hour, minute=minute, second=0, microsecond=0)
