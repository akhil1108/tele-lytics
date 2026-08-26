"""FastAPI dependencies: authentication, tenancy, and role gates.

Two kinds of principal reach the API:

* **users** — dashboard operators carrying a short-lived JWT.
* **devices** — paired handsets carrying a long-lived opaque token that maps
  to exactly one agent.

Both resolve to an `org_id`, which every query then filters on.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import Forbidden, Unauthorized
from app.core.security import TokenError, decode_token, hash_opaque_token
from app.db.enums import UserRole
from app.db.models import Agent, Device, User
from app.db.session import get_session

bearer_scheme = HTTPBearer(auto_error=False)

# Roles that may read across the whole organisation.
STAFF_ROLES: tuple[str, ...] = (UserRole.OWNER, UserRole.ADMIN, UserRole.SUPERVISOR)
# Roles that may change configuration (numbers, agents, users).
ADMIN_ROLES: tuple[str, ...] = (UserRole.OWNER, UserRole.ADMIN)


@dataclass(slots=True)
class DevicePrincipal:
    device: Device
    agent: Agent

    @property
    def org_id(self) -> str:
        return self.device.org_id


async def _credentials(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    if creds is None or not creds.credentials:
        raise Unauthorized()
    return creds.credentials


async def get_current_user(
    token: str = Depends(_credentials),
    session: AsyncSession = Depends(get_session),
) -> User:
    try:
        payload = decode_token(token, expect_type="access")
    except TokenError as exc:
        raise Unauthorized(str(exc)) from exc

    user = await session.get(User, payload.get("sub", ""))
    if user is None or not user.is_active:
        raise Unauthorized("User is inactive or unknown")
    # The org claim is checked against the row so a token minted before a user
    # was moved between organisations cannot read the old tenant's data.
    if user.org_id != payload.get("org"):
        raise Unauthorized("Token does not match user tenancy")
    return user


def require_roles(*roles: str) -> Callable[[User], User]:
    """Dependency factory gating an endpoint on the caller's role."""
    allowed: Sequence[str] = roles or STAFF_ROLES

    async def _dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise Forbidden(f"Requires one of: {', '.join(allowed)}")
        return user

    return _dependency


require_staff = require_roles(*STAFF_ROLES)
require_admin = require_roles(*ADMIN_ROLES)


async def get_current_device(
    request: Request,
    token: str = Depends(_credentials),
    session: AsyncSession = Depends(get_session),
) -> DevicePrincipal:
    """Resolve a mobile device token to its device + agent, and touch last-seen."""
    device = (
        await session.execute(
            select(Device).where(Device.token_hash == hash_opaque_token(token))
        )
    ).scalar_one_or_none()

    if device is None:
        raise Unauthorized("Unknown device token")
    if device.revoked_at is not None:
        raise Unauthorized("Device has been unpaired")

    agent = await session.get(Agent, device.agent_id)
    if agent is None or not agent.is_active:
        raise Unauthorized("Agent is inactive")

    now = datetime.now(tz=device.paired_at.tzinfo)
    device.last_seen_at = now
    agent.last_seen_at = now
    if version := request.headers.get("x-app-version"):
        device.app_version = version[:40]
    await session.commit()

    return DevicePrincipal(device=device, agent=agent)
