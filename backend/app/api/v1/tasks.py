"""Extracted tasks and recommended actions across all calls."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_staff
from app.core.errors import NotFound
from app.db.enums import ActionItemStatus
from app.db.models import ActionItem, Agent, Call, User
from app.db.session import get_session
from app.schemas.calls import ActionItemUpdate, ActionItemWithCall
from app.schemas.common import Page

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=Page[ActionItemWithCall])
async def list_tasks(
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
    status: str | None = Query(default=None),
    kind: str | None = Query(default=None, pattern="^(task|action)$"),
    priority: str | None = None,
    assignee_agent_id: str | None = None,
    overdue_only: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[ActionItemWithCall]:
    filters = [ActionItem.org_id == user.org_id]
    if status:
        filters.append(ActionItem.status == status)
    else:
        # The board is a work queue: closed items are noise unless asked for.
        filters.append(
            ActionItem.status.in_([ActionItemStatus.OPEN, ActionItemStatus.IN_PROGRESS])
        )
    if kind:
        filters.append(ActionItem.kind == kind)
    if priority:
        filters.append(ActionItem.priority == priority)
    if assignee_agent_id:
        filters.append(ActionItem.assignee_agent_id == assignee_agent_id)
    if overdue_only:
        filters.append(ActionItem.due_at.is_not(None))
        filters.append(ActionItem.due_at < datetime.now(UTC))

    total = (
        await session.execute(select(func.count(ActionItem.id)).where(*filters))
    ).scalar_one()

    rows = (
        await session.execute(
            select(ActionItem, Agent, Call)
            .join(Call, Call.id == ActionItem.call_id)
            .outerjoin(Agent, Agent.id == ActionItem.assignee_agent_id)
            .where(*filters)
            # Undated work sinks below dated work rather than vanishing.
            .order_by(
                ActionItem.due_at.is_(None),
                ActionItem.due_at,
                ActionItem.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
    ).all()

    items: list[ActionItemWithCall] = []
    for item, agent, call in rows:
        row = ActionItemWithCall.model_validate(item)
        row.agent_name = agent.display_name if agent else None
        row.customer_number = call.customer_number
        row.call_started_at = call.started_at
        items.append(row)

    return Page[ActionItemWithCall](items=items, total=total, limit=limit, offset=offset)


@router.patch("/{task_id}", response_model=ActionItemWithCall)
async def update_task(
    task_id: str,
    payload: ActionItemUpdate,
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
) -> ActionItemWithCall:
    item = await session.get(ActionItem, task_id)
    if item is None or item.org_id != user.org_id:
        raise NotFound("Task")

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(item, field, value)

    if changes.get("status") == ActionItemStatus.DONE and item.completed_at is None:
        item.completed_at = datetime.now(UTC)
    elif changes.get("status") in (ActionItemStatus.OPEN, ActionItemStatus.IN_PROGRESS):
        item.completed_at = None

    await session.commit()

    call = await session.get(Call, item.call_id)
    agent = (
        await session.get(Agent, item.assignee_agent_id) if item.assignee_agent_id else None
    )
    row = ActionItemWithCall.model_validate(item)
    row.agent_name = agent.display_name if agent else None
    row.customer_number = call.customer_number if call else None
    row.call_started_at = call.started_at if call else None
    return row
