"""End-to-end: handset logs a call, uploads audio, pipeline produces insight."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import JobStatus, ProcessingStage
from app.db.models import ActionItem, Analysis, ProcessingJob, Transcript
from app.services import queue
from app.services.pipeline import run_analysis, run_transcription
from tests.conftest import call_payload

WAV_BYTES = b"RIFF\x00\x00\x00\x00WAVEfmt " + b"\x00" * 512


async def _logged_call(client: AsyncClient, device_headers: dict, **overrides) -> dict:
    response = await client.post(
        "/v1/mobile/calls", headers=device_headers, json=call_payload(**overrides)
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _upload(client: AsyncClient, device_headers: dict, call_id: str) -> dict:
    response = await client.post(
        f"/v1/mobile/calls/{call_id}/recording",
        headers=device_headers,
        files={"file": ("call.wav", WAV_BYTES, "audio/wav")},
        data={"duration_seconds": "240.0", "consent_captured": "true"},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_full_pipeline_produces_transcript_analysis_and_tasks(
    client: AsyncClient,
    session: AsyncSession,
    device_headers: dict,
    recording_policy,
) -> None:
    call = await _logged_call(client, device_headers)
    recording = await _upload(client, device_headers, call["id"])

    assert recording["status"] == "stored"
    assert recording["consent_captured"] is True
    assert recording["purge_after"] is not None  # retention applied at upload

    # Uploading queues stage 1.
    job = (
        await session.execute(
            select(ProcessingJob).where(
                ProcessingJob.call_id == call["id"],
                ProcessingJob.stage == ProcessingStage.TRANSCRIBE,
            )
        )
    ).scalar_one()
    assert job.status == JobStatus.QUEUED

    transcript = await run_transcription(session, call["id"])
    assert transcript.full_text
    assert len(transcript.segments) > 0
    assert {segment.speaker for segment in transcript.segments} == {"agent", "customer"}
    assert any(segment.tone_label for segment in transcript.segments)

    # Stage 1 chains into stage 2.
    analyze_job = (
        await session.execute(
            select(ProcessingJob).where(
                ProcessingJob.call_id == call["id"],
                ProcessingJob.stage == ProcessingStage.ANALYZE,
            )
        )
    ).scalar_one()
    assert analyze_job.status == JobStatus.QUEUED

    analysis = await run_analysis(session, call["id"])
    assert analysis.summary
    assert -1.0 <= analysis.sentiment_score <= 1.0
    assert analysis.sentiment_overall in (
        "very_negative", "negative", "neutral", "positive", "very_positive"
    )
    # Filler counts are computed in code, so they must be present and exact.
    assert "agent" in analysis.stopword_stats
    assert analysis.stopword_stats["agent"]["filler_count"] >= 0
    assert analysis.agent_talk_ratio is not None

    items = (
        await session.execute(select(ActionItem).where(ActionItem.call_id == call["id"]))
    ).scalars().all()
    assert items, "the mock transcript contains commitments, so tasks are expected"
    assert all(item.title for item in items)


async def test_reprocessing_replaces_rather_than_duplicates(
    client: AsyncClient,
    session: AsyncSession,
    device_headers: dict,
    recording_policy,
) -> None:
    call = await _logged_call(client, device_headers)
    await _upload(client, device_headers, call["id"])

    await run_transcription(session, call["id"])
    await run_analysis(session, call["id"])
    first_tasks = len(
        (
            await session.execute(select(ActionItem).where(ActionItem.call_id == call["id"]))
        ).scalars().all()
    )

    # Run both stages again, as a model swap or a retry would.
    await run_transcription(session, call["id"])
    await run_analysis(session, call["id"])

    transcripts = (
        await session.execute(select(Transcript).where(Transcript.call_id == call["id"]))
    ).scalars().all()
    analyses = (
        await session.execute(select(Analysis).where(Analysis.call_id == call["id"]))
    ).scalars().all()
    tasks = (
        await session.execute(select(ActionItem).where(ActionItem.call_id == call["id"]))
    ).scalars().all()

    assert len(transcripts) == 1
    assert len(analyses) == 1
    assert len(tasks) == first_tasks


async def test_logging_the_same_call_twice_is_idempotent(
    client: AsyncClient, device_headers: dict
) -> None:
    first = await _logged_call(client, device_headers, external_ref="retry-me")
    second = await client.post(
        "/v1/mobile/calls",
        headers=device_headers,
        json=call_payload(external_ref="retry-me"),
    )
    assert second.status_code == 201
    assert second.json()["id"] == first["id"]


async def test_duration_is_derived_when_the_handset_omits_it(
    client: AsyncClient, device_headers: dict
) -> None:
    call = await _logged_call(client, device_headers)
    assert call["duration_seconds"] == 240  # 4 minutes between started_at and ended_at


async def test_upload_rejects_unsupported_and_empty_audio(
    client: AsyncClient, device_headers: dict
) -> None:
    call = await _logged_call(client, device_headers)

    wrong_type = await client.post(
        f"/v1/mobile/calls/{call['id']}/recording",
        headers=device_headers,
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert wrong_type.status_code == 400
    assert "Unsupported audio type" in wrong_type.json()["error"]["message"]

    empty = await client.post(
        f"/v1/mobile/calls/{call['id']}/recording",
        headers=device_headers,
        files={"file": ("call.wav", b"", "audio/wav")},
    )
    assert empty.status_code == 400


async def test_a_device_cannot_upload_to_another_agents_call(
    client: AsyncClient,
    session: AsyncSession,
    admin_headers: dict,
    device_headers: dict,
    org,
) -> None:
    from app.db.models import Agent

    other = Agent(org_id=org.id, display_name="Other Agent", phone_number="+919000009999")
    session.add(other)
    await session.commit()

    code = (
        await client.post(f"/v1/auth/agents/{other.id}/pairing-code", headers=admin_headers)
    ).json()["code"]
    other_headers = {
        "Authorization": "Bearer "
        + (await client.post("/v1/auth/devices/pair", json={"code": code})).json()["device_token"]
    }

    call = await _logged_call(client, device_headers)
    intruder = await client.post(
        f"/v1/mobile/calls/{call['id']}/recording",
        headers=other_headers,
        files={"file": ("call.wav", WAV_BYTES, "audio/wav")},
    )
    assert intruder.status_code == 404


async def test_failed_job_retries_then_parks(
    session: AsyncSession, org, agent, client: AsyncClient, device_headers: dict
) -> None:
    call = await _logged_call(client, device_headers)
    job = await queue.enqueue(
        session, org_id=org.id, call_id=call["id"], stage=ProcessingStage.TRANSCRIBE,
        max_attempts=2,
    )
    await session.commit()

    claimed = await queue.claim(session, worker_id="worker-a", limit=5)
    assert [item.id for item in claimed] == [job.id]
    await queue.mark_failed(session, claimed[0], "model timed out")
    assert claimed[0].status == JobStatus.QUEUED  # first failure retries

    claimed[0].scheduled_at = claimed[0].created_at  # skip the backoff window
    await session.commit()

    again = await queue.claim(session, worker_id="worker-a", limit=5)
    await queue.mark_failed(session, again[0], "model timed out")
    assert again[0].status == JobStatus.FAILED  # attempts exhausted


async def test_non_retryable_failure_parks_immediately(
    session: AsyncSession, org, client: AsyncClient, device_headers: dict
) -> None:
    call = await _logged_call(client, device_headers)
    await queue.enqueue(
        session, org_id=org.id, call_id=call["id"], stage=ProcessingStage.TRANSCRIBE,
        max_attempts=5,
    )
    await session.commit()

    claimed = await queue.claim(session, worker_id="worker-a", limit=5)
    await queue.mark_failed(session, claimed[0], "audio rejected", retryable=False)
    assert claimed[0].status == JobStatus.FAILED


async def test_two_workers_cannot_claim_the_same_job(
    session: AsyncSession, org, client: AsyncClient, device_headers: dict
) -> None:
    call = await _logged_call(client, device_headers)
    await queue.enqueue(
        session, org_id=org.id, call_id=call["id"], stage=ProcessingStage.TRANSCRIBE
    )
    await session.commit()

    first = await queue.claim(session, worker_id="worker-a", limit=5)
    second = await queue.claim(session, worker_id="worker-b", limit=5)
    assert len(first) == 1
    assert second == []


async def test_transcription_without_a_recording_is_not_retried(
    session: AsyncSession, client: AsyncClient, device_headers: dict
) -> None:
    from app.core.errors import ProviderError

    call = await _logged_call(client, device_headers)
    with pytest.raises(ProviderError) as caught:
        await run_transcription(session, call["id"])
    assert caught.value.retryable is False
