from pathlib import Path

from pydantic import PositiveInt, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT_ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT_ENV_FILE, env_ignore_empty=True, extra="ignore"
    )

    app_env: str
    openai_api_key: SecretStr
    chat_model: str = "gpt-6-luna"
    max_output_tokens: PositiveInt = 800
    embedding_model: str = "text-embedding-3-small"
    chunking_version: str = "structure_v1"

    qdrant_url: str
    qdrant_api_key: SecretStr

    langsmith_api_key: SecretStr | None = None
    langsmith_tracing: bool = False
    langsmith_project: str | None = None
    langsmith_endpoint: str | None = None

    frontend_origin: str = "http://localhost:4200"

    @property
    def collection_name(self) -> str:
        """Names the index by environment, chunking version and embedding model (ADR 0001, 0002)."""
        return f"{self.app_env}-{self.chunking_version}-{self.embedding_model}"
