"""Lead browsing — the pipeline's per-call lead/other verdict, worked by hand."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_staff
from app.core.errors import NotFound
from app.db.models import Agent, Call, Lead, User
from app.db.session import get_session
from app.schemas.common import Page
from app.schemas.leads import LeadListItem, LeadOut, LeadUpdate
from app.services.timerange import resolve_range

router = APIRouter(prefix="/leads", tags=["leads"])


@router.get("", response_model=Page[LeadListItem])
async def list_leads(
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
    days: int = Query(default=30, ge=1, le=366),
    start: datetime | None = None,
    end: datetime | None = None,
    category: str | None = Query(default=None, description="'lead', 'other', or omit for both"),
    status: str | None = None,
    call_id: str | None = None,
    search: str | None = Query(default=None, description="Name, email, or customer number"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[LeadListItem]:
    filters = [Lead.org_id == user.org_id]
    if call_id:
        # A single call is looked up directly from its detail page — the date
        # range exists to bound the list view, not to hide a specific lookup.
        filters.append(Lead.call_id == call_id)
    else:
        range_start, range_end = resolve_range(days=days, start=start, end=end)
        filters.append(Lead.created_at >= range_start)
        filters.append(Lead.created_at < range_end)
    if category:
        filters.append(Lead.category == category)
    if status:
        filters.append(Lead.status == status)
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(
                Lead.lead_name.ilike(pattern),
                Lead.lead_email.ilike(pattern),
                Lead.customer_number.ilike(pattern),
                Lead.customer_name.ilike(pattern),
            )
        )

    total = (await session.execute(select(func.count(Lead.id)).where(*filters))).scalar_one()

    rows = (
        await session.execute(
            select(Lead, Agent, Call)
            .join(Call, Call.id == Lead.call_id)
            .outerjoin(Agent, Agent.id == Lead.agent_id)
            .where(*filters)
            .order_by(Lead.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()

    items: list[LeadListItem] = []
    for lead, agent, call in rows:
        item = LeadListItem.model_validate(lead)
        item.agent_name = agent.display_name if agent else None
        item.call_started_at = call.started_at if call else None
        items.append(item)

    return Page[LeadListItem](items=items, total=total, limit=limit, offset=offset)


@router.get("/{lead_id}", response_model=LeadOut)
async def get_lead(
    lead_id: str,
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
) -> LeadOut:
    lead = await session.get(Lead, lead_id)
    if lead is None or lead.org_id != user.org_id:
        raise NotFound("Lead")
    return LeadOut.model_validate(lead)


@router.patch("/{lead_id}", response_model=LeadOut)
async def update_lead(
    lead_id: str,
    payload: LeadUpdate,
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
) -> LeadOut:
    lead = await session.get(Lead, lead_id)
    if lead is None or lead.org_id != user.org_id:
        raise NotFound("Lead")

    lead.status = payload.status
    await session.commit()
    return LeadOut.model_validate(lead)
