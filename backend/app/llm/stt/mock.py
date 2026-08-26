"""Deterministic speech provider for local development, demos and tests.

Produces a plausible two-speaker support call so the whole pipeline — worker,
analysis, dashboard — can be exercised with no external model attached. The
output is seeded from the call id, so a given call always transcribes the same
way.
"""

from __future__ import annotations

import hashlib

from app.llm.schemas import ToneReading, TranscriptionResult, TranscriptSegmentResult
from app.llm.stt.base import AudioRef, TranscriptionHints

_SCRIPTS: list[list[tuple[str, str, str]]] = [
    [
        ("agent", "Good morning, thank you for calling Northwind Support, this is Priya. How can I help you today?", "warm"),
        ("customer", "Hi, um, I ordered a router last Tuesday and it still hasn't shown up. The tracking hasn't moved in four days.", "frustrated"),
        ("agent", "I'm sorry about that. Let me pull up the order right now. Can you confirm the order number for me?", "apologetic"),
        ("customer", "Yeah, it's NW dash four four eight one two.", "neutral"),
        ("agent", "Thank you. I can see it. Basically the carrier flagged it at the Pune hub, so it's stuck there.", "calm"),
        ("customer", "That's really not good enough, honestly. I needed this for a client demo on Friday.", "angry"),
        ("agent", "I completely understand. Here's what I'll do — I'll ship a replacement today by express so it reaches you Thursday, and I'll refund the shipping.", "reassuring"),
        ("customer", "Okay, that actually works. Can you email me the new tracking number?", "relieved"),
        ("agent", "Absolutely, I'll send that within the hour. I'll also follow up Thursday to confirm it landed.", "confident"),
        ("customer", "Great, thanks Priya. That's sorted then.", "satisfied"),
    ],
    [
        ("agent", "Hello, this is Rahul from Northwind. Am I speaking with Mr. Sharma?", "neutral"),
        ("customer", "Yes, speaking.", "neutral"),
        ("agent", "I'm calling about your annual plan, which renews on the fifteenth. I wanted to walk you through the new tier.", "enthusiastic"),
        ("customer", "Right, I mean, I've been thinking about downgrading actually. We're not using the analytics add-on at all.", "hesitant"),
        ("agent", "That's fair. If the add-on isn't earning its keep, we can move you to the standard tier and that drops the bill by about thirty percent.", "helpful"),
        ("customer", "Hmm. What happens to the historical data if we drop it?", "concerned"),
        ("agent", "It's retained for ninety days, so you could come back within that window with nothing lost.", "calm"),
        ("customer", "Okay. Send me that in writing and I'll get approval from finance this week.", "neutral"),
        ("agent", "I'll email the comparison this afternoon and check back Friday.", "confident"),
        ("customer", "Perfect, thank you.", "satisfied"),
    ],
]

_TONE_AXES: dict[str, tuple[float, float]] = {
    "warm": (0.6, 0.4), "frustrated": (-0.6, 0.7), "apologetic": (-0.1, 0.35),
    "neutral": (0.0, 0.3), "calm": (0.2, 0.25), "angry": (-0.85, 0.9),
    "reassuring": (0.5, 0.45), "relieved": (0.5, 0.4), "confident": (0.6, 0.5),
    "satisfied": (0.8, 0.35), "enthusiastic": (0.7, 0.7), "hesitant": (-0.2, 0.3),
    "helpful": (0.55, 0.45), "concerned": (-0.35, 0.5),
}


class MockSpeechToText:
    name = "mock"

    async def transcribe(
        self, audio: AudioRef, hints: TranscriptionHints
    ) -> TranscriptionResult:
        seed = hashlib.sha256(
            (hints.call_id or str(audio.size_bytes)).encode("utf-8")
        ).digest()
        script = _SCRIPTS[seed[0] % len(_SCRIPTS)]

        segments: list[TranscriptSegmentResult] = []
        cursor_ms = 0
        for idx, (speaker, text, tone) in enumerate(script):
            # ~2.6 words per second, jittered per segment from the seed.
            jitter = 0.85 + (seed[(idx + 1) % len(seed)] / 255.0) * 0.4
            span = int(len(text.split()) / 2.6 * 1000 * jitter)
            valence, arousal = _TONE_AXES.get(tone, (0.0, 0.3))
            segments.append(
                TranscriptSegmentResult(
                    speaker=speaker,
                    start_ms=cursor_ms,
                    end_ms=cursor_ms + span,
                    text=text,
                    confidence=0.9 + (seed[idx % len(seed)] % 8) / 100.0,
                    tone=ToneReading(
                        label=tone, confidence=0.7 + (seed[idx % len(seed)] % 25) / 100.0,
                        valence=valence, arousal=arousal,
                    ),
                )
            )
            cursor_ms += span + 350  # inter-turn gap

        result = TranscriptionResult(
            provider=self.name,
            model="mock-stt-v1",
            language=hints.language or "en-IN",
            confidence=0.93,
            tone_overall=script[-1][2],
            duration_seconds=round(cursor_ms / 1000, 1),
            segments=segments,
            raw={"note": "synthetic transcript from the mock provider"},
        )
        result.full_text = result.rebuild_full_text()
        return result
