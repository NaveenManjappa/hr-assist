import asyncio
import json
from typing import Any

import httpx2
import pytest
from langchain_core.messages import HumanMessage

from hr_assist.answering.adapters import OpenAIChatModel
from hr_assist.settings import Settings

COMPLETION = {
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "created": 0,
    "model": "gpt-6-luna",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": json.dumps(
                    {"response_type": "answer", "message": "27 days.", "cited_sources": []}
                ),
            },
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
}


def sent_request_body(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> dict[str, Any]:
    sent: list[httpx2.Request] = []

    async def fake_send(
        _: httpx2.AsyncClient, request: httpx2.Request, **__: Any
    ) -> httpx2.Response:
        sent.append(request)
        return httpx2.Response(200, json=COMPLETION, request=request)

    monkeypatch.setattr(httpx2.AsyncClient, "send", fake_send)

    asyncio.run(OpenAIChatModel(settings).generate([HumanMessage("Annual leave?")]))

    body: dict[str, Any] = json.loads(sent[0].content)
    return body


def test_replies_are_capped_at_800_output_tokens_by_default(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    assert sent_request_body(monkeypatch, settings)["max_completion_tokens"] == 800


def test_the_output_token_cap_comes_from_settings(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    capped = settings.model_copy(update={"max_output_tokens": 300})

    assert sent_request_body(monkeypatch, capped)["max_completion_tokens"] == 300
