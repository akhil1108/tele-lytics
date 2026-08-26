"""Heuristic stage-2 provider for development, demos and tests.

Not a stub that returns constants: it reads the transcript with a small lexicon
so the dashboard shows figures that move with the content. That matters because
a dashboard populated with identical rows hides layout and aggregation bugs.
"""

from __future__ import annotations

import re

from app.llm.analysis.base import AnalysisInput
from app.llm.schemas import (
    AnalysisResult,
    CallAnalysis,
    CoachingNotes,
    ExtractedTask,
    RecommendedAction,
    RiskFlag,
    SatisfactionVerdict,
    SentimentPoint,
    SpeakerStopwords,
)

_POSITIVE = {
    "thanks", "thank", "great", "perfect", "appreciate", "helpful", "works",
    "excellent", "sorted", "resolved", "happy", "good", "wonderful", "brilliant",
}
_NEGATIVE = {
    "upset", "angry", "unacceptable", "delay", "delayed", "late", "problem",
    "issue", "complaint", "frustrated", "terrible", "worst", "refund", "cancel",
    "escalate", "disappointed", "wrong", "broken", "stuck",
}
_COMMITMENT = re.compile(
    r"\b(i'll|i will|we'll|we will|let me|i'm going to|i am going to)\s+([^.,;!?]{4,90})",
    re.IGNORECASE,
)
# Stems, not exact words: "downgrading" and "cancelled" must match too.
_CHURN = re.compile(
    r"\b(cancel\w*|downgrad\w*|switch(ing)? to|competitor\w*|close (my|the) account)\b", re.I
)
_ESCALATION = re.compile(r"\b(escalat\w*|supervisor|manager|complain\w*|legal)\b", re.I)

_LABELS = (
    (-0.6, "very_negative"), (-0.2, "negative"), (0.2, "neutral"), (0.6, "positive"),
)


# "Here's what I'll do — I'll ship a replacement" yields a first capture of
# "do" plus a dangling dash. Neither is a task.
_LEADING_JUNK = re.compile(r"^[\s\u2014\u2013,;:-]+")
_EMPTY_VERBS = {"do", "that", "this", "it", "so", "the same", "the following"}
_PROMISE_PREFIX = re.compile(r"^(i'?ll|i will|we'?ll|we will|let me)\s+", re.IGNORECASE)


def _clean_commitment(phrase: str) -> str | None:
    """Turn a captured clause into a task title, or reject it.

    A dash splits an announcement from the promise it introduces — "what I'll
    do — I'll ship a replacement" — so each clause is tried in turn and the
    first real one wins. Taking the first clause unconditionally would throw
    the actual commitment away.
    """
    for clause in re.split(r"\s[\u2014\u2013-]+\s", phrase):
        cleaned = _LEADING_JUNK.sub("", clause).strip(" .,;:")
        cleaned = _PROMISE_PREFIX.sub("", cleaned).strip()
        if len(cleaned) >= 6 and cleaned.lower() not in _EMPTY_VERBS:
            return cleaned[0].upper() + cleaned[1:]
    return None


def _label_for(score: float) -> str:
    for threshold, label in _LABELS:
        if score < threshold:
            return label
    return "very_positive"


def _score_text(text: str) -> float:
    words = re.findall(r"[a-z']+", text.lower())
    if not words:
        return 0.0
    positive = sum(word in _POSITIVE for word in words)
    negative = sum(word in _NEGATIVE for word in words)
    if positive == negative == 0:
        return 0.0
    return max(-1.0, min(1.0, (positive - negative) / max(3.0, (positive + negative))))


class MockAnalysisProvider:
    name = "mock"

    async def analyse(self, payload: AnalysisInput) -> AnalysisResult:
        segments = payload.segments or []
        customer_segments = [s for s in segments if s.get("speaker") == "customer"]
        agent_segments = [s for s in segments if s.get("speaker") == "agent"]

        timeline: list[SentimentPoint] = []
        running: list[float] = []
        for seg in customer_segments:
            score = _score_text(seg.get("text", ""))
            running.append(score)
            if abs(score) >= 0.2:
                timeline.append(
                    SentimentPoint(
                        at_ms=int(seg.get("start_ms") or 0),
                        speaker="customer",
                        score=round(score, 2),
                        label=_label_for(score),
                        note=(seg.get("text", "")[:110] or None),
                    )
                )

        # Weight the closing half of the call: how a customer leaves matters
        # more than how they arrived.
        if running:
            midpoint = len(running) // 2
            early = running[:midpoint] or running
            late = running[midpoint:] or running
            overall = (sum(early) / len(early)) * 0.35 + (sum(late) / len(late)) * 0.65
        else:
            overall = _score_text(payload.transcript_text)
        overall = round(max(-1.0, min(1.0, overall)), 2)

        tasks: list[ExtractedTask] = []
        seen: set[str] = set()
        for seg in agent_segments:
            for match in _COMMITMENT.finditer(seg.get("text", "")):
                phrase = _clean_commitment(match.group(2))
                if phrase is None or phrase.lower() in seen:
                    continue
                seen.add(phrase.lower())
                tasks.append(
                    ExtractedTask(
                        title=phrase[:120],
                        description=None,
                        owner_role="agent",
                        priority="high" if overall < -0.2 else "medium",
                        source_quote=seg.get("text", "")[:160],
                    )
                )
                if len(tasks) >= 5:
                    break
            if len(tasks) >= 5:
                break

        full_text = payload.transcript_text
        risks: list[RiskFlag] = []
        if _CHURN.search(full_text):
            risks.append(
                RiskFlag(
                    kind="churn_risk",
                    severity="high",
                    detail="Customer raised cancelling or downgrading.",
                )
            )
        if _ESCALATION.search(full_text):
            risks.append(
                RiskFlag(
                    kind="escalation",
                    severity="medium",
                    detail="Escalation language used on the call.",
                )
            )
        if overall <= -0.4:
            risks.append(
                RiskFlag(
                    kind="unresolved_complaint",
                    severity="high",
                    detail="Call ended on a negative note.",
                )
            )

        actions: list[RecommendedAction] = []
        if overall < 0:
            actions.append(
                RecommendedAction(
                    action=(
                        "Follow up with this customer within 24 hours to confirm the fix landed."
                    ),
                    rationale="Sentiment stayed negative through the call.",
                    urgency="high" if overall <= -0.4 else "medium",
                )
            )
        if not tasks and overall >= 0.2:
            actions.append(
                RecommendedAction(
                    action="Invite this customer to leave a review.",
                    rationale="Call closed positively with nothing outstanding.",
                    urgency="low",
                )
            )

        satisfied: bool | None
        if abs(overall) < 0.12:
            satisfied = None  # genuinely no signal — abstain rather than guess
        else:
            satisfied = overall > 0

        stats = payload.stopword_stats or {}
        analysis = CallAnalysis(
            summary=_summarise(customer_segments, agent_segments, overall),
            topics=_topics(stats),
            keywords=[
                item["term"]
                for item in stats.get("totals", {}).get("top_content_words", [])[:8]
            ],
            sentiment_overall=_label_for(overall),
            sentiment_score=overall,
            sentiment_timeline=timeline[:6],
            satisfaction=SatisfactionVerdict(
                satisfied=satisfied,
                score=None if satisfied is None else int(round((overall + 1) * 2)) + 1,
                confidence=round(min(0.85, 0.35 + abs(overall) / 2), 2),
                evidence=(customer_segments[-1].get("text") if customer_segments else None),
            ),
            tasks=tasks,
            actions=actions,
            agent_stopwords=_speaker_stopwords(stats.get("agent", {})),
            customer_stopwords=_speaker_stopwords(stats.get("customer", {})),
            risk_flags=risks,
            coaching=CoachingNotes(
                strengths=["Acknowledged the customer's problem before proposing a fix."]
                if overall > -0.3 else [],
                improvements=["Reduce filler speech when explaining the resolution."]
                if stats.get("agent", {}).get("filler_rate_per_100_words", 0) > 5 else [],
            ),
            agent_talk_ratio=_talk_ratio(agent_segments, customer_segments),
            interruption_count=None,
            resolution_status="resolved" if overall >= 0.3 else
            ("follow_up_scheduled" if tasks else "unclear"),
            tone_summary={
                "agent": _dominant_tone(agent_segments),
                "customer": _dominant_tone(customer_segments),
            },
        )

        return AnalysisResult(
            provider=self.name,
            model="heuristic-v1",
            analysis=analysis,
            token_usage={},
            raw={
                "note": "heuristic analysis; set ANALYSIS_PROVIDER=claude for model-backed output"
            },
        )


def _speaker_stopwords(stats: dict) -> SpeakerStopwords:
    return SpeakerStopwords(
        total_filler_count=int(stats.get("filler_count", 0) or 0),
        filler_rate_per_100_words=float(stats.get("filler_rate_per_100_words", 0.0) or 0.0),
        top_fillers=[item["term"] for item in (stats.get("top_fillers") or [])[:5]],
        assessment=None,
    )


def _topics(stats: dict) -> list[str]:
    return [item["term"] for item in stats.get("totals", {}).get("top_content_words", [])[:4]]


def _talk_ratio(agent_segments: list[dict], customer_segments: list[dict]) -> float | None:
    def span(segments: list[dict]) -> int:
        return sum(
            max(0, int(s.get("end_ms") or 0) - int(s.get("start_ms") or 0)) for s in segments
        )

    total = span(agent_segments) + span(customer_segments)
    return round(span(agent_segments) / total, 3) if total else None


def _dominant_tone(segments: list[dict]) -> str:
    tones = [s.get("tone_label") for s in segments if s.get("tone_label")]
    if not tones:
        return "unknown"
    return max(set(tones), key=tones.count)


def _summarise(customer: list[dict], agent: list[dict], score: float) -> str:
    opening = customer[0].get("text", "").strip() if customer else "No customer speech captured."
    closing = customer[-1].get("text", "").strip() if customer else ""
    mood = _label_for(score).replace("_", " ")
    parts = [f"Customer opened with: {opening[:180]}"]
    if closing and closing != opening:
        parts.append(f"The call closed with: {closing[:180]}")
    parts.append(f"Overall customer sentiment read as {mood}.")
    if agent:
        parts.append(f"The agent spoke {len(agent)} times.")
    return " ".join(parts)
