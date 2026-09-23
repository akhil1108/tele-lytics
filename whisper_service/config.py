"""Settings for the Whisper inference service, loaded from the environment.

Mirrors the pattern in `backend/app/core/config.py`: everything has a
sensible default so the service runs with zero configuration for local
testing, and every value that matters in production is an env var.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # ---- Models ----
    # A Hugging Face hub id, or a local path — e.g. the folder you `hf-mount`
    # a fine-tuned checkpoint into.
    whisper_model: str = "openai/whisper-large-v3-turbo"
    diarization_model: str = "pyannote/speaker-diarization-3.1"
    emotion_model: str = "superb/wav2vec2-base-superb-er"

    # pyannote's diarization model is gated on the Hub — you must accept its
    # terms at huggingface.co/pyannote/speaker-diarization-3.1 and pass a
    # token with read access here.
    hf_token: str | None = None

    # Non-English -> English translation, per segment, via OpenAI's hosted
    # Whisper. Runs on the audio directly rather than on already-transcribed
    # text — a local model (Whisper here) transcribing code-switched Indian-
    # language speech tends to romanize it (Latin script, e.g. "agi dhe"
    # rather than ಆಗಿದೆ), and text-translation models expect native script,
    # so they silently fail to translate romanized input. Translating from
    # audio has no such requirement. `whisper-1` is the only OpenAI model
    # the /audio/translations endpoint currently supports.
    openai_api_key: str | None = None
    openai_translation_model: str = "whisper-1"

    # ---- Serving ----
    # Matches STT_API_KEY on the backend: when set, this service requires
    # `Authorization: Bearer <service_api_key>` on every request.
    service_api_key: str | None = None
    port: int = 8001
    # auto picks cuda > mps > cpu. Force one if auto-detection guesses wrong.
    device: str = "auto"

    # Longest recording this service will accept, mirrors MAX_RECORDING_MB.
    max_audio_mb: int = 200


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
