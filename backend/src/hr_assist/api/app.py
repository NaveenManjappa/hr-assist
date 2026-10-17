from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from hr_assist.api import health
from hr_assist.api.errors import register_error_handlers
from hr_assist.api.request_id import REQUEST_ID_HEADER, RequestIdMiddleware, configure_logging
from hr_assist.settings import Settings
from hr_assist.vector_store import QdrantVectorStore, VectorStore


def create_app(
    settings: Settings | None = None, vector_store: VectorStore | None = None
) -> FastAPI:
    configure_logging()
    settings = settings or Settings()
    owned_qdrant = QdrantVectorStore(settings) if vector_store is None else None

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if owned_qdrant is not None:
            await owned_qdrant.close()

    app = FastAPI(title="HR Assist", lifespan=lifespan)
    app.state.vector_store = owned_qdrant or vector_store
    register_error_handlers(app)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
    )
    app.include_router(health.router)
    return app
