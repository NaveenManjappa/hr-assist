import asyncio
import json
from typing import Any

import httpx2
import pytest
from langchain_core.messages import HumanMessage

from hr_assist.config.settings import Settings
from hr_assist.errors import UpstreamError
from hr_assist.integrations.openai import OpenAIChatModel

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


def send_requests(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    status: int = 200,
    sent: list[httpx2.Request] | None = None,
) -> list[httpx2.Request]:
    sent = [] if sent is None else sent

    async def fake_send(
        _: httpx2.AsyncClient, request: httpx2.Request, **__: Any
    ) -> httpx2.Response:
        sent.append(request)
        if status != 200:
            return httpx2.Response(status, json={"error": {"message": "down"}}, request=request)
        return httpx2.Response(200, json=COMPLETION, request=request)

    monkeypatch.setattr(httpx2.AsyncClient, "send", fake_send)

    asyncio.run(OpenAIChatModel(settings).generate([HumanMessage("Annual leave?")]))
    return sent


def sent_request_body(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> dict[str, Any]:
    body: dict[str, Any] = json.loads(send_requests(monkeypatch, settings)[0].content)
    return body


def test_replies_are_capped_at_5000_output_tokens_by_default(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    assert sent_request_body(monkeypatch, settings)["max_completion_tokens"] == 5000


def test_the_output_token_cap_comes_from_settings(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    capped = settings.model_copy(update={"max_output_tokens": 300})

    assert sent_request_body(monkeypatch, capped)["max_completion_tokens"] == 300


def test_reasoning_effort_is_low_by_default(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    assert sent_request_body(monkeypatch, settings)["reasoning_effort"] == "low"


def test_the_reasoning_effort_comes_from_settings(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    effortful = settings.model_copy(update={"reasoning_effort": "high"})

    assert sent_request_body(monkeypatch, effortful)["reasoning_effort"] == "high"


def test_a_chat_request_times_out_after_60_seconds_by_default(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    timeout = send_requests(monkeypatch, settings)[0].extensions["timeout"]

    assert timeout["read"] == 60


def test_the_chat_timeout_comes_from_settings(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    impatient = settings.model_copy(update={"chat_timeout_seconds": 15})

    assert send_requests(monkeypatch, impatient)[0].extensions["timeout"]["read"] == 15


def test_a_failing_chat_request_is_retried_as_many_times_as_settings_allow(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    once = settings.model_copy(update={"chat_max_retries": 1})
    sent: list[httpx2.Request] = []

    async def no_backoff(_: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", no_backoff)

    with pytest.raises(UpstreamError):
        send_requests(monkeypatch, once, status=503, sent=sent)

    assert len(sent) == 2
