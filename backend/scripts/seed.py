"""Populate a development database with a realistic organisation.

    python -m scripts.seed            # create + process demo calls
    python -m scripts.seed --reset    # drop everything first

Runs the real pipeline against the mock providers, so the dashboard comes up
with transcripts, tone, sentiment, filler analysis and extracted tasks — the
same code path production uses, just with different models plugged in.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.logging import configure_logging, get_logger  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.enums import (  # noqa: E402
    AgentStatus,
    CallDirection,
    CallStatus,
    JobStatus,
    NumberKind,
    RecordingStatus,
    UserRole,
)
from app.db.models import (  # noqa: E402
    Agent,
    Call,
    Organization,
    PhoneNumberPolicy,
    ProcessingJob,
    Recording,
    User,
)
from app.db.session import SessionLocal, engine  # noqa: E402
from app.services.pipeline import run_analysis, run_transcription  # noqa: E402
from app.services.retention import compute_purge_after  # noqa: E402
from app.services.storage import build_key, checksum, get_storage  # noqa: E402

log = get_logger("seed")

ADMIN_EMAIL = "admin@northwind.example.com"
ADMIN_PASSWORD = "northwind-admin-2026"

AGENTS = [
    ("Priya Sharma", "+919876543210", "Support", "NW-101"),
    ("Rahul Mehta", "+919876543211", "Sales", "NW-102"),
    ("Aisha Khan", "+919876543212", "Support", "NW-103"),
    ("Daniel Okoro", "+919876543213", "Retention", "NW-104"),
    ("Meera Iyer", "+919876543214", "Sales", "NW-105"),
]

CUSTOMERS = [
    ("+919000000001", "Rohit Verma"),
    ("+919000000002", "Sneha Patil"),
    ("+919000000003", "Arjun Nair"),
    ("+919000000004", "Fatima Sheikh"),
    ("+919000000005", "Vikram Desai"),
    ("+919000000006", "Neha Gupta"),
]

# A tiny valid-looking WAV header; the mock speech provider never decodes it.
DEMO_AUDIO = b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00" + b"\x00" * 2048


async def _complete_jobs(session, call_id: str) -> None:
    jobs = (
        await session.execute(select(ProcessingJob).where(ProcessingJob.call_id == call_id))
    ).scalars().all()
    now = datetime.now(UTC)
    for job in jobs:
        job.status = JobStatus.SUCCEEDED
        job.attempts = max(1, job.attempts)
        job.started_at = job.started_at or now
        job.finished_at = now
    await session.commit()


async def _sync_duration(session, call: Call) -> None:
    recording = (
        await session.execute(select(Recording).where(Recording.call_id == call.id))
    ).scalar_one_or_none()
    if recording and recording.duration_seconds:
        call.duration_seconds = int(recording.duration_seconds)
        call.ended_at = call.started_at + timedelta(seconds=call.duration_seconds)
        await session.commit()


async def reset() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    log.info("dropped all tables")


async def ensure_schema() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def seed(call_count: int, days: int) -> None:
    random.seed(20260826)  # a stable demo dataset between runs

    async with SessionLocal() as session:
        org = Organization(
            name="Northwind Telecom", slug="northwind", timezone="Asia/Kolkata",
            retention_days=90,
        )
        session.add(org)
        await session.flush()

        session.add(
            User(
                org_id=org.id, email=ADMIN_EMAIL, full_name="Ada Admin",
                password_hash=hash_password(ADMIN_PASSWORD), role=UserRole.OWNER,
            )
        )
        session.add(
            User(
                org_id=org.id, email="supervisor@northwind.example.com",
                full_name="Sam Supervisor",
                password_hash=hash_password("northwind-super-2026"),
                role=UserRole.SUPERVISOR,
            )
        )

        agents: list[Agent] = []
        for name, number, team, code in AGENTS:
            agent = Agent(
                org_id=org.id, display_name=name, phone_number=number, team=team,
                employee_code=code,
                status=random.choice(
                    [AgentStatus.AVAILABLE, AgentStatus.ON_CALL, AgentStatus.OFFLINE,
                     AgentStatus.WRAP_UP]
                ),
                status_changed_at=datetime.now(UTC) - timedelta(minutes=random.randint(1, 90)),
                last_seen_at=datetime.now(UTC) - timedelta(minutes=random.randint(0, 20)),
            )
            session.add(agent)
            agents.append(agent)
        await session.flush()

        # Recording is on for most agent lines, deliberately off for one — so
        # the dashboard's coverage view has something real to show.
        for index, agent in enumerate(agents):
            session.add(
                PhoneNumberPolicy(
                    org_id=org.id, e164=agent.phone_number,
                    label=f"{agent.display_name} — {agent.team}",
                    kind=NumberKind.AGENT, owner_agent_id=agent.id,
                    recording_enabled=index != 3,
                    record_inbound=True,
                    record_outbound=index != 4,
                    consent_required=True,
                    consent_prompt="This call may be recorded for quality and training purposes.",
                    retention_days=30 if agent.team == "Sales" else None,
                    notes=None if index != 3 else "Recording paused pending consent review.",
                )
            )
        # One customer who has asked not to be recorded.
        session.add(
            PhoneNumberPolicy(
                org_id=org.id, e164=CUSTOMERS[-1][0], label="Opted out of recording",
                kind=NumberKind.CUSTOMER, recording_enabled=False, consent_required=True,
                notes="Customer requested no call recording on 2026-07-14.",
            )
        )
        await session.commit()

        storage = get_storage()
        now = datetime.now(UTC)
        processed = 0

        for index in range(call_count):
            agent = random.choice(agents)
            customer_number, customer_name = random.choice(CUSTOMERS)
            policy_enabled = agent.employee_code != "NW-104"
            customer_opted_out = customer_number == CUSTOMERS[-1][0]
            direction = random.choice([CallDirection.INBOUND, CallDirection.OUTBOUND])
            should_record = policy_enabled and not customer_opted_out

            started = now - timedelta(
                days=random.randint(0, days - 1),
                hours=random.randint(9, 19),
                minutes=random.randint(0, 59),
            )
            duration = random.randint(45, 620)
            status = CallStatus.MISSED if random.random() < 0.06 else CallStatus.COMPLETED

            call = Call(
                org_id=org.id, agent_id=agent.id, external_ref=f"seed-{index:04d}",
                direction=direction, agent_number=agent.phone_number,
                customer_number=customer_number, customer_name=customer_name,
                started_at=started,
                ended_at=started + timedelta(seconds=duration),
                duration_seconds=duration if status == CallStatus.COMPLETED else 0,
                status=status,
                recording_expected=should_record and status == CallStatus.COMPLETED,
                recording_skipped_reason=(
                    None if should_record
                    else ("customer_opted_out" if customer_opted_out
                          else "recording_disabled_for_number")
                ),
            )
            session.add(call)
            await session.flush()

            if call.recording_expected:
                key = build_key(org.id, call.id, "audio/wav")
                await storage.put(key, DEMO_AUDIO, "audio/wav")
                session.add(
                    Recording(
                        org_id=org.id, call_id=call.id, storage_backend=storage.name,
                        storage_key=key, mime_type="audio/wav", size_bytes=len(DEMO_AUDIO),
                        duration_seconds=float(duration), checksum_sha256=checksum(DEMO_AUDIO),
                        status=RecordingStatus.STORED, consent_captured=True,
                        uploaded_at=call.ended_at,
                        purge_after=compute_purge_after(
                            org_retention_days=org.retention_days,
                            number_retention_days=30 if agent.team == "Sales" else None,
                            uploaded_at=call.ended_at,
                        ),
                    )
                )
                call.has_recording = True
            await session.commit()

            if call.has_recording:
                await run_transcription(session, call.id)
                await run_analysis(session, call.id)
                # The pipeline queues each stage; running it inline here would
                # otherwise leave every job sitting as "queued" and make the
                # dashboard's processing panel report a backlog that is not real.
                await _complete_jobs(session, call.id)
                # The speech model measured the audio; keep the call agreeing
                # with it so the sentiment timeline spans the right window.
                await _sync_duration(session, call)
                processed += 1
                if processed % 10 == 0:
                    log.info("processed calls", extra={"count": processed})

        log.info(
            "seed complete",
            extra={
                "organisation": org.name, "agents": len(agents),
                "calls": call_count, "processed": processed,
            },
        )

    print("\n" + "=" * 62)
    print("  Organisation : Northwind Telecom")
    print(f"  Dashboard    : {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    print("  Supervisor   : supervisor@northwind.example.com / northwind-super-2026")
    print(f"  Calls        : {call_count} ({processed} with full analysis)")
    print("=" * 62 + "\n")


async def amain() -> None:
    parser = argparse.ArgumentParser(description="Seed the call analytics database")
    parser.add_argument("--reset", action="store_true", help="drop all tables first")
    parser.add_argument("--calls", type=int, default=60, help="how many calls to create")
    parser.add_argument("--days", type=int, default=14, help="spread calls over this many days")
    args = parser.parse_args()

    configure_logging()
    if args.reset:
        await reset()
    await ensure_schema()
    await seed(args.calls, args.days)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(amain())
