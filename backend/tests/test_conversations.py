import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import conversations as conversations_api
from app.api.deps import get_current_user
from app.database import get_db
from app.main import app
from app.services import chat, rag
from app.services.conversations import ConversationNotFoundError
from app.services.llm import ChatMessage, LLMError, LLMResult

USER = uuid.UUID("11111111-1111-1111-1111-111111111111")
DOC = uuid.UUID("22222222-2222-2222-2222-222222222222")
CONV = uuid.UUID("33333333-3333-3333-3333-333333333333")
NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)


# --- history --------------------------------------------------------------

def test_history_starts_with_user_skips_empty_and_caps_length() -> None:
    history = rag.history_messages(
        [("assistant", "orphan answer"), ("user", "Q1"), ("assistant", "x" * 50), ("user", "  ")], max_chars=10
    )
    assert history == [ChatMessage("user", "Q1"), ChatMessage("assistant", "x" * 10 + " …")]


def test_messages_put_history_before_the_current_question() -> None:
    history = [ChatMessage("user", "When did it begin?"), ChatMessage("assistant", "In 1789 [p. 2].")]
    messages = rag.build_messages("History", "[Excerpt 1 | p. 2]\nText", "Why?", history)
    assert messages[:2] == history
    assert messages[2].role == "user" and messages[2].content.endswith("Question: Why?")
    assert "<excerpts>" not in messages[0].content  # excerpts only with the current question


# --- follow-up rewriting --------------------------------------------------

HISTORY = [ChatMessage("user", "When did the French Revolution begin?"), ChatMessage("assistant", "In 1789 [p. 2].")]


def test_first_question_is_not_rewritten(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rag, "generate", lambda *a: pytest.fail("no LLM call without history"))
    assert rag.condense_question([], "When?") == "When?"


def test_follow_up_is_rewritten_with_the_conversation(monkeypatch: pytest.MonkeyPatch) -> None:
    prompts = []

    def generate(system, messages):
        prompts.append((system, messages[0].content))
        return LLMResult(text='"Why did the French Revolution begin?"\n', model="m", finish_reason="STOP")

    monkeypatch.setattr(rag, "generate", generate)
    assert rag.condense_question(HISTORY, "Why did it start?") == "Why did the French Revolution begin?"
    system, prompt = prompts[0]
    assert system == rag.CONDENSE_PROMPT
    assert "USER: When did the French Revolution begin?" in prompt and prompt.endswith("Follow-up question: Why did it start?")


@pytest.mark.parametrize(
    "outcome",
    [LLMError("busy"), LLMResult(text="", model="m", finish_reason="STOP"),
     LLMResult(text="y" * 2000, model="m", finish_reason="STOP")],
)
def test_rewrite_falls_back_to_the_original_question(monkeypatch: pytest.MonkeyPatch, outcome) -> None:
    def generate(*_args):
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(rag, "generate", generate)
    assert rag.condense_question(HISTORY, "Why?") == "Why?"


def test_chat_turn_uses_history_and_rewritten_search_query(monkeypatch: pytest.MonkeyPatch) -> None:
    document = SimpleNamespace(id=DOC, title="History", status="ready")
    monkeypatch.setattr(chat.document_service, "get_owned_document", lambda db, u, d: document)
    monkeypatch.setattr(chat.conversations, "get_owned_conversation", lambda db, u, c: SimpleNamespace(id=CONV, document_id=DOC))
    monkeypatch.setattr(chat.conversations, "recent_messages", lambda db, c, limit: [
        SimpleNamespace(role=m.role, content=m.content) for m in HISTORY])
    monkeypatch.setattr(chat, "condense_question", lambda history, q: "Why did the French Revolution begin?")
    searched = []
    monkeypatch.setattr(chat, "search_owned_document", lambda db, doc, q: searched.append(q) or [])

    turn = chat.prepare_turn(None, USER, DOC, CONV, " Why? ")

    assert searched == ["Why did the French Revolution begin?"]
    assert turn.question == "Why?"  # saved and answered as asked
    assert turn.messages[:2] == HISTORY
    assert turn.messages[-1].content.endswith("Question: Why?")


# --- endpoints ------------------------------------------------------------

def conversation(**overrides):
    values = dict(id=CONV, document_id=DOC, title="When did it begin?", created_at=NOW, updated_at=NOW, messages=[])
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=USER, email="a@example.com")
    app.dependency_overrides[get_db] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_create_conversation(client, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(conversations_api.conversation_service, "create_conversation",
                        lambda db, u, d, t: calls.append((u, d, t)) or conversation(title=t))
    response = client.post("/conversations", json={"document_id": str(DOC), "title": "  Notes  "})
    assert response.status_code == 201
    assert calls == [(USER, DOC, "Notes")]
    assert response.json()["title"] == "Notes"


def test_list_conversations_filters_by_document(client, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(conversations_api.conversation_service, "list_conversations",
                        lambda db, u, d: calls.append((u, d)) or [conversation()])
    response = client.get(f"/conversations?document_id={DOC}")
    assert response.status_code == 200 and calls == [(USER, DOC)]
    assert [c["id"] for c in response.json()] == [str(CONV)]


def test_get_conversation_returns_messages_with_sources(client, monkeypatch: pytest.MonkeyPatch) -> None:
    messages = [
        SimpleNamespace(id=1, role="user", content="When?", sources=None, created_at=NOW),
        SimpleNamespace(id=2, role="assistant", content="1789 [p. 2].", sources=[{"page": 2, "similarity": 0.7}], created_at=NOW),
    ]
    monkeypatch.setattr(conversations_api.conversation_service, "get_conversation_with_messages",
                        lambda db, u, c: conversation(messages=messages))
    body = client.get(f"/conversations/{CONV}").json()
    assert [(m["role"], m["content"]) for m in body["messages"]] == [("user", "When?"), ("assistant", "1789 [p. 2].")]
    assert body["messages"][1]["sources"] == [{"page": 2, "similarity": 0.7}]


def test_someone_elses_conversation_is_404(client, monkeypatch: pytest.MonkeyPatch) -> None:
    def not_found(*_args):
        raise ConversationNotFoundError()

    monkeypatch.setattr(conversations_api.conversation_service, "get_conversation_with_messages", not_found)
    monkeypatch.setattr(conversations_api.conversation_service, "delete_conversation", not_found)
    assert client.get(f"/conversations/{CONV}").status_code == 404
    assert client.delete(f"/conversations/{CONV}").json() == {"detail": "Conversation not found."}
