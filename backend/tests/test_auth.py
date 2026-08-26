"""Authentication, tenancy and device pairing."""

from __future__ import annotations

from httpx import AsyncClient

from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD


async def test_login_returns_session_and_tokens(client: AsyncClient, admin) -> None:
    response = await client.post(
        "/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == ADMIN_EMAIL
    assert body["user"]["role"] == "admin"
    assert body["organization_name"] == "Northwind"
    assert body["tokens"]["access_token"]
    assert body["tokens"]["refresh_token"]


async def test_wrong_password_is_indistinguishable_from_unknown_email(
    client: AsyncClient, admin
) -> None:
    wrong = await client.post(
        "/v1/auth/login", json={"email": ADMIN_EMAIL, "password": "not-the-password"}
    )
    unknown = await client.post(
        "/v1/auth/login", json={"email": "nobody@northwindsupport.com", "password": "whatever123"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


async def test_protected_route_rejects_missing_and_bad_tokens(client: AsyncClient) -> None:
    assert (await client.get("/v1/auth/me")).status_code == 401
    bad = await client.get("/v1/auth/me", headers={"Authorization": "Bearer nonsense"})
    assert bad.status_code == 401


async def test_refresh_token_cannot_be_used_as_access_token(
    client: AsyncClient, admin
) -> None:
    login = await client.post(
        "/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    refresh_token = login.json()["tokens"]["refresh_token"]

    response = await client.get(
        "/v1/auth/me", headers={"Authorization": f"Bearer {refresh_token}"}
    )
    assert response.status_code == 401

    exchanged = await client.post("/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert exchanged.status_code == 200
    assert exchanged.json()["access_token"]


async def test_pairing_code_is_single_use(
    client: AsyncClient, admin_headers: dict, agent
) -> None:
    code_response = await client.post(
        f"/v1/auth/agents/{agent.id}/pairing-code", headers=admin_headers
    )
    code = code_response.json()["code"]

    first = await client.post("/v1/auth/devices/pair", json={"code": code})
    assert first.status_code == 200
    assert first.json()["agent_number"] == agent.phone_number

    second = await client.post("/v1/auth/devices/pair", json={"code": code})
    assert second.status_code == 401
    assert "already been used" in second.json()["error"]["message"]


async def test_revoked_device_token_stops_working(
    client: AsyncClient, admin_headers: dict, agent
) -> None:
    code = (
        await client.post(f"/v1/auth/agents/{agent.id}/pairing-code", headers=admin_headers)
    ).json()["code"]
    paired = (await client.post("/v1/auth/devices/pair", json={"code": code})).json()
    headers = {"Authorization": f"Bearer {paired['device_token']}"}

    assert (await client.get("/v1/mobile/me", headers=headers)).status_code == 200

    revoked = await client.post(
        f"/v1/auth/devices/{paired['device_id']}/revoke", headers=admin_headers
    )
    assert revoked.status_code == 200
    assert (await client.get("/v1/mobile/me", headers=headers)).status_code == 401


async def test_device_token_cannot_reach_dashboard_routes(
    client: AsyncClient, device_headers: dict
) -> None:
    """A handset credential is not a dashboard credential."""
    assert (await client.get("/v1/calls", headers=device_headers)).status_code == 401
    assert (await client.get("/v1/analytics/overview", headers=device_headers)).status_code == 401
