from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT_ENV_FILE, env_ignore_empty=True, extra="ignore"
    )

    app_env: str
    openai_api_key: SecretStr
    chat_model: str = "gpt-6-luna"
    embedding_model: str = "text-embedding-3-small"

    qdrant_url: str
    qdrant_api_key: SecretStr

    langsmith_api_key: SecretStr | None = None
    langsmith_tracing: bool = False
    langsmith_project: str | None = None

    frontend_origin: str = "http://localhost:4200"
