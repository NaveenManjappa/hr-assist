from conftest import FakeVectorStore
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hr_assist.api import UpstreamError, create_app
from hr_assist.settings import Settings


def app_with_probe_routes(settings: Settings) -> FastAPI:
    app = create_app(settings, vector_store=FakeVectorStore())

    @app.get("/probe/validated")
    async def validated(limit: int) -> dict[str, int]:
        return {"limit": limit}

    @app.get("/probe/upstream")
    async def upstream() -> None:
        raise UpstreamError("Qdrant timed out")

    return app


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
