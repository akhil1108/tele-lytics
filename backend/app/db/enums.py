"""Domain enumerations.

Stored as plain strings so a new member never needs a migration on Postgres
and the values stay readable in SQLite dumps and API payloads.
"""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    SUPERVISOR = "supervisor"
    AGENT = "agent"


class AgentStatus(StrEnum):
    OFFLINE = "offline"
    AVAILABLE = "available"
    ON_CALL = "on_call"
    WRAP_UP = "wrap_up"
    BREAK = "break"


class CallDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class CallStatus(StrEnum):
    RINGING = "ringing"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    MISSED = "missed"
    FAILED = "failed"


class RecordingStatus(StrEnum):
    PENDING_UPLOAD = "pending_upload"
    STORED = "stored"
    FAILED = "failed"
    PURGED = "purged"


class ProcessingStage(StrEnum):
    TRANSCRIBE = "transcribe"
    ANALYZE = "analyze"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Sentiment(StrEnum):
    VERY_NEGATIVE = "very_negative"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    POSITIVE = "positive"
    VERY_POSITIVE = "very_positive"


class Speaker(StrEnum):
    AGENT = "agent"
    CUSTOMER = "customer"
    UNKNOWN = "unknown"


class ActionItemKind(StrEnum):
    TASK = "task"
    ACTION = "action"


class ActionItemStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    DISMISSED = "dismissed"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class NumberKind(StrEnum):
    AGENT = "agent"
    CUSTOMER = "customer"
    DID = "did"
    OTHER = "other"


class DevicePlatform(StrEnum):
    ANDROID = "android"
    IOS = "ios"
