"""v1 API surface."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import agents, analytics, auth, calls, mobile, policies, tasks, ws

api_router = APIRouter(prefix="/v1")
api_router.include_router(auth.router)
api_router.include_router(agents.router)
api_router.include_router(calls.router)
api_router.include_router(policies.router)
api_router.include_router(analytics.router)
api_router.include_router(tasks.router)
api_router.include_router(mobile.router)

# WebSocket routes are mounted without the /v1 prefix.
ws_router = ws.router
