"""End-to-end check of Supabase Storage for the documents bucket.

Uploads a tiny generated PDF under a random user folder, verifies it, and
always deletes it afterwards. Verifies:
  * bucket is private with a 20 MB limit and PDF-only MIME type
  * upload, no-overwrite, signed-URL download round trip
  * Storage rejects non-PDF content and anonymous public access
  * Storage RLS: a user can read only objects in their own folder
  * delete is idempotent

Usage (from backend/, venv active):
    python -m scripts.verify_storage
"""

import json
import sys
import uuid

import httpx
import pymupdf
from sqlalchemy import text
from storage3.exceptions import StorageApiError

from app.config import get_settings
from app.database import get_engine
from app.services.storage import (
    StorageError,
    build_storage_path,
    create_signed_url,
    delete_file,
    upload_pdf,
)
from app.supabase_client import get_supabase


class Checker:
    def __init__(self) -> None:
        self.failures = 0

    def check(self, label: str, condition: bool, detail: object = "") -> None:
        print(f"  [{'PASS' if condition else 'FAIL'}] {label}" + (f"  ->  {detail}" if detail != "" else ""))
        if not condition:
            self.failures += 1


def make_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "AI Knowledge Base storage check")
    data = doc.tobytes()
    doc.close()
    return data


def count_visible_objects(owner: uuid.UUID, viewer: uuid.UUID, bucket: str) -> int:
    """Count objects in owner's folder as seen by `viewer` under RLS (rolled back)."""
    conn = get_engine().connect()
    trans = conn.begin()
    try:
        conn.execute(text("set local role authenticated"))
        conn.execute(
            text("select set_config('request.jwt.claims', :c, true)"),
            {"c": json.dumps({"sub": str(viewer), "role": "authenticated"})},
        )
        return conn.execute(
            text("select count(*) from storage.objects where bucket_id = :b and name like :prefix"),
            {"b": bucket, "prefix": f"{owner}/%"},
        ).scalar_one()
    finally:
        trans.rollback()
        conn.close()


def main() -> int:
    c = Checker()
    settings = get_settings()
    bucket_name = settings.storage_bucket
    user_id, other_user, document_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    path = build_storage_path(user_id, document_id)
    pdf = make_pdf()

    print("\nBucket configuration:")
    bucket = get_supabase().storage.get_bucket(bucket_name)
    c.check("bucket exists and is private", bucket.public is False)
    c.check("file size limit is 20 MB", bucket.file_size_limit == settings.max_upload_size_bytes, bucket.file_size_limit)
    c.check("only application/pdf allowed", bucket.allowed_mime_types == ["application/pdf"], bucket.allowed_mime_types)

    try:
        print("\nUpload / download:")
        stored = upload_pdf(user_id, document_id, pdf)
        c.check("upload returns {user_id}/{document_id}.pdf", stored == path, stored)

        try:
            upload_pdf(user_id, document_id, pdf)
            c.check("second upload to same path is rejected (no overwrite)", False)
        except StorageError:
            c.check("second upload to same path is rejected (no overwrite)", True)

        url = create_signed_url(path, expires_in=60)
        downloaded = httpx.get(url, timeout=30)
        c.check("signed URL downloads identical bytes", downloaded.status_code == 200 and downloaded.content == pdf, downloaded.status_code)

        public_url = f"{settings.supabase_url}/storage/v1/object/public/{bucket_name}/{path}"
        c.check("public URL is not accessible", httpx.get(public_url, timeout=30).status_code >= 400)

        try:
            get_supabase().storage.from_(bucket_name).upload(
                f"{user_id}/not-a-pdf.txt", b"hello", file_options={"content-type": "text/plain"}
            )
            c.check("non-PDF MIME type rejected by bucket", False)
            delete_file(f"{user_id}/not-a-pdf.txt")
        except StorageApiError as exc:
            c.check("non-PDF MIME type rejected by bucket", True, f"status {exc.status}")

        print("\nStorage RLS (authenticated role):")
        c.check("owner sees their object", count_visible_objects(user_id, user_id, bucket_name) == 1)
        c.check("other user cannot see it", count_visible_objects(user_id, other_user, bucket_name) == 0)
    finally:
        print("\nCleanup:")
        delete_file(path)
        remaining = get_supabase().storage.from_(bucket_name).list(str(user_id))
        c.check("object deleted", remaining == [], remaining)
        try:
            delete_file(path)
            c.check("deleting again is a no-op", True)
        except StorageError:
            c.check("deleting again is a no-op", False)

    print(f"\n{'All checks passed.' if c.failures == 0 else f'{c.failures} check(s) FAILED.'}")
    return 1 if c.failures else 0


if __name__ == "__main__":
    sys.exit(main())
