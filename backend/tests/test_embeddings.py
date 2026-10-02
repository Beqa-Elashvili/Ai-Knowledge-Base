import json
import math
import uuid

import httpx
import pytest

from app.config import Settings
from app.models import EMBEDDING_DIMENSIONS
from app.services import embeddings, ingestion
from app.services.uploads import ValidatedPdf

DIM = EMBEDDING_DIMENSIONS


@pytest.fixture(autouse=True)
def no_sleep_and_fresh_provider(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    sleeps: list[float] = []
    monkeypatch.setattr(embeddings.time, "sleep", sleeps.append)
    monkeypatch.setattr(embeddings, "_provider", None)
    return sleeps


def gemini_with(handler) -> embeddings.GeminiEmbeddings:
    provider = embeddings.GeminiEmbeddings(api_key="secret-key", model="gemini-embedding-2")
    provider._client = httpx.Client(
        base_url=embeddings.GEMINI_BASE_URL,
        headers=provider._client.headers,
        transport=httpx.MockTransport(handler),
    )
    return provider


def vectors_response(request: httpx.Request, scale: float = 3.0) -> httpx.Response:
    count = len(json.loads(request.content)["requests"])
    return httpx.Response(200, json={"embeddings": [{"values": [scale] * DIM} for _ in range(count)]})


class FakeProvider:
    name, model = "fake", "fake-model"

    def __init__(self, max_batch: int = 100) -> None:
        self.max_batch = max_batch
        self.calls: list[tuple[list[str], str]] = []

    def embed_batch(self, texts, task):
        self.calls.append((list(texts), task))
        # Encode the text's number in the vector so order can be checked.
        return [[float(text.split()[-1]) + 1] + [0.0] * (DIM - 1) for text in texts]


def test_gemini_request_shape_and_normalized_output(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return vectors_response(request)

    monkeypatch.setattr(embeddings, "_provider", gemini_with(handler))
    [vector] = embeddings.embed_documents(["hello"])

    request = seen[0]
    body = json.loads(request.content)["requests"][0]
    assert request.url.path.endswith("/models/gemini-embedding-2:batchEmbedContents")
    assert request.headers["x-goog-api-key"] == "secret-key"
    assert "secret-key" not in str(request.url)
    assert body["taskType"] == "RETRIEVAL_DOCUMENT"
    assert body["outputDimensionality"] == DIM
    assert len(vector) == DIM
    assert math.isclose(math.sqrt(sum(x * x for x in vector)), 1.0)


def test_query_uses_query_task_type(monkeypatch: pytest.MonkeyPatch) -> None:
    tasks: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        tasks.append(json.loads(request.content)["requests"][0]["taskType"])
        return vectors_response(request)

    monkeypatch.setattr(embeddings, "_provider", gemini_with(handler))
    assert len(embeddings.embed_query("What is RAG?")) == DIM
    assert tasks == ["RETRIEVAL_QUERY"]


def test_documents_are_batched_and_keep_order(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeProvider(max_batch=4)
    monkeypatch.setattr(embeddings, "_provider", fake)
    texts = [f"chunk {i}" for i in range(10)]

    vectors = embeddings.embed_documents(texts)

    assert [len(batch) for batch, _ in fake.calls] == [4, 4, 2]
    assert all(task == "document" for _, task in fake.calls)
    assert [v[0] for v in vectors] == [1.0] * 10  # normalized
    assert embeddings.embed_documents([]) == []


def test_rate_limit_is_retried_with_server_delay(monkeypatch: pytest.MonkeyPatch, no_sleep_and_fresh_provider) -> None:
    responses = iter([
        httpx.Response(429, json={"error": {"code": 429, "details": [{"retryDelay": "7s"}]}}),
        None,
    ])

    def handler(request: httpx.Request) -> httpx.Response:
        return next(responses) or vectors_response(request)

    monkeypatch.setattr(embeddings, "_provider", gemini_with(handler))
    assert len(embeddings.embed_documents(["a", "b"])) == 2
    assert no_sleep_and_fresh_provider == [7.0]


def test_persistent_outage_gives_safe_502(monkeypatch: pytest.MonkeyPatch, no_sleep_and_fresh_provider) -> None:
    monkeypatch.setattr(embeddings, "_provider", gemini_with(lambda r: httpx.Response(503, text="overloaded")))
    with pytest.raises(embeddings.EmbeddingError) as exc_info:
        embeddings.embed_documents(["a"])
    assert exc_info.value.status_code == 502
    assert "busy" in exc_info.value.message
    assert len(no_sleep_and_fresh_provider) == embeddings.MAX_ATTEMPTS - 1


def test_client_errors_are_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400, json={"error": {"message": "API key not valid"}})

    monkeypatch.setattr(embeddings, "_provider", gemini_with(handler))
    with pytest.raises(embeddings.EmbeddingError) as exc_info:
        embeddings.embed_documents(["a"])
    assert calls == [1]
    assert "API key" not in exc_info.value.message


def test_wrong_dimensions_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    short = lambda r: httpx.Response(200, json={"embeddings": [{"values": [1.0] * 768}]})  # noqa: E731
    monkeypatch.setattr(embeddings, "_provider", gemini_with(short))
    with pytest.raises(embeddings.EmbeddingError):
        embeddings.embed_documents(["a"])


def test_missing_api_key_is_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setattr(embeddings, "get_settings", lambda: Settings())
    with pytest.raises(embeddings.EmbeddingError, match="not configured"):
        embeddings.embed_query("hi")


def test_provider_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    assert Settings(_env_file=None).resolved_embedding_model == "gemini-embedding-2"
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    settings = Settings(_env_file=None)
    assert settings.resolved_embedding_model == "text-embedding-3-small"
    assert settings.embedding_api_key.get_secret_value() == "test-openai-key"


def test_embedding_failure_stores_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Embeddings run before Storage/DB writes, so a failure leaves no trace."""
    class Extracted:
        pages, page_count = ["text"], 1

    class Chunk:
        content = "text"

    def fail(_texts):
        raise embeddings.EmbeddingError()

    monkeypatch.setattr(ingestion, "extract_pages", lambda data, max_pages: Extracted())
    monkeypatch.setattr(ingestion, "chunk_pages", lambda pages, settings, document_id: [Chunk()])
    monkeypatch.setattr(ingestion, "embed_documents", fail)
    monkeypatch.setattr(ingestion.document_service, "create_document", lambda *a, **k: pytest.fail("must not store"))
    with pytest.raises(embeddings.EmbeddingError):
        ingestion.ingest_pdf(None, uuid.uuid4(), ValidatedPdf(filename="a.pdf", data=b"%PDF"))
