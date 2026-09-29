"""End-to-end check of the database schema against the real Supabase DB.

Runs everything inside ONE transaction that is always rolled back, so it
leaves no data behind. Verifies:
  * match_document_chunks returns correct similarity and ordering
  * results never include chunks from another document
  * RLS isolates users when queried with the `authenticated` role
  * ON DELETE CASCADE and the conversation updated_at trigger

Usage (from backend/, venv active):
    python -m scripts.verify_schema
"""

import json
import sys
import uuid

from sqlalchemy import Connection, text

from app.database import get_engine

DIM = 1536


def vec(**components: float) -> str:
    """Build a pgvector literal with the given non-zero dimensions, e.g. vec(d0=1)."""
    values = [0.0] * DIM
    for key, value in components.items():
        values[int(key[1:])] = value
    return "[" + ",".join(str(v) for v in values) + "]"


class Checker:
    def __init__(self) -> None:
        self.failures = 0

    def check(self, label: str, condition: bool, detail: object = "") -> None:
        print(f"  [{'PASS' if condition else 'FAIL'}] {label}" + (f"  ->  {detail}" if detail != "" else ""))
        if not condition:
            self.failures += 1


def as_user(conn: Connection, user_id: uuid.UUID | None) -> None:
    """Switch the transaction to the `authenticated` role with a JWT for user_id."""
    if user_id is None:
        conn.execute(text("reset role"))
        return
    conn.execute(text("set local role authenticated"))
    conn.execute(
        text("select set_config('request.jwt.claims', :claims, true)"),
        {"claims": json.dumps({"sub": str(user_id), "role": "authenticated"})},
    )


def run(conn: Connection, c: Checker) -> None:
    user_a, user_b = uuid.uuid4(), uuid.uuid4()
    for user in (user_a, user_b):
        conn.execute(
            text("insert into auth.users (id, email, aud, role) values (:id, :email, 'authenticated', 'authenticated')"),
            {"id": user, "email": f"verify-{user}@example.test"},
        )

    doc_a = conn.execute(
        text("insert into documents (user_id, title, filename, page_count) values (:u, 'Doc A', 'a.pdf', 3) returning id"),
        {"u": user_a},
    ).scalar_one()
    doc_b = conn.execute(
        text("insert into documents (user_id, title, filename) values (:u, 'Doc B', 'b.pdf') returning id"),
        {"u": user_b},
    ).scalar_one()

    chunks = [
        (doc_a, "exact match", 1, 1, 0, vec(d0=1)),
        (doc_a, "partial match spanning pages", 2, 3, 1, vec(d0=0.8, d1=0.6)),
        (doc_a, "unrelated", 3, 3, 2, vec(d1=1)),
        (doc_b, "other user's identical chunk", 1, 1, 0, vec(d0=1)),
    ]
    for doc, content, page, page_end, idx, emb in chunks:
        conn.execute(
            text(
                "insert into document_chunks (document_id, content, page_number, page_end, chunk_index, embedding) "
                "values (:d, :c, :p, :pe, :i, cast(:e as extensions.vector))"
            ),
            {"d": doc, "c": content, "p": page, "pe": page_end, "i": idx, "e": emb},
        )

    rpc = text("select * from match_document_chunks(cast(:q as extensions.vector), :doc, :k)")
    query = vec(d0=1)

    print("\nVector search (service role):")
    rows = conn.execute(rpc, {"q": query, "doc": doc_a, "k": 5}).mappings().all()
    c.check("returns only Document A chunks", all(r["document_id"] == doc_a for r in rows), f"{len(rows)} rows")
    c.check("Document B's identical chunk excluded", all(r["content"] != "other user's identical chunk" for r in rows))
    sims = [round(r["similarity"], 4) for r in rows]
    c.check("similarities are 1.0, 0.8, 0.0 in order", sims == [1.0, 0.8, 0.0], sims)
    c.check("page range preserved", (rows[1]["page_number"], rows[1]["page_end"]) == (2, 3))
    top2 = conn.execute(rpc, {"q": query, "doc": doc_a, "k": 2}).all()
    c.check("match_count limits results", len(top2) == 2)
    thresholded = conn.execute(
        text("select * from match_document_chunks(cast(:q as extensions.vector), :doc, 5, 0.5)"),
        {"q": query, "doc": doc_a},
    ).all()
    c.check("min_similarity filters weak matches", len(thresholded) == 2)

    conv = conn.execute(
        text("insert into conversations (user_id, document_id, title) values (:u, :d, 'Test') returning id"),
        {"u": user_a, "d": doc_a},
    ).scalar_one()
    conn.execute(text("update conversations set updated_at = '2000-01-01' where id = :id"), {"id": conv})
    conn.execute(
        text("insert into messages (conversation_id, role, content, sources) values (:c, 'user', 'hi', null)"),
        {"c": conv},
    )
    bumped = conn.execute(text("select updated_at > '2001-01-01' from conversations where id = :id"), {"id": conv}).scalar_one()
    print("\nTrigger:")
    c.check("new message bumps conversations.updated_at", bumped)

    print("\nRow Level Security (authenticated role):")
    as_user(conn, user_b)
    c.check("user B cannot see user A's documents", conn.execute(text("select count(*) from documents where id = :d"), {"d": doc_a}).scalar_one() == 0)
    c.check("user B sees own document", conn.execute(text("select count(*) from documents")).scalar_one() == 1)
    c.check("user B cannot read user A's chunks", conn.execute(text("select count(*) from document_chunks where document_id = :d"), {"d": doc_a}).scalar_one() == 0)
    c.check("user B's RPC on Document A returns nothing", conn.execute(rpc, {"q": query, "doc": doc_a, "k": 5}).all() == [])
    c.check("user B cannot see user A's conversation", conn.execute(text("select count(*) from conversations")).scalar_one() == 0)
    c.check("user B cannot see user A's messages", conn.execute(text("select count(*) from messages")).scalar_one() == 0)
    conn.execute(text("savepoint before_forbidden_insert"))
    try:
        conn.execute(
            text("insert into conversations (user_id, document_id) values (:u, :d)"),
            {"u": user_b, "d": doc_a},
        )
        c.check("user B cannot open a conversation on user A's document", False)
    except Exception:
        conn.execute(text("rollback to savepoint before_forbidden_insert"))
        c.check("user B cannot open a conversation on user A's document", True)
    as_user(conn, user_a)
    c.check("user A sees own chunks", conn.execute(text("select count(*) from document_chunks")).scalar_one() == 3)
    c.check("user A's RPC works under RLS", len(conn.execute(rpc, {"q": query, "doc": doc_a, "k": 5}).all()) == 3)
    as_user(conn, None)

    print("\nCascade delete:")
    conn.execute(text("delete from documents where id = :d"), {"d": doc_a})
    remaining = conn.execute(
        text(
            "select (select count(*) from document_chunks where document_id = :d), "
            "(select count(*) from conversations where id = :c), "
            "(select count(*) from messages where conversation_id = :c)"
        ),
        {"d": doc_a, "c": conv},
    ).one()
    c.check("chunks, conversations and messages removed", tuple(remaining) == (0, 0, 0), tuple(remaining))


def main() -> int:
    checker = Checker()
    conn = get_engine().connect()
    trans = conn.begin()
    try:
        run(conn, checker)
    finally:
        trans.rollback()  # never leave test data behind
        conn.close()
    print(f"\n{'All checks passed.' if checker.failures == 0 else f'{checker.failures} check(s) FAILED.'} (transaction rolled back)")
    return 1 if checker.failures else 0


if __name__ == "__main__":
    sys.exit(main())
