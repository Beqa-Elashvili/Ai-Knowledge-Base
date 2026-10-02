import asyncio
import json
import uuid
from types import SimpleNamespace

import httpx
import pytest

from app.api.deps import get_current_user
from app.database import get_db
from app.main import app
from app.services import chat, conversations, gemini, llm
from app.services.llm import LLMError
from app.services.vector_search import RetrievedChunk
from fastapi.testclient import TestClient

USER = uuid.UUID("11111111-1111-1111-1111-111111111111")
DOC = uuid.UUID("22222222-2222-2222-2222-222222222222")
CONV = uuid.UUID("33333333-3333-3333-3333-333333333333")


def parse_events(raw: str) -> list[tuple[str, dict]]:
    events = []
    for block in raw.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        events.append((lines["event"], json.loads(lines["data"])))
    return events


async def collect(stream) -> list[tuple[str, dict]]:
    return parse_events("".join([event async for event in stream]))


# --- Gemini streaming -----------------------------------------------------

def sse_body(*payloads: dict) -> bytes:
    return "".join(f"data: {json.dumps(p)}\r\n\r\n" for p in payloads).encode()


def text_payload(text: str, thought: bool = False, finish: str | None = None) -> dict:
    candidate = {"content": {"parts": [{"text": text, **({"thought": True} if thought else {})}]}}
    if finish:
        candidate["finishReason"] = finish
    return {"candidates": [candidate]}


@pytest.fixture
def gemini_stream(monkeypatch: pytest.MonkeyPatch):
    sleeps: list[float] = []

    async def no_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(llm.asyncio, "sleep", no_sleep)

    def install(handler):
        monkeypatch.setattr(llm, "_async_client", lambda: httpx.AsyncClient(
            base_url=gemini.GEMINI_BASE_URL, transport=httpx.MockTransport(handler)))
        return sleeps

    return install


async def stream_all(system="S", messages=None) -> list[str]:
    return [d async for d in llm.stream_generate(system, messages or [llm.ChatMessage("user", "q")])]


def test_stream_yields_text_deltas_and_skips_thoughts(gemini_stream) -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=sse_body(
            text_payload("hmm", thought=True), text_payload("It began "), text_payload("in 1789 [p. 2].", finish="STOP")))

    gemini_stream(handler)
    assert asyncio.run(stream_all()) == ["It began ", "in 1789 [p. 2]."]
    assert seen[0].url.path.endswith(":streamGenerateContent") and seen[0].url.params["alt"] == "sse"


def test_stream_retries_overload_before_first_text(gemini_stream) -> None:
    responses = iter([httpx.Response(503, json={"error": {"message": "high demand"}}),
                      httpx.Response(200, content=sse_body(text_payload("ok", finish="STOP")))])
    sleeps = gemini_stream(lambda r: next(responses))
    assert asyncio.run(stream_all()) == ["ok"]
    assert len(sleeps) == 1


@pytest.mark.parametrize("payloads", [[{"promptFeedback": {"blockReason": "SAFETY"}}], [text_payload("", finish="SAFETY")]])
def test_stream_without_text_is_an_error(gemini_stream, payloads) -> None:
    gemini_stream(lambda r: httpx.Response(200, content=sse_body(*payloads)))
    with pytest.raises(LLMError, match="declined"):
        asyncio.run(stream_all())


def test_stream_rejected_request_is_safe(gemini_stream) -> None:
    gemini_stream(lambda r: httpx.Response(400, json={"error": {"message": "API key not valid"}}))
    with pytest.raises(LLMError) as exc_info:
        asyncio.run(stream_all())
    assert "API key" not in exc_info.value.message


# --- chat turn ------------------------------------------------------------

def make_turn(conversation_id=None) -> chat.ChatTurn:
    excerpt = RetrievedChunk(uuid.uuid4(), DOC, "The Bastille fell in 1789.", 2, 2, 0, 0.8)
    return chat.ChatTurn(
        user_id=USER, document=SimpleNamespace(id=DOC, title="History"), conversation_id=conversation_id,
        question="When?", excerpts=[excerpt], messages=[llm.ChatMessage("user", "prompt")],
    )


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Record what the chat service saves instead of using a database."""
    saved: dict = {"turns": [], "answers": []}

    def start_turn(db, user_id, document_id, conversation_id, question):
        saved["turns"].append((user_id, document_id, conversation_id, question))
        return conversation_id or CONV, 41

    def save_answer(db, conversation_id, content, sources):
        saved["answers"].append((conversation_id, content, sources))
        return 42

    class NullSession:
        def __enter__(self):
            return None

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(chat.conversations, "start_turn", start_turn)
    monkeypatch.setattr(chat.conversations, "save_assistant_message", save_answer)
    monkeypatch.setattr(chat, "get_sessionmaker", lambda: NullSession)
    return saved


def fake_llm(monkeypatch: pytest.MonkeyPatch, deltas: list[str], fail_after: int | None = None) -> dict:
    state = {"closed": False}

    async def generate(system, messages):
        try:
            for i, text in enumerate(deltas):
                if fail_after is not None and i == fail_after:
                    raise LLMError("The answer was interrupted. Please try again.")
                yield text
        finally:
            state["closed"] = True

    monkeypatch.setattr(chat, "stream_generate", generate)
    return state


def test_full_turn_streams_tokens_then_saves_answer_with_sources(monkeypatch, store) -> None:
    fake_llm(monkeypatch, ["It began ", "in 1789 ", "[p. 2]."])

    async def run():
        return await collect(await chat.open_stream(None, make_turn()))

    events = asyncio.run(run())

    assert [name for name, _ in events] == ["meta", "token", "token", "token", "done"]
    assert events[0][1] == {"conversation_id": str(CONV), "user_message_id": 41}
    assert "".join(data["text"] for name, data in events if name == "token") == "It began in 1789 [p. 2]."
    assert events[-1][1] == {"message_id": 42, "sources": [{"page": 2, "similarity": 0.8}]}
    assert store["turns"] == [(USER, DOC, None, "When?")]
    assert store["answers"] == [(CONV, "It began in 1789 [p. 2].", [{"page": 2, "similarity": 0.8}])]


def test_failure_before_first_token_saves_nothing(monkeypatch, store) -> None:
    fake_llm(monkeypatch, ["never"], fail_after=0)
    with pytest.raises(LLMError):
        asyncio.run(chat.open_stream(None, make_turn()))
    assert store == {"turns": [], "answers": []}


def test_failure_mid_answer_sends_error_and_saves_partial(monkeypatch, store) -> None:
    fake_llm(monkeypatch, ["Partial ", "answer", "never sent"], fail_after=2)

    async def run():
        return await collect(await chat.open_stream(None, make_turn(conversation_id=CONV)))

    events = asyncio.run(run())

    assert [name for name, _ in events] == ["meta", "token", "token", "error"]
    assert events[-1][1] == {"detail": "The answer was interrupted. Please try again.", "message_id": 42}
    assert store["turns"][0][2] == CONV  # existing conversation reused
    assert store["answers"] == [(CONV, "Partial answer" + chat.INTERRUPTED_NOTE, [])]


def test_client_disconnect_stops_generation_and_saves_partial(monkeypatch, store) -> None:
    state = fake_llm(monkeypatch, ["One ", "two ", "three ", "four"])

    async def run():
        stream = await chat.open_stream(None, make_turn())
        received = [await anext(stream) for _ in range(3)]  # meta, "One ", "two "
        await stream.aclose()  # what EventStreamResponse does when the client goes away
        return received

    assert len(asyncio.run(run())) == 3
    assert state["closed"], "LLM stream must be closed"
    assert store["answers"] == [(CONV, "One two" + chat.INTERRUPTED_NOTE, [])]


# --- conversation helpers -------------------------------------------------

def test_conversation_title_from_question() -> None:
    assert conversations.title_from_question("  What   is\nRAG? ") == "What is RAG?"
    long = conversations.title_from_question("word " * 40)
    assert len(long) == conversations.TITLE_MAX_CHARS and long.endswith("…")


def test_conversation_of_another_document_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(chat.document_service, "get_owned_document", lambda db, u, d: SimpleNamespace(id=DOC, title="T"))
    other = SimpleNamespace(id=CONV, document_id=uuid.uuid4())
    monkeypatch.setattr(chat.conversations, "get_owned_conversation", lambda db, u, c: other)
    monkeypatch.setattr(chat, "search_owned_document", lambda *a: pytest.fail("must not search"))
    with pytest.raises(conversations.ConversationNotFoundError):
        chat.prepare_turn(None, USER, DOC, CONV, "q")


# --- endpoint -------------------------------------------------------------

@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=USER, email="a@example.com")
    app.dependency_overrides[get_db] = lambda: None
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def test_chat_endpoint_streams_events(client, monkeypatch, store) -> None:
    calls = []

    def prepare(db, user_id, document_id, conversation_id, message):
        calls.append((user_id, document_id, conversation_id, message))
        return make_turn()

    monkeypatch.setattr(chat, "prepare_turn", prepare)
    fake_llm(monkeypatch, ["Hello [p. 2]."])

    response = client.post("/chat", json={"document_id": str(DOC), "message": " Hi? "})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert calls == [(USER, DOC, None, "Hi?")]
    assert [name for name, _ in parse_events(response.text)] == ["meta", "token", "done"]


def test_chat_endpoint_model_failure_before_streaming_is_502(client, monkeypatch, store) -> None:
    monkeypatch.setattr(chat, "prepare_turn", lambda *a: make_turn())
    fake_llm(monkeypatch, ["x"], fail_after=0)
    response = client.post("/chat", json={"document_id": str(DOC), "message": "Hi"})
    assert response.status_code == 502
    assert response.json() == {"detail": "The answer was interrupted. Please try again."}


@pytest.mark.parametrize("body", [{"message": "q"}, {"document_id": str(DOC), "message": "  "}, {"document_id": "x", "message": "q"}])
def test_chat_endpoint_validates_input(client, monkeypatch, body) -> None:
    monkeypatch.setattr(chat, "prepare_turn", lambda *a: pytest.fail("must not run"))
    assert client.post("/chat", json=body).status_code == 422


def test_client_gone_before_first_token_saves_nothing(monkeypatch, store) -> None:
    """Stop pressed while 'Thinking': the frontend gives the question back,
    so the backend must not save it either."""
    state = fake_llm(monkeypatch, ["Too ", "late"])

    async def gone() -> bool:
        return True

    with pytest.raises(chat.ClientGoneError):
        asyncio.run(chat.open_stream(None, make_turn(), gone))
    assert store == {"turns": [], "answers": []}
    assert state["closed"], "LLM stream must be closed"
