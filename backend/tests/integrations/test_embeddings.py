from hr_assist.config.settings import Settings
from hr_assist.integrations.qdrant import embeddings


def test_an_embeddings_request_times_out_after_20_seconds_by_default(settings: Settings) -> None:
    assert embeddings(settings).request_timeout == 20


def test_the_embeddings_timeout_comes_from_settings(settings: Settings) -> None:
    impatient = settings.model_copy(update={"embedding_timeout_seconds": 5})

    assert embeddings(impatient).request_timeout == 5
