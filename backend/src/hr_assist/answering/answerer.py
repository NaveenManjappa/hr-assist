import logging
import time
from datetime import date
from typing import Protocol

from langchain_core.messages import BaseMessage
from langsmith import traceable

from hr_assist.answering.models import ChatRequest, ChatResponse, Citation, GeneratedReply
from hr_assist.answering.prompt import PROMPT_VERSION, build_prompt
from hr_assist.corpus import Chunk

RETRIEVAL_K = 8
HISTORY_TURNS = 6
SNIPPET_CHARS = 600

logger = logging.getLogger("hr_assist.chat")


class Retriever(Protocol):
    async def retrieve(self, query: str, k: int) -> list[Chunk]: ...


class ChatModel(Protocol):
    async def generate(self, messages: list[BaseMessage]) -> GeneratedReply: ...


class Answerer:
    """2-step RAG: always retrieve, then make one structured-output call (ADR 0002)."""

    def __init__(self, retriever: Retriever, chat_model: ChatModel) -> None:
        self._retriever = retriever
        self._chat_model = chat_model

    @traceable(name="chat")
    async def answer(self, request: ChatRequest) -> ChatResponse:
        started = time.perf_counter()
        chunks = await self._retriever.retrieve(request.messages[-1].content, RETRIEVAL_K)
        prompt = build_prompt(
            request.as_of_date or date.today(), chunks, request.messages[-HISTORY_TURNS:]
        )
        generated = await self._chat_model.generate(prompt)
        reply = generated.reply

        logger.info(
            "chat response_type=%s prompt=%s latency_ms=%.0f chunks=%s token_usage=%s",
            reply.response_type,
            PROMPT_VERSION,
            (time.perf_counter() - started) * 1000,
            [c.id for c in chunks],
            generated.token_usage,
        )
        return ChatResponse(
            response_type=reply.response_type,
            message=reply.message,
            citations=_citations(reply.cited_sources, chunks),
        )


def _citations(cited_sources: list[int], chunks: list[Chunk]) -> list[Citation]:
    """Builds Citations from the metadata of the chunks the model cited by number."""
    numbers = dict.fromkeys(n for n in cited_sources if 1 <= n <= len(chunks))
    return [_citation(chunks[n - 1]) for n in numbers]


def _citation(chunk: Chunk) -> Citation:
    m = chunk.metadata
    return Citation(
        document_id=m.document_id,
        document_version=m.document_version,
        title=m.title,
        section=f"{m.section_number} {m.section_title}",
        page_start=m.page_start,
        page_end=m.page_end,
        snippet=chunk.body[:SNIPPET_CHARS],
        status=m.status,
    )
