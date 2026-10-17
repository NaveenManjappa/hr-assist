from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    api: Literal["up"]
    qdrant: Literal["up", "down"]


@router.get("/api/health")
async def health(request: Request) -> HealthResponse:
    qdrant_up = await request.app.state.vector_store.is_reachable()
    return HealthResponse(
        status="ok" if qdrant_up else "degraded",
        api="up",
        qdrant="up" if qdrant_up else "down",
    )
