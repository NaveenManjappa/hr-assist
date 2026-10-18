from typing import Any

import pytest
from conftest import FakeChatModel, FakeRetriever, FakeVectorStore, make_chunk
from fastapi.testclient import TestClient

from hr_assist.answering import AssistantReply
from hr_assist.api import UpstreamError, create_app
from hr_assist.settings import Settings

QUESTION = (
    "How many days of annual leave does a full-time employee with less than 3 years' "
    "service receive?"
)

ENTITLEMENT = make_chunk("3.1", "Entitlement", "|Less than 3 years|27|8|35|262.5|", page=5)
ACCRUAL = make_chunk("3.2", "Accrual and booking", "Leave accrues at one-twelfth...", page=5)


def chat(
    settings: Settings,
    reply: AssistantReply,
    body: dict[str, Any],
    retriever: FakeRetriever | None = None,
) -> Any:
    app = create_app(
        settings,
        vector_store=FakeVectorStore(),
        retriever=retriever or FakeRetriever([ACCRUAL, ENTITLEMENT]),
        chat_model=FakeChatModel(reply),
    )
    return TestClient(app).post("/api/chat", json=body)


def ask(question: str = QUESTION) -> dict[str, Any]:
    return {"messages": [{"role": "user", "content": question}]}


def test_an_answer_comes_back_with_its_response_type_message_and_citations(
    settings: Settings,
) -> None:
    reply = AssistantReply(
        response_type="answer",
        message="A full-time employee with less than 3 years' service receives 27 days.",
        cited_sources=[2],
    )

    response = chat(settings, reply, ask())

    assert response.status_code == 200
    assert response.json() == {
        "response_type": "answer",
        "message": "A full-time employee with less than 3 years' service receives 27 days.",
        "citations": [
            {
                "document_id": "NDS-HR-LAS-002",
                "document_version": "v1.2",
                "title": "Leave and Absence Standard",
                "section": "3.1 Entitlement",
                "page_start": 5,
                "page_end": 5,
                "snippet": "|Less than 3 years|27|8|35|262.5|",
                "status": "current",
            }
        ],
    }


def test_citations_come_only_from_retrieved_chunk_metadata(settings: Settings) -> None:
    reply = AssistantReply(
        response_type="answer",
        message="Per NDS-HR-FAKE-999 v9.9 §42, you get 99 days.",
        cited_sources=[2, 2, 7, 0, -1],
    )

    citations = chat(settings, reply, ask()).json()["citations"]

    assert [(c["document_id"], c["section"]) for c in citations] == [
        ("NDS-HR-LAS-002", "3.1 Entitlement")
    ]


def test_retrieval_uses_the_latest_question_and_the_top_8_chunks(settings: Settings) -> None:
    retriever = FakeRetriever([ENTITLEMENT])
    body = {
        "messages": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi, how can I help?"},
            {"role": "user", "content": QUESTION},
        ]
    }

    chat(settings, AssistantReply(response_type="answer", message="27 days."), body, retriever)

    assert retriever.queries == [(QUESTION, 8)]


def test_the_prompt_shows_each_source_with_its_status_and_effective_period(
    settings: Settings,
) -> None:
    chat_model = FakeChatModel(AssistantReply(response_type="answer", message="27 days."))
    app = create_app(
        settings,
        vector_store=FakeVectorStore(),
        retriever=FakeRetriever([ENTITLEMENT]),
        chat_model=chat_model,
    )

    TestClient(app).post("/api/chat", json={**ask(), "as_of_date": "2026-11-02"})

    prompt = "\n".join(str(m.content) for m in chat_model.prompts[0])
    assert "2026-11-02" in prompt
    assert "[1]" in prompt
    assert "current" in prompt
    assert "effective 2026-10-01" in prompt
    assert "|Less than 3 years|27|8|35|262.5|" in prompt
    assert QUESTION in prompt


@pytest.mark.parametrize(
    "body",
    [
        {"messages": []},
        {"messages": [{"role": "user", "content": "   "}]},
        {"messages": [{"role": "assistant", "content": "Hi"}]},
        {**ask(), "as_of_date": "02/11/2026"},
    ],
    ids=["no-messages", "blank-question", "last-message-not-from-user", "malformed-as-of-date"],
)
def test_invalid_requests_get_a_422_in_the_shared_error_format(
    settings: Settings, body: dict[str, Any]
) -> None:
    response = chat(settings, AssistantReply(response_type="answer", message="-"), body)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_an_upstream_failure_maps_to_503(settings: Settings) -> None:
    class FailingRetriever(FakeRetriever):
        async def retrieve(self, query: str, k: int) -> list[Any]:
            raise UpstreamError("Qdrant timed out")

    response = chat(
        settings,
        AssistantReply(response_type="answer", message="-"),
        ask(),
        FailingRetriever([]),
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "upstream_unavailable"
