"""Call browsing and detail — the dashboard's main read paths."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.pipeline import run_analysis, run_transcription
from tests.conftest import CUSTOMER_NUMBER, call_payload

WAV = b"RIFF\x00\x00\x00\x00WAVEfmt " + b"\x00" * 256


async def _fully_processed(client: AsyncClient, session: AsyncSession, headers: dict) -> str:
    created = await client.post("/v1/mobile/calls", headers=headers, json=call_payload())
    call_id = created.json()["id"]
    await client.post(
        f"/v1/mobile/calls/{call_id}/recording",
        headers=headers,
        files={"file": ("c.wav", WAV, "audio/wav")},
        data={"duration_seconds": "200"},
    )
    await run_transcription(session, call_id)
    await run_analysis(session, call_id)
    return call_id


async def test_call_detail_returns_every_related_record(
    client: AsyncClient, session: AsyncSession, device_headers: dict,
    admin_headers: dict, recording_policy,
) -> None:
    """The detail page needs recording, transcript, analysis, tasks and jobs in
    one response — and none of them may lazy-load during serialisation."""
    call_id = await _fully_processed(client, session, device_headers)

    response = await client.get(f"/v1/calls/{call_id}", headers=admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["agent_name"] == "Priya Sharma"
    assert body["recording"]["status"] == "stored"
    assert body["transcript"]["segments"]
    assert body["transcript"]["segments"][0]["tone_label"]
    assert body["analysis"]["summary"]
    assert body["analysis"]["stopword_stats"]["agent"]["filler_count"] >= 0
    assert body["action_items"]
    assert {job["stage"] for job in body["jobs"]} == {"transcribe", "analyze"}


async def test_call_list_carries_the_columns_the_table_renders(
    client: AsyncClient, session: AsyncSession, device_headers: dict,
    admin_headers: dict, recording_policy,
) -> None:
    call_id = await _fully_processed(client, session, device_headers)

    response = await client.get("/v1/calls", headers=admin_headers, params={"days": 7})
    assert response.status_code == 200
    item = next(row for row in response.json()["items"] if row["id"] == call_id)

    assert item["agent_name"] == "Priya Sharma"
    assert item["agent_team"] == "Support"
    assert item["has_transcript"] is True
    assert item["has_analysis"] is True
    assert item["processing_status"] == "complete"
    assert item["sentiment_overall"]


async def test_processing_status_tracks_pipeline_progress(
    client: AsyncClient, session: AsyncSession, device_headers: dict,
    admin_headers: dict, recording_policy,
) -> None:
    created = await client.post("/v1/mobile/calls", headers=device_headers, json=call_payload())
    call_id = created.json()["id"]

    async def status_now() -> str:
        listing = await client.get("/v1/calls", headers=admin_headers)
        return next(row for row in listing.json()["items"] if row["id"] == call_id)[
            "processing_status"
        ]

    assert await status_now() == "no_recording"

    await client.post(
        f"/v1/mobile/calls/{call_id}/recording",
        headers=device_headers,
        files={"file": ("c.wav", WAV, "audio/wav")},
    )
    assert await status_now() == "transcribing"

    await run_transcription(session, call_id)
    assert await status_now() == "analysing"

    await run_analysis(session, call_id)
    assert await status_now() == "complete"


async def test_search_matches_both_dialled_and_normalised_numbers(
    client: AsyncClient, device_headers: dict, admin_headers: dict
) -> None:
    await client.post("/v1/mobile/calls", headers=device_headers, json=call_payload())

    for query in (CUSTOMER_NUMBER, "09000000001", "Rohit"):
        response = await client.get(
            "/v1/calls", headers=admin_headers, params={"search": query}
        )
        assert response.json()["total"] == 1, f"search {query!r} found nothing"

    miss = await client.get(
        "/v1/calls", headers=admin_headers, params={"search": "+919999999999"}
    )
    assert miss.json()["total"] == 0


async def test_filters_and_pagination(
    client: AsyncClient, device_headers: dict, admin_headers: dict
) -> None:
    for index in range(5):
        await client.post(
            "/v1/mobile/calls",
            headers=device_headers,
            json=call_payload(
                external_ref=f"page-{index}",
                direction="inbound" if index % 2 == 0 else "outbound",
            ),
        )

    inbound = await client.get(
        "/v1/calls", headers=admin_headers, params={"direction": "inbound"}
    )
    assert inbound.json()["total"] == 3

    page = await client.get("/v1/calls", headers=admin_headers, params={"limit": 2, "offset": 2})
    body = page.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["offset"] == 2


async def test_audio_streams_back_the_uploaded_bytes(
    client: AsyncClient, device_headers: dict, admin_headers: dict, recording_policy
) -> None:
    created = await client.post("/v1/mobile/calls", headers=device_headers, json=call_payload())
    call_id = created.json()["id"]
    await client.post(
        f"/v1/mobile/calls/{call_id}/recording",
        headers=device_headers,
        files={"file": ("c.wav", WAV, "audio/wav")},
    )

    audio = await client.get(f"/v1/calls/{call_id}/audio", headers=admin_headers)
    assert audio.status_code == 200
    assert audio.headers["content-type"].startswith("audio/wav")
    assert audio.content == WAV


async def test_audio_requires_authentication(
    client: AsyncClient, device_headers: dict, recording_policy
) -> None:
    created = await client.post("/v1/mobile/calls", headers=device_headers, json=call_payload())
    response = await client.get(f"/v1/calls/{created.json()['id']}/audio")
    assert response.status_code == 401


async def test_reprocess_requires_the_prior_stage(
    client: AsyncClient, session: AsyncSession, device_headers: dict,
    admin_headers: dict, recording_policy,
) -> None:
    created = await client.post("/v1/mobile/calls", headers=device_headers, json=call_payload())
    call_id = created.json()["id"]

    no_audio = await client.post(
        f"/v1/calls/{call_id}/reprocess", headers=admin_headers, params={"stage": "transcribe"}
    )
    assert no_audio.status_code == 400

    no_transcript = await client.post(
        f"/v1/calls/{call_id}/reprocess", headers=admin_headers, params={"stage": "analyze"}
    )
    assert no_transcript.status_code == 400

    await client.post(
        f"/v1/mobile/calls/{call_id}/recording",
        headers=device_headers,
        files={"file": ("c.wav", WAV, "audio/wav")},
    )
    queued = await client.post(
        f"/v1/calls/{call_id}/reprocess", headers=admin_headers, params={"stage": "transcribe"}
    )
    assert queued.status_code == 200


async def test_task_board_lists_and_closes_items(
    client: AsyncClient, session: AsyncSession, device_headers: dict,
    admin_headers: dict, recording_policy,
) -> None:
    await _fully_processed(client, session, device_headers)

    board = await client.get("/v1/tasks", headers=admin_headers)
    assert board.status_code == 200
    assert board.json()["total"] > 0
    task = board.json()["items"][0]
    assert task["customer_number"] == CUSTOMER_NUMBER

    done = await client.patch(
        f"/v1/tasks/{task['id']}", headers=admin_headers, json={"status": "done"}
    )
    assert done.status_code == 200
    assert done.json()["completed_at"] is not None

    # Closed work drops off the default board.
    after = await client.get("/v1/tasks", headers=admin_headers)
    assert all(item["id"] != task["id"] for item in after.json()["items"])


async def test_agent_roster_reports_per_agent_stats(
    client: AsyncClient, session: AsyncSession, device_headers: dict,
    admin_headers: dict, recording_policy,
) -> None:
    await _fully_processed(client, session, device_headers)

    response = await client.get("/v1/agents", headers=admin_headers, params={"days": 7})
    assert response.status_code == 200
    row = response.json()[0]
    assert row["display_name"] == "Priya Sharma"
    assert row["calls_in_range"] == 1
    assert row["avg_sentiment"] is not None


async def test_presence_counts_update_when_an_agent_goes_on_call(
    client: AsyncClient, device_headers: dict, admin_headers: dict
) -> None:
    before = await client.get("/v1/agents/presence", headers=admin_headers)
    assert before.json()["on_call"] == 0
    assert before.json()["offline"] == 1

    await client.post("/v1/mobile/status", headers=device_headers, json={"status": "on_call"})

    after = await client.get("/v1/agents/presence", headers=admin_headers)
    assert after.json()["on_call"] == 1
    assert after.json()["online"] == 1
    assert after.json()["offline"] == 0


async def test_agent_home_summary(
    client: AsyncClient, session: AsyncSession, device_headers: dict, recording_policy
) -> None:
    await _fully_processed(client, session, device_headers)

    response = await client.get("/v1/mobile/summary", headers=device_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["calls_today"] == 1
    assert body["recorded_today"] == 1
    assert body["talk_seconds_today"] > 0
    assert body["agent_name"] == "Priya Sharma"
