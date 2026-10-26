import logging
import re
import time
from datetime import date
from typing import Protocol

from langchain_core.messages import BaseMessage
from langsmith import traceable

from hr_assist.answering.models import ChatRequest, ChatResponse, Citation, GeneratedReply
from hr_assist.answering.prompt import PROMPT_VERSION, build_prompt
from hr_assist.corpus import Chunk

# A marker such as [2] or [1, 3], with the space before it so a dropped marker leaves none.
_MARKER = re.compile(r"(\s?)\[(\d+(?:\s*,\s*\d+)*)\]")

logger = logging.getLogger("hr_assist.chat")


class Retriever(Protocol):
    async def retrieve(self, query: str, k: int) -> list[Chunk]: ...


class ChatModel(Protocol):
    async def generate(self, messages: list[BaseMessage]) -> GeneratedReply: ...


class Answerer:
    """2-step RAG: always retrieve, then make one structured-output call (ADR 0002)."""

    def __init__(
        self, retriever: Retriever, chat_model: ChatModel, retrieval_k: int, history_turns: int
    ) -> None:
        self._retriever = retriever
        self._chat_model = chat_model
        self._retrieval_k = retrieval_k
        self._history_turns = history_turns

    @traceable(name="chat")
    async def answer(self, request: ChatRequest) -> ChatResponse:
        started = time.perf_counter()
        chunks = await self._retriever.retrieve(request.messages[-1].content, self._retrieval_k)
        prompt = build_prompt(
            request.as_of_date or date.today(), chunks, request.messages[-self._history_turns :]
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
        message, cited = _renumber(reply.message, reply.cited_sources, len(chunks))
        return ChatResponse(
            response_type=reply.response_type,
            message=message,
            citations=[_citation(chunks[n - 1]) for n in cited],
        )


def _renumber(message: str, cited_sources: list[int], source_count: int) -> tuple[str, list[int]]:
    """Orders the cited sources by their first inline marker, then renumbers the markers to match.

    Sources cited without a marker follow the marked ones, and markers that point at no
    retrieved source are dropped.
    """
    valid = range(1, source_count + 1)
    marked = [int(n) for _, group in _MARKER.findall(message) for n in group.split(",")]
    cited = list(dict.fromkeys(n for n in [*marked, *cited_sources] if n in valid))
    position = {source: index for index, source in enumerate(cited, start=1)}

    def replace(match: re.Match[str]) -> str:
        numbers = [int(n) for n in match.group(2).split(",") if int(n) in valid]
        markers = "".join(f"[{position[n]}]" for n in dict.fromkeys(numbers))
        return match.group(1) + markers if markers else ""

    return _MARKER.sub(replace, message), cited


def _citation(chunk: Chunk) -> Citation:
    m = chunk.metadata
    return Citation(
        document_id=m.document_id,
        document_version=m.document_version,
        title=m.title,
        section=f"{m.section_number} {m.section_title}" if m.section_number else m.section_title,
        page_start=m.page_start,
        page_end=m.page_end,
        slide=m.slide,
        snippet=chunk.body,
        status=m.status,
    )
