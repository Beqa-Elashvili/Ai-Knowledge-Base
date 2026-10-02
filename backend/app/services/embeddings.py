"""Text embeddings for chunks (documents) and questions (queries).

    embed_documents(texts) -> one vector per text, sent in batches
    embed_query(text)      -> one vector for a search question

The provider is chosen by EMBEDDING_PROVIDER:
    gemini  Google Gemini API (gemini-embedding-2 by default; free tier)
    openai  OpenAI (text-embedding-3-small)

Every vector has EMBEDDING_DIMENSIONS (1536) values and is L2-normalized,
so cosine search in pgvector behaves the same for every provider. Vectors
from different providers or models are not comparable: after switching,
re-embed existing chunks with `python -m scripts.reembed --all`.

Transient failures (rate limits, 5xx, network) are retried with backoff;
anything else becomes EmbeddingError (502) with a user-safe message.
"""

import logging
import math
import re
import time
from collections.abc import Sequence
from typing import Literal, Protocol

import httpx

from app.config import get_settings
from app.errors import ExternalServiceError
from app.models import EMBEDDING_DIMENSIONS

logger = logging.getLogger(__name__)

TaskType = Literal["document", "query"]

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_MAX_BATCH = 100  # batchEmbedContents limit
RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 5
MAX_RETRY_DELAY_SECONDS = 60.0


class EmbeddingError(ExternalServiceError):
    default_message = "Could not generate embeddings. Please try again."


class _RetryableError(Exception):
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class EmbeddingProvider(Protocol):
    name: str
    model: str
    max_batch: int

    def embed_batch(self, texts: Sequence[str], task: TaskType) -> list[list[float]]: ...


class GeminiEmbeddings:
    name = "gemini"
    max_batch = GEMINI_MAX_BATCH

    _TASK_TYPES = {"document": "RETRIEVAL_DOCUMENT", "query": "RETRIEVAL_QUERY"}

    def __init__(self, api_key: str, model: str, timeout: float = 60.0) -> None:
        self.model = model
        self._client = httpx.Client(
            base_url=GEMINI_BASE_URL,
            headers={"x-goog-api-key": api_key},  # header, never in the URL/logs
            timeout=timeout,
        )

    def embed_batch(self, texts: Sequence[str], task: TaskType) -> list[list[float]]:
        body = {
            "requests": [
                {
                    "model": f"models/{self.model}",
                    "content": {"parts": [{"text": text}]},
                    "taskType": self._TASK_TYPES[task],
                    "outputDimensionality": EMBEDDING_DIMENSIONS,
                }
                for text in texts
            ]
        }
        try:
            response = self._client.post(f"/models/{self.model}:batchEmbedContents", json=body)
        except httpx.TransportError as exc:
            raise _RetryableError(f"network error: {type(exc).__name__}") from exc

        if response.status_code in RETRYABLE_STATUS:
            raise _RetryableError(f"HTTP {response.status_code}", _gemini_retry_delay(response))
        if response.status_code != 200:
            raise EmbeddingError() from RuntimeError(f"Gemini HTTP {response.status_code}: {_error_message(response)}")
        return [item["values"] for item in response.json()["embeddings"]]


class OpenAIEmbeddings:
    name = "openai"
    max_batch = 512

    def __init__(self, api_key: str, model: str, timeout: float = 60.0) -> None:
        import openai  # only needed when this provider is selected

        self.model = model
        self._openai = openai
        self._client = openai.OpenAI(api_key=api_key, timeout=timeout, max_retries=0)

    def embed_batch(self, texts: Sequence[str], task: TaskType) -> list[list[float]]:
        openai = self._openai
        try:
            response = self._client.embeddings.create(
                model=self.model, input=list(texts), dimensions=EMBEDDING_DIMENSIONS
            )
        except (openai.RateLimitError, openai.InternalServerError, openai.APIConnectionError) as exc:
            raise _RetryableError(type(exc).__name__) from exc
        except openai.OpenAIError as exc:
            raise EmbeddingError() from exc
        return [item.embedding for item in sorted(response.data, key=lambda d: d.index)]


_provider: EmbeddingProvider | None = None


def get_provider() -> EmbeddingProvider:
    global _provider
    if _provider is None:
        settings = get_settings()
        key = settings.embedding_api_key
        if key is None:
            logger.error("Embeddings misconfigured: no API key for provider=%s", settings.embedding_provider)
            raise EmbeddingError("Embeddings are not configured on the server.")
        cls = GeminiEmbeddings if settings.embedding_provider == "gemini" else OpenAIEmbeddings
        _provider = cls(key.get_secret_value(), settings.resolved_embedding_model)
    return _provider


def embed_documents(texts: Sequence[str]) -> list[list[float]]:
    """Embed chunk texts in batches; returns vectors in the same order."""
    if not texts:
        return []
    provider = get_provider()
    batch_size = min(provider.max_batch, get_settings().embedding_batch_size)
    started = time.perf_counter()
    vectors: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        vectors.extend(_embed_with_retry(provider, batch, "document"))
    logger.info(
        "Embedded %d chunk(s) provider=%s model=%s batches=%d in %.2fs",
        len(texts), provider.name, provider.model,
        math.ceil(len(texts) / batch_size), time.perf_counter() - started,
    )
    return vectors


def embed_query(text: str) -> list[float]:
    """Embed one search question."""
    if not text.strip():
        raise ValueError("Query text is empty")
    return _embed_with_retry(get_provider(), [text], "query")[0]


def _embed_with_retry(provider: EmbeddingProvider, texts: Sequence[str], task: TaskType) -> list[list[float]]:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            vectors = provider.embed_batch(texts, task)
            break
        except _RetryableError as exc:
            if attempt == MAX_ATTEMPTS:
                logger.error("Embedding failed after %d attempts provider=%s: %s", attempt, provider.name, exc)
                raise EmbeddingError("The AI service is busy right now. Please try again in a minute.") from exc
            delay = min(exc.retry_after or 2.0**attempt, MAX_RETRY_DELAY_SECONDS)
            logger.warning(
                "Embedding attempt %d/%d failed provider=%s (%s); retrying in %.1fs",
                attempt, MAX_ATTEMPTS, provider.name, exc, delay,
            )
            time.sleep(delay)
        except EmbeddingError as exc:
            logger.error("Embedding request rejected provider=%s: %s", provider.name, exc.__cause__)
            raise

    if len(vectors) != len(texts):
        logger.error("Embedding count mismatch: sent %d, got %d", len(texts), len(vectors))
        raise EmbeddingError()
    return [_normalize(v) for v in vectors]


def _normalize(vector: list[float]) -> list[float]:
    if len(vector) != EMBEDDING_DIMENSIONS:
        logger.error("Embedding has %d dimensions, expected %d", len(vector), EMBEDDING_DIMENSIONS)
        raise EmbeddingError()
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0 or not math.isfinite(norm):
        logger.error("Embedding has invalid norm %r", norm)
        raise EmbeddingError()
    return [x / norm for x in vector]


def _gemini_retry_delay(response: httpx.Response) -> float | None:
    """Seconds from a 429's RetryInfo ("retryDelay": "23s") or Retry-After header."""
    try:
        for detail in response.json()["error"].get("details", []):
            match = re.fullmatch(r"(\d+(?:\.\d+)?)s", str(detail.get("retryDelay", "")))
            if match:
                return float(match.group(1))
    except (ValueError, KeyError, AttributeError, TypeError):
        pass
    header = response.headers.get("retry-after", "")
    return float(header) if header.replace(".", "", 1).isdigit() else None


def _error_message(response: httpx.Response) -> str:
    try:
        return str(response.json()["error"]["message"])[:300]
    except (ValueError, KeyError, TypeError):
        return response.text[:300]
