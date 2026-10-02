import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError

from app.services import vector_search
from app.services.documents import DocumentNotFoundError
from app.services.vector_search import DocumentNotReadyError, RetrievedChunk, VectorSearchError

USER = uuid.UUID("11111111-1111-1111-1111-111111111111")
DOC = uuid.UUID("22222222-2222-2222-2222-222222222222")


def row(chunk_index: int, similarity: float, page: int = 1):
    return SimpleNamespace(_mapping=dict(
        id=uuid.uuid4(), document_id=DOC, content=f"chunk {chunk_index}", page_number=page,
        page_end=page, chunk_index=chunk_index, similarity=similarity,
    ))


class FakeSession:
    def __init__(self, rows=(), error: Exception | None = None) -> None:
        self.rows, self.error = list(rows), error
        self.params: dict | None = None
        self.rolled_back = False

    def execute(self, _sql, params):
        if self.error:
            raise self.error
        self.params = params
        return SimpleNamespace(all=lambda: self.rows)

    def rollback(self) -> None:
        self.rolled_back = True


@pytest.fixture
def embedded(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    questions: list[str] = []
    monkeypatch.setattr(vector_search, "embed_query", lambda q: questions.append(q) or [0.5, -0.25])
    return questions


def owned(monkeypatch: pytest.MonkeyPatch, status: str = "ready") -> None:
    def get_owned(db, user_id, document_id):
        assert (user_id, document_id) == (USER, DOC)
        return SimpleNamespace(id=DOC, status=status)

    monkeypatch.setattr(vector_search.document_service, "get_owned_document", get_owned)


def test_returns_ranked_chunks_for_the_document(monkeypatch, embedded) -> None:
    owned(monkeypatch)
    db = FakeSession([row(3, 0.91, page=14), row(0, 0.72, page=2)])

    chunks = vector_search.search_document(db, USER, DOC, "  What is RAG?  ")

    assert embedded == ["What is RAG?"]
    assert db.params == {"embedding": "[0.5,-0.25]", "document_id": DOC, "match_count": 5, "min_similarity": 0.0}
    assert [(c.chunk_index, c.page_number, c.similarity) for c in chunks] == [(3, 14, 0.91), (0, 2, 0.72)]
    assert all(isinstance(c, RetrievedChunk) and c.document_id == DOC for c in chunks)


def test_top_k_is_clamped(monkeypatch, embedded) -> None:
    owned(monkeypatch)
    db = FakeSession()
    vector_search.search_document(db, USER, DOC, "q", top_k=500)
    assert db.params["match_count"] == vector_search.MAX_MATCH_COUNT


def test_other_users_document_is_rejected_before_embedding(monkeypatch, embedded) -> None:
    def not_found(*_args):
        raise DocumentNotFoundError()

    monkeypatch.setattr(vector_search.document_service, "get_owned_document", not_found)
    db = FakeSession()
    with pytest.raises(DocumentNotFoundError):
        vector_search.search_document(db, USER, DOC, "q")
    assert embedded == [] and db.params is None


def test_document_without_embeddings_returns_409(monkeypatch, embedded) -> None:
    owned(monkeypatch, status="processing")
    with pytest.raises(DocumentNotReadyError) as exc_info:
        vector_search.search_document(FakeSession(), USER, DOC, "q")
    assert exc_info.value.status_code == 409
    assert embedded == []


def test_database_failure_is_a_safe_502(monkeypatch, embedded) -> None:
    owned(monkeypatch)
    db = FakeSession(error=OperationalError("select", {}, Exception("password=hunter2")))
    with pytest.raises(VectorSearchError) as exc_info:
        vector_search.search_document(db, USER, DOC, "q")
    assert db.rolled_back
    assert exc_info.value.status_code == 502 and "hunter2" not in exc_info.value.message


def test_empty_question_is_rejected(monkeypatch, embedded) -> None:
    owned(monkeypatch)
    with pytest.raises(ValueError):
        vector_search.search_document(FakeSession(), USER, DOC, "   ")
