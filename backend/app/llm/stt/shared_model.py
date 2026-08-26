"""Adapter for a self-hosted or third-party speech model reached over HTTP.

This is the seam the platform is built around: point `STT_ENDPOINT_URL` at
whatever speech-plus-tone model you are running and the rest of the pipeline is
unchanged. The wire contract is documented in `docs/STT_CONTRACT.md`.

Parsing is deliberately forgiving, because real speech APIs disagree on almost
every field name: seconds vs milliseconds, `speaker`/`channel`/`speaker_label`,
`tone` vs `emotion` vs `affect`, segments under `segments`/`results`/`chunks`.
Anything recognisable is mapped; anything unrecognised is preserved in `raw` so
no information is silently dropped.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import settings
from app.core.errors import ProviderError
from app.core.logging import get_logger
from app.llm.schemas import ToneReading, TranscriptionResult, TranscriptSegmentResult
from app.llm.stt.base import AudioRef, TranscriptionHints

log = get_logger(__name__)

_SEGMENT_KEYS = ("segments", "results", "chunks", "utterances", "turns")
_TEXT_KEYS = ("text", "transcript", "content", "value")
_TONE_KEYS = ("tone", "emotion", "affect", "prosody", "sentiment")


def _first(payload: dict, keys: tuple[str, ...], default: Any = None) -> Any:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return default


def _to_ms(value: Any) -> int:
    """Accept milliseconds or fractional seconds and return milliseconds.

    A float is always seconds; an int below the threshold is seconds too — no
    real segment starts 30 ms into a call and lands on a whole number, whereas
    "starts at second 12" is extremely common.
    """
    if value is None:
        return 0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if isinstance(value, float) or number < 1000:
        return int(round(number * 1000))
    return int(number)


def _map_speaker(value: Any, hints: TranscriptionHints) -> str:
    """Normalise whatever the model calls its speakers to agent/customer."""
    if value is None:
        return "unknown"
    text = str(value).strip().lower()

    if text in ("agent", "rep", "representative", "operator", "caller_a", "local"):
        return "agent"
    if text in ("customer", "client", "caller", "callee", "remote", "caller_b"):
        return "customer"

    # Numeric or SPEAKER_00 style labels: by convention channel 0 is the handset
    # holder, i.e. the agent.
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits:
        return "agent" if int(digits) == 0 else "customer"

    if hints.agent_number and hints.agent_number in text:
        return "agent"
    if hints.customer_number and hints.customer_number in text:
        return "customer"
    return "unknown"


def _parse_tone(payload: dict) -> ToneReading:
    tone = _first(payload, _TONE_KEYS)
    if tone is None:
        return ToneReading(
            valence=_coerce_float(payload.get("valence")),
            arousal=_coerce_float(payload.get("arousal")),
        )
    if isinstance(tone, str):
        return ToneReading(label=tone)
    if isinstance(tone, list) and tone:
        # Ranked emotions: take the strongest.
        top = max(
            (item for item in tone if isinstance(item, dict)),
            key=lambda item: _coerce_float(
                _first(item, ("score", "confidence", "probability"), 0.0)
            ) or 0.0,
            default=None,
        )
        if top is None:
            return ToneReading(label=str(tone[0]))
        return ToneReading(
            label=str(_first(top, ("label", "name", "emotion", "tone"), "")) or None,
            confidence=_coerce_float(_first(top, ("score", "confidence", "probability"))),
        )
    if isinstance(tone, dict):
        return ToneReading(
            label=str(_first(tone, ("label", "name", "emotion", "tone"), "")) or None,
            confidence=_coerce_float(_first(tone, ("confidence", "score", "probability"))),
            valence=_coerce_float(tone.get("valence")),
            arousal=_coerce_float(tone.get("arousal") or tone.get("energy")),
        )
    return ToneReading()


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float | None, low: float, high: float) -> float | None:
    if value is None:
        return None
    return max(low, min(high, value))


class SharedModelSpeechToText:
    """POSTs the audio as multipart/form-data and maps the JSON response."""

    name = "shared_model"

    def __init__(
        self,
        endpoint_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self.endpoint_url = endpoint_url or settings.stt_endpoint_url
        self.api_key = api_key or settings.stt_api_key
        self.model = model or settings.stt_model
        self.timeout_seconds = timeout_seconds or settings.stt_timeout_seconds
        if not self.endpoint_url:
            raise ProviderError(
                "STT_ENDPOINT_URL is not configured; set it or use STT_PROVIDER=mock",
                retryable=False,
            )

    async def transcribe(
        self, audio: AudioRef, hints: TranscriptionHints
    ) -> TranscriptionResult:
        metadata = {
            "language": hints.language or settings.stt_language_hint,
            "diarize": True,
            "return_tone": settings.stt_returns_tone,
            "speakers": 2,
            "call_id": hints.call_id,
            "direction": hints.direction,
            "agent_number": hints.agent_number,
            "customer_number": hints.customer_number,
            "vocabulary": hints.vocabulary,
        }
        if self.model:
            metadata["model"] = self.model

        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    self.endpoint_url,
                    headers=headers,
                    files={"audio": (audio.filename, audio.data, audio.mime_type)},
                    data={"metadata": json.dumps(metadata)},
                )
        except httpx.TimeoutException as exc:
            raise ProviderError(f"speech model timed out after {self.timeout_seconds}s") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"speech model unreachable: {exc}") from exc

        if response.status_code >= 500:
            raise ProviderError(
                f"speech model returned {response.status_code}: {response.text[:400]}"
            )
        if response.status_code >= 400:
            # 4xx means this recording will fail the same way on every retry.
            raise ProviderError(
                f"speech model rejected the request ({response.status_code}): "
                f"{response.text[:400]}",
                retryable=False,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError("speech model did not return JSON", retryable=False) from exc

        return self.parse_payload(payload, hints=hints, audio=audio)

    def parse_payload(
        self,
        payload: dict,
        *,
        hints: TranscriptionHints,
        audio: AudioRef | None = None,
    ) -> TranscriptionResult:
        """Map a provider response onto `TranscriptionResult`.

        Split out from the HTTP call so a new provider shape can be covered by a
        unit test without a server.
        """
        if not isinstance(payload, dict):
            raise ProviderError("speech model response was not an object", retryable=False)

        # Some gateways wrap the useful part.
        for wrapper in ("result", "data", "response", "output"):
            inner = payload.get(wrapper)
            if isinstance(inner, dict) and any(k in inner for k in (*_SEGMENT_KEYS, *_TEXT_KEYS)):
                payload = inner
                break

        raw_segments = _first(payload, _SEGMENT_KEYS, []) or []
        if not isinstance(raw_segments, list):
            raw_segments = []

        segments: list[TranscriptSegmentResult] = []
        for item in raw_segments:
            if isinstance(item, str):
                segments.append(TranscriptSegmentResult(text=item))
                continue
            if not isinstance(item, dict):
                continue

            text = str(_first(item, _TEXT_KEYS, "") or "").strip()
            if not text:
                continue

            start_ms = _to_ms(_first(item, ("start_ms", "start", "begin", "from", "offset")))
            end_ms = _to_ms(_first(item, ("end_ms", "end", "stop", "to")))
            if end_ms < start_ms:
                end_ms = start_ms

            tone = _parse_tone(item)
            segments.append(
                TranscriptSegmentResult(
                    speaker=_map_speaker(
                        _first(item, ("speaker", "speaker_label", "channel", "speaker_id")), hints
                    ),
                    start_ms=start_ms,
                    end_ms=end_ms,
                    text=text,
                    confidence=_clamp(
                        _coerce_float(_first(item, ("confidence", "score", "probability"))),
                        0.0,
                        1.0,
                    ),
                    tone=ToneReading(
                        label=tone.label,
                        confidence=_clamp(tone.confidence, 0.0, 1.0),
                        valence=_clamp(tone.valence, -1.0, 1.0),
                        arousal=_clamp(tone.arousal, 0.0, 1.0),
                    ),
                )
            )

        segments.sort(key=lambda seg: seg.start_ms)

        overall_tone = _parse_tone(payload)
        duration = _coerce_float(
            _first(payload, ("duration_seconds", "duration", "audio_duration"))
        )
        if duration is None and segments:
            duration = round(segments[-1].end_ms / 1000, 2)
        if duration is None and audio is not None:
            duration = audio.duration_seconds

        result = TranscriptionResult(
            provider=self.name,
            model=(
                str(_first(payload, ("model", "model_name", "engine"), self.model) or "") or None
            ),
            language=(
                str(
                    _first(payload, ("language", "detected_language", "lang"), hints.language) or ""
                )
                or None
            ),
            full_text=str(_first(payload, _TEXT_KEYS, "") or ""),
            confidence=_clamp(
                _coerce_float(_first(payload, ("confidence", "score", "avg_confidence"))), 0.0, 1.0
            ),
            tone_overall=overall_tone.label,
            duration_seconds=duration,
            segments=segments,
            raw=payload,
        )
        result.full_text = result.rebuild_full_text()

        if not result.full_text.strip():
            raise ProviderError(
                "speech model returned no usable text; check STT_CONTRACT.md for the "
                "expected response shape",
                retryable=False,
            )
        return result
