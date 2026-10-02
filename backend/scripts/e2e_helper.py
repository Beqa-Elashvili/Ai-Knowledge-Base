"""Backend side of the end-to-end test (frontend/e2e/full-flow.mjs).

Talks to the real Supabase project with the service key, so it is a local
dev tool only. Every command prints one JSON line.

Usage (from backend/, venv active):
    python -m scripts.e2e_helper signup            new UNCONFIRMED user + its signup confirmation
                                                   token (admin generate_link: no email is sent)
    python -m scripts.e2e_helper pdf <path>        write a 12-page PDF, one distinct fact per page
    python -m scripts.e2e_helper check <user_id>   DB + Storage state of the user
    python -m scripts.e2e_helper delete <user_id>  remove the user's documents, files and the user
"""

import json
import random
import secrets
import sys
import uuid

from sqlalchemy import text

from app.config import get_settings
from app.database import get_engine
from app.supabase_client import get_supabase
from scripts.dev_users import delete_user

# One topic per page; the e2e test asks about these facts and expects the
# answer to cite their page.
TOPICS = [
    ("Kazreti copper mine", "The Kazreti copper mine produced 41,000 tonnes of ore in 1987."),
    ("Silk Road caravans", "Silk Road caravans carried saffron through Tbilisi every autumn."),
    ("Gelati Academy", "The Gelati Academy trained 300 scholars in astronomy."),
    ("Enguri Dam", "The Enguri Dam is 271 metres high, one of the tallest arch dams in the world."),
    ("Kakheti wine", "Kakheti winemakers ferment wine in clay qvevri buried underground."),
    ("Mtskheta cathedral", "Svetitskhoveli Cathedral in Mtskheta was rebuilt in the 11th century by the architect Arsukisdze."),
    ("Tbilisi sulphur baths", "The Abanotubani sulphur baths in Tbilisi are fed by hot springs at about 40 degrees Celsius."),
    ("Vardzia cave city", "The Vardzia cave monastery was carved into the Erusheti mountain in the 12th century under Queen Tamar."),
    ("Batumi botanical garden", "The Batumi Botanical Garden hosts more than 5,000 plant species."),
    ("Ushguli villages", "Ushguli, at about 2,100 metres, is one of the highest permanently inhabited settlements in Europe."),
    ("Rikoti tunnel", "The Rikoti road tunnel was completed in 1984 and is 1.7 kilometres long."),
    ("Georgian alphabet", "The Georgian Mkhedruli alphabet has 33 letters in modern use."),
]


def signup() -> None:
    email, password = f"e2e-{uuid.uuid4().hex[:8]}@example.com", secrets.token_urlsafe(14)
    link = get_supabase().auth.admin.generate_link({"type": "signup", "email": email, "password": password})
    print(json.dumps({
        "id": link.user.id,
        "email": email,
        "password": password,
        "token_hash": link.properties.hashed_token,
        "confirmed": link.user.email_confirmed_at is not None,
    }))


def pdf(path: str) -> None:
    import pymupdf

    random.seed(7)
    doc = pymupdf.open()
    for number, (topic, fact) in enumerate(TOPICS, start=1):
        filler = " ".join(
            f"Chapter {number} continues describing {topic}, with observation {random.randint(100, 999)} recorded by the survey team."
            for _ in range(14)
        )
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(50, 50, 545, 800), f"Chapter {number}: {topic}. {fact} {filler}", fontsize=9)
    doc.save(path)
    print(json.dumps({"pages": len(TOPICS)}))


def check(user_id: str) -> None:
    with get_engine().connect() as db:
        row = db.execute(text("""
            select
              (select count(*) from documents where user_id = :u),
              (select count(*) from documents where user_id = :u and status = 'ready'),
              (select count(*) from document_chunks c join documents d on d.id = c.document_id where d.user_id = :u),
              (select count(*) from document_chunks c join documents d on d.id = c.document_id
                 where d.user_id = :u and c.embedding is not null),
              (select count(*) from conversations where user_id = :u),
              (select count(*) from messages m join conversations c on c.id = m.conversation_id where c.user_id = :u),
              (select count(*) from documents where user_id = :u and summary is not null),
              (select count(*) from documents where user_id = :u and jsonb_array_length(questions) > 0)
        """), {"u": user_id}).one()
    files = get_supabase().storage.from_(get_settings().storage_bucket).list(user_id)
    keys = ["documents", "ready", "chunks", "embedded", "conversations", "messages", "with_summary", "with_questions"]
    print(json.dumps({**dict(zip(keys, row)), "stored_files": len(files)}))


def delete(user_id: str) -> None:
    with get_engine().begin() as db:
        db.execute(text("delete from documents where user_id = :u"), {"u": user_id})
    bucket = get_supabase().storage.from_(get_settings().storage_bucket)
    names = [f["name"] for f in bucket.list(user_id)]
    if names:
        bucket.remove([f"{user_id}/{name}" for name in names])
    delete_user(user_id)
    print(json.dumps({"deleted": user_id}))


if __name__ == "__main__":
    command, *args = sys.argv[1:]
    {"signup": signup, "pdf": pdf, "check": check, "delete": delete}[command](*args)
