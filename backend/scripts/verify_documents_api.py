"""End-to-end check of the documents API against real Supabase Auth,
Storage and PostgreSQL.

Creates two throwaway confirmed users, exercises the API in-process, and
always deletes the users, their documents and stored files afterwards.

Usage (from backend/, venv active):
    python -m scripts.verify_documents_api
"""

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


def make_pdf() -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Verification document")
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
        pdf = make_pdf()
        cases = [
            ("wrong extension", ("notes.txt", pdf, "application/pdf"), 415),
            ("wrong MIME type", ("notes.pdf", pdf, "text/plain"), 415),
            ("renamed text file", ("fake.pdf", b"not really a pdf", "application/pdf"), 415),
            ("empty file", ("empty.pdf", b"", "application/pdf"), 400),
            ("over 20 MB", ("big.pdf", b"%PDF-1.7\n" + b"0" * get_settings().max_upload_size_bytes, "application/pdf"), 413),
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
        c.check("status is processing", doc["status"] == "processing")
        c.check("storage_path not exposed", "storage_path" not in doc)
        c.check("file stored at {user_id}/{document_id}.pdf", stored_files(users["a"]) == [f"{doc_id}.pdf"])
        with get_engine().connect() as conn:
            row = conn.execute(text("select user_id::text, storage_path from documents where id = :id"), {"id": doc_id}).one()
        c.check("DB row owned by user A", row[0] == users["a"] and row[1] == f"{users['a']}/{doc_id}.pdf")

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

        print("\nDelete:")
        c.check("user A DELETE -> 204", client.delete(f"/documents/{doc_id}", headers=auth["a"]).status_code == 204)
        c.check("deleted document -> 404", client.get(f"/documents/{doc_id}", headers=auth["a"]).status_code == 404)
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
