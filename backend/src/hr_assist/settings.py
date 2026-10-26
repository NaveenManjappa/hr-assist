from pathlib import Path

from pydantic import NonNegativeInt, PositiveInt, SecretStr
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
    # The chunking strategy: its version, and optionally its size limit and overlap. Unset sizes
    # take the version's own defaults (chunking_v1: 500/60, chunking_v2: 500/100). Only the
    # version names the collection, so change it too if you want to keep the old chunks.
    chunking_version: str = "chunking_v2"
    chunk_max_tokens: PositiveInt | None = None
    chunk_overlap_tokens: NonNegativeInt | None = None
    retrieval_k: PositiveInt = 3
    history_turns: PositiveInt = 5

    qdrant_url: str
    qdrant_api_key: SecretStr

    langsmith_api_key: SecretStr | None = None
    langsmith_tracing: bool = False
    langsmith_project: str | None = None
    langsmith_endpoint: str | None = None

    frontend_origin: str = "http://localhost:4200"

    rate_limit_per_minute: PositiveInt = 10
    rate_limit_per_day: PositiveInt = 100
    rate_limit_global_per_day: PositiveInt = 1000
    trusted_proxy_hops: NonNegativeInt = 1

    @property
    def collection_name(self) -> str:
        """Names the index by environment, chunking version and embedding model (ADR 0001, 0002)."""
        return f"{self.app_env}-{self.chunking_version}-{self.embedding_model}"
