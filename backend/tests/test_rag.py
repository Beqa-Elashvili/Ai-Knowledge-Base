import json
import uuid
from types import SimpleNamespace

import httpx
import pytest

from app.services import gemini, llm, rag
from app.services.llm import LLMError, LLMResult
from app.services.vector_search import RetrievedChunk

USER = uuid.UUID("11111111-1111-1111-1111-111111111111")
DOC = uuid.UUID("22222222-2222-2222-2222-222222222222")


def chunk(index: int, page: int, similarity: float, content: str | None = None, page_end: int | None = None):
    return RetrievedChunk(
        id=uuid.uuid4(), document_id=DOC, content=content or f"Text of chunk {index}.",
        page_number=page, page_end=page_end or page, chunk_index=index, similarity=similarity,
    )


# --- context construction -------------------------------------------------

def test_context_labels_pages_and_uses_reading_order() -> None:
    chunks = [chunk(7, 14, 0.9), chunk(2, 3, 0.8, page_end=4)]  # best first
    context, used = rag.build_context(chunks, max_chars=10_000)

    assert [c.chunk_index for c in used] == [2, 7]
    assert context == "[Excerpt 1 | pp. 3-4]\nText of chunk 2.\n\n[Excerpt 2 | p. 14]\nText of chunk 7."


def test_context_respects_budget_but_keeps_best_chunk() -> None:
    best, second, third = chunk(5, 9, 0.9, "a" * 600), chunk(1, 2, 0.8, "b" * 600), chunk(3, 4, 0.7, "c" * 300)
    _, used = rag.build_context([best, second, third], max_chars=1000)
    assert [c.chunk_index for c in used] == [3, 5]  # second skipped: over budget; third fits

    context, used = rag.build_context([chunk(0, 1, 0.9, "z" * 5000)], max_chars=1000)
    assert len(used) == 1 and context.count("z") == 1000


def test_prompt_contains_rules_title_excerpts_and_question() -> None:
    [message] = rag.build_messages("ML Book", "[Excerpt 1 | p. 2]\nBody", "What is ML?")
    assert message.role == "user"
    assert 'Document: "ML Book"' in message.content
    assert "<excerpts>\n[Excerpt 1 | p. 2]\nBody\n</excerpts>" in message.content
    assert message.content.endswith("Question: What is ML?")
    assert "ONLY" in rag.SYSTEM_PROMPT and "could not find" in rag.SYSTEM_PROMPT
    assert "No relevant excerpts" in rag.build_messages("T", "", "q")[0].content


# --- citations and sources ------------------------------------------------

@pytest.mark.parametrize(
    ("answer", "pages"),
    [
        ("It began in 1789 [p. 2].", {2}),
        ("See [pp. 14-15] and [p. 3, 7].", {3, 7, 14, 15}),
        ("[p. 3; p. 9] [P.4] [page 5] [გვ. 6]", {3, 4, 5, 6, 9}),
        ("No citation here, 1789 [1] [p. 1-9999]", set()),
    ],
)
def test_cited_pages(answer: str, pages: set[int]) -> None:
    assert rag.cited_pages(answer) == pages


def test_sources_are_cited_and_retrieved_pages_only_deduplicated() -> None:
    chunks = [chunk(0, 14, 0.89, page_end=15), chunk(1, 15, 0.70), chunk(2, 17, 0.84), chunk(3, 30, 0.60)]
    answer = "A [p. 15]. B [p. 17]. C [p. 15]. Made-up [p. 99]."

    sources = rag.extract_sources(answer, chunks)

    # 15 keeps its best similarity; 30 was retrieved but not cited; 99 never retrieved
    assert [(s.page, s.similarity) for s in sources] == [(15, 0.89), (17, 0.84)]


def test_answer_without_citations_has_no_sources() -> None:
    assert rag.extract_sources("I could not find this in the document.", [chunk(0, 1, 0.5)]) == []


# --- pipeline -------------------------------------------------------------

def test_answer_question_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    document = SimpleNamespace(id=DOC, title="History", status="ready")
    monkeypatch.setattr(rag.document_service, "get_owned_document", lambda db, u, d: document)
    monkeypatch.setattr(rag, "search_owned_document", lambda db, doc, q: [chunk(4, 2, 0.8, "The Bastille fell in 1789.")])
    prompts = []

    def fake_generate(system, messages):
        prompts.append((system, messages))
        return LLMResult(text="It began in 1789 [p. 2].", model="m", finish_reason="STOP")

    monkeypatch.setattr(rag, "generate", fake_generate)
    result = rag.answer_question(None, USER, DOC, "  When did it start?  ")

    assert result.answer == "It began in 1789 [p. 2]."
    assert [(s.page, s.similarity) for s in result.sources] == [(2, 0.8)]
    assert result.excerpts_used == 1
    system, [message] = prompts[0]
    assert system == rag.SYSTEM_PROMPT
    assert "[Excerpt 1 | p. 2]\nThe Bastille fell in 1789." in message.content
    assert message.content.endswith("Question: When did it start?")


# --- LLM response handling ------------------------------------------------

@pytest.fixture
def gemini_llm(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(gemini.time, "sleep", lambda s: None)

    def install(handler):
        monkeypatch.setattr(llm, "_client", httpx.Client(base_url=gemini.GEMINI_BASE_URL, transport=httpx.MockTransport(handler)))

    return install


def test_llm_request_and_answer(gemini_llm) -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={
            "candidates": [{"finishReason": "STOP", "content": {"parts": [
                {"text": "thinking...", "thought": True}, {"text": " Answer [p. 1]. "}]}}],
            "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 8},
        })

    gemini_llm(handler)
    result = llm.generate("SYS", [llm.ChatMessage("user", "hi"), llm.ChatMessage("assistant", "hello")])

    body = seen[0]
    assert body["systemInstruction"]["parts"][0]["text"] == "SYS"
    assert [c["role"] for c in body["contents"]] == ["user", "model"]
    assert body["generationConfig"]["temperature"] == 0.2
    assert (result.text, result.input_tokens, result.output_tokens) == ("Answer [p. 1].", 120, 8)


@pytest.mark.parametrize(
    "payload",
    [
        {"promptFeedback": {"blockReason": "SAFETY"}},
        {"candidates": [{"finishReason": "SAFETY", "content": {"parts": []}}]},
    ],
)
def test_llm_blocked_answer_is_a_clear_error(gemini_llm, payload) -> None:
    gemini_llm(lambda r: httpx.Response(200, json=payload))
    with pytest.raises(LLMError, match="declined"):
        llm.generate("SYS", [llm.ChatMessage("user", "q")])


def test_llm_overload_is_retried_then_reported(gemini_llm) -> None:
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503, json={"error": {"message": "high demand"}})

    gemini_llm(handler)
    with pytest.raises(LLMError, match="busy") as exc_info:
        llm.generate("SYS", [llm.ChatMessage("user", "q")])
    assert len(calls) == gemini.MAX_ATTEMPTS
    assert exc_info.value.status_code == 502


def test_llm_rejected_request_hides_provider_message(gemini_llm) -> None:
    gemini_llm(lambda r: httpx.Response(400, json={"error": {"message": "API key not valid"}}))
    with pytest.raises(LLMError) as exc_info:
        llm.generate("SYS", [llm.ChatMessage("user", "q")])
    assert "API key" not in exc_info.value.message


def test_page_markers_show_where_pages_begin() -> None:
    content = "End of page one.\n\nStart of page two. Still two.\n\nPage three."
    c = RetrievedChunk(uuid.uuid4(), DOC, content, 1, 3, 0, 0.9, page_breaks=[[18, 2], [48, 3]])
    assert rag.with_page_markers(c) == (
        "End of page one.\n[Page 2 begins here]\nStart of page two. Still two.\n[Page 3 begins here]\nPage three."
    )
    context, _ = rag.build_context([c], max_chars=10_000)
    assert context.startswith("[Excerpt 1 | pp. 1-3]\nEnd of page one.\n[Page 2 begins here]")
    assert rag.with_page_markers(chunk(0, 5, 0.5, "Single page.")) == "Single page."
