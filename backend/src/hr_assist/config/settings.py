from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, NonNegativeInt, PositiveFloat, PositiveInt, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]
REPO_ROOT_ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT_ENV_FILE, env_ignore_empty=True, extra="ignore"
    )

    app_env: str
    openai_api_key: SecretStr
    chat_model: str = "gpt-6-luna"
    max_output_tokens: PositiveInt = 5000
    # Reasoning tokens count against max_output_tokens, so a higher effort needs a higher cap.
    reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"] = "low"
    # Seconds to wait for one OpenAI chat response, and how many times to retry a timeout,
    # connection error, 408, 409, 429 or 5xx. The worst case is timeout x (retries + 1).
    chat_timeout_seconds: PositiveFloat = 60
    chat_max_retries: NonNegativeInt = 2
    embedding_model: str = "text-embedding-3-small"
    # Seconds to wait for one embeddings request. Ingestion sends up to 1000 chunks per request.
    embedding_timeout_seconds: PositiveFloat = 20
    # The chunking strategy: its version, and optionally its size limit and overlap. Unset sizes
    # take the version's own defaults (chunking_v1: 500/60, chunking_v2: 500/100). Only the
    # version names the collection, so change it too if you want to keep the old chunks.
    chunking_version: str = "chunking_v2"
    chunk_max_tokens: PositiveInt | None = None
    chunk_overlap_tokens: NonNegativeInt | None = None
    retrieval_k: PositiveInt = 3
    # The lowest relevance a chunk needs to be retrieved, on LangChain's (cosine + 1) / 2 scale,
    # so 0.65 is a cosine of 0.3. When no chunk passes, the Answerer abstains without the model.
    # 0 turns the filter off.
    retrieval_score_threshold: Annotated[float, Field(ge=0, le=1)] = 0.65
    history_turns: PositiveInt = 5

    qdrant_url: str
    qdrant_api_key: SecretStr

    langsmith_api_key: SecretStr | None = None
    langsmith_tracing: bool = False
    langsmith_project: str | None = None
    langsmith_endpoint: str | None = None

    frontend_origin: str = "http://localhost:4200"

    rate_limit_per_minute: PositiveInt = 20
    rate_limit_per_day: PositiveInt = 100
    rate_limit_global_per_day: PositiveInt = 1000
    trusted_proxy_hops: NonNegativeInt = 1

    @property
    def collection_name(self) -> str:
        """Names the index by environment, chunking version and embedding model (ADR 0001, 0002)."""
        return f"{self.app_env}-{self.chunking_version}-{self.embedding_model}"
