import os

from hr_assist.settings import Settings


def configure_tracing(settings: Settings) -> None:
    """LangChain reads LangSmith settings from the process environment, so export them there."""
    if not settings.langsmith_tracing or settings.langsmith_api_key is None:
        return
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key.get_secret_value()
    if settings.langsmith_project:
        os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    if settings.langsmith_endpoint:
        os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint
