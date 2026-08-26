"""Agent management and presence."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_admin, require_staff
from app.core.errors import Conflict, NotFound
from app.core.security import hash_password
from app.db.enums import ActionItemStatus, UserRole
from app.db.models import ActionItem, Agent, Analysis, Call, User
from app.db.session import get_session
from app.schemas.agents import (
    AgentCreate,
    AgentOut,
    AgentUpdate,
    AgentWithStats,
    PresenceSnapshot,
)
from app.schemas.common import Ack
from app.services import presence
from app.services.timerange import resolve_range

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=list[AgentWithStats])
async def list_agents(
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
    days: int = Query(default=7, ge=1, le=365),
    team: str | None = None,
    status: str | None = None,
    include_inactive: bool = False,
) -> list[AgentWithStats]:
    start, end = resolve_range(days=days)

    stmt = select(Agent).where(Agent.org_id == user.org_id)
    if not include_inactive:
        stmt = stmt.where(Agent.is_active.is_(True))
    if team:
        stmt = stmt.where(Agent.team == team)
    if status:
        stmt = stmt.where(Agent.status == status)

    agents = (await session.execute(stmt.order_by(Agent.display_name))).scalars().all()
    if not agents:
        return []

    agent_ids = [agent.id for agent in agents]
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    # Three grouped queries rather than per-agent lookups: the cost stays flat
    # as the roster grows.
    range_rows = dict(
        (
            await session.execute(
                select(Call.agent_id, func.count(Call.id))
                .where(
                    Call.agent_id.in_(agent_ids),
                    Call.started_at >= start,
                    Call.started_at < end,
                )
                .group_by(Call.agent_id)
            )
        ).all()
    )
    today_rows = dict(
        (
            await session.execute(
                select(Call.agent_id, func.count(Call.id))
                .where(Call.agent_id.in_(agent_ids), Call.started_at >= today_start)
                .group_by(Call.agent_id)
            )
        ).all()
    )
    insight_rows = {
        row[0]: row
        for row in (
            await session.execute(
                select(
                    Call.agent_id,
                    func.avg(Analysis.sentiment_score),
                    func.avg(Call.duration_seconds),
                    func.sum(case((Analysis.customer_satisfied.is_(True), 1), else_=0)),
                    func.sum(case((Analysis.customer_satisfied.is_(False), 1), else_=0)),
                )
                .join(Analysis, Analysis.call_id == Call.id)
                .where(
                    Call.agent_id.in_(agent_ids),
                    Call.started_at >= start,
                    Call.started_at < end,
                )
                .group_by(Call.agent_id)
            )
        ).all()
    }
    task_rows = dict(
        (
            await session.execute(
                select(ActionItem.assignee_agent_id, func.count(ActionItem.id))
                .where(
                    ActionItem.assignee_agent_id.in_(agent_ids),
                    ActionItem.status.in_([ActionItemStatus.OPEN, ActionItemStatus.IN_PROGRESS]),
                )
                .group_by(ActionItem.assignee_agent_id)
            )
        ).all()
    )

    out: list[AgentWithStats] = []
    for agent in agents:
        row = insight_rows.get(agent.id)
        satisfied = int(row[3] or 0) if row else 0
        unsatisfied = int(row[4] or 0) if row else 0
        decided = satisfied + unsatisfied
        item = AgentWithStats.model_validate(agent)
        item.calls_in_range = int(range_rows.get(agent.id, 0))
        item.calls_today = int(today_rows.get(agent.id, 0))
        item.avg_sentiment = round(float(row[1]), 3) if row and row[1] is not None else None
        item.avg_duration_seconds = round(float(row[2]), 1) if row and row[2] else None
        item.satisfied_rate = round(satisfied / decided, 3) if decided else None
        item.open_tasks = int(task_rows.get(agent.id, 0))
        out.append(item)
    return out


@router.get("/presence", response_model=PresenceSnapshot)
async def get_presence(
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
) -> PresenceSnapshot:
    return await presence.snapshot(session, user.org_id)


@router.post("", response_model=AgentOut, status_code=201)
async def create_agent(
    payload: AgentCreate,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AgentOut:
    clash = (
        await session.execute(
            select(Agent).where(
                Agent.org_id == admin.org_id, Agent.phone_number == payload.phone_number
            )
        )
    ).scalar_one_or_none()
    if clash is not None:
        raise Conflict(f"An agent is already registered on {payload.phone_number}")

    user_id: str | None = None
    if payload.email and payload.password:
        login = User(
            org_id=admin.org_id,
            email=payload.email.lower(),
            full_name=payload.display_name,
            password_hash=hash_password(payload.password),
            role=UserRole.AGENT,
        )
        session.add(login)
        await session.flush()
        user_id = login.id

    agent = Agent(
        org_id=admin.org_id,
        user_id=user_id,
        display_name=payload.display_name,
        phone_number=payload.phone_number,
        employee_code=payload.employee_code,
        team=payload.team,
    )
    session.add(agent)
    await session.commit()
    return AgentOut.model_validate(agent)


@router.get("/{agent_id}", response_model=AgentOut)
async def get_agent(
    agent_id: str,
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
) -> AgentOut:
    agent = await session.get(Agent, agent_id)
    if agent is None or agent.org_id != user.org_id:
        raise NotFound("Agent")
    return AgentOut.model_validate(agent)


@router.patch("/{agent_id}", response_model=AgentOut)
async def update_agent(
    agent_id: str,
    payload: AgentUpdate,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AgentOut:
    agent = await session.get(Agent, agent_id)
    if agent is None or agent.org_id != admin.org_id:
        raise NotFound("Agent")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(agent, field, value)
    await session.commit()
    return AgentOut.model_validate(agent)


@router.delete("/{agent_id}", response_model=Ack)
async def deactivate_agent(
    agent_id: str,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Ack:
    """Deactivate rather than delete — call history must survive."""
    agent = await session.get(Agent, agent_id)
    if agent is None or agent.org_id != admin.org_id:
        raise NotFound("Agent")
    agent.is_active = False
    await session.commit()
    return Ack(message=f"{agent.display_name} deactivated")
