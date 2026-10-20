import logging
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from conftest import FakeChatModel, FakeClock, FakeRetriever, FakeVectorStore, make_chunk
from fastapi.testclient import TestClient
from httpx2 import Response

from hr_assist.answering import AssistantReply
from hr_assist.api import create_app
from hr_assist.api.request_id import RequestIdLogFilter
from hr_assist.settings import Settings

ASK = {"messages": [{"role": "user", "content": "How much annual leave do I get?"}]}


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(datetime(2026, 11, 2, 9, 0, tzinfo=UTC))


@pytest.fixture
def chat_model() -> FakeChatModel:
    return FakeChatModel(AssistantReply(response_type="answer", message="27 days."))


@pytest.fixture
def client(settings: Settings, clock: FakeClock, chat_model: FakeChatModel) -> TestClient:
    return client_for(settings, clock, chat_model)


def client_for(settings: Settings, clock: FakeClock, chat_model: FakeChatModel) -> TestClient:
    app = create_app(
        settings,
        vector_store=FakeVectorStore(),
        retriever=FakeRetriever([make_chunk("3.1", "Entitlement", "27 days", page=5)]),
        chat_model=chat_model,
        clock=clock,
    )
    return TestClient(app)


def ask_from(client: TestClient, ip: str, times: int = 1) -> list[Response]:
    return [
        client.post("/api/chat", json=ASK, headers={"X-Forwarded-For": ip}) for _ in range(times)
    ]


def test_the_11th_chat_in_a_minute_is_rejected_until_the_minute_has_passed(
    client: TestClient, clock: FakeClock
) -> None:
    allowed = ask_from(client, "203.0.113.7", times=10)
    clock.advance(seconds=30)
    rejected = ask_from(client, "203.0.113.7")[0]

    assert [r.status_code for r in allowed] == [200] * 10
    assert rejected.status_code == 429
    assert rejected.json() == {
        "error": {
            "code": "rate_limited",
            "message": "You're asking questions too quickly. Please wait a minute and try again.",
            "details": [],
            "request_id": rejected.headers["x-request-id"],
        }
    }
    assert rejected.headers["retry-after"] == "30"
    assert rejected.headers["cache-control"] == "no-store"

    clock.advance(seconds=30)
    assert ask_from(client, "203.0.113.7")[0].status_code == 200


def ask_every_minute(client: TestClient, clock: FakeClock, ip: str, times: int) -> list[Response]:
    responses = []
    for _ in range(times):
        responses.extend(ask_from(client, ip))
        clock.advance(minutes=1)
    return responses


def test_the_101st_chat_in_a_utc_day_gets_the_daily_message(
    client: TestClient, clock: FakeClock
) -> None:
    allowed = ask_every_minute(client, clock, "203.0.113.7", times=100)
    rejected = ask_from(client, "203.0.113.7")[0]

    assert [r.status_code for r in allowed] == [200] * 100
    assert rejected.status_code == 429
    assert rejected.json()["error"]["code"] == "rate_limited"
    assert rejected.json()["error"]["message"] == (
        "You've reached today's limit of questions. Please come back tomorrow."
    )
    # 09:00 + 100 minutes is 10:40, so 13h20m until midnight UTC.
    assert rejected.headers["retry-after"] == str(13 * 3600 + 20 * 60)


def test_the_1001st_chat_across_ips_in_a_utc_day_is_rejected_until_midnight(
    client: TestClient, clock: FakeClock
) -> None:
    allowed = [ask_from(client, f"198.51.100.{n}", times=10) for n in range(100)]
    rejected = ask_from(client, "203.0.113.7")[0]

    assert all(r.status_code == 200 for batch in allowed for r in batch)
    assert rejected.status_code == 429
    assert rejected.json()["error"]["message"] == (
        "HR Assist has answered as many questions as it can today. Please come back tomorrow."
    )
    assert rejected.headers["retry-after"] == str(15 * 3600)

    clock.now = datetime(2026, 11, 2, 23, 59, 59, tzinfo=UTC)
    assert ask_from(client, "203.0.113.7")[0].status_code == 429
    clock.now = datetime(2026, 11, 3, 0, 0, tzinfo=UTC)
    assert ask_from(client, "203.0.113.7")[0].status_code == 200
    assert ask_from(client, "198.51.100.0")[0].status_code == 200


def test_each_ip_has_its_own_per_minute_limit(client: TestClient) -> None:
    ask_from(client, "203.0.113.7", times=10)

    assert ask_from(client, "203.0.113.7")[0].status_code == 429
    assert ask_from(client, "203.0.113.8")[0].status_code == 200


def test_a_rejected_chat_never_reaches_the_model(
    client: TestClient, chat_model: FakeChatModel
) -> None:
    ask_from(client, "203.0.113.7", times=11)

    assert len(chat_model.prompts) == 10


def test_entries_a_client_adds_to_x_forwarded_for_do_not_change_its_bucket(
    client: TestClient,
) -> None:
    ask_from(client, "203.0.113.7", times=10)

    spoofed = ask_from(client, "10.0.0.1, 203.0.113.7")[0]
    many_spoofed = ask_from(client, "10.0.0.2, 10.0.0.3, 203.0.113.7")[0]

    assert spoofed.status_code == 429
    assert many_spoofed.status_code == 429


def test_the_trusted_hop_count_picks_the_client_entry(
    settings: Settings, clock: FakeClock, chat_model: FakeChatModel
) -> None:
    client = client_for(settings.model_copy(update={"trusted_proxy_hops": 2}), clock, chat_model)
    ask_from(client, "10.0.0.1, 203.0.113.7, 35.191.0.1", times=10)

    other_proxy = ask_from(client, "10.0.0.2, 203.0.113.7, 35.191.0.2")[0]
    other_client = ask_from(client, "10.0.0.1, 203.0.113.8, 35.191.0.1")[0]

    assert other_proxy.status_code == 429
    assert other_client.status_code == 200


def test_without_x_forwarded_for_the_socket_peer_is_the_client(client: TestClient) -> None:
    responses = [client.post("/api/chat", json=ASK) for _ in range(11)]

    assert [r.status_code for r in responses] == [200] * 10 + [429]
    assert ask_from(client, "203.0.113.7")[0].status_code == 200


def test_invalid_requests_do_not_use_up_the_quota(client: TestClient) -> None:
    invalid = [
        client.post("/api/chat", json={"messages": []}, headers={"X-Forwarded-For": "203.0.113.7"})
        for _ in range(20)
    ]

    assert [r.status_code for r in invalid] == [422] * 20
    assert [r.status_code for r in ask_from(client, "203.0.113.7", times=10)] == [200] * 10


def test_health_is_never_rate_limited(client: TestClient) -> None:
    ask_from(client, "203.0.113.7", times=11)

    health = [
        client.get("/api/health", headers={"X-Forwarded-For": "203.0.113.7"}) for _ in range(20)
    ]

    assert [r.status_code for r in health] == [200] * 20


@pytest.fixture
def app_logs(caplog: pytest.LogCaptureFixture) -> Iterator[pytest.LogCaptureFixture]:
    app_logger = logging.getLogger("hr_assist")
    caplog.handler.addFilter(RequestIdLogFilter())
    app_logger.addHandler(caplog.handler)
    yield caplog
    app_logger.removeHandler(caplog.handler)


def test_a_rejection_is_logged_with_the_limit_hit_and_the_request_id(
    client: TestClient, app_logs: pytest.LogCaptureFixture
) -> None:
    rejected = ask_from(client, "203.0.113.7", times=11)[-1]

    [record] = [r for r in app_logs.records if r.levelno == logging.WARNING]
    assert "per_ip_minute" in record.getMessage()
    assert record.request_id == rejected.headers["x-request-id"]  # type: ignore[attr-defined]


def test_each_chat_logs_the_forwarded_chain_and_the_client_it_counts_against(
    settings: Settings,
    clock: FakeClock,
    chat_model: FakeChatModel,
    app_logs: pytest.LogCaptureFixture,
) -> None:
    client = client_for(settings.model_copy(update={"trusted_proxy_hops": 2}), clock, chat_model)
    response = ask_from(client, "10.0.0.1, 203.0.113.7, 35.191.0.1")[0]

    [record] = [
        r
        for r in app_logs.records
        if r.name == "hr_assist.rate_limit" and r.levelno == logging.INFO
    ]
    message = record.getMessage()
    assert "X-Forwarded-For='10.0.0.1, 203.0.113.7, 35.191.0.1'" in message
    assert "peer=testclient" in message
    assert "client=203.0.113.7" in message
    assert record.request_id == response.headers["x-request-id"]  # type: ignore[attr-defined]


def test_chats_after_midnight_succeed_when_an_ip_was_turned_away_for_the_day(
    client: TestClient, clock: FakeClock
) -> None:
    ask_every_minute(client, clock, "203.0.113.7", times=100)
    clock.advance(minutes=5)
    assert ask_from(client, "203.0.113.7")[0].status_code == 429

    clock.now = datetime(2026, 11, 3, 0, 0, tzinfo=UTC)

    assert ask_from(client, "198.51.100.1")[0].status_code == 200
    assert ask_from(client, "203.0.113.7")[0].status_code == 200
