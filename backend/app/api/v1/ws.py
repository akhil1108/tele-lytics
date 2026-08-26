"""Realtime dashboard channel.

Browsers cannot set an Authorization header on a WebSocket handshake, so the
access token arrives as a query parameter. It is the same short-lived JWT the
REST API uses and it is validated identically — the transport differs, the
trust model does not.
"""

from __future__ import annotations

import asyncio
import contextlib

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.core.deps import STAFF_ROLES
from app.core.logging import get_logger
from app.core.security import TokenError, decode_token
from app.db.models import User
from app.db.session import SessionLocal
from app.services import presence

log = get_logger(__name__)
router = APIRouter(tags=["realtime"])

# Below the 60s most proxies use to reap an idle upgrade.
HEARTBEAT_SECONDS = 25


@router.websocket("/ws/dashboard")
async def dashboard_socket(
    websocket: WebSocket,
    token: str = Query(..., description="Access token"),
) -> None:
    try:
        claims = decode_token(token, expect_type="access")
    except TokenError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
        return

    async with SessionLocal() as session:
        user = await session.get(User, claims.get("sub", ""))
        if user is None or not user.is_active or user.role not in STAFF_ROLES:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Not permitted")
            return
        org_id = user.org_id
        snapshot = await presence.snapshot(session, org_id)

    await presence.hub.connect(org_id, websocket)
    # Send state immediately: a client that connects between broadcasts must
    # not sit blank until something happens.
    await websocket.send_json({"event": "presence", "data": snapshot.model_dump(mode="json")})

    heartbeat = asyncio.create_task(_heartbeat(websocket))
    try:
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_text("pong")
            elif message == "refresh":
                async with SessionLocal() as session:
                    fresh = await presence.snapshot(session, org_id)
                await websocket.send_json(
                    {"event": "presence", "data": fresh.model_dump(mode="json")}
                )
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("dashboard socket failed", extra={"org_id": org_id})
    finally:
        heartbeat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat
        await presence.hub.disconnect(org_id, websocket)


async def _heartbeat(websocket: WebSocket) -> None:
    """Keep the connection warm through intermediary idle timeouts."""
    while True:
        await asyncio.sleep(HEARTBEAT_SECONDS)
        try:
            await websocket.send_json({"event": "heartbeat", "data": {}})
        except Exception:
            return
