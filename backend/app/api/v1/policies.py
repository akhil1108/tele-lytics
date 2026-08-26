"""Per-number recording policies — the 'is recording set for this number' view."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_admin, require_staff
from app.core.errors import BadRequest, Conflict, NotFound
from app.db.enums import CallDirection
from app.db.models import AuditLog, PhoneNumberPolicy, User
from app.db.session import get_session
from app.schemas.common import Ack, Page
from app.schemas.policies import (
    PolicyCreate,
    PolicyDecision,
    PolicyOut,
    PolicyUpdate,
)
from app.services import policies as policy_service
from app.services.phone import InvalidPhoneNumber, normalize

router = APIRouter(prefix="/numbers", tags=["recording-policies"])


@router.get("", response_model=Page[PolicyOut])
async def list_policies(
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
    search: str | None = None,
    recording_enabled: bool | None = None,
    kind: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[PolicyOut]:
    filters = [PhoneNumberPolicy.org_id == user.org_id]
    if recording_enabled is not None:
        filters.append(PhoneNumberPolicy.recording_enabled.is_(recording_enabled))
    if kind:
        filters.append(PhoneNumberPolicy.kind == kind)
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(PhoneNumberPolicy.e164.ilike(pattern), PhoneNumberPolicy.label.ilike(pattern))
        )

    total = (
        await session.execute(
            select(func.count(PhoneNumberPolicy.id)).where(*filters)
        )
    ).scalar_one()
    rows = (
        await session.execute(
            select(PhoneNumberPolicy)
            .where(*filters)
            .order_by(PhoneNumberPolicy.e164)
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()

    return Page[PolicyOut](
        items=[PolicyOut.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=PolicyOut, status_code=201)
async def create_policy(
    payload: PolicyCreate,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> PolicyOut:
    existing = await policy_service.get_policy(session, admin.org_id, payload.e164)
    if existing is not None:
        raise Conflict(f"A policy already exists for {payload.e164}")

    policy = PhoneNumberPolicy(
        org_id=admin.org_id,
        created_by_user_id=admin.id,
        **payload.model_dump(),
    )
    session.add(policy)
    session.add(
        AuditLog(
            org_id=admin.org_id,
            actor_user_id=admin.id,
            action="policy.created",
            entity_type="phone_number_policy",
            entity_id=policy.id,
            payload={"e164": payload.e164, "recording_enabled": payload.recording_enabled},
        )
    )
    await session.commit()
    return PolicyOut.model_validate(policy)


@router.get("/lookup", response_model=PolicyDecision)
async def lookup(
    number: str = Query(..., description="Agent number to evaluate"),
    customer_number: str | None = None,
    direction: CallDirection = CallDirection.OUTBOUND,
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
) -> PolicyDecision:
    """Evaluate the policy exactly as the handset would.

    Having the dashboard resolve a decision through the same code path is how
    an operator confirms a number is really set up before trusting it.
    """
    try:
        agent_number = normalize(number)
    except InvalidPhoneNumber as exc:
        raise BadRequest(str(exc)) from exc

    return await policy_service.decide(
        session,
        org_id=user.org_id,
        agent_number=agent_number,
        customer_number=customer_number,
        direction=direction,
    )


@router.get("/{policy_id}", response_model=PolicyOut)
async def get_policy(
    policy_id: str,
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
) -> PolicyOut:
    policy = await session.get(PhoneNumberPolicy, policy_id)
    if policy is None or policy.org_id != user.org_id:
        raise NotFound("Recording policy")
    return PolicyOut.model_validate(policy)


@router.patch("/{policy_id}", response_model=PolicyOut)
async def update_policy(
    policy_id: str,
    payload: PolicyUpdate,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> PolicyOut:
    policy = await session.get(PhoneNumberPolicy, policy_id)
    if policy is None or policy.org_id != admin.org_id:
        raise NotFound("Recording policy")

    changes = payload.model_dump(exclude_unset=True)
    before = {key: getattr(policy, key) for key in changes}
    for field, value in changes.items():
        setattr(policy, field, value)

    # Turning recording on or off is the change an auditor asks about, so it is
    # logged with both sides of the switch.
    session.add(
        AuditLog(
            org_id=admin.org_id,
            actor_user_id=admin.id,
            action="policy.updated",
            entity_type="phone_number_policy",
            entity_id=policy.id,
            payload={"e164": policy.e164, "before": before, "after": changes},
        )
    )
    await session.commit()
    return PolicyOut.model_validate(policy)


@router.delete("/{policy_id}", response_model=Ack)
async def delete_policy(
    policy_id: str,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Ack:
    policy = await session.get(PhoneNumberPolicy, policy_id)
    if policy is None or policy.org_id != admin.org_id:
        raise NotFound("Recording policy")

    number = policy.e164
    await session.delete(policy)
    session.add(
        AuditLog(
            org_id=admin.org_id,
            actor_user_id=admin.id,
            action="policy.deleted",
            entity_type="phone_number_policy",
            entity_id=policy_id,
            payload={"e164": number},
        )
    )
    await session.commit()
    # Deleting a policy means recording stops for that number — say so plainly.
    return Ack(message=f"Policy removed; {number} will no longer be recorded")
