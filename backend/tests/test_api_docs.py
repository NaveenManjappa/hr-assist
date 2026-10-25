import pytest
from conftest import FakeVectorStore
from fastapi.testclient import TestClient

from hr_assist.api import create_app
from hr_assist.settings import Settings

API_PAGES = ["/openapi.json", "/docs", "/redoc", "/scalar"]


def client_for(settings: Settings, app_env: str) -> TestClient:
    settings = settings.model_copy(update={"app_env": app_env})
    return TestClient(create_app(settings, vector_store=FakeVectorStore()))


@pytest.mark.parametrize("path", API_PAGES)
def test_the_api_pages_are_served_outside_prod(settings: Settings, path: str) -> None:
    assert client_for(settings, "dev").get(path).status_code == 200


def test_the_scalar_page_loads_the_openapi_schema(settings: Settings) -> None:
    page = client_for(settings, "dev").get("/scalar").text

    assert "/openapi.json" in page


def test_the_schema_lists_both_endpoints_but_not_the_api_pages(settings: Settings) -> None:
    paths = client_for(settings, "dev").get("/openapi.json").json()["paths"]

    assert set(paths) == {"/api/health", "/api/chat"}


@pytest.mark.parametrize("path", API_PAGES)
def test_prod_publishes_no_schema_or_api_pages(settings: Settings, path: str) -> None:
    assert client_for(settings, "prod").get(path).status_code == 404
