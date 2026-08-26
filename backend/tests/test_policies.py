"""Recording policy — the decision the handset must honour."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PhoneNumberPolicy
from app.services import policies
from tests.conftest import AGENT_NUMBER, CUSTOMER_NUMBER


async def test_no_policy_means_do_not_record(session: AsyncSession, org, agent) -> None:
    """Recording defaults to off. An unrecorded call is a gap in a report; an
    unlawfully recorded one is a liability."""
    decision = await policies.decide(
        session, org_id=org.id, agent_number=agent.phone_number, direction="inbound"
    )
    assert decision.should_record is False
    assert decision.reason == "no_policy_configured"


async def test_enabled_policy_records(session: AsyncSession, org, agent, recording_policy):
    decision = await policies.decide(
        session, org_id=org.id, agent_number=agent.phone_number, direction="inbound"
    )
    assert decision.should_record is True
    assert decision.reason == "policy_enabled"
    assert decision.consent_required is True
    assert decision.consent_prompt  # a default prompt is always supplied


async def test_direction_flags_are_honoured(
    session: AsyncSession, org, agent, recording_policy
) -> None:
    recording_policy.record_outbound = False
    await session.commit()

    inbound = await policies.decide(
        session, org_id=org.id, agent_number=agent.phone_number, direction="inbound"
    )
    outbound = await policies.decide(
        session, org_id=org.id, agent_number=agent.phone_number, direction="outbound"
    )
    assert inbound.should_record is True
    assert outbound.should_record is False
    assert outbound.reason == "outbound_calls_not_recorded"


async def test_customer_opt_out_beats_an_enabled_agent_policy(
    session: AsyncSession, org, agent, recording_policy
) -> None:
    """A do-not-record request on the customer's number is worthless unless it
    overrides the agent's own settings."""
    session.add(
        PhoneNumberPolicy(
            org_id=org.id,
            e164=CUSTOMER_NUMBER,
            kind="customer",
            recording_enabled=False,
            label="Opted out",
        )
    )
    await session.commit()

    decision = await policies.decide(
        session,
        org_id=org.id,
        agent_number=agent.phone_number,
        customer_number=CUSTOMER_NUMBER,
        direction="inbound",
    )
    assert decision.should_record is False
    assert decision.reason == "customer_opted_out"


async def test_handset_endpoint_returns_the_same_decision(
    client: AsyncClient, device_headers: dict, recording_policy
) -> None:
    response = await client.get(
        "/v1/mobile/recording-policy",
        headers=device_headers,
        params={"customer_number": "09000000001", "direction": "inbound"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["should_record"] is True
    assert body["number"] == AGENT_NUMBER


async def test_handset_rejects_an_unparseable_number(
    client: AsyncClient, device_headers: dict
) -> None:
    response = await client.get(
        "/v1/mobile/recording-policy",
        headers=device_headers,
        params={"customer_number": "not-a-number"},
    )
    assert response.status_code == 400


async def test_policy_crud_and_number_normalisation(
    client: AsyncClient, admin_headers: dict, agent
) -> None:
    created = await client.post(
        "/v1/numbers",
        headers=admin_headers,
        json={
            "e164": "098765 43211",  # national format, deliberately messy
            "label": "Sales line",
            "recording_enabled": True,
            "retention_days": 30,
        },
    )
    assert created.status_code == 201, created.text
    policy = created.json()
    assert policy["e164"] == "+919876543211"  # normalised on the way in

    duplicate = await client.post(
        "/v1/numbers",
        headers=admin_headers,
        json={"e164": "+919876543211", "recording_enabled": False},
    )
    assert duplicate.status_code == 409

    disabled = await client.patch(
        f"/v1/numbers/{policy['id']}",
        headers=admin_headers,
        json={"recording_enabled": False},
    )
    assert disabled.status_code == 200
    assert disabled.json()["recording_enabled"] is False

    listing = await client.get(
        "/v1/numbers", headers=admin_headers, params={"recording_enabled": False}
    )
    assert listing.status_code == 200
    assert any(item["id"] == policy["id"] for item in listing.json()["items"])

    removed = await client.delete(f"/v1/numbers/{policy['id']}", headers=admin_headers)
    assert removed.status_code == 200
    assert "no longer be recorded" in removed.json()["message"]


async def test_dashboard_lookup_matches_handset_decision(
    client: AsyncClient, admin_headers: dict, recording_policy
) -> None:
    response = await client.get(
        "/v1/numbers/lookup",
        headers=admin_headers,
        params={"number": AGENT_NUMBER, "direction": "inbound"},
    )
    assert response.status_code == 200
    assert response.json()["should_record"] is True


async def test_unknown_direction_skips_the_direction_gates(
    session: AsyncSession, org, agent, recording_policy
) -> None:
    """An imported recording rarely says which way the call went.

    The per-direction switches govern capture, so they must not block an
    import that already happened — but the number-level switch still must.
    """
    recording_policy.record_outbound = False
    await session.commit()

    decision = await policies.decide(
        session, org_id=org.id, agent_number=agent.phone_number, direction="unknown"
    )
    assert decision.should_record is True


async def test_unknown_direction_still_obeys_the_number_switch(
    session: AsyncSession, org, agent, recording_policy
) -> None:
    recording_policy.recording_enabled = False
    await session.commit()

    decision = await policies.decide(
        session, org_id=org.id, agent_number=agent.phone_number, direction="unknown"
    )
    assert decision.should_record is False
    assert decision.reason == "recording_disabled_for_number"


async def test_unknown_direction_still_obeys_a_customer_opt_out(
    session: AsyncSession, org, agent, recording_policy
) -> None:
    session.add(
        PhoneNumberPolicy(
            org_id=org.id, e164=CUSTOMER_NUMBER, kind="customer", recording_enabled=False
        )
    )
    await session.commit()

    decision = await policies.decide(
        session,
        org_id=org.id,
        agent_number=agent.phone_number,
        customer_number=CUSTOMER_NUMBER,
        direction="unknown",
    )
    assert decision.should_record is False
    assert decision.reason == "customer_opted_out"


async def test_both_directions_off_refuses_an_unknown_direction_import(
    session: AsyncSession, org, agent, recording_policy
) -> None:
    recording_policy.record_inbound = False
    recording_policy.record_outbound = False
    await session.commit()

    decision = await policies.decide(
        session, org_id=org.id, agent_number=agent.phone_number, direction="unknown"
    )
    assert decision.should_record is False
    assert decision.reason == "no_direction_recorded"


async def test_handset_can_log_a_call_with_an_unknown_direction(
    client: AsyncClient, device_headers: dict
) -> None:
    from tests.conftest import call_payload

    response = await client.post(
        "/v1/mobile/calls",
        headers=device_headers,
        json=call_payload(direction="unknown", external_ref="imported-1"),
    )
    assert response.status_code == 201, response.text
    assert response.json()["direction"] == "unknown"
