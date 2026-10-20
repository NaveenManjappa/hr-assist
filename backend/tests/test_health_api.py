from collections.abc import Callable

import pytest
from conftest import FakeVectorStore
from fastapi.testclient import TestClient

from hr_assist.api import create_app
from hr_assist.settings import Settings

ClientFactory = Callable[..., TestClient]


@pytest.fixture
def client_with_qdrant(settings: Settings) -> ClientFactory:
    def build(reachable: bool = True) -> TestClient:
        return TestClient(create_app(settings, vector_store=FakeVectorStore(reachable)))

    return build


def test_health_reports_qdrant_up(client_with_qdrant: ClientFactory) -> None:
    response = client_with_qdrant(reachable=True).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "api": "up", "qdrant": "up"}


def test_health_reports_qdrant_down_without_failing(client_with_qdrant: ClientFactory) -> None:
    response = client_with_qdrant(reachable=False).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "degraded", "api": "up", "qdrant": "down"}


@pytest.mark.parametrize("reachable", [True, False], ids=["qdrant-up", "qdrant-down"])
def test_health_responses_are_never_cached(
    client_with_qdrant: ClientFactory, reachable: bool
) -> None:
    response = client_with_qdrant(reachable).get("/api/health")

    assert response.headers["cache-control"] == "no-store"


def test_cors_preflights_are_never_cached(client_with_qdrant: ClientFactory) -> None:
    response = client_with_qdrant().options(
        "/api/chat",
        headers={"Origin": "http://localhost:4200", "Access-Control-Request-Method": "POST"},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


def test_every_response_carries_a_unique_request_id(client_with_qdrant: ClientFactory) -> None:
    client = client_with_qdrant()

    first = client.get("/api/health")
    second = client.get("/api/health")
    not_found = client.get("/api/does-not-exist")

    ids = [r.headers.get("x-request-id") for r in (first, second, not_found)]
    assert all(ids)
    assert len(set(ids)) == 3


def test_a_well_formed_incoming_request_id_is_kept(client_with_qdrant: ClientFactory) -> None:
    response = client_with_qdrant().get("/api/health", headers={"X-Request-ID": "trace-abc_123"})

    assert response.headers["x-request-id"] == "trace-abc_123"


def test_a_malformed_incoming_request_id_is_replaced(client_with_qdrant: ClientFactory) -> None:
    response = client_with_qdrant().get("/api/health", headers={"X-Request-ID": "not ok; <script>"})

    assert response.headers["x-request-id"] not in ("", "not ok; <script>")


def test_cors_allows_only_the_configured_frontend_origin(client_with_qdrant: ClientFactory) -> None:
    client = client_with_qdrant()

    allowed = client.get("/api/health", headers={"Origin": "http://localhost:4200"})
    other = client.get("/api/health", headers={"Origin": "https://evil.example"})

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:4200"
    assert "x-request-id" in allowed.headers["access-control-expose-headers"].lower()
    assert "access-control-allow-origin" not in other.headers
