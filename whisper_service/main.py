"""Whisper + pyannote + emotion inference service.

Implements `docs/STT_CONTRACT.md` from the main repo — this is a drop-in for
`STT_PROVIDER=shared_model`. Point `STT_ENDPOINT_URL` at
`http://<host>:<port>/transcribe` and nothing else in the platform changes.

    STT_PROVIDER=shared_model
    STT_ENDPOINT_URL=http://localhost:8001/transcribe
    STT_MODEL=openai/whisper-large-v3-turbo
    STT_API_KEY=<same value as SERVICE_API_KEY below, if set>
"""

from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path

from fastapi import FastAPI, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse

import models
from config import settings

app = FastAPI(title="Whisper inference service")


@app.on_event("startup")
async def _load_models() -> None:
    models.warm_up()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "device": models.DEVICE}


@app.post("/transcribe")
async def transcribe(
    audio: UploadFile,
    metadata: str = Form(...),
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    if settings.service_api_key:
        expected = f"Bearer {settings.service_api_key}"
        if authorization != expected:
            raise HTTPException(status_code=401, detail="Invalid or missing bearer token")

    try:
        meta = json.loads(metadata)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"metadata is not valid JSON: {exc}") from exc

    raw = await audio.read()
    if len(raw) > settings.max_audio_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"audio exceeds {settings.max_audio_mb}MB")
    if not raw:
        raise HTTPException(status_code=400, detail="empty audio upload")

    suffix = Path(audio.filename or "audio.m4a").suffix or ".m4a"
    try:
        wav_path = models.decode_to_wav(raw, suffix)
    except RuntimeError as exc:
        # Bad/corrupt audio fails the same way on every retry.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        response = _run_pipeline(wav_path, meta)
    except RuntimeError as exc:
        # Model/infra trouble — worth retrying per STT_CONTRACT.md's 5xx rule.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        shutil.rmtree(Path(wav_path).parent, ignore_errors=True)

    return JSONResponse(response)


def _run_pipeline(wav_path: str, meta: dict) -> dict:
    waveform, sample_rate = models.load_waveform(wav_path)
    duration_seconds = round(waveform.shape[-1] / sample_rate, 2)

    full_text, chunks = models.transcribe(
        wav_path,
        language=meta.get("language"),
        vocabulary=meta.get("vocabulary") or [],
    )

    turns: list[models.Turn] = []
    roles: dict[str, str] = {}
    if meta.get("diarize", True):
        turns = models.diarize(wav_path, num_speakers=meta.get("speakers"))
        roles = models.roles_for(turns)

    segments = []
    tone_labels: list[str] = []
    for chunk in chunks:
        speaker = models.speaker_for(turns, roles, chunk.start_s, chunk.end_s) if turns else "unknown"
        segment_wave = models.slice_waveform(waveform, sample_rate, chunk.start_s, chunk.end_s)
        tone = models.score_tone(segment_wave, sample_rate)
        tone_labels.append(tone.label)

        segments.append(
            {
                "speaker": speaker,
                "start_ms": int(chunk.start_s * 1000),
                "end_ms": int(chunk.end_s * 1000),
                "text": chunk.text,
                "tone": {
                    "label": tone.label,
                    "confidence": tone.confidence,
                    "valence": tone.valence,
                    "arousal": tone.arousal,
                },
            }
        )

    tone_overall = Counter(tone_labels).most_common(1)[0][0] if tone_labels else None

    return {
        "provider": "whisper-service",
        "model": settings.whisper_model,
        "language": meta.get("language"),
        "text": full_text,
        "duration_seconds": duration_seconds,
        "tone_overall": tone_overall,
        "segments": segments,
    }
