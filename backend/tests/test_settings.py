import pytest
from pydantic import ValidationError

from hr_assist.settings import Settings


def test_the_collection_is_named_by_environment_chunking_version_and_embedding_model(
    settings: Settings,
) -> None:
    settings = settings.model_copy(update={"chunking_version": "chunking_v2"})

    assert settings.collection_name == "test-chunking_v2-text-embedding-3-small"


def test_chunk_sizes_do_not_change_the_collection_name(settings: Settings) -> None:
    settings = settings.model_copy(
        update={
            "chunking_version": "chunking_v2",
            "chunk_max_tokens": 1000,
            "chunk_overlap_tokens": 100,
        }
    )

    assert settings.collection_name == "test-chunking_v2-text-embedding-3-small"


def test_the_retrieval_score_threshold_defaults_to_0_65(settings: Settings) -> None:
    assert settings.retrieval_score_threshold == 0.65


def test_the_retrieval_score_threshold_comes_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RETRIEVAL_SCORE_THRESHOLD", "0.45")

    assert make_settings().retrieval_score_threshold == 0.45


@pytest.mark.parametrize("threshold", [-0.1, 1.1])
def test_the_retrieval_score_threshold_must_be_between_0_and_1(threshold: float) -> None:
    with pytest.raises(ValidationError):
        make_settings(retrieval_score_threshold=threshold)


def make_settings(**overrides: float) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        openai_api_key="sk-test",
        qdrant_url="https://qdrant.invalid",
        qdrant_api_key="qdrant-test",
        **overrides,
    )
