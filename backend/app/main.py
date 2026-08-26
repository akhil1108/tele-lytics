"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.router import api_router, ws_router
from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import configure_logging, get_logger
from app.db.session import engine

log = get_logger(__name__)

DESCRIPTION = """
Call analytics platform API.

Two clients talk to this service:

* the **admin dashboard** (`/v1/...` with a user JWT) — agents, calls,
  transcripts, insights and recording policy.
* the **agent mobile app** (`/v1/mobile/...` with a device token) — presence,
  call logging, per-number recording policy, and recording upload.

Uploaded audio runs through a two-stage pipeline: a speech model produces the
transcript and per-utterance tone, then an insight model produces sentiment,
filler-word analysis, tasks, recommended actions and a satisfaction verdict.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    log.info(
        "starting api",
        extra={
            "env": settings.app_env,
            "stt_provider": settings.stt_provider,
            "analysis_provider": settings.analysis_provider,
            "storage": settings.storage_backend,
        },
    )
    yield
    await engine.dispose()
    log.info("api stopped")


app = FastAPI(
    title=settings.app_name,
    description=DESCRIPTION,
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.detail}},
        headers=getattr(exc, "headers", None),
    )


@app.get("/health", tags=["meta"])
async def health() -> dict:
    """Liveness plus a real database round-trip — a process that cannot reach
    its database is not healthy, however happily it is running."""
    database_ok = True
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        log.exception("health check could not reach the database")
        database_ok = False

    return {
        "status": "ok" if database_ok else "degraded",
        "database": "ok" if database_ok else "unreachable",
        "env": settings.app_env,
        "version": app.version,
        "providers": {
            "speech_to_text": settings.stt_provider,
            "analysis": settings.analysis_provider,
            "storage": settings.storage_backend,
        },
    }


app.include_router(api_router)
app.include_router(ws_router)
