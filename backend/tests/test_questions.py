import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import documents as documents_api
from app.api.deps import get_current_user
from app.database import get_db
from app.main import app
from app.services import llm, questions
from app.services.llm import LLMError, LLMResult
from app.services.vector_search import DocumentNotReadyError

USER = uuid.UUID("11111111-1111-1111-1111-111111111111")
DOC = uuid.UUID("22222222-2222-2222-2222-222222222222")


# --- excerpt sampling -----------------------------------------------------

def test_short_document_is_used_whole() -> None:
    chunks = [("a" * 10, 1, 1), ("b" * 10, 2, 2)]
    assert questions.sample_excerpts(chunks, max_chars=100) == chunks


def test_long_document_is_sampled_evenly_from_start_to_end() -> None:
    chunks = [(f"{i:03d}" + "x" * 97, i + 1, i + 1) for i in range(100)]  # 100 chunks x 100 chars
    picked = questions.sample_excerpts(chunks, max_chars=1000)
    pages = [page for _, page, _ in picked]
    assert len(picked) == 10 and sum(len(c) for c, _, _ in picked) <= 1000
    assert pages[0] == 1 and pages[-1] == 100  # covers beginning and end
    assert pages == sorted(pages)  # reading order
    gaps = [b - a for a, b in zip(pages, pages[1:])]
    assert max(gaps) - min(gaps) <= 1  # evenly spread


# --- cleaning -------------------------------------------------------------

def test_questions_are_cleaned_and_deduplicated() -> None:
    raw = [
        "1. What is the main argument of the document?",
        "what is the main argument of the document?",  # duplicate (case)
        "  - How does   backpropagation adjust weights  ",
        "Why?",  # too short
        "x" * 300 + "?",  # too long
        42,  # not a string
        "Which king's rule did the revolution end.",
    ]
    assert questions.clean_questions(raw, limit=10) == [
        "What is the main argument of the document?",
        "How does backpropagation adjust weights?",
        "Which king's rule did the revolution end?",
    ]
    assert len(questions.clean_questions([f"Question number {i}?" for i in range(9)], limit=6)) == 6


def test_prompt_has_summary_and_page_labelled_excerpts() -> None:
    prompt = questions.build_prompt("ML Book", "A book about ML.", [("Intro text", 1, 1), ("Later text", 4, 5)])
    assert prompt.startswith('Document: "ML Book"')
    assert "<summary>\nA book about ML.\n</summary>" in prompt
    assert "[p. 1]\nIntro text" in prompt and "[pp. 4-5]\nLater text" in prompt
    assert "<summary>" not in questions.build_prompt("T", None, [("x", 1, 1)])


def test_json_mode_request() -> None:
    body = llm.build_request("S", [llm.ChatMessage("user", "q")], questions.RESPONSE_SCHEMA)
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["generationConfig"]["responseSchema"]["properties"]["questions"]["type"] == "ARRAY"
    assert "responseMimeType" not in llm.build_request("S", [llm.ChatMessage("user", "q")])["generationConfig"]


# --- service --------------------------------------------------------------

class FakeDb:
    def __init__(self, rows) -> None:
        self.rows, self.committed = rows, False

    def execute(self, _stmt):
        return SimpleNamespace(all=lambda: self.rows)

    def commit(self):
        self.committed = True

    def refresh(self, _obj):
        pass

    def rollback(self):
        pass


def owned(monkeypatch, **overrides):
    document = SimpleNamespace(id=DOC, title="History", status="ready", summary=None, questions=None)
    for key, value in overrides.items():
        setattr(document, key, value)
    monkeypatch.setattr(questions.document_service, "get_owned_document", lambda db, u, d: document)
    return document


def reply(monkeypatch, text: str) -> list:
    calls = []
    monkeypatch.setattr(questions, "generate", lambda system, messages, schema: calls.append((system, messages, schema))
                        or LLMResult(text=text, model="m", finish_reason="STOP"))
    return calls


def test_questions_are_generated_and_stored(monkeypatch) -> None:
    document = owned(monkeypatch, summary="About the revolution.")
    calls = reply(monkeypatch, json.dumps({"questions": ["When did the French Revolution begin?", "Whose rule did it end?"]}))
    db = FakeDb([("The Bastille fell in 1789.", 2, 2)])

    result = questions.generate_questions(db, USER, DOC, language="Georgian")

    assert result.questions == ["When did the French Revolution begin?", "Whose rule did it end?"] and db.committed
    system, [message], schema = calls[0]
    assert "Write 6 questions" in system and "Write the questions in Georgian." in system
    assert "About the revolution." in message.content and "The Bastille fell in 1789." in message.content
    assert schema is questions.RESPONSE_SCHEMA
    assert document.questions == result.questions


@pytest.mark.parametrize("text", ["not json", json.dumps({"questions": []}), json.dumps({"questions": ["?"]}), json.dumps(["a"])])
def test_unusable_reply_keeps_previous_questions(monkeypatch, text) -> None:
    document = owned(monkeypatch, questions=["Old question here?"])
    reply(monkeypatch, text)
    db = FakeDb([("Text.", 1, 1)])
    with pytest.raises(LLMError):
        questions.generate_questions(db, USER, DOC)
    assert document.questions == ["Old question here?"] and not db.committed


def test_not_ready_is_409_without_llm(monkeypatch) -> None:
    owned(monkeypatch, status="processing")
    monkeypatch.setattr(questions, "generate", lambda *a: pytest.fail("no LLM call"))
    with pytest.raises(DocumentNotReadyError):
        questions.generate_questions(FakeDb([]), USER, DOC)


# --- endpoint -------------------------------------------------------------

@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=USER, email="a@example.com")
    app.dependency_overrides[get_db] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_questions_endpoint(client, monkeypatch) -> None:
    calls = []
    document = SimpleNamespace(id=DOC, title="Doc", filename="doc.pdf", status="ready", page_count=3, summary=None,
                               questions=["What is RAG?"], created_at=datetime(2026, 10, 2, tzinfo=timezone.utc))
    monkeypatch.setattr(documents_api, "generate_questions", lambda db, u, d, lang: calls.append((u, d, lang)) or document)
    response = client.post(f"/documents/{DOC}/questions", json={"language": "Georgian"})
    assert response.status_code == 200 and response.json()["questions"] == ["What is RAG?"]
    assert calls == [(USER, DOC, "Georgian")]
    assert client.post(f"/documents/{DOC}/questions", json={"language": "say hi; now"}).status_code == 422
