"""Pipeline worker.

Run alongside the API:

    python -m app.worker

Several workers can run at once — claiming is atomic, so they will not collide.

`Worker.run()` is this loop: poll forever, idle-backing-off between empty
ticks. Where nothing can run a long-lived process — a Cloudflare Container
has no equivalent of "just keep looping," only requests a Durable Object
routes in — `Worker.run_once()` is the same unit of work (one claim-and-
process pass) exposed for something external to invoke on a schedule
instead. See `POST /internal/worker/tick` in `app/main.py`.
"""

from __future__ import annotations

import asyncio
import signal
from datetime import UTC, datetime, timedelta

from app.core.config import settings
from app.core.errors import ProviderError
from app.core.logging import configure_logging, get_logger
from app.db.models import ProcessingJob
from app.db.session import SessionLocal
from app.services import queue
from app.services.pipeline import run_stage
from app.services.retention import purge_expired_recordings

log = get_logger(__name__)

_MAINTENANCE_INTERVAL = timedelta(minutes=10)


class Worker:
    def __init__(self) -> None:
        self.worker_id = queue.worker_identity()
        self._stopping = asyncio.Event()
        self._last_maintenance = datetime.now(UTC) - _MAINTENANCE_INTERVAL

    def request_stop(self, *_: object) -> None:
        if not self._stopping.is_set():
            log.info("shutdown requested; finishing current jobs")
            self._stopping.set()

    async def run(self) -> None:
        log.info(
            "worker started",
            extra={
                "worker_id": self.worker_id,
                "stt_provider": settings.stt_provider,
                "analysis_provider": settings.analysis_provider,
            },
        )
        while not self._stopping.is_set():
            processed = await self.run_once()

            if processed == 0:
                # Idle: wait out the poll interval, but wake immediately on stop.
                try:
                    await asyncio.wait_for(
                        self._stopping.wait(), timeout=settings.worker_poll_interval_seconds
                    )
                except TimeoutError:
                    pass
        log.info("worker stopped", extra={"worker_id": self.worker_id})

    async def run_once(self) -> int:
        """One claim-and-process pass. Never raises — a failed tick logs and
        reports zero processed, same as an empty queue, so a caller (the
        loop above, or an HTTP handler) doesn't need its own error handling."""
        try:
            return await self._tick()
        except Exception:
            log.exception("worker tick failed")
            return 0

    async def _tick(self) -> int:
        await self._maintenance()

        async with SessionLocal() as session:
            jobs = await queue.claim(
                session, worker_id=self.worker_id, limit=settings.worker_batch_size
            )

        if not jobs:
            return 0

        # Jobs run concurrently: both stages are I/O bound on a model call.
        await asyncio.gather(*(self._run_job(job.id) for job in jobs))
        return len(jobs)

    async def _run_job(self, job_id: str) -> None:
        async with SessionLocal() as session:
            job = await session.get(ProcessingJob, job_id)
            if job is None:
                return

            log.info(
                "job started",
                extra={
                    "job_id": job.id, "stage": job.stage,
                    "call_id": job.call_id, "attempt": job.attempts,
                },
            )
            try:
                await run_stage(session, job.stage, job.call_id)
            except ProviderError as exc:
                await session.rollback()
                await queue.mark_failed(session, job, str(exc), retryable=exc.retryable)
            except Exception as exc:  # unexpected — retry, it may be transient
                await session.rollback()
                log.exception("job raised", extra={"job_id": job.id, "stage": job.stage})
                await queue.mark_failed(session, job, f"{type(exc).__name__}: {exc}")
            else:
                await queue.mark_succeeded(session, job)
                log.info("job finished", extra={"job_id": job.id, "stage": job.stage})

    async def _maintenance(self) -> None:
        now = datetime.now(UTC)
        if now - self._last_maintenance < _MAINTENANCE_INTERVAL:
            return
        self._last_maintenance = now

        async with SessionLocal() as session:
            await queue.reclaim_stale(session)
            purged = await purge_expired_recordings(session)
            if purged:
                log.info("retention purge complete", extra={"purged": purged})


async def amain() -> None:
    configure_logging()
    worker = Worker()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, worker.request_stop)
        except NotImplementedError:  # pragma: no cover - Windows
            signal.signal(sig, worker.request_stop)

    await worker.run()


def main() -> None:
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
