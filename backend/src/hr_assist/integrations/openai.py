from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.messages import BaseMessage

from hr_assist.answering.models import AssistantReply, GeneratedReply
from hr_assist.config.settings import Settings
from hr_assist.errors import UpstreamError


class OpenAIChatModel:
    def __init__(self, settings: Settings) -> None:
        self._model = (
            init_chat_model(
                settings.chat_model,
                model_provider="openai",
                api_key=settings.openai_api_key.get_secret_value(),
                max_tokens=settings.max_output_tokens,
                reasoning_effort=settings.reasoning_effort,
                timeout=settings.chat_timeout_seconds,
                max_retries=settings.chat_max_retries,
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
