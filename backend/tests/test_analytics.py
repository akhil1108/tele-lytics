"""Dashboard aggregates and tenant isolation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.models import Analysis, Call, Organization, User
from app.services import metrics
from app.services.pipeline import run_analysis, run_transcription
from app.services.timerange import resolve_range
from tests.conftest import call_payload

WAV = b"RIFF\x00\x00\x00\x00WAVEfmt " + b"\x00" * 256


async def _processed_call(client, session, device_headers, ref: str) -> str:
    created = await client.post(
        "/v1/mobile/calls", headers=device_headers, json=call_payload(external_ref=ref)
    )
    call_id = created.json()["id"]
    await client.post(
        f"/v1/mobile/calls/{call_id}/recording",
        headers=device_headers,
        files={"file": ("c.wav", WAV, "audio/wav")},
        data={"duration_seconds": "180"},
    )
    await run_transcription(session, call_id)
    await run_analysis(session, call_id)
    return call_id


async def test_overview_reflects_processed_calls(
    client: AsyncClient, session: AsyncSession, device_headers: dict,
    admin_headers: dict, recording_policy,
) -> None:
    for index in range(3):
        await _processed_call(client, session, device_headers, f"ref-{index}")

    response = await client.get(
        "/v1/analytics/overview", headers=admin_headers, params={"days": 7}
    )
    assert response.status_code == 200
    body = response.json()

    assert body["calls_total"] == 3
    assert body["calls_recorded"] == 3
    assert body["calls_analysed"] == 3
    assert body["recording_coverage"] == 1.0
    assert body["agents_total"] == 1
    assert body["numbers_with_recording_enabled"] == 1
    assert body["avg_sentiment"] is not None
    assert body["total_talk_seconds"] > 0


async def test_satisfaction_rate_excludes_abstentions(
    session: AsyncSession, org, agent
) -> None:
    """A call the model could not judge must not count as a dissatisfied one."""
    now = datetime.now(UTC)
    for index, verdict in enumerate([True, True, False, None]):
        call = Call(
            org_id=org.id, agent_id=agent.id, direction="inbound",
            agent_number=agent.phone_number, customer_number="+919000000009",
            started_at=now - timedelta(minutes=index + 1), duration_seconds=120,
        )
        session.add(call)
        await session.flush()
        session.add(
            Analysis(
                org_id=org.id, call_id=call.id, provider="mock",
                summary="s", sentiment_overall="neutral", sentiment_score=0.1,
                customer_satisfied=verdict,
            )
        )
    await session.commit()

    start, end = resolve_range(days=7)
    result = await metrics.overview(session, org.id, start, end)

    assert result.satisfied_count == 2
    assert result.unsatisfied_count == 1
    assert result.unknown_satisfaction_count == 1
    # 2 of the 3 decided calls, not 2 of 4.
    assert result.satisfaction_rate == round(2 / 3, 3)


async def test_recording_coverage_ignores_calls_policy_excluded(
    session: AsyncSession, org, agent
) -> None:
    """Coverage measures pipeline reliability, not policy scope."""
    now = datetime.now(UTC)
    # Two calls policy said to record; one succeeded. One call policy excluded.
    for expected, recorded in [(True, True), (True, False), (False, False)]:
        session.add(
            Call(
                org_id=org.id, agent_id=agent.id, direction="outbound",
                agent_number=agent.phone_number, customer_number="+919000000008",
                started_at=now - timedelta(minutes=1), duration_seconds=60,
                recording_expected=expected, has_recording=recorded,
            )
        )
    await session.commit()

    start, end = resolve_range(days=7)
    result = await metrics.overview(session, org.id, start, end)
    assert result.calls_total == 3
    assert result.recording_coverage == 0.5  # 1 of 2 expected, not 1 of 3


async def test_timeseries_fills_empty_buckets(
    client: AsyncClient, admin_headers: dict, recording_policy
) -> None:
    response = await client.get(
        "/v1/analytics/timeseries",
        headers=admin_headers,
        params={"days": 7, "bucket": "day"},
    )
    assert response.status_code == 200
    points = response.json()
    # A gap-free axis: eight day boundaries span a seven-day window.
    assert len(points) == 8
    assert all(point["calls"] == 0 for point in points)


async def test_sentiment_breakdown_has_a_stable_label_order(
    client: AsyncClient, admin_headers: dict
) -> None:
    response = await client.get("/v1/analytics/sentiment", headers=admin_headers)
    assert [row["label"] for row in response.json()] == [
        "very_negative", "negative", "neutral", "positive", "very_positive"
    ]


async def test_leaderboard_and_fillers(
    client: AsyncClient, session: AsyncSession, device_headers: dict,
    admin_headers: dict, recording_policy,
) -> None:
    await _processed_call(client, session, device_headers, "lead-1")

    board = await client.get("/v1/analytics/agents", headers=admin_headers)
    assert board.status_code == 200
    rows = board.json()
    assert len(rows) == 1
    assert rows[0]["calls"] == 1
    assert rows[0]["agent_name"] == "Priya Sharma"

    fillers = await client.get(
        "/v1/analytics/fillers", headers=admin_headers, params={"speaker": "agent"}
    )
    assert fillers.status_code == 200
    assert all("term" in item and "count" in item for item in fillers.json())


async def test_recording_coverage_by_number_pairs_config_with_reality(
    client: AsyncClient, session: AsyncSession, device_headers: dict,
    admin_headers: dict, recording_policy,
) -> None:
    await _processed_call(client, session, device_headers, "cov-1")

    response = await client.get("/v1/analytics/recording-coverage", headers=admin_headers)
    assert response.status_code == 200
    rows = response.json()
    assert rows[0]["recording_enabled"] is True
    assert rows[0]["configured"] is True
    assert rows[0]["calls"] == 1
    assert rows[0]["recorded"] == 1


async def test_one_tenant_cannot_see_another(
    client: AsyncClient, session: AsyncSession, device_headers: dict,
    admin_headers: dict, recording_policy,
) -> None:
    await _processed_call(client, session, device_headers, "mine-1")

    other_org = Organization(name="Contoso", slug="contoso")
    session.add(other_org)
    await session.flush()
    session.add(
        User(
            org_id=other_org.id, email="admin@contoso-demo.com", full_name="Other Admin",
            password_hash=hash_password("another-strong-password"), role="admin",
        )
    )
    await session.commit()

    login = await client.post(
        "/v1/auth/login",
        json={"email": "admin@contoso-demo.com", "password": "another-strong-password"},
    )
    other_headers = {"Authorization": f"Bearer {login.json()['tokens']['access_token']}"}

    calls = await client.get("/v1/calls", headers=other_headers)
    assert calls.status_code == 200
    assert calls.json()["total"] == 0

    overview = await client.get("/v1/analytics/overview", headers=other_headers)
    assert overview.json()["calls_total"] == 0
    assert overview.json()["agents_total"] == 0


async def test_supervisor_cannot_change_configuration(
    client: AsyncClient, session: AsyncSession, org, admin_headers: dict
) -> None:
    session.add(
        User(
            org_id=org.id, email="sup@northwindsupport.com", full_name="Sam Supervisor",
            password_hash=hash_password("supervisor-password-1"), role="supervisor",
        )
    )
    await session.commit()

    login = await client.post(
        "/v1/auth/login",
        json={"email": "sup@northwindsupport.com", "password": "supervisor-password-1"},
    )
    headers = {"Authorization": f"Bearer {login.json()['tokens']['access_token']}"}

    # Supervisors read everything...
    assert (await client.get("/v1/analytics/overview", headers=headers)).status_code == 200
    assert (await client.get("/v1/calls", headers=headers)).status_code == 200

    # ...but do not change recording configuration or the roster.
    blocked = await client.post(
        "/v1/numbers", headers=headers, json={"e164": "+919111111111", "recording_enabled": True}
    )
    assert blocked.status_code == 403
    blocked_agent = await client.post(
        "/v1/agents", headers=headers,
        json={"display_name": "Nope", "phone_number": "+919222222222"},
    )
    assert blocked_agent.status_code == 403
