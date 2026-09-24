"""Contracts between the pipeline and its two models.

Stage 1 (speech) returns a `TranscriptionResult`; stage 2 (insight) returns a
`CallAnalysis`. Both are plain Pydantic models so a provider can be swapped
without the pipeline noticing.

`CallAnalysis` doubles as the structured-output schema handed to Claude, which
is why every field carries a description: those descriptions are the only
instruction the model gets about what belongs in each slot.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Speaker = Literal["agent", "customer", "unknown"]
SentimentLabel = Literal["very_negative", "negative", "neutral", "positive", "very_positive"]
PriorityLabel = Literal["low", "medium", "high", "urgent"]


# ------------------------------------------------------------- stage 1: speech


class ToneReading(BaseModel):
    """Paralinguistic reading for a stretch of audio."""

    label: str | None = Field(
        default=None,
        description="Dominant tone, e.g. calm, frustrated, apologetic, enthusiastic, rushed.",
    )
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    valence: float | None = Field(
        default=None, ge=-1.0, le=1.0, description="Pleasantness, -1 unpleasant to +1 pleasant."
    )
    arousal: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Energy, 0 flat to 1 highly activated."
    )


class TranscriptSegmentResult(BaseModel):
    speaker: Speaker = "unknown"
    start_ms: int = Field(default=0, ge=0)
    end_ms: int = Field(default=0, ge=0)
    text: str = ""
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    tone: ToneReading = Field(default_factory=ToneReading)


class TranscriptionResult(BaseModel):
    provider: str
    model: str | None = None
    language: str | None = None
    full_text: str = ""
    confidence: float | None = None
    tone_overall: str | None = None
    duration_seconds: float | None = None
    segments: list[TranscriptSegmentResult] = Field(default_factory=list)
    raw: dict = Field(default_factory=dict)

    def rebuild_full_text(self) -> str:
        """Some providers return segments but no joined text."""
        if self.full_text.strip():
            return self.full_text
        return "\n".join(
            f"{seg.speaker}: {seg.text.strip()}" for seg in self.segments if seg.text.strip()
        )


# ------------------------------------------------------------ stage 2: insight


class ExtractedTask(BaseModel):
    title: str = Field(description="Imperative one-line task, e.g. 'Send the revised quote'.")
    description: str | None = Field(
        default=None, description="What exactly needs doing, and any detail stated on the call."
    )
    owner_role: Literal["agent", "customer", "supervisor", "other"] = Field(
        default="agent", description="Who committed to doing this on the call."
    )
    priority: PriorityLabel = "medium"
    due_hint: str | None = Field(
        default=None,
        description="Timing exactly as expressed on the call, e.g. 'by Friday', 'end of day'.",
    )
    source_quote: str | None = Field(
        default=None, description="Short verbatim quote that this task was drawn from."
    )


class RecommendedAction(BaseModel):
    action: str = Field(description="A concrete next step for the business, not for the customer.")
    rationale: str | None = Field(default=None, description="Why the call implies this step.")
    urgency: PriorityLabel = "medium"
    source_quote: str | None = None


class SentimentPoint(BaseModel):
    at_ms: int = Field(ge=0, description="Offset into the call.")
    speaker: Speaker = "customer"
    score: float = Field(ge=-1.0, le=1.0)
    label: SentimentLabel = "neutral"
    note: str | None = None


class RiskFlag(BaseModel):
    kind: Literal[
        "escalation",
        "churn_risk",
        "compliance",
        "competitor_mention",
        "abusive_language",
        "unresolved_complaint",
        "pricing_objection",
        "other",
    ]
    severity: PriorityLabel = "medium"
    detail: str
    source_quote: str | None = None


class SatisfactionVerdict(BaseModel):
    satisfied: bool | None = Field(
        default=None,
        description="True if the customer ended the call satisfied; null if the call gives no "
        "usable signal either way. Do not guess.",
    )
    score: int | None = Field(
        default=None, ge=1, le=5, description="Predicted CSAT on a 1-5 scale."
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: str | None = Field(
        default=None, description="The specific moment on the call that decided this."
    )


class SpeakerStopwords(BaseModel):
    """Filler / low-content speech, counted per speaker.

    Stage 2 refines a deterministic count computed in `app.llm.stopwords`; the
    model's job is to judge which of those were genuinely padding rather than
    meaningful use ('like' as a simile is not a filler).
    """

    total_filler_count: int = 0
    filler_rate_per_100_words: float = 0.0
    top_fillers: list[str] = Field(default_factory=list)
    assessment: str | None = Field(
        default=None, description="One line on whether filler speech hurt this call."
    )


class CustomParameterScore(BaseModel):
    """One org-defined rating parameter, scored for this call.

    `parameter_name` must match a name from the `<rating_parameters>` block in
    the prompt exactly — the pipeline matches on it and drops anything that
    doesn't resolve, so an invented name is silently discarded rather than
    breaking persistence.
    """

    parameter_name: str
    score: float = Field(description="Within the parameter's stated scale.")
    rationale: str | None = Field(
        default=None, description="One line grounding the score in what was said."
    )


class LeadExtraction(BaseModel):
    """Contact and intent details, plus the lead/other verdict, for this call.

    A "lead" is a prospective customer with real purchase intent. Existing-
    customer support, vendor/supplier calls, and wrong-number or spam calls are
    "other" — leave `name`/`email`/`purpose`/`intent` null when nothing of the
    kind was actually said; do not infer contact details from the phone number.
    """

    name: str | None = None
    email: str | None = None
    purpose: str | None = Field(default=None, description="Why they called, in a few words.")
    intent: str | None = Field(
        default=None, description="What they want to happen next, e.g. 'wants a demo'."
    )
    category: Literal["lead", "other"] = "other"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str | None = Field(
        default=None, description="Why this call was or wasn't judged a lead."
    )
    source_quote: str | None = None


class CoachingNotes(BaseModel):
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    missed_opportunities: list[str] = Field(default_factory=list)


class CallAnalysis(BaseModel):
    """The complete stage-2 output. This is the structured-output schema."""

    summary: str = Field(description="Three or four sentences: why they called and how it ended.")
    topics: list[str] = Field(
        default_factory=list, description="Two to six short topic labels."
    )
    keywords: list[str] = Field(default_factory=list, description="Salient terms, products, names.")

    sentiment_overall: SentimentLabel = "neutral"
    sentiment_score: float = Field(
        default=0.0, ge=-1.0, le=1.0, description="Customer sentiment across the whole call."
    )
    sentiment_timeline: list[SentimentPoint] = Field(
        default_factory=list,
        description="Sentiment at the points where it visibly moved — not one entry per segment.",
    )

    satisfaction: SatisfactionVerdict = Field(default_factory=SatisfactionVerdict)

    category_name: str = Field(
        description="Exact name of the single best-fitting entry from <categories>."
    )
    category_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    custom_ratings: list[CustomParameterScore] = Field(
        default_factory=list,
        description="One entry for every parameter listed in <rating_parameters>.",
    )
    lead: LeadExtraction = Field(default_factory=LeadExtraction)

    tasks: list[ExtractedTask] = Field(
        default_factory=list, description="Commitments made on the call that someone must complete."
    )
    actions: list[RecommendedAction] = Field(
        default_factory=list,
        description="Steps the business should take that were not explicitly promised.",
    )

    agent_stopwords: SpeakerStopwords = Field(default_factory=SpeakerStopwords)
    customer_stopwords: SpeakerStopwords = Field(default_factory=SpeakerStopwords)

    risk_flags: list[RiskFlag] = Field(default_factory=list)
    coaching: CoachingNotes = Field(default_factory=CoachingNotes)

    agent_talk_ratio: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Share of speaking time taken by the agent."
    )
    interruption_count: int | None = Field(default=None, ge=0)
    resolution_status: Literal[
        "resolved", "partially_resolved", "unresolved", "follow_up_scheduled", "unclear"
    ] = "unclear"
    tone_summary: dict[str, str] = Field(
        default_factory=dict,
        description="Per-speaker tone in a few words, keyed 'agent' and 'customer'.",
    )


class AnalysisResult(BaseModel):
    """`CallAnalysis` plus the provenance the pipeline records alongside it."""

    provider: str
    model: str | None = None
    analysis: CallAnalysis
    token_usage: dict = Field(default_factory=dict)
    raw: dict = Field(default_factory=dict)
