"""Deterministic stop-word and filler analysis.

Two different things get counted here, and the dashboard shows both:

* **fillers** — padding that carries no content ("um", "you know", "basically").
  This is what supervisors actually mean by "stop words used": it is a coaching
  signal, and its rate per 100 words is comparable across calls of any length.
* **stop words** — the classic function-word list. Removing them is how the
  content-density and keyword figures are computed.

Counting happens in code rather than in the model because counts must be exact
and reproducible; the model is asked only to *judge* the counts it is given.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field

# Classic English function words. Used for content density, not for coaching.
STOP_WORDS: frozenset[str] = frozenset(
    """
a about above after again against all am an and any are aren't as at be because been before being
below between both but by can cannot could couldn't did didn't do does doesn't doing don't down
during each few for from further had hadn't has hasn't have haven't having he her here hers
herself him himself his how i if in into is isn't it its itself let's me more most mustn't my
myself no nor not of off on once only or other ought our ours ourselves out over own same shan't
she should shouldn't so some such than that the their theirs them themselves then there these they
this those through to too under until up very was wasn't we were weren't what when where which
while who whom why with won't would wouldn't you your yours yourself yourselves
""".split()
)

# Single-word fillers and hedges.
FILLER_WORDS: tuple[str, ...] = (
    "um", "uh", "erm", "er", "ah", "hmm", "mmm", "eh", "huh",
    "like", "actually", "basically", "literally", "obviously", "honestly",
    "right", "okay", "ok", "yeah", "yep", "so", "well", "just", "really",
    "anyway", "anyways", "totally", "seriously", "apparently",
    # Hindi/Hinglish fillers, common on Indian support and sales floors.
    "matlab", "achha", "acha", "haan", "arre", "bas", "toh", "yaar", "na",
)

# Multi-word fillers. Matched before single words so "you know" is not counted
# twice (once as a phrase, once as bare "know").
FILLER_PHRASES: tuple[str, ...] = (
    "you know", "i mean", "sort of", "kind of", "you see", "i guess",
    "as such", "at the end of the day", "to be honest", "if you will",
    "or something", "and all that", "what i'm saying is", "the thing is",
    "kya bolte hain", "aisa hai",
)

# Hedges are tracked separately: they weaken a commitment rather than pad it.
HEDGE_PHRASES: tuple[str, ...] = (
    "i think", "maybe", "possibly", "probably", "i'm not sure", "i am not sure",
    "should be", "might be", "hopefully", "we'll try", "we will try", "i'll try",
)

_WORD_RE = re.compile(r"[a-z']+")
_PHRASE_RES: dict[str, re.Pattern[str]] = {
    phrase: re.compile(r"\b" + re.escape(phrase) + r"\b")
    for phrase in (*FILLER_PHRASES, *HEDGE_PHRASES)
}


@dataclass
class SpeakerStopwordStats:
    word_count: int = 0
    filler_count: int = 0
    filler_rate_per_100_words: float = 0.0
    hedge_count: int = 0
    stopword_count: int = 0
    content_word_count: int = 0
    content_density: float = 0.0
    top_fillers: list[dict] = field(default_factory=list)
    top_content_words: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace("’", "'")).strip()


def analyse_text(text: str) -> SpeakerStopwordStats:
    """Count fillers, hedges and stop words in one speaker's speech."""
    normalised = _normalise(text)
    stats = SpeakerStopwordStats()
    if not normalised:
        return stats

    filler_counts: Counter[str] = Counter()
    hedge_count = 0

    # Phrases first; each match is blanked so its words cannot be recounted.
    for phrase, pattern in _PHRASE_RES.items():
        matches = pattern.findall(normalised)
        if not matches:
            continue
        if phrase in HEDGE_PHRASES:
            hedge_count += len(matches)
        else:
            filler_counts[phrase] += len(matches)
        normalised = pattern.sub(" ", normalised)

    words = _WORD_RE.findall(normalised)
    # Phrase matches were removed above, so add their words back to the total.
    phrase_words = sum(count * len(phrase.split()) for phrase, count in filler_counts.items())
    stats.word_count = len(words) + phrase_words

    content_words: Counter[str] = Counter()
    for word in words:
        if word in FILLER_WORDS:
            filler_counts[word] += 1
        if word in STOP_WORDS:
            stats.stopword_count += 1
        elif word not in FILLER_WORDS and len(word) > 2:
            content_words[word] += 1

    stats.filler_count = sum(filler_counts.values())
    stats.hedge_count = hedge_count
    stats.content_word_count = sum(content_words.values())
    if stats.word_count:
        stats.filler_rate_per_100_words = round(100 * stats.filler_count / stats.word_count, 2)
        stats.content_density = round(stats.content_word_count / stats.word_count, 3)

    stats.top_fillers = [
        {"term": term, "count": count} for term, count in filler_counts.most_common(10)
    ]
    stats.top_content_words = [
        {"term": term, "count": count} for term, count in content_words.most_common(15)
    ]
    return stats


def analyse_segments(segments: list) -> dict:
    """Aggregate per speaker over transcript segments.

    Accepts anything with `.speaker` and `.text` (the stage-1 result objects or
    the ORM segment rows — both fit).
    """
    buckets: dict[str, list[str]] = {"agent": [], "customer": [], "unknown": []}
    for segment in segments:
        speaker = getattr(segment, "speaker", "unknown") or "unknown"
        speaker = str(speaker)
        buckets.setdefault(speaker, []).append(getattr(segment, "text", "") or "")

    result: dict = {}
    for speaker, chunks in buckets.items():
        if not any(chunk.strip() for chunk in chunks):
            continue
        result[speaker] = analyse_text(" ".join(chunks)).to_dict()

    combined = analyse_text(
        " ".join(chunk for chunks in buckets.values() for chunk in chunks)
    ).to_dict()
    result["totals"] = combined
    return result


def talk_ratio(segments: list) -> float | None:
    """Share of speaking *time* held by the agent, from segment durations.

    Falls back to word share when a provider gives no usable timings.
    """
    duration: dict[str, int] = {"agent": 0, "customer": 0}
    words: dict[str, int] = {"agent": 0, "customer": 0}

    for segment in segments:
        speaker = str(getattr(segment, "speaker", "unknown") or "unknown")
        if speaker not in duration:
            continue
        start = int(getattr(segment, "start_ms", 0) or 0)
        end = int(getattr(segment, "end_ms", 0) or 0)
        if end > start:
            duration[speaker] += end - start
        words[speaker] += len(_WORD_RE.findall(_normalise(getattr(segment, "text", "") or "")))

    total_ms = duration["agent"] + duration["customer"]
    if total_ms > 0:
        return round(duration["agent"] / total_ms, 3)

    total_words = words["agent"] + words["customer"]
    if total_words > 0:
        return round(words["agent"] / total_words, 3)
    return None
