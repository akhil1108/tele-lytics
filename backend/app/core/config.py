"""Application settings, loaded from the environment (see `.env.example`)."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- Core ----
    app_env: Literal["development", "test", "staging", "production"] = "development"
    app_name: str = "Tele-lytics"
    log_level: str = "INFO"
    api_base_url: str = "http://localhost:8000"

    # ---- Security ----
    secret_key: str = "insecure-development-key-change-me"
    access_token_ttl_minutes: int = 60
    refresh_token_ttl_days: int = 30
    device_token_ttl_days: int = 180
    # NoDecode: without it pydantic-settings tries to JSON-parse the env var,
    # which fails before the comma-splitting validator below ever runs.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    # ---- Database ----
    database_url: str = "sqlite+aiosqlite:///./data/callanalytics.sqlite3"

    # ---- Storage ----
    storage_backend: Literal["local", "s3"] = "local"
    storage_local_path: str = "./storage"
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_endpoint_url: str | None = None

    # ---- Speech to text ----
    stt_provider: Literal["shared_model", "mock"] = "mock"
    stt_endpoint_url: str | None = None
    stt_api_key: str | None = None
    stt_model: str | None = None
    stt_timeout_seconds: int = 900
    stt_language_hint: str = "en-IN"
    stt_returns_tone: bool = True

    # ---- Analysis LLM ----
    analysis_provider: Literal["claude", "mock", "workers_ai"] = "mock"
    anthropic_api_key: str | None = None
    analysis_model: str = "claude-opus-5"
    analysis_effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"
    analysis_max_tokens: int = 16000

    # Cloudflare Workers AI — lightweight, self-hosted-in-Cloudflare
    # alternative to Claude. Reached via Workers AI's OpenAI-compatible
    # endpoint, wrapped with Instructor for validate-and-retry structured
    # output (Cloudflare doesn't guarantee schema conformance on its own).
    workers_ai_account_id: str | None = None
    workers_ai_api_token: str | None = None
    workers_ai_model: str = "@cf/ibm-granite/granite-4.0-h-micro"
    workers_ai_max_tokens: int = 16000
    workers_ai_max_retries: int = 2
    workers_ai_timeout_seconds: int = 300

    # ---- Worker ----
    worker_poll_interval_seconds: float = 2.0
    worker_batch_size: int = 4
    worker_max_attempts: int = 3
    max_recording_mb: int = 200
    # Set to enable POST /internal/worker/tick — a single claim-and-process
    # pass over the job queue, triggered externally rather than by the
    # `python -m app.worker` loop's own polling. This is what lets the worker
    # run as a Cloudflare Container: there is no long-lived process to poll
    # in a loop there, only a Durable Object alarm invoking this endpoint on
    # a schedule. Unset (the default) leaves the endpoint disabled — the
    # `worker` service in docker-compose.yml never needs it, since it runs
    # the real loop directly.
    worker_tick_secret: str | None = None

    # ---- Retention ----
    default_retention_days: int = 90

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def max_recording_bytes(self) -> int:
        return self.max_recording_mb * 1024 * 1024

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
