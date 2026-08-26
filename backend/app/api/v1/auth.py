"""Dashboard authentication and mobile device pairing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user, require_admin
from app.core.errors import BadRequest, Conflict, NotFound, Unauthorized
from app.core.security import (
    TokenError,
    create_token,
    decode_token,
    generate_device_token,
    generate_pairing_code,
    hash_opaque_token,
    hash_password,
    normalize_pairing_code,
    verify_password,
)
from app.db.enums import UserRole
from app.db.models import Agent, AuditLog, Device, Organization, PairingCode, User
from app.db.session import get_session
from app.schemas.auth import (
    ChangePasswordRequest,
    CreateUserRequest,
    DeviceSessionOut,
    LoginRequest,
    PairDeviceRequest,
    PairingCodeOut,
    RefreshRequest,
    SessionOut,
    TokenPair,
    UserOut,
)
from app.schemas.common import Ack

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_token(subject=user.id, org_id=user.org_id, role=user.role),
        refresh_token=create_token(
            subject=user.id, org_id=user.org_id, role=user.role, token_type="refresh"
        ),
        expires_in=settings.access_token_ttl_minutes * 60,
    )


@router.post("/login", response_model=SessionOut)
async def login(
    payload: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> SessionOut:
    user = (
        await session.execute(select(User).where(User.email == payload.email.lower()))
    ).scalar_one_or_none()

    # Same response for an unknown email and a wrong password, so the endpoint
    # cannot be used to enumerate accounts.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise Unauthorized("Incorrect email or password")
    if not user.is_active:
        raise Unauthorized("This account has been deactivated")

    user.last_login_at = datetime.now(UTC)
    org = await session.get(Organization, user.org_id)
    session.add(
        AuditLog(
            org_id=user.org_id,
            actor_user_id=user.id,
            action="auth.login",
            entity_type="user",
            entity_id=user.id,
            ip_address=request.client.host if request.client else None,
        )
    )
    await session.commit()

    return SessionOut(
        user=UserOut.model_validate(user),
        organization_name=org.name if org else "",
        tokens=_issue(user),
    )


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    payload: RefreshRequest, session: AsyncSession = Depends(get_session)
) -> TokenPair:
    try:
        claims = decode_token(payload.refresh_token, expect_type="refresh")
    except TokenError as exc:
        raise Unauthorized(str(exc)) from exc

    user = await session.get(User, claims.get("sub", ""))
    if user is None or not user.is_active:
        raise Unauthorized("User is inactive or unknown")
    return _issue(user)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/change-password", response_model=Ack)
async def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Ack:
    if not verify_password(payload.current_password, user.password_hash):
        raise Unauthorized("Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    await session.commit()
    return Ack(message="Password updated")


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(
    payload: CreateUserRequest,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> UserOut:
    email = payload.email.lower()
    existing = (
        await session.execute(
            select(User).where(User.org_id == admin.org_id, User.email == email)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise Conflict("A user with that email already exists")

    if payload.role not in tuple(UserRole):
        raise BadRequest(f"Unknown role: {payload.role}")

    user = User(
        org_id=admin.org_id,
        email=email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    session.add(user)
    await session.commit()
    return UserOut.model_validate(user)


@router.get("/users", response_model=list[UserOut])
async def list_users(
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[UserOut]:
    rows = (
        await session.execute(
            select(User).where(User.org_id == admin.org_id).order_by(User.full_name)
        )
    ).scalars().all()
    return [UserOut.model_validate(row) for row in rows]


# ------------------------------------------------------------ device pairing


@router.post("/agents/{agent_id}/pairing-code", response_model=PairingCodeOut, status_code=201)
async def create_pairing_code(
    agent_id: str,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> PairingCodeOut:
    """Mint a one-time code for an agent to type into the mobile app."""
    agent = await session.get(Agent, agent_id)
    if agent is None or agent.org_id != admin.org_id:
        raise NotFound("Agent")

    display, code_hash = generate_pairing_code()
    expires_at = datetime.now(UTC) + timedelta(minutes=30)
    session.add(
        PairingCode(
            org_id=admin.org_id,
            agent_id=agent.id,
            code_hash=code_hash,
            expires_at=expires_at,
            created_by_user_id=admin.id,
        )
    )
    await session.commit()
    # The plaintext code is returned exactly once, here.
    return PairingCodeOut(code=display, agent_id=agent.id, expires_at=expires_at)


@router.post("/devices/pair", response_model=DeviceSessionOut)
async def pair_device(
    payload: PairDeviceRequest,
    session: AsyncSession = Depends(get_session),
) -> DeviceSessionOut:
    """Exchange a pairing code for a long-lived device token. Unauthenticated —
    the code itself is the credential."""
    code_hash = hash_opaque_token(normalize_pairing_code(payload.code))
    pairing = (
        await session.execute(select(PairingCode).where(PairingCode.code_hash == code_hash))
    ).scalar_one_or_none()

    if pairing is None:
        raise Unauthorized("Invalid pairing code")
    if pairing.used_at is not None:
        raise Unauthorized("This pairing code has already been used")
    if pairing.expires_at < datetime.now(UTC):
        raise Unauthorized("This pairing code has expired")

    agent = await session.get(Agent, pairing.agent_id)
    if agent is None or not agent.is_active:
        raise Unauthorized("Agent is inactive")
    org = await session.get(Organization, pairing.org_id)

    token, token_hash = generate_device_token()
    device = Device(
        org_id=pairing.org_id,
        agent_id=agent.id,
        platform=payload.platform,
        device_name=payload.device_name,
        os_version=payload.os_version,
        app_version=payload.app_version,
        push_token=payload.push_token,
        token_hash=token_hash,
    )
    session.add(device)
    pairing.used_at = datetime.now(UTC)
    session.add(
        AuditLog(
            org_id=pairing.org_id,
            actor_type="device",
            action="device.paired",
            entity_type="agent",
            entity_id=agent.id,
            payload={"platform": payload.platform, "device_name": payload.device_name},
        )
    )
    await session.commit()

    return DeviceSessionOut(
        device_token=token,
        device_id=device.id,
        agent_id=agent.id,
        agent_name=agent.display_name,
        agent_number=agent.phone_number,
        org_id=agent.org_id,
        organization_name=org.name if org else "",
    )


@router.post("/devices/{device_id}/revoke", response_model=Ack)
async def revoke_device(
    device_id: str,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Ack:
    device = await session.get(Device, device_id)
    if device is None or device.org_id != admin.org_id:
        raise NotFound("Device")
    device.revoked_at = datetime.now(UTC)
    await session.commit()
    return Ack(message="Device unpaired")
