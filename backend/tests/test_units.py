"""Unit coverage for the pieces the pipeline's correctness rests on."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.llm.stopwords import analyse_segments, analyse_text, talk_ratio
from app.llm.stt.base import TranscriptionHints
from app.llm.stt.shared_model import SharedModelSpeechToText
from app.services.duedates import resolve_due_date
from app.services.phone import InvalidPhoneNumber, mask, normalize
from app.services.retention import compute_purge_after
from app.services.timerange import default_bucket, resolve_range


class _Segment:
    def __init__(self, speaker: str, text: str, start_ms: int = 0, end_ms: int = 0) -> None:
        self.speaker, self.text = speaker, text
        self.start_ms, self.end_ms = start_ms, end_ms


# ---------------------------------------------------------------- phone


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+91 98765-43210", "+919876543210"),
        ("09876543210", "+919876543210"),
        ("9876543210", "+919876543210"),
        ("0091 9876543210", "+919876543210"),
        ("919876543210", "+919876543210"),
        ("+1 (415) 555-0123", "+14155550123"),
    ],
)
def test_number_normalisation(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "abc", "12", "+"])
def test_unparseable_numbers_are_rejected(raw: str) -> None:
    with pytest.raises(InvalidPhoneNumber):
        normalize(raw)


def test_masking_keeps_the_last_four_digits() -> None:
    masked = mask("+919876543210")
    assert masked.startswith("+91")
    assert masked.endswith("3210")
    assert "9876" not in masked


# ------------------------------------------------------------- stopwords


def test_multi_word_fillers_are_not_double_counted() -> None:
    stats = analyse_text("you know, you know it works")
    # "you know" counts twice as a phrase; the bare "know" is not re-counted.
    assert stats.filler_count == 2
    assert {item["term"] for item in stats.top_fillers} == {"you know"}


def test_hedges_are_tracked_separately_from_fillers() -> None:
    stats = analyse_text("I think we should probably ship it")
    assert stats.hedge_count >= 2
    assert stats.filler_count == 0


def test_filler_rate_is_length_independent() -> None:
    short = analyse_text("um yes")
    long = analyse_text("um yes " + "word " * 100)
    assert short.filler_rate_per_100_words > long.filler_rate_per_100_words


def test_empty_text_yields_zeroed_stats() -> None:
    stats = analyse_text("   ")
    assert stats.word_count == 0
    assert stats.filler_rate_per_100_words == 0.0


def test_segment_aggregation_splits_by_speaker() -> None:
    stats = analyse_segments(
        [_Segment("agent", "Um, hello there."), _Segment("customer", "I am upset.")]
    )
    assert stats["agent"]["filler_count"] == 1
    assert stats["customer"]["filler_count"] == 0
    assert stats["totals"]["word_count"] > 0


def test_talk_ratio_prefers_timings_and_falls_back_to_words() -> None:
    timed = talk_ratio([_Segment("agent", "a", 0, 6000), _Segment("customer", "b", 6000, 8000)])
    assert timed == 0.75

    untimed = talk_ratio([_Segment("agent", "one two three"), _Segment("customer", "four")])
    assert untimed == 0.75

    assert talk_ratio([]) is None


# ------------------------------------------------------------ due dates


def test_due_dates_resolve_from_spoken_phrases() -> None:
    wednesday = datetime(2026, 8, 26, 9, 30, tzinfo=UTC)
    assert resolve_due_date("by Friday", now=wednesday).strftime("%a") == "Fri"
    assert resolve_due_date("tomorrow", now=wednesday).day == 27
    assert resolve_due_date("in 3 days", now=wednesday).day == 29
    assert resolve_due_date("next week", now=wednesday).strftime("%a") == "Mon"


def test_unrecognised_timing_stays_unresolved() -> None:
    """Better an empty due date than a wrong one on a customer commitment."""
    assert resolve_due_date("sometime soon-ish maybe") is None
    assert resolve_due_date(None) is None
    assert resolve_due_date("") is None


# ------------------------------------------------------------- retention


def test_retention_precedence_and_indefinite_hold() -> None:
    uploaded = datetime(2026, 1, 1, tzinfo=UTC)
    assert compute_purge_after(
        org_retention_days=90, number_retention_days=7, uploaded_at=uploaded
    ).day == 8
    assert compute_purge_after(
        org_retention_days=30, number_retention_days=None, uploaded_at=uploaded
    ).day == 31
    assert compute_purge_after(org_retention_days=0, number_retention_days=None) is None


# ------------------------------------------------------------ time range


def test_range_is_capped_and_ordered() -> None:
    start, end = resolve_range(days=10_000)
    assert (end - start).days <= 366

    flipped_start, flipped_end = resolve_range(
        start=datetime(2026, 5, 1, tzinfo=UTC), end=datetime(2026, 4, 1, tzinfo=UTC)
    )
    assert flipped_start < flipped_end


def test_bucket_scales_with_the_window() -> None:
    now = datetime(2026, 8, 26, tzinfo=UTC)
    assert default_bucket(now.replace(hour=0), now.replace(hour=12)) == "hour"
    assert default_bucket(now.replace(day=1), now) == "day"
    assert default_bucket(now.replace(year=2025), now) == "week"


# --------------------------------------------------- shared model parsing


@pytest.fixture
def parser() -> SharedModelSpeechToText:
    return SharedModelSpeechToText(endpoint_url="http://speech.invalid/transcribe")


@pytest.fixture
def hints() -> TranscriptionHints:
    return TranscriptionHints(agent_number="+919876543210", customer_number="+919000000001")


def test_parses_whisper_style_seconds_and_speaker_labels(parser, hints) -> None:
    result = parser.parse_payload(
        {
            "language": "en",
            "segments": [
                {"speaker": "SPEAKER_00", "start": 0.0, "end": 3.4, "text": "Hello",
                 "emotion": [{"label": "calm", "score": 0.6}, {"label": "warm", "score": 0.9}]},
                {"speaker": "SPEAKER_01", "start": 3.6, "end": 8.2, "text": "I have a problem",
                 "emotion": "frustrated"},
            ],
        },
        hints=hints,
    )
    assert [segment.speaker for segment in result.segments] == ["agent", "customer"]
    assert result.segments[0].end_ms == 3400  # seconds promoted to milliseconds
    assert result.segments[0].tone.label == "warm"  # highest-scoring emotion wins
    assert result.duration_seconds == 8.2


def test_parses_wrapped_millisecond_payloads(parser, hints) -> None:
    result = parser.parse_payload(
        {
            "result": {
                "model": "asr-2", "duration_seconds": 12.5, "text": "full text",
                "tone": {"label": "tense"},
                "utterances": [
                    {"speaker": "agent", "start_ms": 0, "end_ms": 5000, "content": "Hi",
                     "tone": {"label": "warm", "confidence": 0.7, "valence": 0.5}}
                ],
            }
        },
        hints=hints,
    )
    assert result.model == "asr-2"
    assert result.tone_overall == "tense"
    assert result.segments[0].tone.valence == 0.5


def test_out_of_range_scores_are_clamped(parser, hints) -> None:
    result = parser.parse_payload(
        {"chunks": ["one", "two"], "confidence": 1.4}, hints=hints
    )
    assert result.confidence == 1.0
    assert len(result.segments) == 2


def test_an_empty_transcript_is_a_permanent_failure(parser, hints) -> None:
    """Retrying an empty result just burns the same call three more times."""
    from app.core.errors import ProviderError

    with pytest.raises(ProviderError) as caught:
        parser.parse_payload({"segments": []}, hints=hints)
    assert caught.value.retryable is False


def test_segments_are_returned_in_time_order(parser, hints) -> None:
    result = parser.parse_payload(
        {
            "segments": [
                {"speaker": "agent", "start_ms": 5000, "end_ms": 7000, "text": "second"},
                {"speaker": "customer", "start_ms": 1000, "end_ms": 3000, "text": "first"},
            ]
        },
        hints=hints,
    )
    assert [segment.text for segment in result.segments] == ["first", "second"]
