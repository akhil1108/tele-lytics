"""Rating parameters, call categories, and the per-call lead verdict."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CallCategory, Lead, Organization
from app.services.pipeline import _resolve_category, run_analysis, run_transcription
from tests.conftest import call_payload

WAV_BYTES = b"RIFF\x00\x00\x00\x00WAVEfmt " + b"\x00" * 512


async def _logged_call(client: AsyncClient, device_headers: dict, **overrides) -> dict:
    response = await client.post(
        "/v1/mobile/calls", headers=device_headers, json=call_payload(**overrides)
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _upload(client: AsyncClient, device_headers: dict, call_id: str) -> None:
    response = await client.post(
        f"/v1/mobile/calls/{call_id}/recording",
        headers=device_headers,
        files={"file": ("call.wav", WAV_BYTES, "audio/wav")},
        data={"duration_seconds": "240.0", "consent_captured": "true"},
    )
    assert response.status_code == 201, response.text


# ------------------------------------------------------------- category resolution


async def test_category_falls_back_to_default_on_no_match(
    session: AsyncSession, org: Organization
) -> None:
    other = CallCategory(org_id=org.id, name="Support Request", sort_order=0)
    default = CallCategory(org_id=org.id, name="Other", is_default=True, sort_order=1)
    session.add_all([other, default])
    await session.commit()

    resolved = _resolve_category("Something the model invented", [other, default])
    assert resolved is default


async def test_category_matches_case_insensitively(
    session: AsyncSession, org: Organization
) -> None:
    category = CallCategory(org_id=org.id, name="Sales Enquiry", sort_order=0)
    session.add(category)
    await session.commit()

    resolved = _resolve_category("sales enquiry", [category])
    assert resolved is category


# --------------------------------------------------------------------- lead upsert


async def test_reanalysing_a_call_replaces_rather_than_duplicates_its_lead(
    client: AsyncClient, session: AsyncSession, device_headers: dict, recording_policy
) -> None:
    call = await _logged_call(client, device_headers)
    await _upload(client, device_headers, call["id"])

    await run_transcription(session, call["id"])
    await run_analysis(session, call["id"])
    await run_analysis(session, call["id"])  # a second run, as a model swap would trigger

    leads = (
        await session.execute(select(Lead).where(Lead.call_id == call["id"]))
    ).scalars().all()
    assert len(leads) == 1


async def test_marking_a_lead_contacted_survives_reanalysis(
    client: AsyncClient,
    session: AsyncSession,
    admin_headers: dict,
    device_headers: dict,
    recording_policy,
) -> None:
    """A supervisor's follow-up status is workflow state, not pipeline output —
    a re-run must not silently reset it back to 'new'."""
    call = await _logged_call(client, device_headers)
    await _upload(client, device_headers, call["id"])
    await run_transcription(session, call["id"])
    await run_analysis(session, call["id"])

    lead = (
        await session.execute(select(Lead).where(Lead.call_id == call["id"]))
    ).scalar_one()
    response = await client.patch(
        f"/v1/leads/{lead.id}", headers=admin_headers, json={"status": "contacted"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "contacted"

    await run_analysis(session, call["id"])
    await session.refresh(lead)
    assert lead.status == "contacted"


# ---------------------------------------------------------- rating parameter CRUD


async def test_rating_parameter_crud_is_admin_only(
    client: AsyncClient, admin_headers: dict
) -> None:
    create = await client.post(
        "/v1/rating-parameters",
        headers=admin_headers,
        json={"name": "Empathy", "description": "Did the agent acknowledge how they felt?"},
    )
    assert create.status_code == 201, create.text
    parameter_id = create.json()["id"]

    listed = await client.get("/v1/rating-parameters", headers=admin_headers)
    assert any(p["id"] == parameter_id for p in listed.json())

    bad_scale = await client.post(
        "/v1/rating-parameters",
        headers=admin_headers,
        json={"name": "Broken", "scale_min": 5, "scale_max": 1},
    )
    assert bad_scale.status_code == 400

    deleted = await client.delete(f"/v1/rating-parameters/{parameter_id}", headers=admin_headers)
    assert deleted.status_code == 200


async def test_default_call_category_cannot_be_deleted_or_deactivated(
    client: AsyncClient, session: AsyncSession, admin_headers: dict, org: Organization
) -> None:
    category = CallCategory(org_id=org.id, name="Other", is_default=True)
    session.add(category)
    await session.commit()

    delete = await client.delete(f"/v1/call-categories/{category.id}", headers=admin_headers)
    assert delete.status_code == 400

    deactivate = await client.patch(
        f"/v1/call-categories/{category.id}", headers=admin_headers, json={"is_active": False}
    )
    assert deactivate.status_code == 400
