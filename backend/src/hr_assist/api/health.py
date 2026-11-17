from typing import Literal, Protocol

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class VectorStore(Protocol):
    async def is_reachable(self) -> bool: ...


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    api: Literal["up"]
    qdrant: Literal["up", "down"]


@router.get("/api/health")
async def health(request: Request) -> HealthResponse:
    vector_store: VectorStore = request.app.state.vector_store
    qdrant_up = await vector_store.is_reachable()
    return HealthResponse(
        status="ok" if qdrant_up else "degraded",
        api="up",
        qdrant="up" if qdrant_up else "down",
    )
