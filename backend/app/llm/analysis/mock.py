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
    CustomParameterScore,
    ExtractedTask,
    LeadExtraction,
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

# Keyword buckets used to pick a category *by meaning*; the actual name
# returned is always one from the org's own list (payload.categories), matched
# case-insensitively against these keys — see `_pick_category`.
_CATEGORY_KEYWORDS = {
    "sales_enquiry": {
        "price", "pricing", "quote", "quotation", "buy", "purchase", "interested",
        "demo", "trial", "plan", "upgrade", "subscription", "cost",
    },
    "vendor_call": {
        "supplier", "vendor", "purchase order", "invoice from", "procurement",
        "quotation for", "partnership", "distributor",
    },
    "transactional": {
        "invoice", "payment", "bill", "billing", "renew", "renewal", "receipt",
        "order status", "tracking", "delivery", "refund",
    },
    "complaint": {
        "complaint", "unacceptable", "terrible", "worst", "disappointed", "angry",
    },
    "support_request": {
        "help", "issue", "problem", "not working", "broken", "trouble", "error",
    },
    "recruitment": {"interview", "resume", "cv", "position", "hiring", "job opening"},
    "wrong_number": {"wrong number", "who is this", "sorry, wrong"},
}

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_NAME_INTRO = re.compile(
    r"\b(?:my name is|this is|i am|i'm)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)"
)
_PURCHASE_INTENT = re.compile(
    r"\b(interested in|looking to buy|would like to purchase|want to sign up|"
    r"can (i|we) get a quote|thinking about upgrading)\b", re.I
)

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

        category_name, category_confidence = _pick_category(full_text, payload.categories)
        lead = _extract_lead(customer_segments, full_text, category_name, overall)
        custom_ratings = _score_ratings(payload.rating_parameters, overall)

        stats = payload.stopword_stats or {}
        analysis = CallAnalysis(
            summary=_summarise(customer_segments, agent_segments, overall),
            category_name=category_name,
            category_confidence=category_confidence,
            custom_ratings=custom_ratings,
            lead=lead,
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


def _pick_category(text: str, categories: list[dict]) -> tuple[str, float]:
    """Match the transcript against each category's keyword bucket by name.

    Falls back to whichever category the org flagged `default` (or the first
    one, or "Other" as a last resort if the org has none configured yet).
    """
    default_name = next(
        (c["name"] for c in categories if c.get("default")),
        categories[0]["name"] if categories else "Other",
    )
    if not categories:
        return default_name, 0.3

    lowered = text.lower()
    best_name: str | None = None
    best_hits = 0
    for category in categories:
        bucket_key = category["name"].strip().lower().replace(" ", "_")
        keywords = _CATEGORY_KEYWORDS.get(bucket_key)
        if not keywords:
            # Org renamed/added a category we have no bucket for — try a loose
            # match on its own name appearing in the transcript instead.
            keywords = {category["name"].lower()}
        hits = sum(1 for kw in keywords if kw in lowered)
        if hits > best_hits:
            best_hits = hits
            best_name = category["name"]

    if best_name is None:
        return default_name, 0.3
    return best_name, round(min(0.9, 0.5 + 0.1 * best_hits), 2)


def _extract_lead(
    customer_segments: list[dict], full_text: str, category_name: str, overall: float
) -> LeadExtraction:
    # Contact details are only ever taken from what the CUSTOMER said — the
    # agent also self-introduces by name at the top of every call, and matching
    # against the whole transcript would misattribute that as the lead's name.
    customer_text = "\n".join(s.get("text", "") for s in customer_segments)
    email_match = _EMAIL.search(customer_text)
    email = email_match.group(0).rstrip(".,;:") if email_match else None
    name_match = _NAME_INTRO.search(customer_text)
    has_intent = bool(_PURCHASE_INTENT.search(full_text))

    looks_like_lead = (
        has_intent
        and category_name.strip().lower() not in {"vendor_call", "vendor call", "transactional"}
        and overall >= -0.1
    )

    opening = customer_segments[0].get("text", "").strip() if customer_segments else None
    return LeadExtraction(
        name=name_match.group(1) if (name_match and looks_like_lead) else None,
        email=email if looks_like_lead else None,
        purpose=(opening[:160] if (looks_like_lead and opening) else None),
        intent="Wants pricing or a demo" if (looks_like_lead and has_intent) else None,
        category="lead" if looks_like_lead else "other",
        confidence=0.65 if looks_like_lead else 0.55,
        reason=(
            "Customer expressed purchase intent."
            if looks_like_lead
            else "No purchase intent detected; reads as an existing-customer or non-sales call."
        ),
        source_quote=opening[:160] if (looks_like_lead and opening) else None,
    )


def _score_ratings(parameters: list[dict], overall: float) -> list[CustomParameterScore]:
    """Scale overall call sentiment into each parameter's own range.

    A heuristic stand-in for real per-criterion judgement — good enough that
    demo data shows varied, plausible-looking scores rather than one constant.
    """
    scores: list[CustomParameterScore] = []
    for param in parameters:
        lo = float(param.get("scale_min", 1))
        hi = float(param.get("scale_max", 5))
        # overall runs -1..1; map onto [lo, hi] and round to the nearest 0.5.
        raw = lo + (overall + 1) / 2 * (hi - lo)
        score = round(max(lo, min(hi, raw)) * 2) / 2
        scores.append(
            CustomParameterScore(
                parameter_name=param["name"],
                score=score,
                rationale=(
                    "Call sentiment stayed positive throughout."
                    if overall > 0.2
                    else "Call sentiment was mixed or negative."
                    if overall < -0.2
                    else "Call was largely neutral on this measure."
                ),
            )
        )
    return scores


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
