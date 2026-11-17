from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore as LangChainQdrantStore
from qdrant_client import AsyncQdrantClient, QdrantClient, models

from hr_assist.config.settings import Settings
from hr_assist.corpus import Chunk, ChunkMetadata
from hr_assist.errors import UpstreamError


class QdrantVectorStore:
    """Reports whether Qdrant is reachable, for the health check (async client)."""

    def __init__(self, settings: Settings) -> None:
        self._client = AsyncQdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key.get_secret_value(),
            timeout=5,
        )

    async def is_reachable(self) -> bool:
        try:
            await self._client.get_collections()
        except Exception:
            return False
        return True

    async def close(self) -> None:
        await self._client.close()


class QdrantRetriever:
    def __init__(self, settings: Settings) -> None:
        self._client = QdrantClient(
            url=settings.qdrant_url, api_key=settings.qdrant_api_key.get_secret_value(), timeout=10
        )
        self._store = LangChainQdrantStore(
            client=self._client,
            collection_name=settings.collection_name,
            embedding=OpenAIEmbeddings(
                model=settings.embedding_model, openai_api_key=settings.openai_api_key
            ),
            validate_collection_config=False,
        )
        self._score_threshold = settings.retrieval_score_threshold
        # Superseded documents stay indexed but aren't searched (ADR 0007).
        self._current_only = models.Filter(
            must=[
                models.FieldCondition(
                    key="metadata.status", match=models.MatchValue(value="current")
                )
            ]
        )

    async def retrieve(self, query: str, k: int) -> list[Chunk]:
        try:
            retriever = self._store.as_retriever(
                search_type="similarity_score_threshold",
                search_kwargs={
                    "k": k,
                    "score_threshold": float(self._score_threshold),
                    "filter": self._current_only,
                },
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


def rebuild_index(chunks: list[Chunk], settings: Settings) -> None:
    """Embeds the chunks and replaces the whole collection with them."""
    store = LangChainQdrantStore.from_documents(
        [
            Document(page_content=c.text, metadata=c.metadata.model_dump(mode="json"))
            for c in chunks
        ],
        OpenAIEmbeddings(model=settings.embedding_model, openai_api_key=settings.openai_api_key),
        ids=[c.id for c in chunks],
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key.get_secret_value(),
        collection_name=settings.collection_name,
        force_recreate=True,
    )
    # Retrieval filters on Document Status (ADR 0007), and Qdrant Cloud needs an index to filter.
    store.client.create_payload_index(
        settings.collection_name,
        field_name="metadata.status",
        field_schema=models.PayloadSchemaType.KEYWORD,
        wait=True,
    )
