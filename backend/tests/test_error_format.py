import logging
from collections.abc import Iterator

import pytest
from conftest import FakeVectorStore
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hr_assist.api import UpstreamError, create_app
from hr_assist.api.request_id import RequestIdLogFilter
from hr_assist.settings import Settings


def app_with_probe_routes(settings: Settings) -> FastAPI:
    app = create_app(settings, vector_store=FakeVectorStore())

    @app.get("/probe/validated")
    async def validated(limit: int) -> dict[str, int]:
        return {"limit": limit}

    @app.get("/probe/upstream")
    async def upstream() -> None:
        raise UpstreamError("Qdrant timed out")

    @app.get("/probe/upstream-with-cause")
    async def upstream_with_cause() -> None:
        try:
            raise ConnectionError("Collection prod-structure_v1 not found")
        except ConnectionError as exc:
            raise UpstreamError("Searching the policy index failed.") from exc

    @app.get("/api/probe/crash")
    async def crash() -> None:
        raise RuntimeError("database password is hunter2")

    return app


def test_unexpected_failures_use_the_shared_format_with_500(settings: Settings) -> None:
    client = TestClient(app_with_probe_routes(settings), raise_server_exceptions=False)

    response = client.get("/api/probe/crash")

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "internal_error",
            "message": "Something went wrong. Please try again.",
            "details": [],
            "request_id": response.headers["x-request-id"],
        }
    }
    assert response.headers["cache-control"] == "no-store"


def test_validation_errors_use_the_shared_format_with_422(settings: Settings) -> None:
    response = TestClient(app_with_probe_routes(settings)).get("/probe/validated?limit=many")

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["message"] == "The request is invalid."
    assert error["request_id"] == response.headers["x-request-id"]
    assert error["details"][0]["loc"] == ["query", "limit"]


def test_upstream_failures_use_the_shared_format_with_503(settings: Settings) -> None:
    response = TestClient(app_with_probe_routes(settings)).get("/probe/upstream")

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "upstream_unavailable",
            "message": "Qdrant timed out",
            "details": [],
            "request_id": response.headers["x-request-id"],
        }
    }


@pytest.fixture
def app_logs(caplog: pytest.LogCaptureFixture) -> Iterator[pytest.LogCaptureFixture]:
    app_logger = logging.getLogger("hr_assist")
    caplog.handler.addFilter(RequestIdLogFilter())
    app_logger.addHandler(caplog.handler)
    yield caplog
    app_logger.removeHandler(caplog.handler)


def test_an_upstream_failure_logs_its_cause_but_keeps_it_out_of_the_response(
    settings: Settings, app_logs: pytest.LogCaptureFixture
) -> None:
    response = TestClient(app_with_probe_routes(settings)).get("/probe/upstream-with-cause")

    assert response.json()["error"]["message"] == "Searching the policy index failed."
    assert "not found" not in response.text
    [record] = [r for r in app_logs.records if r.levelno == logging.ERROR]
    assert "Collection prod-structure_v1 not found" in app_logs.text
    assert record.request_id == response.headers["x-request-id"]  # type: ignore[attr-defined]
