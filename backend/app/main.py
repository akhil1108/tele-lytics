"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.router import api_router, ws_router
from app.core.config import settings
from app.core.errors import AppError, Unauthorized
from app.core.logging import configure_logging, get_logger
from app.db.session import engine
from app.worker import Worker

log = get_logger(__name__)

DESCRIPTION = """
Tele-lytics platform API.

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


# Constructed once, not per request: `Worker` throttles its own maintenance
# pass (reclaiming stale jobs, purging expired recordings) to once per
# `_MAINTENANCE_INTERVAL`, which only holds if the same instance answers
# every tick. Harmless if this process also happens to run the real
# `python -m app.worker` loop — same job-claiming table, same atomicity.
_tick_worker = Worker()


@app.post("/internal/worker/tick", tags=["meta"])
async def worker_tick(authorization: str | None = Header(default=None)) -> dict:
    """One pipeline-worker pass, for callers with no long-lived process to
    loop in — see the module docstring in `app/worker.py`. Disabled unless
    `WORKER_TICK_SECRET` is set; the docker-compose `worker` service never
    calls this, it runs the real loop directly."""
    if not settings.worker_tick_secret or authorization != f"Bearer {settings.worker_tick_secret}":
        raise Unauthorized()
    processed = await _tick_worker.run_once()
    return {"processed": processed}


app.include_router(api_router)
app.include_router(ws_router)
