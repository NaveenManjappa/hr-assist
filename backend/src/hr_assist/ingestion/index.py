from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore

from hr_assist.corpus import Chunk
from hr_assist.settings import Settings


def rebuild_index(chunks: list[Chunk], settings: Settings) -> None:
    """Embeds the chunks and replaces the whole collection with them."""
    QdrantVectorStore.from_documents(
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
