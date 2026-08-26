"""Insight provider interface (pipeline stage 2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.llm.schemas import AnalysisResult


@dataclass(slots=True)
class AnalysisInput:
    """Everything stage 2 sees. Built by the pipeline from stage-1 output."""

    call_id: str
    transcript_text: str
    segments: list[dict[str, Any]] = field(default_factory=list)
    call_context: dict[str, Any] = field(default_factory=dict)
    stopword_stats: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class AnalysisProvider(Protocol):
    name: str

    async def analyse(self, payload: AnalysisInput) -> AnalysisResult: ...
