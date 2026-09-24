"""Live agent presence and dashboard fan-out.

The dashboard's "agents on call right now" figure has to be live, not polled,
so status changes are broadcast over a WebSocket to every connected dashboard
in the same organisation.

State of record is the `agents.status` column; this module is the notification
layer on top of it. A dashboard that connects late gets a snapshot immediately,
so a dropped broadcast can never leave a client permanently stale.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.enums import AgentStatus
from app.db.models import Agent
from app.schemas.agents import PresenceSnapshot

log = get_logger(__name__)

# Anything other than OFFLINE counts as online.
ONLINE_STATUSES = (
    AgentStatus.AVAILABLE,
    AgentStatus.ON_CALL,
    AgentStatus.WRAP_UP,
    AgentStatus.BREAK,
)


class PresenceHub:
    """In-process WebSocket registry, keyed by organisation.

    Single-process only. Running several API replicas needs a shared bus
    (Redis pub/sub) behind this same interface — see docs/ARCHITECTURE.md.
    """

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, org_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[org_id].add(websocket)
        log.info("dashboard connected", extra={"org_id": org_id, "clients": self.count(org_id)})

    async def disconnect(self, org_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections[org_id].discard(websocket)
            if not self._connections[org_id]:
                del self._connections[org_id]

    def count(self, org_id: str) -> int:
        return len(self._connections.get(org_id, ()))

    async def broadcast(self, org_id: str, event: str, data: dict[str, Any]) -> None:
        async with self._lock:
            targets = list(self._connections.get(org_id, ()))
        if not targets:
            return

        message = json.dumps(
            {"event": event, "data": data, "ts": datetime.now(UTC).isoformat()}, default=str
        )
        dead: list[WebSocket] = []
        for websocket in targets:
            try:
                await websocket.send_text(message)
            except Exception:
                dead.append(websocket)

        if dead:
            async with self._lock:
                for websocket in dead:
                    self._connections[org_id].discard(websocket)


hub = PresenceHub()


async def snapshot(session: AsyncSession, org_id: str) -> PresenceSnapshot:
    """Count agents by status in one grouped query."""
    rows = (
        await session.execute(
            select(Agent.status, func.count(Agent.id))
            .where(Agent.org_id == org_id, Agent.is_active.is_(True))
            .group_by(Agent.status)
        )
    ).all()

    counts = {status: count for status, count in rows}
    online = sum(counts.get(status, 0) for status in ONLINE_STATUSES)

    return PresenceSnapshot(
        total_agents=sum(counts.values()),
        online=online,
        available=counts.get(AgentStatus.AVAILABLE, 0),
        on_call=counts.get(AgentStatus.ON_CALL, 0),
        wrap_up=counts.get(AgentStatus.WRAP_UP, 0),
        on_break=counts.get(AgentStatus.BREAK, 0),
        offline=counts.get(AgentStatus.OFFLINE, 0),
        updated_at=datetime.now(UTC),
    )


async def set_status(
    session: AsyncSession,
    agent: Agent,
    status: AgentStatus | str,
    *,
    call_id: str | None = None,
    broadcast: bool = True,
) -> Agent:
    """Update an agent's status and tell every connected dashboard."""
    now = datetime.now(UTC)
    agent.status = str(status)
    agent.status_changed_at = now
    agent.last_seen_at = now
    agent.current_call_id = call_id if str(status) == AgentStatus.ON_CALL else None
    await session.commit()

    if broadcast:
        await hub.broadcast(
            agent.org_id,
            "agent.status",
            {
                "agent_id": agent.id,
                "display_name": agent.display_name,
                "status": agent.status,
                "current_call_id": agent.current_call_id,
            },
        )
        await hub.broadcast(
            agent.org_id, "presence", (await snapshot(session, agent.org_id)).model_dump()
        )
    return agent


async def notify_call_event(
    session: AsyncSession, org_id: str, event: str, payload: dict[str, Any]
) -> None:
    """Push a call/pipeline event to dashboards (call logged, analysis ready)."""
    await hub.broadcast(org_id, event, payload)
