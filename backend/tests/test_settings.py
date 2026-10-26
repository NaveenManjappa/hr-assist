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
