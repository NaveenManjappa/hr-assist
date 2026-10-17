import pytest

from hr_assist.settings import Settings


class FakeVectorStore:
    def __init__(self, reachable: bool = True) -> None:
        self.reachable = reachable

    async def is_reachable(self) -> bool:
        return self.reachable


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        openai_api_key="sk-test",
        qdrant_url="https://qdrant.invalid",
        qdrant_api_key="qdrant-test",
    )
