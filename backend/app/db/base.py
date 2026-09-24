"""Declarative base plus small column helpers shared by every model."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, String, TypeDecorator
from sqlalchemy.orm import DeclarativeBase, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class UTCDateTime(TypeDecorator):
    """Always hand back timezone-aware UTC datetimes.

    SQLite drops tzinfo on the way in and returns naive values on the way out,
    which makes `ended_at - started_at` blow up when one side came from Postgres.
    Normalising in one place keeps the rest of the code free of tz guards.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class Base(DeclarativeBase):
    pass


def pk_column():
    return mapped_column(String(36), primary_key=True, default=new_id)


def fk_column(
    target: str, *, nullable: bool = False, index: bool = True, ondelete: str = "CASCADE"
):
    from sqlalchemy import ForeignKey

    return mapped_column(
        String(36),
        ForeignKey(target, ondelete=ondelete),
        nullable=nullable,
        index=index,
    )


def created_at_column():
    return mapped_column(UTCDateTime, default=utcnow, nullable=False)


def updated_at_column():
    return mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False)
