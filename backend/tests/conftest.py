from datetime import date, datetime, timedelta

import pytest
from langchain_core.messages import BaseMessage

from hr_assist.answering import AssistantReply, GeneratedReply
from hr_assist.corpus import Chunk, ChunkMetadata
from hr_assist.settings import Settings


class FakeVectorStore:
    def __init__(self, reachable: bool = True) -> None:
        self.reachable = reachable

    async def is_reachable(self) -> bool:
        return self.reachable


class FakeRetriever:
    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        self.queries: list[tuple[str, int]] = []

    async def retrieve(self, query: str, k: int) -> list[Chunk]:
        self.queries.append((query, k))
        return self.chunks[:k]


class FakeChatModel:
    def __init__(self, reply: AssistantReply) -> None:
        self.reply = reply
        self.prompts: list[list[BaseMessage]] = []

    async def generate(self, messages: list[BaseMessage]) -> GeneratedReply:
        self.prompts.append(messages)
        return GeneratedReply(
            reply=self.reply,
            token_usage={"input_tokens": 1200, "output_tokens": 80, "total_tokens": 1280},
        )


def make_chunk(
    section_number: str,
    section_title: str,
    body: str,
    page: int,
    document_id: str = "NDS-HR-LAS-002",
) -> Chunk:
    return Chunk(
        id=f"{document_id}-{section_number}",
        text=f"Header line\n{section_number} {section_title}\n\n{body}",
        metadata=ChunkMetadata(
            document_id=document_id,
            document_version="v1.2",
            title="Leave and Absence Standard",
            document_kind="policy_document",
            status="current",
            effective_from=date(2026, 10, 1),
            effective_to=None,
            section_number=section_number,
            section_title=section_title,
            section_path=["3 Annual leave", f"{section_number} {section_title}"],
            page_start=page,
            page_end=page,
            chunking_version="structure_v1",
        ),
    )


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        openai_api_key="sk-test",
        qdrant_url="https://qdrant.invalid",
        qdrant_api_key="qdrant-test",
    )


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)
