"""Speech-to-text provider interface (pipeline stage 1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from app.llm.schemas import TranscriptionResult


@dataclass(slots=True)
class AudioRef:
    """A recording handed to a speech provider."""

    data: bytes
    mime_type: str = "audio/mp4"
    filename: str = "recording.m4a"
    duration_seconds: float | None = None
    sample_rate: int | None = None
    channels: int | None = None

    @property
    def size_bytes(self) -> int:
        return len(self.data)


@dataclass(slots=True)
class TranscriptionHints:
    """Context that measurably improves diarisation and accuracy.

    Passing the agent's and customer's numbers lets a provider that does
    channel- or number-aware diarisation label speakers correctly instead of
    guessing from voice alone.
    """

    language: str | None = None
    agent_number: str | None = None
    customer_number: str | None = None
    agent_name: str | None = None
    direction: str | None = None
    call_id: str | None = None
    vocabulary: list[str] = field(default_factory=list)


@runtime_checkable
class SpeechToTextProvider(Protocol):
    """Implemented by every stage-1 backend."""

    name: str

    async def transcribe(
        self, audio: AudioRef, hints: TranscriptionHints
    ) -> TranscriptionResult: ...
