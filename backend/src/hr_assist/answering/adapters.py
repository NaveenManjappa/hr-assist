from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.messages import BaseMessage
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from hr_assist.answering.models import AssistantReply, GeneratedReply
from hr_assist.corpus import Chunk, ChunkMetadata
from hr_assist.errors import UpstreamError
from hr_assist.settings import Settings


class QdrantRetriever:
    def __init__(self, settings: Settings) -> None:
        self._client = QdrantClient(
            url=settings.qdrant_url, api_key=settings.qdrant_api_key.get_secret_value(), timeout=10
        )
        self._store = QdrantVectorStore(
            client=self._client,
            collection_name=settings.collection_name,
            embedding=OpenAIEmbeddings(
                model=settings.embedding_model, openai_api_key=settings.openai_api_key
            ),
            validate_collection_config=False,
        )
        self._score_threshold = settings.retrieval_score_threshold

    async def retrieve(self, query: str, k: int) -> list[Chunk]:
        try:
            retriever = self._store.as_retriever(
                search_type="similarity_score_threshold",
                search_kwargs={"k": k, "score_threshold": float(self._score_threshold)},
            )
            documents = await retriever.ainvoke(query, config={"run_name": "retrieve"})
        except Exception as exc:
            raise UpstreamError("Searching the policy index failed.") from exc
        return [
            Chunk(
                id=str(doc.metadata["_id"]),
                text=doc.page_content,
                metadata=ChunkMetadata.model_validate(doc.metadata),
            )
            for doc in documents
        ]

    async def close(self) -> None:
        self._client.close()


class OpenAIChatModel:
    def __init__(self, settings: Settings) -> None:
        self._model = (
            init_chat_model(
                settings.chat_model,
                model_provider="openai",
                api_key=settings.openai_api_key.get_secret_value(),
                max_tokens=settings.max_output_tokens,
                reasoning_effort=settings.reasoning_effort,
            )
            .with_structured_output(AssistantReply, include_raw=True)
            .with_config(run_name="generate")
        )

    async def generate(self, messages: list[BaseMessage]) -> GeneratedReply:
        try:
            result: Any = await self._model.ainvoke(messages)
        except Exception as exc:
            raise UpstreamError("The language model could not be reached.") from exc
        parsed = result["parsed"]
        if not isinstance(parsed, AssistantReply):
            raise UpstreamError("The language model returned a reply that could not be read.")
        usage = result["raw"].usage_metadata or {}
        return GeneratedReply(
            reply=parsed,
            token_usage={
                k: usage[k] for k in ("input_tokens", "output_tokens", "total_tokens") if k in usage
            },
        )
