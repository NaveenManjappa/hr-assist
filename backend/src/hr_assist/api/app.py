from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from hr_assist.answering import Answerer, ChatModel, Retriever
from hr_assist.answering.adapters import OpenAIChatModel, QdrantRetriever
from hr_assist.api import chat, health
from hr_assist.api.errors import InternalErrorMiddleware, register_error_handlers
from hr_assist.api.no_store import NoStoreMiddleware
from hr_assist.api.request_id import REQUEST_ID_HEADER, RequestIdMiddleware, configure_logging
from hr_assist.settings import Settings
from hr_assist.tracing import configure_tracing
from hr_assist.vector_store import QdrantVectorStore, VectorStore


def create_app(
    settings: Settings | None = None,
    vector_store: VectorStore | None = None,
    retriever: Retriever | None = None,
    chat_model: ChatModel | None = None,
) -> FastAPI:
    configure_logging()
    settings = settings or Settings()
    configure_tracing(settings)
    cleanups: list[Callable[[], Awaitable[None]]] = []

    if vector_store is None:
        owned_vector_store = QdrantVectorStore(settings)
        cleanups.append(owned_vector_store.close)
        vector_store = owned_vector_store
    if retriever is None:
        owned_retriever = QdrantRetriever(settings)
        cleanups.append(owned_retriever.close)
        retriever = owned_retriever
    chat_model = chat_model or OpenAIChatModel(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        for cleanup in cleanups:
            await cleanup()

    app = FastAPI(title="HR Assist", lifespan=lifespan)
    app.state.vector_store = vector_store
    app.state.answerer = Answerer(retriever, chat_model)
    register_error_handlers(app)
    app.add_middleware(InternalErrorMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
    )
    # Outermost, so CORS preflight answers are marked too.
    app.add_middleware(NoStoreMiddleware)
    app.include_router(health.router)
    app.include_router(chat.router)
    return app
