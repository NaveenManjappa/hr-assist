from typing import Protocol

from qdrant_client import AsyncQdrantClient

from hr_assist.settings import Settings


class VectorStore(Protocol):
    async def is_reachable(self) -> bool: ...


class QdrantVectorStore:
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
