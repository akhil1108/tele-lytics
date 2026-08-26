"""Test fixtures.

Every test runs against a fresh in-memory SQLite database with the mock
providers selected, so the suite needs no Postgres, no object store and no
model credentials.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

# Configure before any application module reads settings.
_TMP_STORAGE = tempfile.mkdtemp(prefix="call-analytics-test-")
os.environ.update(
    APP_ENV="test",
    DATABASE_URL="sqlite+aiosqlite:///:memory:",
    SECRET_KEY="test-secret-key-not-for-production",
    STORAGE_BACKEND="local",
    STORAGE_LOCAL_PATH=_TMP_STORAGE,
    STT_PROVIDER="mock",
    ANALYSIS_PROVIDER="mock",
    CORS_ORIGINS="http://localhost:3000",
)

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.enums import UserRole  # noqa: E402
from app.db.models import Agent, Organization, PhoneNumberPolicy, User  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

ADMIN_EMAIL = "admin@northwindsupport.com"
ADMIN_PASSWORD = "correct-horse-battery"
AGENT_NUMBER = "+919876543210"
CUSTOMER_NUMBER = "+919000000001"


@pytest.fixture(autouse=True)
async def _schema() -> AsyncIterator[None]:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as db:
        yield db


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        yield http_client


@pytest.fixture
async def org(session: AsyncSession) -> Organization:
    organization = Organization(name="Northwind", slug="northwind", retention_days=90)
    session.add(organization)
    await session.commit()
    return organization


@pytest.fixture
async def admin(session: AsyncSession, org: Organization) -> User:
    user = User(
        org_id=org.id,
        email=ADMIN_EMAIL,
        full_name="Ada Admin",
        password_hash=hash_password(ADMIN_PASSWORD),
        role=UserRole.ADMIN,
    )
    session.add(user)
    await session.commit()
    return user


@pytest.fixture
async def agent(session: AsyncSession, org: Organization) -> Agent:
    record = Agent(
        org_id=org.id,
        display_name="Priya Sharma",
        phone_number=AGENT_NUMBER,
        team="Support",
        employee_code="NW-101",
    )
    session.add(record)
    await session.commit()
    return record


@pytest.fixture
async def recording_policy(
    session: AsyncSession, org: Organization, agent: Agent
) -> PhoneNumberPolicy:
    policy = PhoneNumberPolicy(
        org_id=org.id,
        e164=agent.phone_number,
        label="Priya — support line",
        owner_agent_id=agent.id,
        recording_enabled=True,
        record_inbound=True,
        record_outbound=True,
        consent_required=True,
    )
    session.add(policy)
    await session.commit()
    return policy


@pytest.fixture
async def admin_headers(client: AsyncClient, admin: User) -> dict[str, str]:
    response = await client.post(
        "/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['tokens']['access_token']}"}


@pytest.fixture
async def device_headers(
    client: AsyncClient, admin_headers: dict[str, str], agent: Agent
) -> dict[str, str]:
    code_response = await client.post(
        f"/v1/auth/agents/{agent.id}/pairing-code", headers=admin_headers
    )
    assert code_response.status_code == 201, code_response.text

    pair_response = await client.post(
        "/v1/auth/devices/pair",
        json={"code": code_response.json()["code"], "platform": "android",
              "device_name": "Pixel 8"},
    )
    assert pair_response.status_code == 200, pair_response.text
    return {"Authorization": f"Bearer {pair_response.json()['device_token']}"}


def call_payload(**overrides) -> dict:
    started = datetime.now(UTC) - timedelta(minutes=10)
    payload = {
        "external_ref": "handset-call-1",
        "direction": "inbound",
        "customer_number": CUSTOMER_NUMBER,
        "customer_name": "Rohit Verma",
        "started_at": started.isoformat(),
        "ended_at": (started + timedelta(minutes=4)).isoformat(),
        "status": "completed",
        "recording_expected": True,
    }
    payload.update(overrides)
    return payload
