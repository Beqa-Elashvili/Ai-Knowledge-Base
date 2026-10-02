"""End-to-end check of the documents API against real Supabase Auth,
Storage and PostgreSQL.

Creates two throwaway confirmed users, exercises the API in-process, and
always deletes the users, their documents and stored files afterwards.

Usage (from backend/, venv active):
    python -m scripts.verify_documents_api
"""

import json
import secrets
import sys
import uuid

import pymupdf
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import get_settings
from app.database import get_engine
from app.main import app
from app.supabase_client import get_supabase
from scripts.dev_users import delete_user, ensure_confirmed_user, sign_in


class Checker:
    def __init__(self) -> None:
        self.failures = 0

    def check(self, label: str, condition: bool, detail: object = "") -> None:
        print(f"  [{'PASS' if condition else 'FAIL'}] {label}" + (f"  ->  {detail}" if detail != "" else ""))
        if not condition:
            self.failures += 1


def make_pdf(pages: int = 1, text_on_pages: bool = True, **save_kwargs) -> bytes:
    doc = pymupdf.open()
    for number in range(1, pages + 1):
        page = doc.new_page()
        if text_on_pages:
            page.insert_text((72, 72), f"Verification document, page {number}")
    data = doc.tobytes(**save_kwargs)
    doc.close()
    return data


TOPIC_PAGES = [
    "Photosynthesis is the process by which green plants use sunlight, water and carbon dioxide to make glucose and oxygen inside their chloroplasts. ",
    "The French Revolution began in 1789 when the people of Paris stormed the Bastille, ending the absolute monarchy of Louis XVI. ",
    "A neural network learns by backpropagation: the error of its prediction flows backwards through the layers to adjust every weight. ",
]


def make_topic_pdf() -> bytes:
    """One topic per page, each page longer than a chunk, so every topic
    lands in its own chunk(s) with a known page number."""
    doc = pymupdf.open()
    for sentence in TOPIC_PAGES:
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(50, 50, 545, 800), sentence * 14, fontsize=9)
    data = doc.tobytes()
    doc.close()
    return data


def stored_files(user_id: str) -> list[str]:
    return [f["name"] for f in get_supabase().storage.from_(get_settings().storage_bucket).list(user_id)]


def main() -> int:
    c = Checker()
    client = TestClient(app, raise_server_exceptions=False)
    password = secrets.token_urlsafe(16)
    users: dict[str, str] = {}

    try:
        auth: dict[str, dict[str, str]] = {}
        for name in ("a", "b"):
            email = f"verify-{name}-{uuid.uuid4().hex[:8]}@example.com"
            users[name] = ensure_confirmed_user(email, password)
            auth[name] = {"Authorization": f"Bearer {sign_in(email, password)}"}

        print("\nAuthentication:")
        c.check("no token -> 401", client.get("/documents").status_code == 401)
        c.check("garbage token -> 401", client.get("/documents", headers={"Authorization": "Bearer x.y.z"}).status_code == 401)
        me = client.get("/auth/me", headers=auth["a"])
        c.check("/auth/me returns the token's user", me.status_code == 200 and me.json()["id"] == users["a"])

        print("\nUpload validation:")
        pdf = make_pdf(pages=3)
        encrypted = make_pdf(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o")
        cases = [
            ("wrong extension", ("notes.txt", pdf, "application/pdf"), 415),
            ("wrong MIME type", ("notes.pdf", pdf, "text/plain"), 415),
            ("renamed text file", ("fake.pdf", b"not really a pdf", "application/pdf"), 415),
            ("empty file", ("empty.pdf", b"", "application/pdf"), 400),
            ("over 20 MB", ("big.pdf", b"%PDF-1.7\n" + b"0" * get_settings().max_upload_size_bytes, "application/pdf"), 413),
            ("damaged PDF", ("broken.pdf", b"%PDF-1.7 garbage garbage", "application/pdf"), 422),
            ("password-protected PDF", ("locked.pdf", encrypted, "application/pdf"), 422),
            ("scanned PDF without text", ("scan.pdf", make_pdf(pages=2, text_on_pages=False), "application/pdf"), 422),
        ]
        for label, file_tuple, expected in cases:
            r = client.post("/documents/upload", files={"file": file_tuple}, headers=auth["a"])
            c.check(f"{label} -> {expected}", r.status_code == expected, f"{r.status_code} {r.json().get('detail')}")
        c.check("rejected uploads stored nothing", stored_files(users["a"]) == [])

        print("\nUpload:")
        r = client.post(
            "/documents/upload",
            files={"file": ("Machine_Learning-Fundamentals.pdf", pdf, "application/pdf")},
            headers=auth["a"],
        )
        c.check("valid PDF -> 201", r.status_code == 201, r.status_code)
        doc = r.json()
        doc_id = doc["id"]
        c.check("title derived from filename", doc["title"] == "Machine Learning Fundamentals", doc["title"])
        c.check("status is ready", doc["status"] == "ready", doc["status"])
        c.check("page_count from extraction", doc["page_count"] == 3, doc["page_count"])
        c.check("storage_path not exposed", "storage_path" not in doc)
        c.check("file stored at {user_id}/{document_id}.pdf", stored_files(users["a"]) == [f"{doc_id}.pdf"])
        with get_engine().connect() as conn:
            row = conn.execute(text("select user_id::text, storage_path from documents where id = :id"), {"id": doc_id}).one()
        c.check("DB row owned by user A", row[0] == users["a"] and row[1] == f"{users['a']}/{doc_id}.pdf")
        with get_engine().connect() as conn:
            chunk_rows = conn.execute(
                text(
                    "select chunk_index, page_number, page_end, content, vector_dims(embedding), vector_norm(embedding) "
                    "from document_chunks where document_id = :id order by chunk_index"
                ),
                {"id": doc_id},
            ).all()
        c.check("chunks saved with the document", len(chunk_rows) >= 1, f"{len(chunk_rows)} chunk(s)")
        c.check("chunk indexes are 0..n-1", [r[0] for r in chunk_rows] == list(range(len(chunk_rows))))
        c.check(
            "chunk page range covers pages 1-3 of the PDF",
            (chunk_rows[0][1], chunk_rows[-1][2]) == (1, 3) and all(1 <= r[1] <= r[2] <= 3 for r in chunk_rows),
            [(r[1], r[2]) for r in chunk_rows],
        )
        c.check("chunk text comes from the PDF", "page 2" in " ".join(r[3] for r in chunk_rows))
        c.check("every chunk has a 1536-d embedding", all(r[4] == 1536 for r in chunk_rows), [r[4] for r in chunk_rows])
        c.check("embeddings are normalized", all(abs(r[5] - 1) < 1e-3 for r in chunk_rows), [round(r[5], 4) for r in chunk_rows])

        r = client.post(
            "/documents/upload",
            files={"file": ("x.pdf", pdf, "application/pdf")},
            data={"title": "  Custom title  "},
            headers=auth["a"],
        )
        c.check("explicit title is trimmed and used", r.status_code == 201 and r.json()["title"] == "Custom title")
        second_id = r.json()["id"]

        print("\nOwnership:")
        listing = client.get("/documents", headers=auth["a"]).json()
        c.check("user A lists 2 documents, newest first", [d["id"] for d in listing] == [second_id, doc_id])
        c.check("user B lists none", client.get("/documents", headers=auth["b"]).json() == [])
        c.check("user B GET A's document -> 404", client.get(f"/documents/{doc_id}", headers=auth["b"]).status_code == 404)
        c.check("user B DELETE A's document -> 404", client.delete(f"/documents/{doc_id}", headers=auth["b"]).status_code == 404)
        c.check("A's document survived B's delete attempt", client.get(f"/documents/{doc_id}", headers=auth["a"]).status_code == 200)
        c.check("unknown id -> 404", client.get(f"/documents/{uuid.uuid4()}", headers=auth["a"]).status_code == 404)

        print("\nVector search:")
        r = client.post("/documents/upload", files={"file": ("topics.pdf", make_topic_pdf(), "application/pdf")}, headers=auth["a"])
        topics_id = r.json()["id"]
        c.check("topic PDF uploaded and ready", r.status_code == 201 and r.json()["status"] == "ready")
        expected_pages = [
            ("How do plants turn sunlight into food?", 1),
            ("როდის დაიწყო საფრანგეთის რევოლუცია?", 2),  # Georgian question, English document
            ("How are the weights of a model updated during training?", 3),
        ]
        for question, page in expected_pages:
            r = client.post(f"/documents/{topics_id}/search", json={"question": question, "top_k": 3}, headers=auth["a"])
            results = r.json().get("results", []) if r.status_code == 200 else []
            c.check(
                f"{question[:40]!r} -> page {page} first",
                bool(results) and results[0]["page_number"] == page,
                [(x["page_number"], round(x["similarity"], 3)) for x in results] or r.status_code,
            )
        similarities = [x["similarity"] for x in results]
        c.check("results are sorted best first", similarities == sorted(similarities, reverse=True))
        r = client.post(f"/documents/{doc_id}/search", json={"question": "photosynthesis in plants", "top_k": 50}, headers=auth["a"])
        other = r.json().get("results", []) if r.status_code == 200 else []
        c.check(
            "searching another document never returns this one's chunks",
            bool(other) and all("Verification document" in x["content"] for x in other),
            [x["content"][:30] for x in other] or r.status_code,
        )
        c.check(
            "user B searching A's document -> 404",
            client.post(f"/documents/{topics_id}/search", json={"question": "q"}, headers=auth["b"]).status_code == 404,
        )
        c.check(
            "empty question -> 422",
            client.post(f"/documents/{topics_id}/search", json={"question": "  "}, headers=auth["a"]).status_code == 422,
        )

        print("\nRAG answers:")

        def ask(question: str, who: str = "a"):
            r = client.post(f"/documents/{topics_id}/ask", json={"question": question}, headers=auth[who])
            return r.status_code, (r.json() if r.status_code == 200 else {"answer": "", "sources": [], "detail": r.json().get("detail")})

        code, body = ask("When did the French Revolution begin?")
        c.check("answer comes from the document", code == 200 and "1789" in body["answer"], body.get("answer") or body)
        c.check("sources = the page it came from", [s["page"] for s in body["sources"]] == [2], body["sources"])
        code, body = ask("როგორ ამზადებენ მცენარეები საკვებს?")
        c.check(
            "Georgian question -> Georgian answer from page 1",
            code == 200 and any("ა" <= ch <= "ჿ" for ch in body["answer"]) and [s["page"] for s in body["sources"]] == [1],
            (body.get("answer", "")[:80], body["sources"]),
        )
        code, body = ask("Who won the 2018 FIFA World Cup?")
        c.check("question not covered by the document -> no sources", code == 200 and body["sources"] == [], (body.get("answer", "")[:80], body["sources"]))
        c.check("user B asking about A's document -> 404", ask("When?", who="b")[0] == 404)

        print("\nStreaming chat:")

        def chat(message: str, who: str = "a", **extra):
            r = client.post("/chat", json={"document_id": topics_id, "message": message, **extra}, headers=auth[who])
            if r.status_code != 200:
                return r.status_code, []
            blocks = [dict(line.split(": ", 1) for line in b.split("\n")) for b in r.text.strip().split("\n\n")]
            return r.status_code, [(b["event"], json.loads(b["data"])) for b in blocks]

        code, events = chat("When did the French Revolution begin?")
        names = [name for name, _ in events]
        c.check("events: meta, token..., done", code == 200 and names[0] == "meta" and names[-1] == "done" and "token" in names, names[:3] + ["..."] + names[-1:])
        answer = "".join(data["text"] for name, data in events if name == "token")
        conv_id = events[0][1]["conversation_id"] if events else None
        c.check("streamed answer is grounded", "1789" in answer, answer[:80])
        c.check("done carries page 2 as source", events and [s["page"] for s in events[-1][1]["sources"]] == [2], events[-1][1] if events else None)
        with get_engine().connect() as conn:
            rows = conn.execute(
                text("select m.role, m.content, m.sources, cv.title, cv.user_id::text, cv.document_id::text "
                     "from messages m join conversations cv on cv.id = m.conversation_id "
                     "where cv.id = :id order by m.id"), {"id": conv_id}).all()
        c.check("conversation saved for user A and this document", bool(rows) and rows[0][4] == users["a"] and rows[0][5] == topics_id)
        c.check("conversation titled from the first question", bool(rows) and rows[0][3] == "When did the French Revolution begin?")
        c.check("user + assistant messages saved", [r[0] for r in rows] == ["user", "assistant"])
        c.check("saved answer == streamed answer, with sources", len(rows) == 2 and rows[1][1] == answer and rows[1][2] == events[-1][1]["sources"])
        code, events = chat("And what about photosynthesis?", conversation_id=conv_id)
        with get_engine().connect() as conn:
            count = conn.execute(text("select count(*) from messages where conversation_id = :id"), {"id": conv_id}).scalar_one()
        c.check("follow-up continues the same conversation", code == 200 and events[0][1]["conversation_id"] == conv_id and count == 4)
        c.check("user B using A's conversation -> 404", chat("q", who="b", conversation_id=conv_id)[0] == 404)
        r = client.post("/chat", json={"document_id": doc_id, "conversation_id": conv_id, "message": "q"}, headers=auth["a"])
        c.check("conversation used with another document -> 404", r.status_code == 404)
        c.check("unknown conversation -> 404", chat("q", conversation_id=str(uuid.uuid4()))[0] == 404)
        client.delete(f"/documents/{topics_id}", headers=auth["a"])

        print("\nDelete:")
        c.check("user A DELETE -> 204", client.delete(f"/documents/{doc_id}", headers=auth["a"]).status_code == 204)
        c.check("deleted document -> 404", client.get(f"/documents/{doc_id}", headers=auth["a"]).status_code == 404)
        with get_engine().connect() as conn:
            left_chunks = conn.execute(
                text("select count(*) from document_chunks where document_id = :id"), {"id": doc_id}
            ).scalar_one()
        c.check("its chunks were deleted (cascade)", left_chunks == 0)
        c.check("stored file removed", stored_files(users["a"]) == [f"{second_id}.pdf"], stored_files(users["a"]))
        c.check("second delete -> 404", client.delete(f"/documents/{doc_id}", headers=auth["a"]).status_code == 404)
    finally:
        print("\nCleanup:")
        bucket = get_supabase().storage.from_(get_settings().storage_bucket)
        for user_id in users.values():
            files = stored_files(user_id)
            if files:
                bucket.remove([f"{user_id}/{name}" for name in files])
            delete_user(user_id)  # cascades to documents/conversations/messages
        with get_engine().connect() as conn:
            left = conn.execute(
                text("select count(*) from documents where user_id::text = any(:ids)"), {"ids": list(users.values())}
            ).scalar_one()
        c.check("test users, documents and files removed", left == 0 and all(stored_files(u) == [] for u in users.values()))

    print(f"\n{'All checks passed.' if c.failures == 0 else f'{c.failures} check(s) FAILED.'}")
    return 1 if c.failures else 0


if __name__ == "__main__":
    sys.exit(main())
